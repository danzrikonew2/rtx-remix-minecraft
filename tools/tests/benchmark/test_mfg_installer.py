# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import os
import subprocess

import pytest

from rtx_tools.benchmark import util

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows addon installer")
HELPER = util.PROJECT_DIR / "packaging" / "mfg-unlocker.ps1"


def run_helper(game, mode):
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(HELPER),
            "-GameDir",
            str(game),
            "-Mode",
            mode,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        env={key: value for key, value in os.environ.items() if key.upper() != "PSMODULEPATH"},
    )


def test_disable_preserves_payload_and_unrelated_runtime(tmp_path):
    addon = tmp_path / "rtx-remix-addons" / "mfg-unlocker"
    addon.mkdir(parents=True)
    (addon / "enabled.txt").write_text("1.7.0")
    (addon / "MFGUnlocker.dll").write_bytes(b"payload sentinel")
    (tmp_path / "d3d9.dll").write_bytes(b"runtime sentinel")
    result = run_helper(tmp_path, "Disable")
    assert result.returncode == 0, result.stderr
    assert not (addon / "enabled.txt").exists()
    assert (addon / "MFGUnlocker.dll").read_bytes() == b"payload sentinel"
    assert (tmp_path / "d3d9.dll").read_bytes() == b"runtime sentinel"


def test_unknown_dll_is_rejected_before_java_copy_or_download(tmp_path):
    addon = tmp_path / "rtx-remix-addons" / "mfg-unlocker"
    addon.mkdir(parents=True)
    (addon / "MFGUnlocker.dll").write_bytes(b"unrecognized payload")
    result = run_helper(tmp_path, "Install")
    assert result.returncode != 0
    assert "unrecognized addon DLL" in result.stderr
    assert (addon / "MFGUnlocker.dll").read_bytes() == b"unrecognized payload"
    assert not (addon / "java").exists()
    assert not (addon / "enabled.txt").exists()


def test_menu_reset_backs_up_ui_and_preserves_rendering_settings(tmp_path):
    addon = tmp_path / "rtx-remix-addons" / "mfg-unlocker"
    runtime_bin = addon / "java" / "bin"
    runtime_bin.mkdir(parents=True)
    (runtime_bin / "javaw.exe").write_bytes(b"runtime sentinel")
    ui = runtime_bin / "RTXMFG-UI.ini"
    old_ui = "[Overlay]\nToggleKey=123\n"
    ui.write_text(old_ui)
    config = runtime_bin / "RTXMFG-Universal.json"
    config.write_text('{"mode":"follow"}')
    result = run_helper(tmp_path, "ResetMenu")
    assert result.returncode == 0, result.stderr
    assert "ToggleKey=8" in ui.read_text()
    backups = list(runtime_bin.glob("RTXMFG-UI.ini.*.bak"))
    assert len(backups) == 1
    assert backups[0].read_text() == old_ui
    assert config.read_text() == '{"mode":"follow"}'
    assert (runtime_bin / "javaw.exe").read_bytes() == b"runtime sentinel"
