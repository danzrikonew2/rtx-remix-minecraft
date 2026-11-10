# SPDX-License-Identifier: Apache-2.0
"""Protect the NVIDIA-only OFF/ON comparison's metadata admission gate."""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "run_fg_comparison.ps1"
POWERSHELL = shutil.which("powershell.exe")


@unittest.skipUnless(POWERSHELL, "Windows PowerShell is required")
class ComparisonPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.metadata = {}
        for mode in ("off", "on"):
            folder = self.root / "build" / mode
            (folder / "Package").mkdir(parents=True)
            self.metadata[mode] = {
                "frame_generation_requested": mode,
                "optiscaler_fork_sha256": "0" * 64,
            }
            self.save(mode)

    def save(self, mode):
        path = self.root / "build" / mode / "probe-inputs.json"
        path.write_text(json.dumps(self.metadata[mode]), encoding="utf-8")

    def preflight(self):
        return subprocess.run(
            [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT),
             "-RepoRoot", str(self.root), "-OffProbeName", "off", "-OnProbeName", "on",
             "-ValidateBaselinesOnly"],
            capture_output=True, text=True, check=False, timeout=30,
        )

    def test_legacy_metadata_defaults_to_nvidia_dlssg(self):
        result = self.preflight()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("both pinned NVIDIA DLSSG", result.stdout)
        self.assertEqual(sorted(p.name for p in (self.root / "build").iterdir()), ["off", "on"])

    def test_explicit_dlssg_is_admitted(self):
        for mode in ("off", "on"):
            self.metadata[mode]["frame_generation_output"] = "dlssg"
            self.save(mode)
        result = self.preflight()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_fsrfg_is_rejected_in_either_baseline(self):
        for mode in ("off", "on"):
            with self.subTest(mode=mode):
                self.metadata[mode]["frame_generation_output"] = "fsrfg"
                self.save(mode)
                result = self.preflight()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("not a verified NVIDIA FG", result.stdout + result.stderr)
                del self.metadata[mode]["frame_generation_output"]
                self.save(mode)

    def test_missing_explicit_output_does_not_succeed(self):
        self.metadata["on"]["frame_generation_output"] = None
        self.save("on")
        result = self.preflight()
        self.assertNotEqual(result.returncode, 0)

    def test_mode_mismatch_is_rejected_before_test_launch(self):
        self.metadata["on"]["frame_generation_requested"] = "off"
        self.save("on")
        result = self.preflight()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not a verified NVIDIA FG", result.stdout + result.stderr)

    def test_bad_hash_is_rejected(self):
        self.metadata["off"]["optiscaler_fork_sha256"] = "bad"
        self.save("off")
        result = self.preflight()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid pinned OptiScaler hash", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
