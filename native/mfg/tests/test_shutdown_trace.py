# SPDX-License-Identifier: Apache-2.0
"""Conservative source and provenance tests for a separate r4 shutdown trace."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prepare_shutdown_trace import INPUT, PROVIDER, R3_CLONE, stage, trace_input, trace_provider  # noqa: E402


@unittest.skipUnless(
    (R3_CLONE / INPUT).is_file() and (R3_CLONE / PROVIDER).is_file(),
    "Retired optional FSR diagnostic clone is absent; source fixture was archived during cleanup",
)
class ShutdownTraceTests(unittest.TestCase):
    def test_all_shutdown_paths_have_balanced_durable_markers(self):
        before = (R3_CLONE / INPUT).read_text(encoding="utf-8-sig").replace("\r\n", "\n")
        patched = trace_input(before)
        for suffix in (
            "shutdown_enter", "shutdown_original_ngx_begin", "shutdown_original_ngx_end",
            "shutdown_fg_begin", "shutdown_fg_end", "shutdown_exit", "shutdown1_enter",
            "shutdown1_original_ngx_begin", "shutdown1_original_ngx_end",
            "shutdown1_fg_begin", "shutdown1_fg_end",
            "shutdown1_delegate_plain_begin", "shutdown1_delegate_plain_end",
        ):
            self.assertEqual(patched.count(f'ShutdownProbeTrace("{suffix}")'), 1, suffix)
        self.assertIn("std::fflush(stderr)", patched)
        self.assertEqual(patched.count("NVNGXProxy::VULKAN_Shutdown()();"), 1)
        self.assertEqual(patched.count("NVNGXProxy::VULKAN_Shutdown1()(InDevice);"), 1)

    def test_provider_wrappers_preserve_original_result(self):
        before = (R3_CLONE / PROVIDER).read_text(encoding="utf-8-sig").replace("\r\n", "\n")
        patched = trace_provider(before)
        self.assertIn("const auto result = provider->VULKAN_Shutdown();", patched)
        self.assertIn("const auto result = provider->VULKAN_Shutdown1(InDevice);", patched)
        self.assertIn("ShutdownProbeTrace(\"provider_shutdown1_call_end\")", patched)
        self.assertIn("return result;", patched)

    def test_overlay_staged_without_modifying_existing_r3(self):
        original = {name: (R3_CLONE / name).read_bytes() for name in (INPUT, PROVIDER)}
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "r4"
            manifest = stage(R3_CLONE, output, verify_r3=False)
            self.assertEqual(manifest["status"], "SOURCE_ONLY_UNBUILT")
            self.assertEqual(json.loads((output / "shutdown-source-manifest.json").read_text()), manifest)
            self.assertNotEqual(manifest["files"][INPUT]["r3_source_sha256"],
                                manifest["files"][INPUT]["r4_source_sha256"])
            for name, content in original.items():
                self.assertEqual((R3_CLONE / name).read_bytes(), content)
            with self.assertRaises(FileExistsError):
                stage(R3_CLONE, output, verify_r3=False)


if __name__ == "__main__":
    unittest.main()
