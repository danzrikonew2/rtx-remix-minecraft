# SPDX-License-Identifier: Apache-2.0
"""Ensure a teardown timeout never certifies incomplete GPU-frame work."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from classify_probe_run import classify  # noqa: E402


COMPLETE = ("Probe presents=140 foreground presents=120\n"
            "Real Remix: Vulkan hooked=1 presents=140 menu draws=0 failures=0\n"
            "Remix Vulkan host retired\n"
            "Beginning Remix Shutdown\n")


class ProbeTerminationTests(unittest.TestCase):
    def test_stock_shutdown_timeout_is_analysis_eligible_but_not_clean(self):
        outcome = classify(COMPLETE, 140, timed_out=True, exit_code=-1)
        self.assertEqual(outcome["result"], "shutdown_timeout_after_complete_render")
        self.assertTrue(outcome["eligible_for_diagnostic_analysis"])
        self.assertFalse(outcome["rendering_and_shutdown_both_passed"])
        self.assertFalse(outcome["actual_interpolated_display_frames_verified"])

    def test_clean_shutdown_requires_complete_post_render_marker(self):
        good = classify(COMPLETE + "Remix Shutdown completed\n", 140, False, 0)
        self.assertEqual(good["result"], "clean_shutdown")
        self.assertTrue(good["rendering_and_shutdown_both_passed"])
        missing = classify(COMPLETE, 140, False, 0)
        self.assertFalse(missing["eligible_for_diagnostic_analysis"])

    def test_rejects_incomplete_frames_render_failures_and_missing_host_retirement(self):
        variants = (COMPLETE.replace("presents=140 foreground", "presents=139 foreground"),
                    COMPLETE.replace("failures=0", "failures=1"),
                    COMPLETE.replace("Remix Vulkan host retired\n", ""),
                    COMPLETE.replace("Vulkan hooked=1", "Vulkan hooked=0"),
                    COMPLETE.replace("Beginning Remix Shutdown\n", ""),
                    COMPLETE + "FAIL: something\n", COMPLETE + COMPLETE)
        for broken in variants:
            with self.subTest(broken=broken[-75:]):
                self.assertFalse(classify(broken, 140, True, -1)["eligible_for_diagnostic_analysis"])

    def test_non_timeout_failure_and_proclaimed_timeout_after_clean_shutdown_rejected(self):
        self.assertFalse(classify(COMPLETE, 140, False, 1)["eligible_for_diagnostic_analysis"])
        self.assertFalse(classify(COMPLETE + "Remix Shutdown completed\n", 140, True, -1)
                         ["eligible_for_diagnostic_analysis"])
        self.assertFalse(classify(COMPLETE, 140, True, 0)["eligible_for_diagnostic_analysis"])

    def test_duplicate_termination_markers_and_truncated_output_rejected(self):
        for broken in (COMPLETE + "Beginning Remix Shutdown\n",
                       COMPLETE + "Remix Vulkan host retired\n",
                       COMPLETE + "Remix Shutdown completed\nRemix Shutdown completed\n",
                       COMPLETE.replace("Real Remix: Vulkan hooked=1 presents=140 menu draws=0 failures=0\n", ""),
                       COMPLETE.replace("Probe presents=140 foreground presents=120\n", "")):
            with self.subTest(broken=broken[-65:]):
                self.assertFalse(classify(broken, 140, True, -1)["eligible_for_diagnostic_analysis"])

    def test_process_and_observer_are_reported_independently(self):
        result = classify(COMPLETE, 140, True, -1, process_pid=6808,
                          process_birth=9999, observer_required=True,
                          observer_exit_code=1, observer_timed_out=True)
        self.assertEqual(result["result"], "shutdown_timeout_after_complete_render")
        self.assertEqual(result["process_pid"], 6808)
        self.assertFalse(result["observer_passed"])
        self.assertFalse(result["rendering_and_shutdown_both_passed"])
        ok = classify(COMPLETE + "Remix Shutdown completed\n", 140, False, 0,
                      observer_required=True, observer_exit_code=0)
        self.assertTrue(ok["observer_passed"])
        with self.assertRaisesRegex(ValueError, "process identity"):
            classify(COMPLETE, 140, True, -1, process_pid=-1)


if __name__ == "__main__":
    unittest.main()
