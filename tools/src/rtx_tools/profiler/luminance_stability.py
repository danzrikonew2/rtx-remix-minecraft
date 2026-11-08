#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Measure relative display-luminance variation in a fixed screen-space ROI.

Input is a sequence of lossless PNG frames captured at a fixed camera and output
configuration. The reported luminance is relative display luminance computed
from sRGB-decoded pixels; it is not a scene-linear radiance measurement.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import TypedDict, cast

import numpy as np
from PIL import Image

Roi = tuple[int, int, int, int]


class LuminanceSummary(TypedDict):
    frame_count: int
    sample_rate_hz: float
    roi: dict[str, int]
    mean_relative_luminance: float
    raw_stddev_percent_of_mean: float
    detrended_stddev_percent_of_mean: float
    detrended_peak_to_peak_percent_of_mean: float
    strongest_non_dc_frequency_hz: float | None
    strongest_non_dc_amplitude: float | None


def roi_luminance(path: Path, roi: Roi) -> float:
    """Return mean Rec. 709 relative luminance for an exclusive-coordinate ROI."""
    return _read_roi_luminance(path, roi)[0]


def _read_roi_luminance(path: Path, roi: Roi) -> tuple[float, tuple[int, int]]:
    x0, y0, x1, y1 = roi
    with Image.open(path) as image:
        width, height = image.size
        if x0 < 0 or y0 < 0 or x1 <= x0 or y1 <= y0 or x1 > width or y1 > height:
            raise ValueError(f"ROI {roi} is outside {path.name} dimensions {width}x{height}")
        rgb = np.asarray(image.crop(roi).convert("RGB"), dtype=np.float64) / 255.0
    encoded = rgb
    linear = np.where(encoded <= 0.04045, encoded / 12.92, ((encoded + 0.055) / 1.055) ** 2.4)
    luminance = linear @ np.array([0.2126, 0.7152, 0.0722])
    return float(np.mean(luminance)), (width, height)


def analyze_frames(
    frames: list[Path], roi: Roi, sample_rate_hz: float
) -> tuple[LuminanceSummary, list[dict[str, float | int]]]:
    if sample_rate_hz <= 0 or not math.isfinite(sample_rate_hz):
        raise ValueError("sample rate must be a finite positive number")
    if len(frames) < 3:
        raise ValueError("at least three frames are required")

    samples: list[float] = []
    dimensions: tuple[int, int] | None = None
    for frame in frames:
        luminance, current_dimensions = _read_roi_luminance(frame, roi)
        if dimensions is not None and current_dimensions != dimensions:
            raise ValueError(
                f"capture dimensions changed from {dimensions[0]}x{dimensions[1]} "
                f"to {current_dimensions[0]}x{current_dimensions[1]} at {frame.name}"
            )
        dimensions = current_dimensions
        samples.append(luminance)
    values = np.asarray(samples, dtype=np.float64)
    if not np.all(np.isfinite(values)) or float(np.mean(values)) <= 0:
        raise ValueError("ROI must contain finite, nonzero luminance")
    mean = float(np.mean(values))
    times = np.arange(len(values), dtype=np.float64) / sample_rate_hz
    slope, intercept = np.polyfit(times, values, 1)
    detrended = values - (slope * times + intercept)
    spectrum = np.abs(np.fft.rfft(detrended)) / len(detrended)
    frequencies = np.fft.rfftfreq(len(detrended), d=1.0 / sample_rate_hz)
    if len(spectrum) > 1:
        peak_index = int(np.argmax(spectrum[1:]) + 1)
        amplitude_scale = 1.0 if len(values) % 2 == 0 and peak_index == len(values) // 2 else 2.0
        measured_amplitude = float(amplitude_scale * spectrum[peak_index])
        roundoff_tolerance = 100.0 * np.finfo(np.float64).eps * max(mean, float(np.max(np.abs(values))))
        if measured_amplitude > roundoff_tolerance:
            peak_frequency: float | None = float(frequencies[peak_index])
            peak_amplitude: float | None = measured_amplitude
        else:
            peak_frequency = peak_amplitude = None
    else:
        peak_frequency = peak_amplitude = None

    summary: LuminanceSummary = {
        "frame_count": len(frames),
        "sample_rate_hz": sample_rate_hz,
        "roi": {"x0": roi[0], "y0": roi[1], "x1": roi[2], "y1": roi[3]},
        "mean_relative_luminance": mean,
        "raw_stddev_percent_of_mean": float(np.std(values) / mean * 100.0),
        "detrended_stddev_percent_of_mean": float(np.std(detrended) / mean * 100.0),
        "detrended_peak_to_peak_percent_of_mean": float(np.ptp(detrended) / mean * 100.0),
        "strongest_non_dc_frequency_hz": peak_frequency,
        "strongest_non_dc_amplitude": peak_amplitude,
    }
    rows: list[dict[str, float | int]] = [
        {
            "frame": index,
            "time_seconds": float(time),
            "relative_luminance": float(value),
            "detrended_luminance": float(detrend),
        }
        for index, (time, value, detrend) in enumerate(zip(times, values, detrended, strict=True))
    ]
    return summary, rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("frames", type=Path, help="Directory containing lossless PNG frame captures")
    parser.add_argument("--pattern", default="*.png", help="Frame filename glob, sorted lexicographically")
    parser.add_argument(
        "--roi",
        nargs=4,
        type=int,
        required=True,
        metavar=("X0", "Y0", "X1", "Y1"),
        help="Fixed screen-space rectangle; X1/Y1 are exclusive",
    )
    parser.add_argument("--fps", type=float, required=True, help="Uniform capture sample rate in frames per second")
    parser.add_argument("--csv", type=Path, help="Per-frame output CSV (default: frames/luminance.csv)")
    parser.add_argument("--json", type=Path, help="Summary output JSON (default: frames/luminance-summary.json)")
    args = parser.parse_args()

    frames = sorted(args.frames.glob(args.pattern))
    summary, rows = analyze_frames(frames, cast(Roi, tuple(args.roi)), args.fps)
    csv_path = args.csv or args.frames / "luminance.csv"
    json_path = args.json or args.frames / "luminance-summary.json"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    json_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
