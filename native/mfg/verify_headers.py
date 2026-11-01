# SPDX-License-Identifier: Apache-2.0
"""Check the upstream SDK source pins; optionally adopt their exact Windows text representation."""

import argparse
import hashlib
import re
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--source", type=Path, required=True)
parser.add_argument("--streamline", type=Path, required=True)
parser.add_argument("--imgui", type=Path, required=True)
parser.add_argument("--normalize-pinned-text", action="store_true")
args = parser.parse_args()
roots = {"StreamlineRoot": args.streamline, "ImGuiRoot": args.imgui}
script = (args.source / "source/native/build.ps1").read_text(encoding="utf-8")
rows = re.findall(
    r"Assert-InputHash \(Join-Path \$(StreamlineRoot|ImGuiRoot) '([^']+)'\) '([A-F0-9]{64})'",
    script,
)
if len(rows) != 36:
    raise SystemExit("Unexpected upstream SDK pin table")
for root, name, expected in rows:
    path = roots[root] / name
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest().upper() != expected:
        windows = raw.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        if (
            not args.normalize_pinned_text
            or hashlib.sha256(windows).hexdigest().upper() != expected
        ):
            raise SystemExit(f"SDK pin mismatch: {root}/{name}")
        path.write_bytes(windows)
print(f"PASS: all {len(rows)} upstream Streamline/ImGui input pins")
