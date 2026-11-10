# SPDX-License-Identifier: Apache-2.0
"""Check immutable source packaging and fail-closed isolation for NGX probes."""

import configparser
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import prepare_ngx_run_copy as copy_tool  # noqa: E402


class NgxRunCopyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.build = self.root / "build"
        self.build.mkdir()
        self.source = self.build / "trusted" / "Package"
        self.source.mkdir(parents=True)
        self.binary = self.source / "OptiScaler.dll"
        self.binary.write_bytes(b"verified synthetic fixture")
        self.sha = hashlib.sha256(self.binary.read_bytes()).hexdigest()
        self.ini = self.source / "OptiScaler.ini"
        self.ini.write_text("[Plugins]\nPath=original\n[Libraries]\nOptiDllPath=original\n"
                            "[FrameGen]\nEnabled=true\nFGOutput=fsrfg\n", encoding="utf-8")
        (self.source / "OptiScaler.log").write_text("old trace\n", encoding="utf-8")
        (self.source / "OptiScaler").mkdir()
        (self.source / "OptiScaler" / "amd_fidelityfx_vk.dll").write_bytes(b"provider-pin")
        self.destination = self.build / "runs" / "test-a" / "Package"
        self.destination.parent.parent.mkdir()

    def stage(self, sha=None):
        return copy_tool.snapshot(self.root, self.source, self.destination,
                                  sha or self.sha, verify_source=False)

    def test_isolates_ini_log_and_pinned_dependencies(self):
        before = {p.relative_to(self.source): p.read_bytes()
                  for p in self.source.rglob("*") if p.is_file()}
        output = self.stage()
        self.assertEqual(output, self.destination / "OptiScaler.dll")
        self.assertFalse((self.destination / "OptiScaler.log").exists())
        config = configparser.ConfigParser(interpolation=None)
        config.read(self.destination / "OptiScaler.ini")
        self.assertEqual(config.get("Plugins", "Path"),
                         str(self.destination / "OptiScaler" / "plugins"))
        self.assertEqual(config.get("Libraries", "OptiDllPath"),
                         str(self.destination / "OptiScaler"))
        self.assertEqual(config.get("FrameGen", "FGOutput"), "fsrfg")
        self.assertEqual((self.destination / "OptiScaler" / "amd_fidelityfx_vk.dll").read_bytes(),
                         b"provider-pin")
        for rel, content in before.items():
            self.assertEqual((self.source / rel).read_bytes(), content)
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.stage()

    def test_dll_hash_mismatch_does_not_publish(self):
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            self.stage("0" * 64)
        self.assertFalse(self.destination.parent.exists())

    def test_baseline_sidecars_are_cloned_without_modifying_originals(self):
        expected = {}
        for name in ("probe-inputs.json", "LICENSE", "SOURCE.txt"):
            data = ("baseline " + name).encode("utf-8")
            (self.source.parent / name).write_bytes(data)
            expected[name] = data
        self.stage()
        for name, content in expected.items():
            self.assertEqual((self.destination.parent / name).read_bytes(), content)
            self.assertEqual((self.source.parent / name).read_bytes(), content)

    def test_baseline_missing_sidecar_rejected_atomically(self):
        (self.source.parent / "probe-inputs.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "sidecar missing"):
            self.stage()
        self.assertFalse(self.destination.parent.exists())

    def test_incomplete_configuration_does_not_publish(self):
        self.ini.write_text("[Plugins]\nPath=original\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Libraries"):
            self.stage()
        self.assertFalse(self.destination.parent.exists())

    def test_missing_verification_rejects_before_publication(self):
        with patch.object(copy_tool, "verify_original", side_effect=ValueError("untrusted manifest")):
            with self.assertRaisesRegex(ValueError, "untrusted manifest"):
                copy_tool.snapshot(self.root, self.source, self.destination, self.sha)
        self.assertFalse(self.destination.parent.exists())

    def test_rejects_outside_build_and_source_as_destination(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            copy_tool.snapshot(self.root, self.source, self.root / "outside" / "Package",
                               self.sha, verify_source=False)
        with self.assertRaisesRegex(ValueError, "own run destination"):
            copy_tool.snapshot(self.root, self.source, self.source, self.sha,
                               verify_source=False)

    def test_manifest_dispatch(self):
        with patch.object(copy_tool, "verify_color_package") as color, \
                patch.object(copy_tool, "verify_motion_package") as motion, \
                patch.object(copy_tool, "verify_gpucontent_package") as gpucontent, \
                patch.object(copy_tool, "verify_shutdown_package") as shutdown, \
                patch.object(copy_tool, "verify_trace_package") as trace, \
                patch.object(copy_tool, "verify_baseline_package") as baseline:
            copy_tool.verify_original(self.root, self.source)
            baseline.assert_called_once()
            (self.source.parent / "trace-build-manifest.json").write_text("{}")
            copy_tool.verify_original(self.root, self.source)
            trace.assert_called_once()
            (self.source.parent / "shutdown-build-manifest.json").write_text("{}")
            copy_tool.verify_original(self.root, self.source)
            shutdown.assert_called_once()
            (self.source.parent / "gpucontent-build-manifest.json").write_text("{}")
            copy_tool.verify_original(self.root, self.source)
            gpucontent.assert_called_once_with(self.root, self.source)
            self.assertEqual(shutdown.call_count, 1)
            (self.source.parent / "motion-build-manifest.json").write_text("{}")
            copy_tool.verify_original(self.root, self.source)
            motion.assert_called_once_with(self.root, self.source)
            self.assertEqual(gpucontent.call_count, 1)
            (self.source.parent / "color-build-manifest.json").write_text("{}")
            copy_tool.verify_original(self.root, self.source)
            color.assert_called_once_with(self.root, self.source)
            self.assertEqual(motion.call_count, 1)


if __name__ == "__main__":
    unittest.main()
