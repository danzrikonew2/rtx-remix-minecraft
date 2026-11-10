# SPDX-License-Identifier: Apache-2.0
"""Configure an isolated OptiScaler native probe, never the user's game INI."""

import argparse
import configparser
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--ini", type=Path, required=True)
parser.add_argument("--package", type=Path, required=True)
parser.add_argument("--final-package", type=Path, required=True)
parser.add_argument("--fg-state", choices=("on", "off"), default="on")
parser.add_argument("--fg-output", choices=("dlssg", "fsrfg"), default="dlssg")
args = parser.parse_args()
ini = args.ini.resolve(strict=True)
package = args.package.resolve(strict=True)
final_package = args.final_package.resolve(strict=False)
if ini.parent != package:
    raise SystemExit("Refusing to edit an INI outside the isolated package directory")
if package.name != "Package" or final_package.name != "Package":
    raise SystemExit("Both staging and final package directories must end in Package")
if final_package == package:
    raise SystemExit("A staging package must be published to a different directory")
if final_package.exists():
    raise SystemExit("Refusing to configure paths to an existing published package")

config = configparser.ConfigParser(interpolation=None)
config.optionxform = str
with ini.open("r", encoding="utf-8-sig") as stream:
    config.read_file(stream)

required = {
    "Upscalers": {"VulkanUpscaler": "dlss"},
    "FrameGen": {
        "Enabled": "true" if args.fg_state == "on" else "false",
        "FGInput": "upscaler",
        "FGOutput": args.fg_output,
        "FGNvngxReplacement": "None",
    },
    "DLSSG": {"InterpolationCount": "1"},
    "Menu": {
        "OverlayMenu": "true",
        "DisableSplash": "true",
        "ShortcutKey": "45",
        "FGShortcutKey": "35",
    },
    "Plugins": {
        "LoadAsiPlugins": "true",
        "Path": str(final_package / "OptiScaler" / "plugins"),
    },
    "Libraries": {"OptiDllPath": str(final_package / "OptiScaler")},
    "Log": {"LogToFile": "true", "LogLevel": "1"},
}
for section, properties in required.items():
    if not config.has_section(section):
        config.add_section(section)
    for key, value in properties.items():
        config.set(section, key, value)

# Only a newly extracted, temporary copy is modified. Use atomic replacement
# so a failed write cannot leave a truncated configuration file.
temporary = ini.with_name(ini.name + ".staging")
if temporary.exists():
    raise SystemExit(f"Refusing to overwrite existing temporary INI: {temporary}")
try:
    with temporary.open("x", encoding="utf-8", newline="\n") as stream:
        config.write(stream)
    temporary.replace(ini)
finally:
    temporary.unlink(missing_ok=True)

print(f"PASS: isolated OptiScaler probe INI configured: {ini}")
print(f"Probe FG {args.fg_state.upper()} output={args.fg_output} configured; displayed FG is unverified.")
