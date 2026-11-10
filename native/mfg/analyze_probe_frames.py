# SPDX-License-Identifier: Apache-2.0
"""Compare isolated FG OFF/ON native source and DWM traces without claiming scanout.

Desktop Duplication only observes the compositor. Hash differences alone can
come from original animation, cursor/UI updates or unrelated desktop changes.
This report deliberately never marks distinct interpolated monitor frames as
verified, even if DWM sample rates exceed the source-present rate.
"""

import argparse
import csv
import hashlib
import json
import math
import re
from pathlib import Path
from statistics import median


class TraceError(ValueError):
    pass


def rows(path: Path, required: set[str]) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if (not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames))
                or not required.issubset(reader.fieldnames)):
            raise TraceError(f"Incomplete CSV schema in {path}; require {sorted(required)}")
        data = list(reader)
    return data


def ticks_and_rate(times: list[int], hz: int) -> dict[str, float | int | None]:
    valid = sorted(set(times))
    intervals = [(next_time - current) * 1000.0 / hz
                 for current, next_time in zip(valid, valid[1:])]
    if not intervals:
        return {"unique_events": len(valid), "observed_hz": None,
                "median_interval_ms": None, "p95_interval_ms": None}
    intervals.sort()
    return {
        "unique_events": len(valid),
        "observed_hz": round((len(valid) - 1) * hz / (valid[-1] - valid[0]), 3),
        "median_interval_ms": round(intervals[len(intervals) // 2], 3),
        "p95_interval_ms": round(intervals[math.ceil(len(intervals) * .95) - 1], 3),
    }


def distribution(samples: list[int | float]) -> dict[str, float | int | None]:
    if not samples:
        return {"samples": 0, "median": None, "p95": None, "max": None}
    ordered = sorted(samples)
    return {"samples": len(ordered), "median": round(median(ordered), 3),
            "p95": round(ordered[math.ceil(len(ordered) * .95) - 1], 3),
            "max": round(ordered[-1], 3)}


def read_source(path: Path) -> tuple[dict, int, list[tuple[int, float, int | None, int | None]]]:
    data = rows(path, {"sourceFrame", "beforePresentQpc", "afterPresentQpc",
                       "foreground", "qpcHz"})
    if not data:
        raise TraceError(f"No source frames in {path}")
    try:
        clocks = {int(row["qpcHz"]) for row in data}
        if len(clocks) != 1 or next(iter(clocks)) <= 0:
            raise TraceError(f"Unstable/invalid clock in {path}")
        hz = next(iter(clocks))
        frame_ids = [int(row["sourceFrame"]) for row in data]
        if any(b <= a for a, b in zip(frame_ids, frame_ids[1:])):
            raise TraceError(f"Source frames are not strictly increasing in {path}")
        before = [int(row["beforePresentQpc"]) for row in data]
        after = [int(row["afterPresentQpc"]) for row in data]
        if any(end < start for start, end in zip(before, after)):
            raise TraceError(f"Source Present returned before its call began in {path}")
        if any(later <= earlier for earlier, later in zip(after, after[1:])):
            raise TraceError(f"Source Present timestamps are not strictly increasing in {path}")
        focus = [int(row["foreground"]) for row in data]
        if any(flag not in (0, 1) for flag in focus):
            raise TraceError(f"Invalid foreground flag in {path}")
        # The memory fields were added after the initial source trace format;
        # older recordings remain readable but cannot produce VRAM estimates.
        memory_fields = ("gpuLocalUsageBytes", "gpuLocalBudgetBytes")
        if any(field in data[0] for field in memory_fields) and not all(
                field in data[0] for field in memory_fields):
            raise TraceError(f"Incomplete GPU memory fields in {path}")
        have_memory = all(field in data[0] for field in memory_fields)
        usage = [int(row["gpuLocalUsageBytes"]) if row["gpuLocalUsageBytes"] else None
                 for row in data] if have_memory else [None] * len(data)
        budget = [int(row["gpuLocalBudgetBytes"]) if row["gpuLocalBudgetBytes"] else None
                  for row in data] if have_memory else [None] * len(data)
        if any(value < 0 for value in usage + budget if value is not None):
            raise TraceError(f"Negative GPU memory counter in {path}")
    except (ValueError, TypeError) as exc:
        raise TraceError(f"Malformed source CSV in {path}: {exc}") from exc
    # Restrict rate measurements to the longest uninterrupted foreground run.
    # Disjoint focus intervals would otherwise inflate their elapsed time.
    runs: list[list[tuple[int, float, int | None, int | None]]] = []
    current: list[tuple[int, float, int | None, int | None]] = []
    for start, stamp, flag, used, allotted in zip(before, after, focus, usage, budget):
        if flag:
            current.append((stamp, (stamp - start) * 1000.0 / hz, used, allotted))
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    focused = max(runs, key=len, default=[])
    focused_after = [entry[0] for entry in focused]
    if any(later <= earlier for earlier, later in zip(focused_after, focused_after[1:])):
        raise TraceError(f"Source timestamps are not strictly increasing in {path}")
    metric = ticks_and_rate(focused_after, hz)
    return {"frames_total": len(data), "foreground_frames": sum(focus),
            "foreground_fraction": round(sum(focus) / len(data), 4),
            "longest_continuous_foreground_frames": len(focused),
            "focused_source_presents": metric}, hz, focused


def read_desktop(path: Path) -> tuple[dict, int, list[tuple[int, int, int]]]:
    data = rows(path, {"sample", "captureQpc", "desktopPresentQpc",
                       "accumulatedFrames", "hashChanged", "roiHash", "qpcHz"})
    if not data:
        raise TraceError(f"No DWM samples in {path}")
    try:
        clocks = {int(row["qpcHz"]) for row in data}
        if len(clocks) != 1 or next(iter(clocks)) <= 0:
            raise TraceError(f"Unstable/invalid clock in {path}")
        hz = next(iter(clocks))
        samples = [int(row["sample"]) for row in data]
        if samples != list(range(1, len(data) + 1)):
            raise TraceError(f"Desktop sample IDs are not contiguous in {path}")
        captures = [int(row["captureQpc"]) for row in data]
        if any(stamp <= 0 for stamp in captures) or any(
                later <= earlier for earlier, later in zip(captures, captures[1:])):
            raise TraceError(f"Desktop capture timestamps are not strictly increasing in {path}")
        timestamps = [int(row["desktopPresentQpc"]) for row in data]
        if any(stamp < 0 or stamp > captured for stamp, captured in zip(timestamps, captures)):
            raise TraceError(f"Desktop presentation timestamps are outside their capture window in {path}")
        # DXGI_OUTDUPL_FRAME_INFO.LastPresentTime is zero for a pointer-only
        # desktop update. Ignore these rows when checking DWM present order.
        actual_presents = [stamp for stamp in timestamps if stamp > 0]
        if any(b < a for a, b in zip(actual_presents, actual_presents[1:])):
            raise TraceError(f"Desktop presentation timestamps move backwards in {path}")
        accumulated = [int(row["accumulatedFrames"]) for row in data]
        changes = [int(row["hashChanged"]) for row in data]
        hashes = [int(row["roiHash"]) for row in data]
        if any(value < 0 or value >= 1 << 64 for value in hashes):
            raise TraceError(f"Invalid ROI hash in {path}")
        if changes[0] != 1 or any(changed != int(prev != current) for changed, prev, current in
                                      zip(changes[1:], hashes, hashes[1:])):
            raise TraceError(f"ROI hash change flags disagree with ROI hashes in {path}")
        if any(value not in (0, 1) for value in changes) or any(value < 0 for value in accumulated):
            raise TraceError(f"Invalid DWM counters in {path}")
    except (ValueError, TypeError) as exc:
        raise TraceError(f"Malformed desktop CSV in {path}: {exc}") from exc
    valid = [(stamp, changed, count) for stamp, changed, count
             in zip(timestamps, changes, accumulated) if stamp > 0]
    metric = ticks_and_rate([stamp for stamp, _, _ in valid], hz)
    return {"sample_count": len(data), "distinct_roi_hash_events": sum(changes),
            "roi_hash_change_fraction": round(sum(changes) / len(data), 4),
            "dwm_accumulated_frame_gaps": sum(value > 1 for value in accumulated),
            "compositor_presents": metric}, hz, valid


def read_pair(source: Path, desktop: Path) -> dict:
    source_metrics, source_hz, focused = read_source(source)
    desktop_metrics, desktop_hz, dwm = read_desktop(desktop)
    if source_hz != desktop_hz:
        raise TraceError(f"Source and observer QPC clock frequencies differ: {source_hz}, {desktop_hz}")
    if len(focused) < 2 or len(dwm) < 2:
        raise TraceError("Insufficient foreground source events or DWM presentations for overlap")
    first = max(focused[0][0], dwm[0][0])
    last = min(focused[-1][0], dwm[-1][0])
    if last <= first:
        raise TraceError("Source and desktop traces contain no overlapping foreground time window")
    matched_source = [entry for entry in focused if first <= entry[0] <= last]
    matched_desktop = [(stamp, changed, count) for stamp, changed, count in dwm
                       if first <= stamp <= last]
    source_metrics["focused_source_presents"] = ticks_and_rate(
        [entry[0] for entry in matched_source], source_hz)
    source_metrics["api_present_call_duration_ms"] = distribution(
        [entry[1] for entry in matched_source])
    source_metrics["dxgi_process_local_memory_bytes"] = distribution(
        [entry[2] for entry in matched_source if entry[2] is not None])
    source_metrics["dxgi_process_local_budget_bytes"] = distribution(
        [entry[3] for entry in matched_source if entry[3] is not None])
    desktop_metrics["compositor_presents"] = ticks_and_rate(
        [stamp for stamp, _, _ in matched_desktop], desktop_hz)
    desktop_metrics["overlap_hash_changes"] = sum(changed for _, changed, _ in matched_desktop)
    desktop_metrics["overlap_accumulated_frame_gaps"] = sum(
        count > 1 for _, _, count in matched_desktop)
    return {"clock_hz": source_hz,
            "overlap": {"start_qpc": first, "end_qpc": last,
                        "duration_ms": round((last - first) * 1000 / source_hz, 3)},
            "source": source_metrics, "desktop": desktop_metrics}


def read_status(path: Path) -> dict:
    """Validate the probe process's own successive, PID-matched status snapshots.

    Provider counters establish activity within the native process, never that
    a generated image reached DWM or physical scanout.
    """
    with path.open("r", encoding="utf-8-sig") as stream:
        try:
            data = [json.loads(line) for line in stream if line.strip()]
        except json.JSONDecodeError as exc:
            raise TraceError(f"Malformed process status NDJSON in {path}: {exc}") from exc
    if not data:
        raise TraceError(f"No PID-matched provider status samples in {path}")
    counters = ("fgCreates", "fgEvaluations", "fgSuccessEvaluations", "fgBatches",
                "fgFailedBatches")
    try:
        if any(not isinstance(row, dict) for row in data):
            raise TraceError(f"Invalid status row in {path}")
        pids = {row["pid"] for row in data}
        births = {row["processBirth"] for row in data}
        if (len(pids) != 1 or len(births) != 1 or
                type(data[0]["pid"]) is not int or data[0]["pid"] <= 0 or
                type(data[0]["processBirth"]) is not int or data[0]["processBirth"] <= 0):
            raise TraceError(f"Provider status mixes process identities in {path}")
        elapsed = [row["elapsedMs"] for row in data]
        if (any(type(value) is not int or value < 0 for value in elapsed) or
                any(b <= a for a, b in zip(elapsed, elapsed[1:]))):
            raise TraceError(f"Provider status sample times are invalid in {path}")
        clocks = {row["qpcHz"] for row in data}
        qpc = [row["sampleQpc"] for row in data]
        if (len(clocks) != 1 or type(data[0]["qpcHz"]) is not int or
                data[0]["qpcHz"] <= 0 or
                any(type(value) is not int or value <= 0 for value in qpc) or
                any(b <= a for a, b in zip(qpc, qpc[1:]))):
            raise TraceError(f"Provider QPC timestamps or clock are invalid in {path}")
        if any(type(row["fgEnabled"]) is not bool or type(row["fgApplied"]) is not bool
               for row in data):
            raise TraceError(f"Provider status enabled/applied fields are invalid in {path}")
        for field in counters:
            counts = [row[field] for row in data]
            if (any(type(count) is not int or count < 0 for count in counts) or
                    any(b < a for a, b in zip(counts, counts[1:]))):
                raise TraceError(f"Provider counter {field} is invalid or regresses in {path}")
    except (KeyError, TypeError, ValueError) as exc:
        raise TraceError(f"Malformed provider status in {path}: {exc}") from exc
    return {
        "samples": len(data), "pid": data[0]["pid"],
        "process_birth": data[0]["processBirth"],
        "last_route": data[-1].get("route"),
        "last_route_failure_reason": data[-1].get("routeFailureReason"),
        "fg_enabled_observed": any(row["fgEnabled"] for row in data),
        "fg_applied_observed": any(row["fgApplied"] for row in data),
        "last_counters": {field: data[-1][field] for field in counters},
        "clock_hz": data[0]["qpcHz"],
        "timeline": [{"qpc": row["sampleQpc"],
                      "enabled": row["fgEnabled"], "applied": row["fgApplied"],
                      "counters": {field: row[field] for field in counters}}
                     for row in data],
    }


def read_termination(path: Path) -> dict:
    """Read the native runner's distinct render/teardown outcome."""
    try:
        record = json.loads(path.read_text(encoding="utf-8-sig"))
    except (ValueError, UnicodeError) as exc:
        raise TraceError(f"Malformed termination report in {path}: {exc}") from exc
    if not isinstance(record, dict) or record.get("schema") != "remix-native-probe-termination-v1":
        raise TraceError(f"Invalid termination schema in {path}")
    return record


def verify_bound_traces(record: dict, paths: dict[str, Path], mode: str) -> None:
    """Reject swapped, missing or modified traces against the runner record."""
    recorded = record.get("trace_sha256")
    if not isinstance(recorded, dict):
        raise TraceError(f"FG {mode} termination is missing bound trace hashes")
    for kind, path in paths.items():
        expected = recorded.get(kind)
        if (not isinstance(expected, str) or len(expected) != 64 or
                any(character not in "0123456789abcdef" for character in expected)):
            raise TraceError(f"FG {mode} missing/invalid {kind} trace SHA-256")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise TraceError(f"FG {mode} {kind} trace SHA-256 mismatch: {path}")
    if "observer_log" in paths:
        observer_text = paths["observer_log"].read_text(encoding="utf-8-sig")
        owner = re.findall(r"^Observer PID=(\d+)\b", observer_text, re.MULTILINE)
        if len(owner) != 1 or int(owner[0]) != record.get("process_pid"):
            raise TraceError(f"FG {mode} observer process target PID disagrees with termination")


def validate_termination(record: dict, trace: dict, status: dict, mode: str) -> None:
    """Accept only a complete render with verified observer and process identity.

    A renderer teardown timeout remains a failure even when we can evaluate
    independent source/DWM/provider evidence collected before shutdown.
    """
    if any(type(record.get(key)) is not int or record[key] <= 0 for key in
           ("requested_frames", "rendered_frames", "process_pid", "process_birth")):
        raise TraceError(f"FG {mode} has missing/invalid termination frame or process identity")
    if type(record.get("foreground_frames")) is not int or record["foreground_frames"] < 0:
        raise TraceError(f"FG {mode} has invalid foreground count")
    if (record["requested_frames"] != record["rendered_frames"] or
            record["rendered_frames"] != trace["source"]["frames_total"] or
            record["foreground_frames"] != trace["source"]["foreground_frames"]):
        raise TraceError(f"FG {mode} termination and source frame counts disagree")
    if (record["process_pid"] != status["pid"] or
            record["process_birth"] != status["process_birth"]):
        raise TraceError(f"FG {mode} termination and provider process identity disagree")
    if (record.get("observer_required") is not True or
            record.get("observer_passed") is not True or
            record.get("observer_timed_out") is not False or
            type(record.get("observer_exit_code")) is not int or
            record["observer_exit_code"] != 0):
        raise TraceError(f"FG {mode} independent DWM observer did not finish successfully")
    if (record.get("frame_loop_complete") is not True or
            record.get("eligible_for_diagnostic_analysis") is not True or
            record.get("host_retired") is not True or
            record.get("shutdown_started") is not True or
            record.get("remix_render_failures") != 0 or
            record.get("actual_interpolated_display_frames_verified") is not False):
        raise TraceError(f"FG {mode} native render or termination evidence is incomplete")
    if record.get("result") == "clean_shutdown":
        valid = (record.get("process_timed_out") is False and
                 record.get("shutdown_completed") is True and
                 record.get("rendering_and_shutdown_both_passed") is True and
                 type(record.get("exit_code")) is int and record["exit_code"] == 0)
    elif record.get("result") == "shutdown_timeout_after_complete_render":
        valid = (record.get("process_timed_out") is True and
                 record.get("shutdown_completed") is False and
                 record.get("rendering_and_shutdown_both_passed") is False and
                 type(record.get("exit_code")) is int and record["exit_code"] != 0)
    else:
        valid = False
    if not valid:
        raise TraceError(f"FG {mode} has contradictory native process termination state")


def ratio(on: float | None, off: float | None) -> float | None:
    return round(on / off, 4) if on is not None and off is not None and off > 0 else None


def provider_window(status: dict, trace: dict) -> dict:
    """Constrain provider diagnostics to a measured source/DWM overlap.

    Counters sampled during startup or shutdown cannot certify work during
    foreground rendering. Even valid positive deltas remain provider evidence,
    not proof that any generated image was actually displayed.
    """
    if status["clock_hz"] != trace["clock_hz"]:
        raise TraceError("Provider status and source/DWM QPC clock frequencies differ")
    window = trace["overlap"]
    samples = [row for row in status["timeline"]
               if window["start_qpc"] <= row["qpc"] <= window["end_qpc"]]
    first = samples[0]["counters"] if samples else {}
    last = samples[-1]["counters"] if samples else {}
    # Only compare counters from consecutive snapshots where both the route
    # request and actual application were observed active. A full-overlap
    # delta can include work done after FG was disabled, or bridge two
    # unrelated active periods. A single active snapshot proves no delta.
    intervals = []
    active_run = []

    def finish_run() -> None:
        if len(active_run) < 2:
            return
        start, end = active_run[0], active_run[-1]
        changes = {key: end["counters"][key] - start["counters"][key]
                   for key in start["counters"]}
        qualified = all(changes[key] > 0 for key in
                        ("fgEvaluations", "fgSuccessEvaluations", "fgBatches"))
        intervals.append({
            "start_qpc": start["qpc"], "end_qpc": end["qpc"],
            "samples": len(active_run),
            "duration_ms": round((end["qpc"] - start["qpc"]) * 1000 /
                                 status["clock_hz"], 3),
            "counter_delta": changes,
            "qualified": qualified,
        })

    for row in samples:
        if row["enabled"] and row["applied"]:
            active_run.append(row)
        else:
            finish_run()
            active_run = []
    finish_run()
    return {
        "samples": len(samples),
        "duration_ms": (round((samples[-1]["qpc"] - samples[0]["qpc"]) * 1000 /
                              status["clock_hz"], 3) if len(samples) >= 2 else None),
        "enabled": any(row["enabled"] for row in samples),
        "applied": any(row["applied"] for row in samples),
        "counter_delta": {key: last[key] - first[key] for key in first},
        "enabled_activity": {
            "both_flags_observed": any(row["enabled"] and row["applied"]
                                       for row in samples),
            "qualified": any(interval["qualified"] for interval in intervals),
            "intervals": intervals,
        },
    }


def compare(off: dict, on: dict, off_status: dict | None = None,
            on_status: dict | None = None) -> dict:
    enough = all(item["source"]["focused_source_presents"]["unique_events"] >= 40 and
                 item["desktop"]["compositor_presents"]["unique_events"] >= 40 and
                 item["overlap"]["duration_ms"] >= 500
                 for item in (off, on))
    controlled_provider = False
    windows = None
    if off_status is not None and on_status is not None:
        off_window = provider_window(off_status, off)
        on_window = provider_window(on_status, on)
        windows = {"off": off_window, "on": on_window}
        off_counter = off_status["last_counters"]
        on_counter = on_status["last_counters"]
        controlled_provider = (
            off_window["samples"] >= 2 and
            on_window["samples"] >= 2 and
            not off_status["fg_enabled_observed"] and
            not off_status["fg_applied_observed"] and
            all(off_counter[key] == 0 for key in
                ("fgEvaluations", "fgSuccessEvaluations", "fgBatches", "fgFailedBatches")) and
            on_window["enabled_activity"]["qualified"] and
            on_counter["fgCreates"] > 0 and
            on_counter["fgEvaluations"] > 0 and
            on_counter["fgFailedBatches"] == 0)
    return {
        "gate_h": "BLOCKED - independent physical scanout and true interpolation unverified",
        "sufficient_compositor_samples_for_diagnostic": enough,
        "controlled_provider_activity_for_diagnostic": controlled_provider,
        "provider_status": {"off": off_status, "on": on_status},
        "provider_measured_windows": windows,
        "fg_off": off,
        "fg_on": on,
        "observed_rate_ratios_on_over_off": {
            "source_presents": ratio(on["source"]["focused_source_presents"]["observed_hz"],
                                     off["source"]["focused_source_presents"]["observed_hz"]),
            "dwm_compositor": ratio(on["desktop"]["compositor_presents"]["observed_hz"],
                                    off["desktop"]["compositor_presents"]["observed_hz"]),
            "dxgi_process_local_memory_peak": ratio(
                on["source"]["dxgi_process_local_memory_bytes"]["max"],
                off["source"]["dxgi_process_local_memory_bytes"]["max"]),
        },
        "limitations": [
            "DWM Desktop Duplication is not physical monitor scanout or photon measurement.",
            "Desktop ROI hashes do not distinguish interpolated frames from original animation/UI.",
            "Captured DWM samples can drop compositor frames and cannot establish GPU VRAM or input latency.",
            "DXGI local memory is a WDDM per-process estimate on the window's display adapter, not total VRAM or device-wide usage.",
            "API Present call duration is not motion-to-photon latency.",
            "Verify FG provider counters, distinct generated Vulkan images, display scanout, end-to-end latency and GPU memory separately.",
            "Provider evaluations/batches indicate internal activity; they do not establish correct interpolation or scanout.",
            "Provider activity requires evaluation, success and batch counter increases within one consecutive run of sampled FG-enabled-and-applied states during the source/DWM QPC foreground overlap; status polling does not prove continuous state between samples.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for mode in ("off", "on"):
        parser.add_argument(f"--{mode}-source", required=True, type=Path)
        parser.add_argument(f"--{mode}-desktop", required=True, type=Path)
        parser.add_argument(f"--{mode}-status", type=Path)
        parser.add_argument(f"--{mode}-termination", type=Path)
        parser.add_argument(f"--{mode}-observer-log", type=Path)
    parser.add_argument("--output", type=Path,
                        help="Optional report path; parent directory must already exist")
    args = parser.parse_args()
    if (args.off_status is None) != (args.on_status is None):
        parser.error("Provider status must include both --off-status and --on-status")
    if (args.off_termination is None) != (args.on_termination is None):
        parser.error("Termination reports must include both --off-termination and --on-termination")
    termination = {}
    try:
        if args.off_termination:
            termination = {mode: read_termination(getattr(args, f"{mode}_termination"))
                           for mode in ("off", "on")}
        off_trace = read_pair(args.off_source, args.off_desktop)
        on_trace = read_pair(args.on_source, args.on_desktop)
        off_status = read_status(args.off_status) if args.off_status else None
        on_status = read_status(args.on_status) if args.on_status else None
        if termination:
            if off_status is None or on_status is None:
                raise TraceError("Termination validation requires both process-matched provider status traces")
            for mode in ("off", "on"):
                observer_log = getattr(args, f"{mode}_observer_log")
                if observer_log is None:
                    raise TraceError(f"FG {mode} requires the independently bound observer log")
                verify_bound_traces(termination[mode], {
                    "source": getattr(args, f"{mode}_source"),
                    "desktop": getattr(args, f"{mode}_desktop"),
                    "status": getattr(args, f"{mode}_status"),
                    "observer_log": observer_log,
                }, mode)
            validate_termination(termination["off"], off_trace, off_status, "off")
            validate_termination(termination["on"], on_trace, on_status, "on")
        report = compare(off_trace, on_trace, off_status, on_status)
        report["termination"] = termination
        report["termination_eligible_for_diagnostic"] = bool(termination)
        code = 0 if (report["sufficient_compositor_samples_for_diagnostic"] and
                     (not args.off_status or report["controlled_provider_activity_for_diagnostic"])) else 2
    except (TraceError, OSError, UnicodeError) as exc:
        report = {"gate_h": "BLOCKED", "error": str(exc), "termination": termination,
                  "termination_eligible_for_diagnostic": False}
        code = 2
    serialized = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
