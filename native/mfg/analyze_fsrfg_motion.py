# SPDX-License-Identifier: Apache-2.0
"""Audit fixture-specific foreground pixels in GPU-completed FSRFG ROIs.

This is evidence about two GPU readback images. It is not scanout, FG frame
pacing, interpolated-motion correctness or 2x FPS measurement.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path

from analyze_fsrfg_trace import audit as trace_audit


FIELD = re.compile(r"(?:^|\s)([a-z_][a-z_0-9]*)=([^\s]+)")
HEX_MASK = re.compile(r"[0-9a-f]{1024}\Z")
VALID_FORMATS = {37, 43, 44, 50}  # RGBA8/BGRA8 UNORM and SRGB


def decode_mask(mask: str) -> dict:
    """The shader capture emits 64 little-endian-x 64-bit hexadecimal rows."""
    if not HEX_MASK.fullmatch(mask):
        raise ValueError("foreground mask must contain 64 hex rows of 16 digits")
    hits = 0
    sum_x = 0
    sum_y = 0
    bounds = [64, 64, -1, -1]
    for y in range(64):
        bits = int(mask[y * 16:(y + 1) * 16], 16)
        hits += bits.bit_count()
        if bits:
            bounds[1] = min(bounds[1], y)
            bounds[3] = max(bounds[3], y)
        while bits:
            lowest = bits & -bits
            x = lowest.bit_length() - 1
            bounds[0] = min(bounds[0], x)
            bounds[2] = max(bounds[2], x)
            sum_x += x
            sum_y += y
            bits &= bits - 1
    return {
        "hits": hits,
        "bounds_xyxy": bounds if hits else None,
        "centroid_xy": [round(sum_x / hits, 3), round(sum_y / hits, 3)] if hits else None,
    }


def audit_motion(log: str, gpu_frames: list[int]) -> dict:
    errors = []
    records = {}
    seen_masks = {"generated": set(), "real": set()}
    for line in log.splitlines():
        if "FGMOTION " not in line:
            continue
        details = line.split("FGMOTION ", 1)[1].strip()
        if details.startswith("unsupported_pixel_format "):
            errors.append("unsupported_motion_pixel_format")
            continue
        if not details.startswith("roi_frame="):
            errors.append("unrecognized_motion_event")
            continue
        fields = dict(FIELD.findall(details))
        try:
            frame = int(fields["roi_frame"])
            fmt = int(fields["format"])
            if frame in records or fmt not in VALID_FORMATS:
                raise ValueError("duplicate frame or unrecognized 8-bit format")
            entry = {"frame": frame, "format": fmt}
            for kind in ("generated", "real"):
                mask = fields[f"{kind}_mask"]
                metrics = decode_mask(mask)
                if int(fields[f"{kind}_hits"]) != metrics["hits"]:
                    raise ValueError("mask hit count disagrees with GPU log")
                rgb_max = fields.get(f"{kind}_rgb_max")
                if rgb_max is not None:
                    maxima = [int(part) for part in rgb_max.split(",")]
                    if len(maxima) != 3 or any(value < 0 or value > 255 for value in maxima):
                        raise ValueError("invalid RGB extrema")
                    metrics["rgb_max"] = maxima
                entry[kind] = metrics
                seen_masks[kind].add(mask)
            entry["generated_vs_real_mask_distinct"] = (
                fields["generated_mask"] != fields["real_mask"]
            )
            records[frame] = entry
        except (KeyError, ValueError):
            errors.append("malformed_motion_event")

    expected = set(gpu_frames)
    if len(expected) != len(gpu_frames):
        errors.append("duplicate_gpu_completion_frame")
    if not expected or set(records) != expected:
        errors.append("motion_and_gpu_completed_frame_mismatch")
    frames = [records[k] for k in sorted(records)]
    has_both = all(row["generated"]["hits"] > 0 and row["real"]["hits"] > 0
                   for row in frames) and bool(frames)
    generated_centroids = [row["generated"]["centroid_xy"] for row in frames]
    real_centroids = [row["real"]["centroid_xy"] for row in frames]
    varying = (len(seen_masks["generated"]) >= 2 and len(seen_masks["real"]) >= 2)
    motion_detected = has_both and varying and len(frames) >= 3
    return {
        "motion_diagnostic_valid": not errors,
        "motion_failure_reasons": list(dict.fromkeys(errors)),
        "motion_sample_count": len(frames),
        "motion_sampled_frames": sorted(records),
        "motion_format_values": sorted({row["format"] for row in frames}),
        "motion_generated_unique_masks": len(seen_masks["generated"]),
        "motion_real_unique_masks": len(seen_masks["real"]),
        "motion_generated_vs_real_distinct_masks": sum(
            row["generated_vs_real_mask_distinct"] for row in frames),
        "motion_generated_centroid_first_last": [generated_centroids[0], generated_centroids[-1]] if frames else None,
        "motion_real_centroid_first_last": [real_centroids[0], real_centroids[-1]] if frames else None,
        "fixture_foreground_in_both_gpu_readbacks_proven": has_both,
        "fixture_foreground_changed_over_time": motion_detected,
        "motion_samples": frames,
        "interpolated_motion_correctness_proven": False,
        "physical_monitor_scanout_proven": False,
        "fg_2x_proven": False,
        "gate_h": "BLOCKED",
        "interpretation": (
            "The format-aware masks detect the red moving fixture within the "
            "GPU-completed 64x64 generated/real readbacks. Changed masks "
            "alone do not prove useful interpolation, monitor scanout, "
            "smooth frame pacing, 2x FPS, or game integration."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--stimulus-log", required=True, type=Path)
    parser.add_argument("--expected-pid", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"Refusing overwrite of motion audit: {args.output}")
    raw_log = args.log.read_bytes()
    raw_stimulus = args.stimulus_log.read_bytes()
    log = raw_log.decode("utf-8-sig", errors="replace")
    stimulus = raw_stimulus.decode("utf-8-sig", errors="replace")
    base = trace_audit(log, expected_pid=args.expected_pid, stimulus_log=stimulus)
    motion = audit_motion(log, base["gpu_sampled_frames"])
    report = {**base, **motion}
    report["diagnostic_valid"] = base["diagnostic_valid"] and motion["motion_diagnostic_valid"]
    report["failure_reasons"] = base["failure_reasons"] + motion["motion_failure_reasons"]
    report["trace_sha256"] = hashlib.sha256(raw_log).hexdigest()
    report["stimulus_log_sha256"] = hashlib.sha256(raw_stimulus).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "motion_samples"}, indent=2))
    return 0 if report["diagnostic_valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
