# SPDX-License-Identifier: Apache-2.0
"""Regression tests for deterministic DWM-compositor midpoint evidence."""

import csv
import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analyze_dlssg_compositor_motion import (TraceError, compare_motion,
                                             read_motion_run)  # noqa: E402


def write_csv(path, fields, entries):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(entries)


class CompositorMotionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def run_files(self, name, *, doubled, midpoint=True, source_bias=0.0):
        source_path = self.root / f"{name}.source.csv"
        desktop_path = self.root / f"{name}.desktop.csv"
        frames = 90
        source_rows = []
        endpoints = []
        for index in range(frames):
            frame = index + 1
            expected = 128.0 + 40.0 * math.sin(index / 9.0) + source_bias
            endpoint = 120.0 + 20.0 * math.sin(index / 9.0)
            source_rows.append({
                "sourceFrame": frame,
                "afterPresentQpc": 1_000_000 + index * 166_667,
                "foreground": 1,
                "qpcHz": 10_000_000,
                "expectedCropCentroidX": expected,
            })
            endpoints.append(endpoint)
        write_csv(source_path,
                  ["sourceFrame", "afterPresentQpc", "foreground", "qpcHz",
                   "expectedCropCentroidX"], source_rows)

        states = []
        sample = 1
        first = 29
        for index in range(first, frames - 1):
            left = endpoints[index]
            right = endpoints[index + 1]
            if doubled:
                states.append((source_rows[index]["afterPresentQpc"] + 20_000, left))
                value = (left + right) * .5 if midpoint else left
                states.append((source_rows[index]["afterPresentQpc"] + 80_000, value))
            else:
                states.append((source_rows[index]["afterPresentQpc"] + 20_000, left))
        states.append((source_rows[-1]["afterPresentQpc"] - 10_000, endpoints[-1]))
        desktop_rows = []
        for stamp, centroid in states:
            desktop_rows.append({
                "sample": sample,
                "desktopPresentQpc": stamp,
                "hashChanged": 1,
                "roiHash": sample,
                "qpcHz": 10_000_000,
                "orangePixels": 1000,
                "orangeCentroidX": centroid,
            })
            sample += 1
        write_csv(desktop_path,
                  ["sample", "desktopPresentQpc", "hashChanged", "roiHash", "qpcHz",
                   "orangePixels", "orangeCentroidX"], desktop_rows)
        return source_path, desktop_path

    def test_midpoint_states_pass_compositor_evidence(self):
        off_paths = self.run_files("off", doubled=False)
        on_paths = self.run_files("on", doubled=True, midpoint=True)
        report = compare_motion(read_motion_run(*off_paths), read_motion_run(*on_paths))
        self.assertEqual(report["dwm_compositor_midpoint_evidence"], "PASS")
        self.assertAlmostEqual(report["steady_state"]["on_over_off_state_count_ratio"], 2.0,
                               delta=.05)
        self.assertGreaterEqual(
            report["intermediate_states"]["within_half_plus_minus_tolerance_fraction"], .95)

    def test_doubled_endpoint_duplicates_do_not_fake_interpolation(self):
        off_paths = self.run_files("off-duplicate", doubled=False)
        on_paths = self.run_files("on-duplicate", doubled=True, midpoint=False)
        report = compare_motion(read_motion_run(*off_paths), read_motion_run(*on_paths))
        self.assertEqual(report["dwm_compositor_midpoint_evidence"], "FAIL")
        self.assertLess(
            report["intermediate_states"]["within_half_plus_minus_tolerance_fraction"], .5)

    def test_source_motion_mismatch_is_rejected(self):
        off_paths = self.run_files("off-source", doubled=False)
        on_paths = self.run_files("on-source", doubled=True, source_bias=1.0)
        with self.assertRaisesRegex(TraceError, "source motion differs"):
            compare_motion(read_motion_run(*off_paths), read_motion_run(*on_paths))


if __name__ == "__main__":
    unittest.main()
