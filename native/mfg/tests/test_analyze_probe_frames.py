# SPDX-License-Identifier: Apache-2.0
"""Regression cases against false positive frame-generation evidence."""

import csv
import json
import copy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analyze_probe_frames import (TraceError, compare, read_pair, read_status,
                                  validate_termination, verify_bound_traces)  # noqa: E402
from classify_probe_run import classify, sha256_file  # noqa: E402


def write_csv(path, fields, entries):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(entries)


def mutate_csv(path, row_number, field, value):
    with path.open("r", newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames
        data = list(reader)
    data[row_number][field] = value
    write_csv(path, fields, data)


def write_status(path, applied=False, evaluations=0, failures=0, pid=1234):
    records = []
    for index in range(3):
        records.append(dict(pid=pid, processBirth=9999, elapsedMs=index * 1000,
                            sampleQpc=1_500_000 + index * 2_000_000,
                            qpcHz=10_000_000,
                            fgEnabled=applied, fgApplied=applied,
                            fgCreates=int(applied), fgEvaluations=evaluations * index,
                            fgSuccessEvaluations=evaluations * index,
                            fgBatches=evaluations * index,
                            fgFailedBatches=failures * index, route="dlssg"))
    path.write_text("".join(json.dumps(record) + "\n" for record in records),
                    encoding="utf-8")


def change_status(path, transform):
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    transform(records)
    path.write_text("".join(json.dumps(record) + "\n" for record in records),
                    encoding="utf-8")


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def pair(self, name, source_count, desktop_count, desktop_clock=10_000_000,
             hash_changes=True, desktop_step=50000, desktop_offset=100002,
             with_memory=True):
        source = self.root / f"{name}.source.csv"
        desktop = self.root / f"{name}.dwm.csv"
        source_fields = ["sourceFrame", "beforePresentQpc", "afterPresentQpc", "foreground", "qpcHz"]
        if with_memory:
            source_fields.extend(("gpuLocalUsageBytes", "gpuLocalBudgetBytes"))
        write_csv(source,
                  source_fields,
                  [dict(sourceFrame=i + 1, beforePresentQpc=100000 + i * 100000,
                        afterPresentQpc=100001 + i * 100000, foreground=1, qpcHz=10_000_000,
                        **({"gpuLocalUsageBytes": 2_000_000, "gpuLocalBudgetBytes": 8_000_000}
                           if with_memory else {}))
                   for i in range(source_count)])
        write_csv(desktop,
                  ["sample", "captureQpc", "desktopPresentQpc", "accumulatedFrames",
                   "hashChanged", "roiHash", "qpcHz"],
                  [dict(sample=i + 1, captureQpc=desktop_offset + i * desktop_step,
                        desktopPresentQpc=desktop_offset + i * desktop_step,
                        accumulatedFrames=1, hashChanged=int(hash_changes or i == 0),
                        roiHash=i if hash_changes else 42, qpcHz=desktop_clock)
                   for i in range(desktop_count)])
        return source, desktop

    def test_double_compositor_rate_with_identical_pixels_does_not_prove_fg(self):
        off = self.pair("off", 70, 70, desktop_step=100000)
        on = self.pair("on", 70, 140, hash_changes=False)
        output = compare(read_pair(*off), read_pair(*on))
        self.assertTrue(output["sufficient_compositor_samples_for_diagnostic"])
        self.assertEqual(output["gate_h"].split(" - ")[0], "BLOCKED")
        self.assertEqual(output["fg_on"]["desktop"]["distinct_roi_hash_events"], 1)
        self.assertAlmostEqual(output["observed_rate_ratios_on_over_off"]["dwm_compositor"], 2, delta=.01)
        self.assertEqual(output["observed_rate_ratios_on_over_off"]["dxgi_process_local_memory_peak"], 1)
        self.assertEqual(output["fg_on"]["source"]["dxgi_process_local_memory_bytes"]["samples"], 69)

    def test_no_foreground_cannot_pass_sample_gate(self):
        off = self.pair("off", 70, 70)
        on = self.pair("on", 70, 3)
        output = compare(read_pair(*off), read_pair(*on))
        self.assertFalse(output["sufficient_compositor_samples_for_diagnostic"])

    def test_mismatched_qpc_frequency_rejected(self):
        source, desktop = self.pair("bad-clock", 50, 50, desktop_clock=1_000_000)
        with self.assertRaisesRegex(TraceError, "clock frequencies differ"):
            read_pair(source, desktop)

    def test_disjoint_qpc_windows_cannot_make_false_fps_comparison(self):
        source, desktop = self.pair("disjoint", 70, 140, desktop_offset=50_000_000)
        with self.assertRaisesRegex(TraceError, "no overlapping foreground time window"):
            read_pair(source, desktop)

    def test_only_observed_overlap_counts_towards_sample_gate(self):
        off = self.pair("off", 70, 70, desktop_step=100000)
        on = self.pair("on", 70, 140, desktop_offset=6_500_000)
        output = compare(read_pair(*off), read_pair(*on))
        self.assertFalse(output["sufficient_compositor_samples_for_diagnostic"])
        self.assertLess(output["fg_on"]["overlap"]["duration_ms"], 500)

    def test_old_source_traces_report_memory_unavailable(self):
        old_source, old_desktop = self.pair("old", 70, 70, with_memory=False)
        old = read_pair(old_source, old_desktop)
        self.assertEqual(old["source"]["dxgi_process_local_memory_bytes"]["samples"], 0)

    def test_forged_hash_change_flags_rejected(self):
        source, desktop = self.pair("bad-hash", 70, 140, hash_changes=False)
        mutate_csv(desktop, 10, "hashChanged", 1)
        with self.assertRaisesRegex(TraceError, "ROI hash change flags"):
            read_pair(source, desktop)

    def test_missing_desktop_sample_ids_rejected(self):
        source, desktop = self.pair("missing-sample", 70, 140)
        mutate_csv(desktop, 12, "sample", 999)
        with self.assertRaisesRegex(TraceError, "sample IDs are not contiguous"):
            read_pair(source, desktop)

    def test_non_monotonic_desktop_capture_rejected(self):
        source, desktop = self.pair("bad-capture", 70, 140)
        mutate_csv(desktop, 12, "captureQpc", 0)
        with self.assertRaisesRegex(TraceError, "capture timestamps"):
            read_pair(source, desktop)

    def test_desktop_present_later_than_capture_rejected(self):
        source, desktop = self.pair("future-present", 70, 140)
        mutate_csv(desktop, 12, "desktopPresentQpc", 100_000_000)
        with self.assertRaisesRegex(TraceError, "outside their capture window"):
            read_pair(source, desktop)

    def test_pointer_only_desktop_updates_do_not_invalidate_real_presents(self):
        source, desktop = self.pair("pointer-update", 70, 140)
        mutate_csv(desktop, 12, "desktopPresentQpc", 0)
        output = read_pair(source, desktop)
        self.assertGreater(output["desktop"]["compositor_presents"]["unique_events"], 40)

    def test_non_monotonic_source_presents_rejected_even_outside_focus(self):
        source, desktop = self.pair("bad-source", 70, 140)
        mutate_csv(source, 12, "beforePresentQpc", 1_100_002)
        mutate_csv(source, 12, "afterPresentQpc", 1_100_003)
        with self.assertRaisesRegex(TraceError, "Source Present timestamps"):
            read_pair(source, desktop)

    def test_provider_activity_is_reported_but_does_not_certify_scanout(self):
        off = self.pair("off-status", 70, 70, desktop_step=100000)
        on = self.pair("on-status", 70, 140)
        off_path = self.root / "off.ndjson"
        on_path = self.root / "on.ndjson"
        write_status(off_path)
        write_status(on_path, applied=True, evaluations=10)
        output = compare(read_pair(*off), read_pair(*on),
                         read_status(off_path), read_status(on_path))
        self.assertTrue(output["controlled_provider_activity_for_diagnostic"])
        self.assertTrue(output["sufficient_compositor_samples_for_diagnostic"])
        self.assertEqual(output["provider_measured_windows"]["on"]["counter_delta"]["fgEvaluations"], 20)
        self.assertTrue(output["provider_measured_windows"]["on"]["enabled_activity"]["qualified"])
        self.assertEqual(output["provider_measured_windows"]["on"]["enabled_activity"]["intervals"][0]["samples"], 3)
        self.assertEqual(output["gate_h"].split(" - ")[0], "BLOCKED")

    def compare_provider(self, transform_on=None, transform_off=None):
        off = self.pair("off-provider", 70, 70)
        on = self.pair("on-provider", 70, 140)
        off_path, on_path = self.root / "off-provider.ndjson", self.root / "on-provider.ndjson"
        write_status(off_path)
        write_status(on_path, applied=True, evaluations=10)
        if transform_off:
            change_status(off_path, transform_off)
        if transform_on:
            change_status(on_path, transform_on)
        return compare(read_pair(*off), read_pair(*on),
                       read_status(off_path), read_status(on_path))

    def test_disabled_last_interval_cannot_supply_enabled_work_delta(self):
        def alter(rows):
            rows[2]["fgEnabled"] = rows[2]["fgApplied"] = False
            for counter in ("fgEvaluations", "fgSuccessEvaluations", "fgBatches"):
                rows[1][counter] = 0

        report = self.compare_provider(transform_on=alter)
        self.assertEqual(report["provider_measured_windows"]["on"]["counter_delta"]["fgEvaluations"], 20)
        self.assertFalse(report["provider_measured_windows"]["on"]["enabled_activity"]["qualified"])
        self.assertFalse(report["controlled_provider_activity_for_diagnostic"])

    def test_enabled_and_applied_at_different_snapshots_cannot_qualify(self):
        def alter(rows):
            for index, row in enumerate(rows):
                row["fgApplied"] = bool(index % 2)
                row["fgEnabled"] = not row["fgApplied"]

        report = self.compare_provider(transform_on=alter)
        active = report["provider_measured_windows"]["on"]["enabled_activity"]
        self.assertFalse(active["both_flags_observed"])
        self.assertFalse(active["qualified"])
        self.assertFalse(report["controlled_provider_activity_for_diagnostic"])

    def test_active_snapshots_separated_by_disabled_state_do_not_form_an_interval(self):
        def alter(rows):
            rows[1]["fgEnabled"] = rows[1]["fgApplied"] = False

        report = self.compare_provider(transform_on=alter)
        self.assertEqual(report["provider_measured_windows"]["on"]["enabled_activity"]["intervals"], [])
        self.assertFalse(report["controlled_provider_activity_for_diagnostic"])

    def test_disjoint_active_runs_cannot_combine_partial_counter_deltas(self):
        def alter(rows):
            for index in (3, 4):
                row = dict(rows[-1])
                row["elapsedMs"] = index * 200
                row["sampleQpc"] = 1_500_000 + index * 1_000_000
                rows.append(row)
            for index, row in enumerate(rows):
                row["elapsedMs"] = index * 200
                row["sampleQpc"] = 1_500_000 + index * 1_000_000
                row["fgEnabled"] = row["fgApplied"] = index != 2
                row["fgEvaluations"] = 0 if index == 0 else 10
                row["fgSuccessEvaluations"] = row["fgBatches"] = 10 if index == 4 else 0

        report = self.compare_provider(transform_on=alter)
        active = report["provider_measured_windows"]["on"]["enabled_activity"]
        self.assertEqual(len(active["intervals"]), 2)
        self.assertFalse(active["qualified"])
        self.assertEqual(report["provider_measured_windows"]["on"]["counter_delta"]["fgEvaluations"], 10)
        self.assertFalse(report["controlled_provider_activity_for_diagnostic"])

    def test_activity_in_later_consecutive_enabled_interval_qualifies(self):
        def alter(rows):
            rows[0]["fgEnabled"] = rows[0]["fgApplied"] = False

        report = self.compare_provider(transform_on=alter)
        active = report["provider_measured_windows"]["on"]["enabled_activity"]
        self.assertTrue(active["qualified"])
        self.assertEqual(active["intervals"][0]["samples"], 2)
        self.assertEqual(active["intervals"][0]["counter_delta"]["fgEvaluations"], 10)
        self.assertTrue(report["controlled_provider_activity_for_diagnostic"])

    def test_off_profile_unexpected_batches_block_controlled_trial(self):
        def alter(rows):
            rows[-1]["fgBatches"] = 1

        report = self.compare_provider(transform_off=alter)
        self.assertTrue(report["provider_measured_windows"]["on"]["enabled_activity"]["qualified"])
        self.assertFalse(report["controlled_provider_activity_for_diagnostic"])

    def test_no_provider_evaluations_cannot_satisfy_controlled_trial(self):
        off = self.pair("off-no-provider", 70, 70)
        on = self.pair("on-no-provider", 70, 140)
        off_path = self.root / "off.ndjson"
        on_path = self.root / "on.ndjson"
        write_status(off_path)
        write_status(on_path, applied=True)
        output = compare(read_pair(*off), read_pair(*on),
                         read_status(off_path), read_status(on_path))
        self.assertFalse(output["controlled_provider_activity_for_diagnostic"])

    def test_provider_failure_cannot_satisfy_controlled_trial(self):
        off = self.pair("off-error", 70, 70)
        on = self.pair("on-error", 70, 140)
        off_path = self.root / "off.ndjson"
        on_path = self.root / "on.ndjson"
        write_status(off_path)
        write_status(on_path, applied=True, evaluations=10, failures=1)
        output = compare(read_pair(*off), read_pair(*on),
                         read_status(off_path), read_status(on_path))
        self.assertFalse(output["controlled_provider_activity_for_diagnostic"])

    def test_mixed_process_status_is_rejected(self):
        path = self.root / "mixed-pid.ndjson"
        write_status(path, applied=True, evaluations=3)
        records = [json.loads(line) for line in path.read_text().splitlines()]
        records[-1]["pid"] = 999
        path.write_text("".join(json.dumps(row) + "\n" for row in records))
        with self.assertRaisesRegex(TraceError, "mixes process identities"):
            read_status(path)

    def test_regressing_provider_counter_is_rejected(self):
        path = self.root / "counter-regression.ndjson"
        write_status(path, applied=True, evaluations=5)
        records = [json.loads(line) for line in path.read_text().splitlines()]
        records[-1]["fgEvaluations"] = 0
        path.write_text("".join(json.dumps(row) + "\n" for row in records))
        with self.assertRaisesRegex(TraceError, "fgEvaluations"):
            read_status(path)

    def test_startup_only_provider_activity_cannot_satisfy_foreground_gate(self):
        off = self.pair("off-startup", 70, 70)
        on = self.pair("on-startup", 70, 140)
        off_path = self.root / "off.ndjson"
        on_path = self.root / "on.ndjson"
        write_status(off_path)
        write_status(on_path, applied=True, evaluations=10)
        rows = [json.loads(line) for line in on_path.read_text().splitlines()]
        rows[0]["sampleQpc"] = 50_000  # Before the source/DWM overlap.
        for field in ("fgEvaluations", "fgSuccessEvaluations", "fgBatches"):
            rows[1][field] = rows[2][field] = 20
        on_path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        report = compare(read_pair(*off), read_pair(*on),
                         read_status(off_path), read_status(on_path))
        self.assertFalse(report["controlled_provider_activity_for_diagnostic"])
        self.assertEqual(report["provider_measured_windows"]["on"]["counter_delta"]["fgEvaluations"], 0)

    def test_shutdown_only_provider_activity_cannot_satisfy_foreground_gate(self):
        off = self.pair("off-shutdown", 70, 70)
        on = self.pair("on-shutdown", 70, 140)
        off_path = self.root / "off.ndjson"
        on_path = self.root / "on.ndjson"
        write_status(off_path)
        write_status(on_path, applied=True, evaluations=10)
        rows = [json.loads(line) for line in on_path.read_text().splitlines()]
        rows[2]["sampleQpc"] = 9_000_000  # After the foreground trace.
        for field in ("fgEvaluations", "fgSuccessEvaluations", "fgBatches"):
            rows[1][field] = 0
        on_path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        report = compare(read_pair(*off), read_pair(*on),
                         read_status(off_path), read_status(on_path))
        self.assertFalse(report["controlled_provider_activity_for_diagnostic"])

    def test_provider_qpc_clock_must_match_native_trace(self):
        off = self.pair("off-qpc", 70, 70)
        on = self.pair("on-qpc", 70, 140)
        off_path = self.root / "off.ndjson"
        on_path = self.root / "on.ndjson"
        write_status(off_path)
        write_status(on_path, applied=True, evaluations=10)
        rows = [json.loads(line) for line in on_path.read_text().splitlines()]
        for row in rows:
            row["qpcHz"] = 1_000_000
        on_path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        with self.assertRaisesRegex(TraceError, "QPC clock frequencies differ"):
            compare(read_pair(*off), read_pair(*on), read_status(off_path), read_status(on_path))

    def test_invalid_provider_qpc_and_missing_qpc_rejected(self):
        path = self.root / "bad-qpc.ndjson"
        write_status(path, applied=True, evaluations=10)
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[1]["sampleQpc"] = rows[0]["sampleQpc"]
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        with self.assertRaisesRegex(TraceError, "Provider QPC timestamps"):
            read_status(path)
        del rows[1]["sampleQpc"]
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        with self.assertRaisesRegex(TraceError, "Malformed provider status"):
            read_status(path)

    def termination_fixture(self, *, mode="on", timed_out=True):
        source, desktop = self.pair(f"{mode}-termination", 70, 140)
        status_path = self.root / f"{mode}-termination.ndjson"
        write_status(status_path, applied=mode == "on",
                     evaluations=10 if mode == "on" else 0)
        stdout = ("Probe presents=70 foreground presents=70\n"
                  "Real Remix: Vulkan hooked=1 presents=70 menu draws=0 failures=0\n"
                  "Remix Vulkan host retired\nBeginning Remix Shutdown\n")
        if not timed_out:
            stdout += "Remix Shutdown completed\n"
        termination = classify(stdout, 70, timed_out, -1 if timed_out else 0,
                               process_pid=1234, process_birth=9999,
                               observer_required=True, observer_exit_code=0)
        observer = self.root / f"{mode}-termination.observer.log"
        observer.write_text("Observer PID=1234 clockHz=10000000 ROI=256x256\n"
                            "DWM foreground samples=140\n", encoding="utf-8")
        termination["trace_sha256"] = {
            "source": sha256_file(source),
            "desktop": sha256_file(desktop),
            "status": sha256_file(status_path),
            "observer_log": sha256_file(observer),
        }
        report_path = self.root / f"{mode}-termination.json"
        report_path.write_text(json.dumps(termination), encoding="utf-8")
        return source, desktop, status_path, report_path, termination

    def test_completed_render_with_shutdown_timeout_remains_diagnostic_eligible(self):
        source, desktop, status, _, report = self.termination_fixture()
        validate_termination(report, read_pair(source, desktop), read_status(status), "on")
        self.assertFalse(report["rendering_and_shutdown_both_passed"])
        self.assertFalse(report["actual_interpolated_display_frames_verified"])

    def test_termination_validation_rejects_observer_identity_and_count_failures(self):
        source, desktop, status, _, baseline = self.termination_fixture()
        trace, parsed = read_pair(source, desktop), read_status(status)
        for patch, message in (
                ({"observer_passed": False}, "observer"),
                ({"observer_exit_code": 1}, "observer"),
                ({"process_birth": 4444}, "identity"),
                ({"process_pid": 9999}, "identity"),
                ({"rendered_frames": 69}, "counts"),
                ({"foreground_frames": 69}, "counts"),
                ({"result": "incomplete_or_failed"}, "termination"),
                ({"process_timed_out": False}, "termination"),
                ({"shutdown_completed": True}, "termination"),
                ({"exit_code": 0}, "termination")):
            with self.subTest(patch=patch):
                forged = copy.deepcopy(baseline)
                forged.update(patch)
                with self.assertRaisesRegex(TraceError, message):
                    validate_termination(forged, trace, parsed, "on")

    def test_cli_preserves_timeout_and_still_requires_fg_provider_activity(self):
        off = self.termination_fixture(mode="off", timed_out=False)
        on = self.termination_fixture(mode="on", timed_out=True)
        output = self.root / "off-on.json"
        command = [sys.executable, str(Path(__file__).resolve().parents[1] /
                    "analyze_probe_frames.py"),
                   "--off-source", str(off[0]), "--off-desktop", str(off[1]),
                   "--off-status", str(off[2]), "--off-termination", str(off[3]),
                   "--off-observer-log", str(self.root / "off-termination.observer.log"),
                   "--on-source", str(on[0]), "--on-desktop", str(on[1]),
                   "--on-status", str(on[2]), "--on-termination", str(on[3]),
                   "--on-observer-log", str(self.root / "on-termination.observer.log"),
                   "--output", str(output)]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, msg=result.stderr + result.stdout)
        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertTrue(report["termination_eligible_for_diagnostic"])
        self.assertEqual(report["termination"]["on"]["result"],
                         "shutdown_timeout_after_complete_render")
        self.assertTrue(report["controlled_provider_activity_for_diagnostic"])
        self.assertEqual(report["gate_h"].split(" - ")[0], "BLOCKED")

        # The same valid termination artifacts cannot override inactive DLSSG.
        write_status(on[2], applied=False)
        # Rebind the intentional fixture update so this checks FG gates,
        # independently of the missing/swapped-trace integrity rejection.
        on_report = json.loads(on[3].read_text(encoding="utf-8"))
        on_report["trace_sha256"]["status"] = sha256_file(on[2])
        on[3].write_text(json.dumps(on_report), encoding="utf-8")
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 2)
        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertTrue(report["termination_eligible_for_diagnostic"])
        self.assertFalse(report["controlled_provider_activity_for_diagnostic"])

        # Corrupting the ON DWM evidence must also fail closed.
        on[1].unlink()
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 2)
        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertFalse(report["termination_eligible_for_diagnostic"])
        self.assertIn("error", report)

    def test_bound_traces_reject_stale_or_swapped_evidence(self):
        off = self.termination_fixture(mode="off", timed_out=False)
        on = self.termination_fixture(mode="on", timed_out=True)
        paths = {"source": on[0], "desktop": on[1], "status": on[2],
                 "observer_log": self.root / "on-termination.observer.log"}
        verify_bound_traces(on[4], paths, "on")
        for kind, replacement in (("source", off[0]), ("desktop", off[1]),
                                  ("status", off[2]),
                                  ("observer_log", self.root / "off-termination.observer.log")):
            with self.subTest(kind=kind):
                changed = dict(paths)
                changed[kind] = replacement
                # Source/desktop fixture contents may match, while ON/OFF
                # provider counters must differ. Mutate when needed.
                if kind != "status" and replacement.read_bytes() == paths[kind].read_bytes():
                    replacement.write_bytes(replacement.read_bytes() + b"\n")
                with self.assertRaisesRegex(TraceError, "SHA-256 mismatch"):
                    verify_bound_traces(on[4], changed, "on")
        missing = copy.deepcopy(on[4])
        missing["trace_sha256"].pop("source")
        with self.assertRaisesRegex(TraceError, "source trace SHA-256"):
            verify_bound_traces(missing, paths, "on")

    def test_bound_observer_pid_cannot_be_swapped_into_another_trial(self):
        source, desktop, status, _, termination = self.termination_fixture()
        observer = self.root / "on-termination.observer.log"
        observer.write_text("Observer PID=2222 clockHz=10000000\n", encoding="utf-8")
        termination["trace_sha256"]["observer_log"] = sha256_file(observer)
        with self.assertRaisesRegex(TraceError, "observer process target PID"):
            verify_bound_traces(termination, {"source": source, "desktop": desktop,
                                              "status": status, "observer_log": observer}, "on")


if __name__ == "__main__":
    unittest.main()
