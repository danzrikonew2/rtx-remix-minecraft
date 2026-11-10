# SPDX-License-Identifier: Apache-2.0
"""Validate the isolated DLSSG/FSRFG selection and fail-closed provider pin."""

import configparser
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verify_optiscaler_probe import PINS, verify  # noqa: E402

TOOLS = Path(__file__).resolve().parents[1]


class ProbeFgOutputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.package = self.root / "staging" / "Package"
        self.package.mkdir(parents=True)
        self.ini = self.package / "OptiScaler.ini"
        self.ini.write_text("[FrameGen]\nEnabled=false\n", encoding="utf-8")
        self.final = self.root / "published" / "Package"

    def configure(self, *options):
        return subprocess.run([
            sys.executable, str(TOOLS / "configure_probe_ini.py"),
            "--ini", str(self.ini), "--package", str(self.package),
            "--final-package", str(self.final), *options,
        ], capture_output=True, text=True, check=False)

    def test_default_dlssg_is_backward_compatible(self):
        result = self.configure()
        self.assertEqual(result.returncode, 0, result.stderr)
        config = configparser.ConfigParser()
        config.read(self.ini)
        self.assertEqual(config.get("FrameGen", "FGOutput"), "dlssg")
        self.assertEqual(config.get("FrameGen", "Enabled"), "true")

    def test_explicit_fsrfg_on_and_off(self):
        for state in ("on", "off"):
            with self.subTest(state=state):
                result = self.configure("--fg-state", state, "--fg-output", "fsrfg")
                self.assertEqual(result.returncode, 0, result.stderr)
                config = configparser.ConfigParser()
                config.read(self.ini)
                self.assertEqual(config.get("FrameGen", "FGOutput"), "fsrfg")
                self.assertEqual(config.get("FrameGen", "Enabled"), str(state == "on").lower())
                self.assertEqual(config.get("Upscalers", "VulkanUpscaler"), "dlss")

    def test_invalid_output_does_not_modify_ini(self):
        before = self.ini.read_bytes()
        result = self.configure("--fg-output", "unknown")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.ini.read_bytes(), before)

    def test_configurator_rejects_existing_published_package(self):
        self.final.mkdir(parents=True)
        before = self.ini.read_bytes()
        result = self.configure("--fg-output", "fsrfg")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.ini.read_bytes(), before)

    def prepare_metadata(self, *, fg_output=None):
        metadata = dict(schema=1, streamline_sdk="2.14.1", **PINS)
        if fg_output is not None:
            metadata["frame_generation_output"] = fg_output
        (self.package.parent / "probe-inputs.json").write_text(json.dumps(metadata), encoding="utf-8")

    def test_rejects_unknown_metadata_output_before_file_access(self):
        self.prepare_metadata(fg_output="other")
        with self.assertRaisesRegex(ValueError, "Unknown Frame Generation output mode"):
            verify(self.root, self.package, self.final)

    def test_fsrfg_fails_closed_when_provider_is_missing(self):
        self.prepare_metadata(fg_output="fsrfg")
        with self.assertRaisesRegex(ValueError, "Required file missing:.*amd_fidelityfx_vk.dll"):
            verify(self.root, self.package, self.final)

    def test_fsrfg_rejects_provider_hash_mismatch(self):
        self.prepare_metadata(fg_output="fsrfg")
        provider = self.package / "OptiScaler" / "amd_fidelityfx_vk.dll"
        provider.parent.mkdir()
        provider.write_bytes(b"untrusted provider")
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch:.*amd_fidelityfx_vk.dll"):
            verify(self.root, self.package, self.final)

    def test_legacy_metadata_still_selects_dlssg(self):
        self.prepare_metadata()
        with self.assertRaisesRegex(ValueError, "Required file missing:.*OptiScaler_v10"):
            verify(self.root, self.package, self.final)


if __name__ == "__main__":
    unittest.main()
