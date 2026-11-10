# SPDX-License-Identifier: Apache-2.0
"""Synthetic integrity tests for r6 GPU-completed fixture masks."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analyze_fsrfg_motion import audit_motion, decode_mask  # noqa: E402


def mask_at(x: int, y: int) -> str:
    return "".join(f"{(1 << x) if row == y else 0:016x}" for row in range(64))


def line(frame: int, x: int) -> str:
    return (f"FGMOTION roi_frame={frame} format=44 generated_mask={mask_at(x, 12)} "
            f"real_mask={mask_at(x + 1, 12)} generated_hits=1 real_hits=1")


class MotionAuditTests(unittest.TestCase):
    def test_mask_orientation_centroid_and_hits(self):
        result = decode_mask(mask_at(3, 9))
        self.assertEqual(result, {"hits": 1, "bounds_xyxy": [3, 9, 3, 9],
                                  "centroid_xy": [3, 9]})

    def test_valid_temporal_foreground(self):
        report = audit_motion("\n".join(line(i, i + 5) for i in range(4)), [0, 1, 2, 3])
        self.assertTrue(report["motion_diagnostic_valid"])
        self.assertTrue(report["fixture_foreground_changed_over_time"])
        self.assertEqual(report["motion_generated_vs_real_distinct_masks"], 4)
        self.assertFalse(report["interpolated_motion_correctness_proven"])
        self.assertEqual(report["gate_h"], "BLOCKED")

    def test_missing_mismatch_and_duplicate_rejected(self):
        self.assertIn("motion_and_gpu_completed_frame_mismatch",
                      audit_motion(line(1, 2), [1, 2])["motion_failure_reasons"])
        self.assertIn("malformed_motion_event",
                      audit_motion(line(1, 2) + "\n" + line(1, 3), [1])["motion_failure_reasons"])

    def test_bad_hit_counter_rejected(self):
        invalid = line(4, 10).replace("generated_hits=1", "generated_hits=2")
        self.assertIn("malformed_motion_event", audit_motion(invalid, [4])["motion_failure_reasons"])

    def test_optional_rgb_extrema_checked(self):
        correct = line(1, 9) + " generated_rgb_max=235,220,26 real_rgb_max=235,220,26"
        result = audit_motion(correct, [1])
        self.assertTrue(result["motion_diagnostic_valid"])
        self.assertEqual(result["motion_samples"][0]["generated"]["rgb_max"], [235, 220, 26])
        invalid = correct.replace("235,220,26", "1000,220,26", 1)
        self.assertIn("malformed_motion_event", audit_motion(invalid, [1])["motion_failure_reasons"])

    def test_truncated_masks_and_wrong_format_rejected(self):
        self.assertIn("malformed_motion_event", audit_motion(line(4, 10).replace("format=44", "format=97"), [4])["motion_failure_reasons"])
        self.assertIn("malformed_motion_event", audit_motion(line(4, 10).replace(mask_at(10, 12), "a"), [4])["motion_failure_reasons"])


if __name__ == "__main__":
    unittest.main()
