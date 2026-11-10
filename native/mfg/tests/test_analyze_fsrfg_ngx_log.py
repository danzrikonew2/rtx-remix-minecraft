# SPDX-License-Identifier: Apache-2.0
"""Synthetic evidence tests; successful preparation must never imply x2 FG."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analyze_fsrfg_ngx_log import audit  # noqa: E402


def fixture(frames=14, begin=11, pacing_error=False):
    stdout = [
        "probe=real_win32_vulkan_wsi ngx_evaluate=1 fg_proven=0",
        "csv=seq,elapsed_ms,source_present_result",
    ]
    log = [
        "[I] FSRFG_Vk::CreateSwapchain Swapchain context creation result: The operation was successful.",
        "[I] FSRFG_Vk::CreateContext FG context creation result: The operation was successful.",
    ]
    for n in range(frames):
        stdout.extend([f"ngx_evaluate={n} result=1", f"frame={n},{n * 31},VK_SUCCESS"])
        log.extend([
            "[D] NVSDK_NGX_VULKAN_EvaluateFeature Handle: 1000000",
            f"[D] IFGFeature::StartNewFrame _frameCount: {n + 1}, fIndex: {(n + 1) % 4}",
        ])
        if n + 1 >= begin:
            log.extend([
                f"[D] FSRFG_Vk::Dispatch Configure result: The operation was successful., frame: {n + 1}, fIndex: {(n + 1) % 4}",
                f"[D] FSRFG_Vk::Dispatch Prepare result: The operation was successful., frame: {n + 1}, fIndex: {(n + 1) % 4}",
            ])
    log += [
        "[D] FSRFG_Vk::DispatchCallback Frame id 11 after 0, resetting",
        "[I] FSRFG_Vk::DestroyFGContext Destroy FG context result: The operation was successful.",
        "[I] FSRFG_Vk::ReleaseSwapchainContext Destroy swapchain context result: The operation was successful.",
    ]
    if pacing_error:
        log.append("[D] FSRFG_Vk::ConfigureFramePaceTuning Frame pacing tuning configure result: The underlying runtime returned an error code.")
    stdout.extend([f"ngx_evaluations_completed={frames}",
                   "stage=ngx_shutdown_skipped clean_shutdown_proven=0",
                   "result=NGX_EVALUATE_PRESENT_SHUTDOWN_SKIPPED fg_proven=0 generated_frames_verified=0 clean_shutdown_proven=0"])
    return "\n".join(log), "\n".join(stdout)


class FsrfgNgxEvidenceTests(unittest.TestCase):
    def test_provider_prepare_evidence_never_claims_generated_frames(self):
        log, stdout = fixture(pacing_error=True)
        result = audit(log, stdout, frames=14)
        self.assertTrue(result["diagnostic_valid"], result["failure_reasons"])
        self.assertEqual(result["ffx"]["prepare_success_count"], 4)
        self.assertEqual(result["ffx"]["callback_reset_debug_lines"], 1)
        self.assertIsNone(result["ffx"]["callback_dispatch_success_count"])
        self.assertFalse(result["fg_2x_proven"])
        self.assertFalse(result["physical_scanout_verified"])
        self.assertFalse(result["ngx_normal_shutdown_proven"])
        self.assertEqual(result["gate_h"], "BLOCKED")
        self.assertEqual(len(result["ffx"]["frame_pacing_configuration_errors"]), 1)

    def test_early_exit_before_ten_frame_target_is_not_fg(self):
        log, stdout = fixture(frames=8)
        result = audit(log, stdout, frames=8)
        self.assertTrue(result["diagnostic_valid"])
        self.assertEqual(result["ffx"]["prepare_success_count"], 0)
        self.assertFalse(result["fg_2x_proven"])

    def test_missing_prepare_or_duplicate_configure_fails_closed(self):
        log, stdout = fixture()
        for bad in (
            log.replace("FSRFG_Vk::Dispatch Prepare result:", "FSRFG_Vk::Dispatch Suppressed result:", 1),
            log + "\n" + "[D] FSRFG_Vk::Dispatch Configure result: The operation was successful., frame: 14, fIndex: 2",
        ):
            with self.subTest(bad=bad[-90:]):
                result = audit(bad, stdout, frames=14)
                self.assertFalse(result["diagnostic_valid"])
                self.assertIn("configure_prepare_frames_or_indices_mismatch", result["failure_reasons"])

    def test_failed_ffx_result_and_missing_context_rejected(self):
        log, stdout = fixture()
        result = audit(log.replace("Dispatch Prepare result: The operation was successful.",
                                   "Dispatch Prepare result: DEVICE_LOST", 1), stdout, frames=14)
        self.assertFalse(result["diagnostic_valid"])
        self.assertIn("ffx_configure_or_prepare_error", result["failure_reasons"])
        result = audit(log.replace("CreateContext FG context creation", "CreateContext Failed"), stdout, frames=14)
        self.assertFalse(result["diagnostic_valid"])

    def test_different_source_run_or_stale_log_rejected(self):
        log, stdout = fixture()
        bad = stdout.replace("frame=2,62,VK_SUCCESS", "frame=2,62,VK_ERROR_DEVICE_LOST")
        self.assertFalse(audit(log, bad, frames=14)["diagnostic_valid"])
        self.assertFalse(audit(log, stdout, frames=64)["diagnostic_valid"])
        self.assertFalse(audit(log + "\n" + log, stdout, frames=14)["diagnostic_valid"])

    def test_ngx_failure_duplicate_and_missing_shutdown_rejected(self):
        log, stdout = fixture()
        self.assertFalse(audit(log, stdout.replace("ngx_evaluate=3 result=1", "ngx_evaluate=3 result=0"), frames=14)["diagnostic_valid"])
        self.assertFalse(audit(log, stdout.replace("SHUTDOWN_SKIPPED", "UNEXPECTED"), frames=14)["diagnostic_valid"])


if __name__ == "__main__":
    unittest.main()
