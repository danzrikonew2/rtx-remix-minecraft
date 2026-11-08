# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import math

import numpy as np
import pytest
from PIL import Image

from rtx_tools.profiler.luminance_stability import analyze_frames, roi_luminance


def _write_gray(path, value):
    Image.new("RGB", (8, 8), (value, value, value)).save(path)


def test_roi_luminance_uses_linearized_srgb_and_exclusive_bounds(tmp_path):
    frame = tmp_path / "frame.png"
    Image.new("RGB", (8, 8), (128, 128, 128)).save(frame)

    assert roi_luminance(frame, (2, 2, 6, 6)) == pytest.approx(0.21586, abs=0.0001)
    with pytest.raises(ValueError, match="outside"):
        roi_luminance(frame, (0, 0, 9, 8))


def test_analysis_detects_periodic_brightness_while_removing_slow_drift(tmp_path):
    rate = 10.0
    count = 200
    indices = np.arange(count)
    values = np.clip(130 + 0.03 * indices + 18 * np.sin(2 * math.pi * 1.0 * indices / rate), 0, 255)
    frames = []
    for index, value in enumerate(values):
        path = tmp_path / f"frame_{index:04}.png"
        _write_gray(path, round(float(value)))
        frames.append(path)

    summary, rows = analyze_frames(frames, (0, 0, 8, 8), rate)

    assert len(rows) == count
    assert summary["raw_stddev_percent_of_mean"] > 5
    assert summary["detrended_stddev_percent_of_mean"] > 5
    assert summary["strongest_non_dc_frequency_hz"] == pytest.approx(1.0, abs=0.05)
    assert summary["detrended_peak_to_peak_percent_of_mean"] > 20


def test_analysis_rejects_too_few_frames_and_invalid_rate(tmp_path):
    frame = tmp_path / "frame.png"
    _write_gray(frame, 128)
    with pytest.raises(ValueError, match="three frames"):
        analyze_frames([frame, frame], (0, 0, 8, 8), 5.0)
    with pytest.raises(ValueError, match="positive"):
        analyze_frames([frame] * 3, (0, 0, 8, 8), 0.0)


def test_constant_capture_has_no_significant_frequency(tmp_path):
    frames = []
    for index in range(30):
        path = tmp_path / f"frame_{index:04}.png"
        _write_gray(path, 128)
        frames.append(path)

    summary, _ = analyze_frames(frames, (0, 0, 8, 8), 5.0)

    assert summary["detrended_stddev_percent_of_mean"] < 1e-10
    assert summary["strongest_non_dc_frequency_hz"] is None
    assert summary["strongest_non_dc_amplitude"] is None


def test_nyquist_peak_amplitude_is_not_doubled(tmp_path):
    frames = []
    for index, value in enumerate([0, 255] * 50):
        path = tmp_path / f"frame_{index:04}.png"
        _write_gray(path, value)
        frames.append(path)

    summary, _ = analyze_frames(frames, (0, 0, 8, 8), 50.0)

    assert summary["strongest_non_dc_frequency_hz"] == pytest.approx(25.0)
    assert summary["strongest_non_dc_amplitude"] == pytest.approx(0.5, abs=0.01)


def test_analysis_rejects_capture_dimensions_that_change(tmp_path):
    frames = []
    for index, size in enumerate(((8, 8), (8, 8), (9, 8))):
        path = tmp_path / f"frame_{index:04}.png"
        Image.new("RGB", size, (128, 128, 128)).save(path)
        frames.append(path)

    with pytest.raises(ValueError, match="dimensions changed"):
        analyze_frames(frames, (0, 0, 8, 8), 5.0)
