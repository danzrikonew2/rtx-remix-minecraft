# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import argparse
import json

from rtx_tools.profiler import jfr_summary


def test_os_memory_is_not_reported_as_process_rss(monkeypatch, capsys):
    monkeypatch.setattr(jfr_summary, "jfr_summary_text", lambda _: "")
    monkeypatch.setattr(jfr_summary, "parse_summary_meta", lambda _: {})
    monkeypatch.setattr(jfr_summary, "parse_summary_events", lambda _: [("jdk.PhysicalMemory", 1, 1)])
    monkeypatch.setattr(
        jfr_summary,
        "jfr_events",
        lambda _, types: (
            [{"values": {"totalSize": 64000, "usedSize": 30000}}] if types == ["jdk.PhysicalMemory"] else []
        ),
    )
    jfr_summary.run(argparse.Namespace(jfr_file="capture.jfr", json=True, threads=False))
    result = json.loads(capsys.readouterr().out)
    assert result["system_memory"] == {"total": 64000, "used_last": 30000}
    assert "rss" not in result
