# SPDX-License-Identifier: Apache-2.0
"""Verify source overlay integrity and conservative FSRFG trace accounting."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analyze_fsrfg_trace import audit  # noqa: E402
from prepare_fsrfg_trace import FFX, HOOKS, SOURCE, replace_once, stage, trace_ffx, trace_hooks  # noqa: E402


def sample(pid=4200, frame=11, result="The operation was successful.", requested=1):
    return "\n".join([
        f"[19:50:00.100] FGTRACE callback_enter pid={pid} tid=15 frame={frame} requested={requested} reset_before=0 present_color_input=0x1234",
        f"[19:50:00.101] FGTRACE callback_dispatch_begin pid={pid} tid=15 frame={frame} requested={requested} reset=1",
        f"[19:50:00.110] FGTRACE callback_dispatch_end pid={pid} tid=15 frame={frame} requested={requested} result={result}",
        f"[19:50:00.111] FGTRACE provider_output_present pid={pid} tid=15 result=0 swapchains=1",
        f"[19:50:00.111] FGTRACE provider_output_image pid={pid} index=1 swapchain_hash=443 result=0",
        f"[19:50:00.112] FGTRACE swapchain_image pid={pid} index=1 image_hash=887",
    ])


def gpu_sample(frame=11, sequence=1, generated="a", real="b"):
    return "\n".join([
        f"[23:00] FGGPUCONTENT gpu_copy_recorded frame={frame} roi_center=64x64 format=44 queued={sequence} completion_pending=1",
        f"[23:00] FGGPUCONTENT gpu_complete=1 frame={frame} generated_sha256={generated * 64} "
        f"real_sha256={real * 64} region=64x64 distinct={str(generated != real).lower()} complete={sequence}",
    ])


def moving_stimulus():
    return "\n".join([
        "stage=vulkan_swapchain_created width=704 height=401 images=3 format=44",
        "stage=ngx_resources_ready render=468x266 display=704x401 staging_bytes=1991808",
        "source_scene=11 box_x=210 box_y=93 mv_x=-5 mv_y=-1 gpu_roi_center_aligned=1",
        "source_scene=12 box_x=215 box_y=94 mv_x=-5 mv_y=-1 gpu_roi_center_aligned=1",
    ])


class FsrfgTraceTests(unittest.TestCase):
    def test_dispatch_and_present_do_not_prove_gpu_generated_scanout(self):
        report = audit(sample())
        self.assertTrue(report["diagnostic_valid"], report["failure_reasons"])
        self.assertEqual(report["callback_dispatch_success_events"], 1)
        self.assertEqual(report["requested_generation_count_sum"], 1)
        self.assertEqual(report["provider_output_vk_success_calls"], 1)
        self.assertFalse(report["fg_2x_proven"])
        self.assertIsNone(report["gpu_completed_generated_images"])

    def test_failure_and_orphaned_dispatch_rejected(self):
        report = audit(sample(result="The underlying runtime failed"))
        self.assertFalse(report["diagnostic_valid"])
        self.assertIn("ffx_callback_dispatch_failed", report["failure_reasons"])
        report = audit(sample().replace("FGTRACE callback_dispatch_begin", "FGTRACE callback_omitted"))
        self.assertIn("callback_dispatch_begin_end_mismatch", report["failure_reasons"])

    def test_mixed_pids_require_explicit_selection(self):
        log = sample(4200) + "\n" + sample(4201, 12)
        self.assertIn("mixed_process_trace_requires_explicit_expected_pid", audit(log)["failure_reasons"])
        report = audit(log, expected_pid=4201)
        self.assertTrue(report["diagnostic_valid"])
        self.assertEqual(report["callback_entry_events"], 1)
        self.assertEqual(report["trace_process_ids"], [4200, 4201])
        self.assertFalse(audit(log, expected_pid=9999)["diagnostic_valid"])

    def test_duplicate_frame_and_zero_requested_never_pass_fg(self):
        self.assertIn("duplicate_callback_dispatch_frame", audit(sample() + "\n" + sample())["failure_reasons"])
        report = audit(sample(requested=0))
        self.assertTrue(report["diagnostic_valid"])
        self.assertEqual(report["requested_generation_count_sum"], 0)
        self.assertFalse(report["fg_2x_proven"])

    def test_requested_count_change_or_reversed_callback_order_rejected(self):
        changed = sample().replace("callback_dispatch_end pid=4200 tid=15 frame=11 requested=1",
                                   "callback_dispatch_end pid=4200 tid=15 frame=11 requested=2")
        self.assertIn("callback_dispatch_requested_count_changed_frame_11", audit(changed)["failure_reasons"])
        lines = sample().splitlines()
        lines[1], lines[2] = lines[2], lines[1]
        self.assertIn("callback_dispatch_end_without_prior_begin_frame_11", audit("\n".join(lines))["failure_reasons"])

    def test_missing_dispatch_duplicate_skip_and_failed_present_rejected(self):
        self.assertIn("no_callback_dispatch_begin_events", audit("FGTRACE swapchain_image pid=4200 index=0 image_hash=44")["failure_reasons"])
        dup = sample() + "\nFGTRACE callback_skip_duplicate pid=4200 frame=11"
        self.assertIn("callback_skipped_duplicate_frame", audit(dup)["failure_reasons"])
        fail = sample().replace("provider_output_present pid=4200 tid=15 result=0",
                                "provider_output_present pid=4200 tid=15 result=-4")
        self.assertIn("provider_output_present_failed_or_missing_result", audit(fail)["failure_reasons"])

    def test_gpu_complete_readback_is_counted_without_scanout_claim(self):
        report = audit(sample(frame=11) + "\n" + sample(frame=12) + "\n" +
                       gpu_sample(11, 1, "a", "b") + "\n" + gpu_sample(12, 2, "c", "d"))
        self.assertTrue(report["diagnostic_valid"], report["failure_reasons"])
        self.assertEqual(report["gpu_completed_generated_images"], 2)
        self.assertEqual(report["gpu_generated_vs_real_distinct_samples"], 2)
        self.assertEqual(report["gpu_unique_generated_roi_hashes"], 2)
        self.assertEqual(report["gpu_sampled_frames"], [11, 12])
        self.assertTrue(report["distinct_generated_image_content_proven"])
        self.assertFalse(report["moving_object_inside_sampled_roi_proven"])
        self.assertFalse(report["useful_temporal_interpolation_proven"])
        self.assertFalse(report["physical_monitor_scanout_proven"])
        self.assertEqual(report["gate_h"], "BLOCKED")

    def test_gpu_rejects_malformed_hash_missing_completion_and_unmatched_frame(self):
        base = sample()
        malformed = base + "\n" + gpu_sample().replace("a" * 64, "invalid")
        self.assertIn("malformed_or_unmatched_gpu_content_event", audit(malformed)["failure_reasons"])
        missing = base + "\n" + gpu_sample().splitlines()[0]
        self.assertIn("gpu_content_copy_completion_mismatch", audit(missing)["failure_reasons"])
        unmatched = base + "\n" + gpu_sample(frame=17)
        self.assertIn("malformed_or_unmatched_gpu_content_event", audit(unmatched)["failure_reasons"])
        wrong_distinct = base + "\n" + gpu_sample().replace("distinct=true", "distinct=false")
        self.assertIn("malformed_or_unmatched_gpu_content_event", audit(wrong_distinct)["failure_reasons"])

    def test_gpu_events_cannot_be_attributed_in_multi_pid_log(self):
        report = audit(sample(4200) + "\n" + sample(4201, 12) + "\n" + gpu_sample(), expected_pid=4200)
        self.assertIn("gpu_content_unattributable_to_process", report["failure_reasons"])
        self.assertIsNone(report["gpu_completed_generated_images"])

    def test_stimulus_geometry_checks_projected_motion_and_vectors(self):
        trace = sample(frame=11) + "\n" + sample(frame=12) + "\n" + \
                gpu_sample(11, 1) + "\n" + gpu_sample(12, 2, "c", "d")
        report = audit(trace, stimulus_log=moving_stimulus())
        self.assertTrue(report["diagnostic_valid"], report["failure_reasons"])
        self.assertTrue(report["stimulus_projected_roi_overlap_verified"])
        self.assertTrue(report["stimulus_box_edge_crossed_roi"])
        self.assertEqual(report["stimulus_source_frames_matched"], 2)
        self.assertFalse(report["useful_temporal_interpolation_proven"])
        wrong_mv = moving_stimulus().replace("box_x=215 box_y=94 mv_x=-5", "box_x=215 box_y=94 mv_x=0")
        self.assertIn("invalid_gpu_stimulus_geometry: stimulus motion vector disagrees with source positions",
                      audit(trace, stimulus_log=wrong_mv)["failure_reasons"])
        offscreen = moving_stimulus().replace("box_x=215", "box_x=5")
        self.assertIn("invalid_gpu_stimulus_geometry: moving stimulus does not cover every GPU ROI",
                      audit(trace, stimulus_log=offscreen)["failure_reasons"])

    def test_gpu_runtime_error_fails_diagnostic(self):
        report = audit(sample() + "\n" + gpu_sample() +
                       "\nFGGPUCONTENT invalidate_failed frame=11 result=-4")
        self.assertIn("gpu_content_runtime_error", report["failure_reasons"])

    def test_gpu_unknown_events_and_bad_completion_status_are_rejected(self):
        base = sample() + "\n" + gpu_sample()
        for extra in ("gpu_complete=0 frame=11", "unrecognized_kind frame=11"):
            with self.subTest(extra=extra):
                report = audit(base + "\nFGGPUCONTENT " + extra)
                self.assertIn("unrecognized_gpu_content_event", report["failure_reasons"])
        valid_meta = "\nFGGPUCONTENT enabled limit=12 roi=64x64 capture_interferes_with_pacing=1"
        valid_meta += "\nFGGPUCONTENT summary attempted=1 completed=1 pending=0 no_scanout_proof=1"
        self.assertTrue(audit(base + valid_meta)["diagnostic_valid"])

    def test_gpu_invalid_queue_sequence_is_rejected(self):
        base = sample() + "\n" + gpu_sample()
        for broken in ("queued=0", "queued=3", "queued=nan"):
            with self.subTest(queue=broken):
                report = audit(base.replace("queued=1", broken))
                self.assertIn("malformed_or_unmatched_gpu_content_event", report["failure_reasons"])

    def test_source_anchors_are_unique_and_injections_do_not_change_pinned_checkout(self):
        originals = {name: (SOURCE / name).read_bytes() for name in (FFX, HOOKS)}
        self.assertIn("FGTRACE callback_dispatch_end", trace_ffx(originals[FFX].decode("utf-8-sig").replace("\r\n", "\n")))
        self.assertIn("FGTRACE provider_output_present", trace_hooks(originals[HOOKS].decode("utf-8-sig").replace("\r\n", "\n")))
        with self.assertRaises(ValueError):
            replace_once("hello", "missing", "replacement")
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "trace-overlay"
            manifest = stage(SOURCE, destination)
            self.assertEqual(manifest["status"], "SOURCE_ONLY_UNBUILT")
            self.assertGreater(len(manifest["missing_submodules"]), 0)
            manifest_on_disk = json.loads((destination / "trace-source-manifest.json").read_text())
            self.assertEqual(manifest, manifest_on_disk)
            for name, contents in originals.items():
                self.assertEqual((SOURCE / name).read_bytes(), contents)
            with self.assertRaises(FileExistsError):
                stage(SOURCE, destination)


if __name__ == "__main__":
    unittest.main()
