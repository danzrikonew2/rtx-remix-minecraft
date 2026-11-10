# SPDX-License-Identifier: Apache-2.0
"""Audit isolated OptiScaler FSRFG trace events without claiming FG acceptance.

Requires a separately built diagnostic OptiScaler fork. The r5 opt-in trace
adds bounded GPU-completed ROI SHA-256 evidence, but neither the sampled pixels
nor queue-present results establish actual monitor scanout or interpolation.
"""

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path


EVENT = re.compile(r"FGTRACE (?P<kind>[a-z_]+) pid=(?P<pid>\d+)(?P<detail>.*)$")
FRAME = re.compile(r"(?:^| )frame=(\d+)(?: |$)")
REQUESTED = re.compile(r"(?:^| )requested=(\d+)(?: |$)")
RESULT = re.compile(r"(?:^| )result=(.+)$")
SUCCESS = "The operation was successful."
GPU_FIELDS = re.compile(r"(?:^|\s)([a-z_][a-z_0-9]*)=([^\s]+)")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
ROI = re.compile(r"(\d+)x(\d+)\Z")
SWAP_EXTENT = re.compile(r"stage=vulkan_swapchain_created width=(\d+) height=(\d+)")
RENDER_EXTENT = re.compile(r"stage=ngx_resources_ready render=(\d+)x(\d+) display=(\d+)x(\d+)")
SOURCE_FRAME = re.compile(
    r"source_scene=(\d+) box_x=(-?\d+) box_y=(-?\d+) mv_x=(-?[\d.]+) mv_y=(-?[\d.]+)"
    r" gpu_roi_center_aligned=(\d+)"
)


def check_stimulus_geometry(stimulus: str, frames: list[int]) -> dict:
    """Check the source box's projected overlap; never infer generated pixels."""
    swap = SWAP_EXTENT.search(stimulus)
    render = RENDER_EXTENT.search(stimulus)
    if swap is None or render is None or not frames:
        raise ValueError("missing stimulus extent or GPU frames")
    output_w, output_h = (int(swap[1]), int(swap[2]))
    input_w, input_h, display_w, display_h = map(int, render.groups())
    if ((output_w, output_h) != (display_w, display_h) or
            min(output_w, output_h, input_w, input_h) < 64):
        raise ValueError("invalid stimulus render or output geometry")
    box = {}
    for match in SOURCE_FRAME.finditer(stimulus):
        frame = int(match[1])
        if frame in box:
            raise ValueError("duplicate source scene frame")
        box[frame] = (int(match[2]), int(match[3]), float(match[4]),
                      float(match[5]), int(match[6]))
    if any(frame not in box or box[frame][4] != 1 for frame in frames):
        raise ValueError("missing or unaligned source scene frame")
    # A 64x64 output-center pixel region maps approximately to these source
    # bounds under the fixture's input/output scaling. It does not account for
    # any spatial reconstruction or motion warp within the upscaler.
    left = ((output_w - 64) / 2) * input_w / output_w
    right = ((output_w + 64) / 2) * input_w / output_w
    top = ((output_h - 64) / 2) * input_h / output_h
    bottom = ((output_h + 64) / 2) * input_h / output_h
    positions = [(box[frame][0], box[frame][1]) for frame in frames]
    all_overlap = all(x < right and x + 90 > left and
                      y < bottom and y + 70 > top for x, y in positions)
    if not all_overlap:
        raise ValueError("moving stimulus does not cover every GPU ROI")
    for before, after in zip(frames, frames[1:]):
        if after != before + 1:
            continue
        a, b = box[before], box[after]
        if abs(b[2] - (a[0] - b[0])) > 0.01 or abs(b[3] - (a[1] - b[1])) > 0.01:
            raise ValueError("stimulus motion vector disagrees with source positions")
    first_edges = [x for x, _ in positions]
    edge_crossed = min(first_edges) < left < max(first_edges)
    return {
        "stimulus_source_frames_matched": len(frames),
        "stimulus_projected_roi_overlap_verified": True,
        "stimulus_box_edge_crossed_roi": edge_crossed,
        "stimulus_source_roi_bounds": [round(left, 2), round(top, 2),
                                       round(right, 2), round(bottom, 2)],
    }


def audit(text: str, *, expected_pid: int | None = None,
          stimulus_log: str | None = None) -> dict:
    """Require matched begin/end callbacks; retain honest visibility limits."""
    if expected_pid is not None and expected_pid <= 0:
        raise ValueError("expected PID must be positive")
    events = []
    encountered_pids = set()
    gpu_lines = []
    for line in text.splitlines():
        if "FGGPUCONTENT " in line:
            gpu_lines.append(line.split("FGGPUCONTENT ", 1)[1].strip())
        match = EVENT.search(line)
        if match is None:
            continue
        pid = int(match["pid"])
        encountered_pids.add(pid)
        if expected_pid is None or pid == expected_pid:
            events.append((match["kind"], pid, match["detail"]))

    errors = []
    entries, begins, ends = Counter(), Counter(), Counter()
    begin_requests = {}
    requests, successes, failures = [], [], []
    output_presents = 0
    output_images = 0
    swapchain_images = 0
    cancelled = 0
    duplicates = 0
    for kind, pid, detail in events:
        if kind in {"callback_enter", "callback_dispatch_begin", "callback_dispatch_end",
                    "callback_skip_duplicate", "callback_cancel"}:
            frame_match = FRAME.search(detail)
            if frame_match is None:
                errors.append(f"{kind}_missing_frame")
                continue
            key = (pid, int(frame_match[1]))
            if kind == "callback_enter":
                entries[key] += 1
            elif kind == "callback_skip_duplicate":
                duplicates += 1
            elif kind == "callback_cancel":
                cancelled += 1
            elif kind == "callback_dispatch_begin":
                if entries[key] <= begins[key]:
                    errors.append(f"callback_dispatch_begin_without_prior_entry_frame_{key[1]}")
                requested = REQUESTED.search(detail)
                if requested is None:
                    errors.append(f"callback_dispatch_begin_missing_requested_frame_{key[1]}")
                else:
                    begin_requests[key] = int(requested[1])
                begins[key] += 1
            else:
                if begins[key] <= ends[key]:
                    errors.append(f"callback_dispatch_end_without_prior_begin_frame_{key[1]}")
                ends[key] += 1
                requested = REQUESTED.search(detail)
                result = RESULT.search(detail)
                if requested is None or result is None:
                    errors.append(f"callback_dispatch_end_incomplete_frame_{key[1]}")
                    continue
                requests.append(int(requested[1]))
                if key in begin_requests and int(requested[1]) != begin_requests[key]:
                    errors.append(f"callback_dispatch_requested_count_changed_frame_{key[1]}")
                if result[1].strip() == SUCCESS:
                    successes.append(key)
                else:
                    failures.append({"pid": pid, "frame": key[1], "result": result[1].strip()})
        elif kind == "provider_output_present":
            result = RESULT.search(detail)
            # Return result 0 is Vulkan VK_SUCCESS; other success-like results are not counted.
            if result and result[1].split(" ", 1)[0] == "0":
                output_presents += 1
            else:
                errors.append("provider_output_present_failed_or_missing_result")
        elif kind == "adapter_present":
            result = RESULT.search(detail)
            if not result or result[1].split(" ", 1)[0] != "0":
                errors.append("adapter_present_failed_or_missing_result")
        elif kind == "provider_output_image":
            output_images += 1
        elif kind == "swapchain_image":
            swapchain_images += 1

    if not events:
        errors.append("no_instrumented_trace_events_for_target_pid")
    elif not begins:
        errors.append("no_callback_dispatch_begin_events")
    if len(encountered_pids) > 1 and expected_pid is None:
        errors.append("mixed_process_trace_requires_explicit_expected_pid")
    if begins != ends:
        errors.append("callback_dispatch_begin_end_mismatch")
    if any(begins[key] > entries[key] for key in begins):
        errors.append("callback_dispatch_without_entry")
    if any(v > 1 for v in begins.values()) or any(v > 1 for v in ends.values()):
        errors.append("duplicate_callback_dispatch_frame")
    if failures:
        errors.append("ffx_callback_dispatch_failed")
    if duplicates:
        errors.append("callback_skipped_duplicate_frame")

    # r5 FGGPUCONTENT lines currently omit the process ID. Never attribute
    # their readbacks to a chosen process when the log contains mixed PIDs.
    ambiguous_gpu_pid = len(encountered_pids) != 1 or (
        expected_pid is not None and expected_pid not in encountered_pids
    )
    gpu_copies = {}
    gpu_samples = []
    if gpu_lines and ambiguous_gpu_pid:
        errors.append("gpu_content_unattributable_to_process")
    elif gpu_lines:
        for record in gpu_lines:
            if "_failed" in record or record.startswith("error"):
                errors.append("gpu_content_runtime_error")
                continue
            is_copy = record.startswith("gpu_copy_recorded ")
            is_complete = record.startswith("gpu_complete=1 ")
            if not (is_copy or is_complete):
                if not (record.startswith("enabled ") or record.startswith("summary ")):
                    errors.append("unrecognized_gpu_content_event")
                continue
            fields = dict(GPU_FIELDS.findall(record))
            try:
                frame = int(fields["frame"])
                region_key = "roi_center" if is_copy else "region"
                region = ROI.fullmatch(fields[region_key])
                if frame < 0 or region is None or int(region[1]) <= 0 or int(region[2]) <= 0:
                    raise ValueError("invalid region or frame")
                size = (int(region[1]), int(region[2]))
                if is_copy:
                    if (frame in gpu_copies or fields.get("completion_pending") != "1" or
                            int(fields["queued"]) != len(gpu_copies) + 1):
                        raise ValueError("duplicate or invalid GPU copy")
                    gpu_copies[frame] = size
                    continue
                generated, real = fields["generated_sha256"], fields["real_sha256"]
                distinct = fields["distinct"]
                sequence = int(fields["complete"])
                if (not SHA256.fullmatch(generated) or not SHA256.fullmatch(real) or
                        distinct not in {"true", "false", "0", "1"} or
                        (distinct in {"true", "1"}) != (generated != real) or
                        sequence != len(gpu_samples) + 1 or
                        frame not in gpu_copies or gpu_copies[frame] != size or
                        any(item["frame"] == frame for item in gpu_samples) or
                        (next(iter(encountered_pids)), frame) not in successes):
                    raise ValueError("invalid GPU completion")
                gpu_samples.append({"frame": frame, "generated": generated, "real": real})
            except (KeyError, ValueError):
                errors.append("malformed_or_unmatched_gpu_content_event")
        if len(gpu_copies) != len(gpu_samples):
            errors.append("gpu_content_copy_completion_mismatch")

    gpu_count = len(gpu_samples) if gpu_copies or gpu_samples else None
    gpu_distinct_count = sum(s["generated"] != s["real"] for s in gpu_samples)
    gpu_unique_generated = len({s["generated"] for s in gpu_samples})
    gpu_unique_real = len({s["real"] for s in gpu_samples})
    stimulus_details = {
        "stimulus_source_frames_matched": 0,
        "stimulus_projected_roi_overlap_verified": False,
        "stimulus_box_edge_crossed_roi": False,
        "stimulus_source_roi_bounds": None,
    }
    if stimulus_log is not None:
        try:
            stimulus_details = check_stimulus_geometry(
                stimulus_log, [sample["frame"] for sample in gpu_samples]
            )
        except ValueError as exc:
            errors.append(f"invalid_gpu_stimulus_geometry: {exc}")

    return {
        "diagnostic_valid": not errors,
        "failure_reasons": list(dict.fromkeys(errors)),
        "target_pid": expected_pid,
        "trace_process_ids": sorted(encountered_pids),
        "callback_entry_events": sum(entries.values()),
        "callback_dispatch_begin_events": sum(begins.values()),
        "callback_dispatch_end_events": sum(ends.values()),
        "callback_dispatch_success_events": len(successes),
        "callback_dispatch_failures": failures,
        "callback_duplicate_skip_events": duplicates,
        "callback_cancel_events": cancelled,
        "requested_generation_count_sum": sum(requests),
        "provider_output_vk_success_calls": output_presents,
        "provider_output_image_index_events": output_images,
        "adapter_swapchain_image_handle_events": swapchain_images,
        "gpu_completed_generated_images": gpu_count,
        "gpu_generated_vs_real_distinct_samples": gpu_distinct_count if gpu_count is not None else None,
        "gpu_unique_generated_roi_hashes": gpu_unique_generated if gpu_count is not None else None,
        "gpu_unique_real_roi_hashes": gpu_unique_real if gpu_count is not None else None,
        "gpu_sampled_frames": [s["frame"] for s in gpu_samples],
        **stimulus_details,
        "distinct_generated_image_content_proven": gpu_unique_generated >= 2,
        "moving_object_inside_sampled_roi_proven": False,
        "useful_temporal_interpolation_proven": False,
        "physical_monitor_scanout_proven": False,
        "fg_2x_proven": False,
        "gate_h": "BLOCKED",
        "interpretation": (
            "FFX callbacks and Vulkan queue-present results are CPU-side observations. "
            "Optional GPU-completed ROI hashes show only sampled image bytes, not that moving "
            "objects were correctly interpolated, that frames were independently composited, "
            "or that any frame reached the physical monitor. Absence of a provider_output "
            "event may mean a bypassed Vulkan hook."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--expected-pid", type=int)
    parser.add_argument("--stimulus-log", type=Path,
                        help="optional NGX source-scene stdout for projected ROI geometry")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"Refusing to overwrite an existing audit: {args.output}")
    payload = args.log.read_bytes()
    stimulus = args.stimulus_log.read_bytes() if args.stimulus_log is not None else None
    report = audit(payload.decode("utf-8-sig", errors="replace"), expected_pid=args.expected_pid,
                   stimulus_log=stimulus.decode("utf-8-sig", errors="replace") if stimulus is not None else None)
    report["trace_sha256"] = hashlib.sha256(payload).hexdigest()
    if stimulus is not None:
        report["stimulus_log_sha256"] = hashlib.sha256(stimulus).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["diagnostic_valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
