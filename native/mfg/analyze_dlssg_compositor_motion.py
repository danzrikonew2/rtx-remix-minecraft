# SPDX-License-Identifier: Apache-2.0
"""Verify deterministic NVIDIA DLSS-G interpolation in DWM-composited pixels.

This analyzer compares matched FG OFF/ON runs of the isolated moving-target
probe.  It proves compositor-level interpolation only when the ON run contains
the same real-frame endpoint motion as OFF plus one stable intermediate state
near the spatial midpoint between adjacent endpoints.  Desktop Duplication is
still not physical monitor scanout or a motion-to-photon measurement.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from pathlib import Path
from statistics import mean, median

from analyze_probe_frames import (TraceError, compare as compare_provider,
                                  read_pair, read_status, read_termination,
                                  verify_bound_traces)


SOURCE_FIELDS = {"sourceFrame", "afterPresentQpc", "foreground", "qpcHz",
                 "expectedCropCentroidX"}
DESKTOP_FIELDS = {"sample", "desktopPresentQpc", "hashChanged", "roiHash",
                  "qpcHz", "orangePixels", "orangeCentroidX"}


def rows(path: Path, required: set[str]) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if (not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames))
                or not required.issubset(reader.fieldnames)):
            raise TraceError(f"Incomplete motion CSV schema in {path}; require {sorted(required)}")
        return list(reader)


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * fraction) - 1))
    return ordered[index]


def rounded(value: float | None, digits: int = 6) -> float | None:
    return round(value, digits) if value is not None else None


def distribution(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"samples": 0, "median": None, "p05": None, "p95": None,
                "mean": None, "max": None}
    return {
        "samples": len(values),
        "median": rounded(median(values)),
        "p05": rounded(percentile(values, .05)),
        "p95": rounded(percentile(values, .95)),
        "mean": rounded(mean(values)),
        "max": rounded(max(values)),
    }


def read_motion_run(source_path: Path, desktop_path: Path,
                    start_frame: int = 30) -> dict:
    source_rows = rows(source_path, SOURCE_FIELDS)
    desktop_rows = rows(desktop_path, DESKTOP_FIELDS)
    if not source_rows or not desktop_rows:
        raise TraceError("Motion analysis requires non-empty source and desktop traces")

    try:
        source_clocks = {int(row["qpcHz"]) for row in source_rows}
        desktop_clocks = {int(row["qpcHz"]) for row in desktop_rows}
        if (len(source_clocks) != 1 or len(desktop_clocks) != 1 or
                source_clocks != desktop_clocks or next(iter(source_clocks)) <= 0):
            raise TraceError("Motion traces have mismatched or invalid QPC clocks")
        qpc_hz = next(iter(source_clocks))

        source = []
        for row in source_rows:
            frame = int(row["sourceFrame"])
            stamp = int(row["afterPresentQpc"])
            foreground = int(row["foreground"])
            expected = float(row["expectedCropCentroidX"])
            if stamp <= 0 or foreground not in (0, 1) or not math.isfinite(expected):
                raise TraceError(f"Invalid source motion row in {source_path}")
            source.append({"frame": frame, "qpc": stamp,
                           "foreground": foreground, "expected_x": expected})
        if any(b["frame"] <= a["frame"] or b["qpc"] <= a["qpc"]
               for a, b in zip(source, source[1:])):
            raise TraceError(f"Source motion ordering is invalid in {source_path}")

        selected = [row for row in source if row["frame"] >= start_frame]
        if len(selected) < 40:
            raise TraceError(f"Fewer than 40 source frames remain after start frame {start_frame}")
        if selected[0]["frame"] != start_frame:
            raise TraceError(f"Requested start frame {start_frame} is absent from {source_path}")
        if not all(row["foreground"] == 1 for row in selected):
            raise TraceError("Motion proof window contains source frames that were not foreground")

        start_qpc, end_qpc = selected[0]["qpc"], selected[-1]["qpc"]
        states = []
        previous_qpc = 0
        for row in desktop_rows:
            stamp = int(row["desktopPresentQpc"])
            changed = int(row["hashChanged"])
            orange_pixels = int(row["orangePixels"])
            centroid = float(row["orangeCentroidX"])
            if stamp < 0 or changed not in (0, 1) or orange_pixels < 0:
                raise TraceError(f"Invalid desktop motion row in {desktop_path}")
            if stamp > 0 and stamp < previous_qpc:
                raise TraceError(f"Desktop presentation timestamps move backwards in {desktop_path}")
            if stamp > 0:
                previous_qpc = stamp
            if (start_qpc <= stamp <= end_qpc and changed and orange_pixels > 0 and
                    math.isfinite(centroid) and centroid >= 0):
                states.append({"qpc": stamp, "centroid_x": centroid,
                               "roi_hash": int(row["roiHash"]),
                               "sample": int(row["sample"])})
    except (TypeError, ValueError) as exc:
        raise TraceError(f"Malformed motion CSV: {exc}") from exc

    if len(states) < 40:
        raise TraceError("Fewer than 40 changed orange DWM states remain in the proof window")
    if any(b["qpc"] <= a["qpc"] for a, b in zip(states, states[1:])):
        raise TraceError("Changed DWM motion states are not strictly time ordered")

    duration_qpc = states[-1]["qpc"] - states[0]["qpc"]
    state_hz = ((len(states) - 1) * qpc_hz / duration_qpc) if duration_qpc > 0 else None
    return {
        "start_frame": start_frame,
        "source": selected,
        "states": states,
        "qpc_hz": qpc_hz,
        "changed_orange_states": len(states),
        "changed_orange_state_hz": rounded(state_hz, 3),
    }


def _best_endpoint_alignment(off_x: list[float], on_x: list[float]) -> dict:
    """Find the 2x phase that maps ON real-frame endpoints back to OFF."""
    minimum_matches = max(40, len(off_x) - 4)
    best = None
    for offset in range(-5, 6):
        errors = []
        matches = []
        for index, endpoint in enumerate(off_x):
            on_index = offset + 2 * index
            if 0 <= on_index < len(on_x):
                error = abs(on_x[on_index] - endpoint)
                errors.append(error)
                matches.append((index, on_index, error))
        if len(matches) < minimum_matches:
            continue
        score = (median(errors), mean(errors), -len(matches), abs(offset))
        if best is None or score < best[0]:
            best = (score, offset, matches)
    if best is None:
        raise TraceError("Unable to align enough ON states to the OFF real-frame endpoints")
    _, offset, matches = best
    return {"offset": offset, "matches": matches}


def compare_motion(off: dict, on: dict, *, min_motion_px: float = .15,
                   endpoint_tolerance_px: float = .01,
                   midpoint_fraction_tolerance: float = .15) -> dict:
    off_source = off["source"]
    on_source = on["source"]
    if [row["frame"] for row in off_source] != [row["frame"] for row in on_source]:
        raise TraceError("FG OFF/ON source frame identities differ in the proof window")
    source_deltas = [abs(a["expected_x"] - b["expected_x"])
                     for a, b in zip(off_source, on_source)]
    if max(source_deltas, default=0) > .001:
        raise TraceError("FG OFF/ON deterministic source motion differs in the proof window")

    off_x = [row["centroid_x"] for row in off["states"]]
    on_x = [row["centroid_x"] for row in on["states"]]
    state_ratio = len(on_x) / len(off_x)
    alignment = _best_endpoint_alignment(off_x, on_x)
    endpoint_errors = [entry[2] for entry in alignment["matches"]]
    endpoint_within = sum(error <= endpoint_tolerance_px for error in endpoint_errors)

    midpoint_fractions = []
    midpoint_abs_fraction_errors = []
    midpoint_abs_pixel_errors = []
    midpoint_endpoint_distances = []
    one_intermediate_intervals = 0
    candidate_intervals = 0
    offset = alignment["offset"]
    for index in range(len(off_x) - 1):
        left_index = offset + 2 * index
        right_index = offset + 2 * (index + 1)
        if not (0 <= left_index < len(on_x) and 0 <= right_index < len(on_x)):
            continue
        candidate_intervals += 1
        if right_index - left_index != 2:
            continue
        one_intermediate_intervals += 1
        left, right = off_x[index], off_x[index + 1]
        delta = right - left
        if abs(delta) < min_motion_px:
            continue
        intermediate = on_x[left_index + 1]
        fraction = (intermediate - left) / delta
        midpoint = (left + right) * .5
        midpoint_fractions.append(fraction)
        midpoint_abs_fraction_errors.append(abs(fraction - .5))
        midpoint_abs_pixel_errors.append(abs(intermediate - midpoint))
        midpoint_endpoint_distances.append(min(abs(intermediate - left),
                                               abs(intermediate - right)))

    endpoint_match_fraction = endpoint_within / len(endpoint_errors) if endpoint_errors else 0.0
    single_intermediate_fraction = (one_intermediate_intervals / candidate_intervals
                                    if candidate_intervals else 0.0)
    midpoint_within = sum(abs(value - .5) <= midpoint_fraction_tolerance
                          for value in midpoint_fractions)
    midpoint_within_fraction = (midpoint_within / len(midpoint_fractions)
                                if midpoint_fractions else 0.0)
    midpoint_abs_p95 = percentile(midpoint_abs_fraction_errors, .95)
    midpoint_pixel_p95 = percentile(midpoint_abs_pixel_errors, .95)

    compositor_pass = (
        1.90 <= state_ratio <= 2.10 and
        len(alignment["matches"]) >= max(40, int(len(off_x) * .95)) and
        endpoint_match_fraction >= .98 and
        single_intermediate_fraction >= .95 and
        len(midpoint_fractions) >= 40 and
        midpoint_within_fraction >= .95 and
        midpoint_abs_p95 is not None and midpoint_abs_p95 <= midpoint_fraction_tolerance and
        midpoint_pixel_p95 is not None and midpoint_pixel_p95 <= .5)

    return {
        "dwm_compositor_midpoint_evidence": "PASS" if compositor_pass else "FAIL",
        "source_motion_match_max_abs_px": rounded(max(source_deltas, default=0)),
        "steady_state": {
            "start_frame": off["start_frame"],
            "off_changed_orange_states": len(off_x),
            "on_changed_orange_states": len(on_x),
            "on_over_off_state_count_ratio": rounded(state_ratio),
            "off_changed_orange_state_hz": off["changed_orange_state_hz"],
            "on_changed_orange_state_hz": on["changed_orange_state_hz"],
            "state_hz_ratio_on_over_off": rounded(
                on["changed_orange_state_hz"] / off["changed_orange_state_hz"], 4)
                if off["changed_orange_state_hz"] else None,
        },
        "endpoint_alignment": {
            "on_index_offset_for_off_index_zero": offset,
            "matched_endpoints": len(endpoint_errors),
            "within_tolerance": endpoint_within,
            "within_tolerance_fraction": rounded(endpoint_match_fraction, 4),
            "tolerance_px": endpoint_tolerance_px,
            "absolute_error_px": distribution(endpoint_errors),
        },
        "intermediate_states": {
            "candidate_endpoint_intervals": candidate_intervals,
            "intervals_with_exactly_one_on_state_between_endpoints": one_intermediate_intervals,
            "single_intermediate_fraction": rounded(single_intermediate_fraction, 4),
            "minimum_endpoint_motion_px": min_motion_px,
            "measurable_midpoint_intervals": len(midpoint_fractions),
            "normalized_position": distribution(midpoint_fractions),
            "absolute_fraction_error_from_half": distribution(midpoint_abs_fraction_errors),
            "absolute_midpoint_error_px": distribution(midpoint_abs_pixel_errors),
            "minimum_distance_to_either_endpoint_px": distribution(midpoint_endpoint_distances),
            "within_half_plus_minus_tolerance": midpoint_within,
            "within_half_plus_minus_tolerance_fraction": rounded(midpoint_within_fraction, 4),
            "normalized_tolerance": midpoint_fraction_tolerance,
        },
    }


def read_nvidia_provider_log(path: Path) -> dict:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    evaluation_results = [int(value) for value in re.findall(
        r"NVSDK_NGX_VULKAN_EvaluateFeature VULKAN_EvaluateFeature result for \(1\): (\d+)", text)]
    create_results = [int(value) for value in re.findall(
        r"NVSDK_NGX_VULKAN_CreateFeature1 VULKAN_CreateFeature1 result for \(11\): (\d+)", text)]
    max_interpolations = [int(value) for value in re.findall(
        r"Max supported interpolations: (\d+)", text)]
    provider_pass = (
        "FrameGen.Enabled: true" in text and
        "FrameGen.FGOutput: dlssg" in text and
        "DLSSG.InterpolationCount: 1" in text and
        "nvngx_dlssg.dll found at" in text and
        any(value == 1 for value in create_results) and
        bool(evaluation_results) and all(value == 1 for value in evaluation_results) and
        "DLSS-G interpolation state changed from disabled to enabled" in text and
        "mode=sl::DLSSGMode::eOn, numFramesToGenerate=1" in text)
    return {
        "nvidia_dlssg_provider_log": "PASS" if provider_pass else "FAIL",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "nvngx_dlssg_found": "nvngx_dlssg.dll found at" in text,
        "create_successes": sum(value == 1 for value in create_results),
        "evaluations": len(evaluation_results),
        "successful_evaluations": sum(value == 1 for value in evaluation_results),
        "failed_evaluations": sum(value != 1 for value in evaluation_results),
        "max_supported_interpolations": max(max_interpolations) if max_interpolations else None,
        "requested_interpolations": 1 if "DLSSG.InterpolationCount: 1" in text else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for mode in ("off", "on"):
        parser.add_argument(f"--{mode}-source", required=True, type=Path)
        parser.add_argument(f"--{mode}-desktop", required=True, type=Path)
        parser.add_argument(f"--{mode}-status", type=Path)
        parser.add_argument(f"--{mode}-termination", type=Path)
        parser.add_argument(f"--{mode}-observer-log", type=Path)
    parser.add_argument("--on-provider-log", type=Path)
    parser.add_argument("--start-frame", type=int, default=30)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report: dict = {
        "physical_monitor_scanout_verified": False,
        "minecraft_gameplay_verified": False,
        "gate_h": "BLOCKED - physical monitor scanout remains unverified",
    }
    try:
        off = read_motion_run(args.off_source, args.off_desktop, args.start_frame)
        on = read_motion_run(args.on_source, args.on_desktop, args.start_frame)
        motion = compare_motion(off, on)
        report.update(motion)

        have_status = args.off_status is not None and args.on_status is not None
        if (args.off_status is None) != (args.on_status is None):
            raise TraceError("Provider status must include both FG OFF and ON traces")
        provider_comparison = None
        if have_status:
            provider_comparison = compare_provider(
                read_pair(args.off_source, args.off_desktop),
                read_pair(args.on_source, args.on_desktop),
                read_status(args.off_status), read_status(args.on_status))
            report["controlled_provider_activity_for_diagnostic"] = provider_comparison[
                "controlled_provider_activity_for_diagnostic"]
            report["provider_measured_windows"] = provider_comparison["provider_measured_windows"]
        else:
            report["controlled_provider_activity_for_diagnostic"] = False

        binding_args = [args.off_termination, args.on_termination,
                        args.off_observer_log, args.on_observer_log]
        if any(value is not None for value in binding_args):
            if not all(value is not None for value in binding_args) or not have_status:
                raise TraceError("Trace binding requires both termination, status, and observer artifacts")
            terminations = {mode: read_termination(getattr(args, f"{mode}_termination"))
                            for mode in ("off", "on")}
            for mode in ("off", "on"):
                verify_bound_traces(terminations[mode], {
                    "source": getattr(args, f"{mode}_source"),
                    "desktop": getattr(args, f"{mode}_desktop"),
                    "status": getattr(args, f"{mode}_status"),
                    "observer_log": getattr(args, f"{mode}_observer_log"),
                }, mode)
            report["trace_binding_verified"] = True
            report["termination_results"] = {
                mode: {
                    "result": terminations[mode].get("result"),
                    "frame_loop_complete": terminations[mode].get("frame_loop_complete"),
                    "shutdown_completed": terminations[mode].get("shutdown_completed"),
                } for mode in ("off", "on")
            }
        else:
            report["trace_binding_verified"] = False

        if args.on_provider_log:
            report["provider_log"] = read_nvidia_provider_log(args.on_provider_log)
        else:
            report["provider_log"] = {"nvidia_dlssg_provider_log": "UNVERIFIED"}

        attributed = (
            report["dwm_compositor_midpoint_evidence"] == "PASS" and
            report["controlled_provider_activity_for_diagnostic"] and
            report["trace_binding_verified"] and
            report["provider_log"]["nvidia_dlssg_provider_log"] == "PASS")
        report["nvidia_dlssg_dwm_compositor_interpolation"] = "PASS" if attributed else "FAIL"
        report["limitations"] = [
            "Desktop Duplication observes DWM-composited pixels, not physical monitor scanout.",
            "The midpoint proof uses the isolated deterministic moving-target probe, not Minecraft gameplay.",
            "Centroid motion verifies spatial interpolation of this target; it is not a full image-quality metric.",
            "Shutdown completion is reported separately and is not required for already-flushed render evidence.",
        ]
        code = 0 if attributed else 2
    except (OSError, UnicodeError, TraceError) as exc:
        report["error"] = str(exc)
        report["nvidia_dlssg_dwm_compositor_interpolation"] = "FAIL"
        code = 2

    serialized = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
