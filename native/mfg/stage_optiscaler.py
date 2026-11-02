# SPDX-License-Identifier: Apache-2.0
"""Stage a local adapter candidate without changing Prism settings or launching Minecraft."""

import argparse
import configparser
import hashlib
import shutil
from pathlib import Path


def digest(path):
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            checksum.update(chunk)
    return checksum.hexdigest()


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--package", type=Path, required=True)
parser.add_argument("--candidate", type=Path, required=True)
parser.add_argument("--candidate-sha256", required=True)
parser.add_argument("--addon", type=Path, required=True)
args = parser.parse_args()
package = args.package.resolve(strict=True)
candidate = args.candidate.resolve(strict=True)
addon = args.addon.resolve(strict=True)
if (
    digest(package / "OptiScaler.dll")
    != "0b70d723f61fcf1cc38c26e4033666bd08936f435a848f624222c77dc86ca7fe"
):
    raise SystemExit("Unrecognized OptiScaler adapter")
if digest(candidate) != args.candidate_sha256:
    raise SystemExit("MFG candidate checksum mismatch")
if (
    not (addon / "java/bin/javaw.exe").is_file()
    or not (addon / "enabled.txt").is_file()
):
    raise SystemExit("Install the isolated experimental addon first")
destination = addon / "optiscaler-development"
if destination.exists():
    raise SystemExit(
        "Preserving existing adapter directory; stage into a new addon installation"
    )
for required in (
    "OptiScaler.ini",
    "OptiScaler/nvngx_dlssnr.dll",
    "OptiScaler/streamline/sl.interposer.dll",
    "Licenses",
):
    if not (package / required).exists():
        raise SystemExit(f"Missing input: {required}")
for notice in ("LICENSE", "SOURCE.txt"):
    if not (package.parent / notice).is_file():
        raise SystemExit(f"Keep the OptiScaler {notice} beside the extracted package")
destination.mkdir()
shutil.copy2(package / "OptiScaler.dll", destination / "OptiScaler.dll")
shutil.copytree(package / "OptiScaler", destination / "OptiScaler")
shutil.copytree(package / "Licenses", destination / "Licenses")
shutil.copy2(
    package.parent / "LICENSE", destination / "Licenses/OptiScaler-LICENSE.txt"
)
shutil.copy2(
    package.parent / "SOURCE.txt", destination / "Licenses/OptiScaler-SOURCE.txt"
)
shutil.copy2(
    Path(__file__).with_name("LICENSE-MFG"), destination / "Licenses/MFG-LICENSE.txt"
)
shutil.copy2(candidate, destination / "OptiScaler/plugins/MFGUnlocker.asi")
# MFG's provider lookup checks beside its own module. Keep the unchanged NVIDIA
# provider beside the ASI as well as in OptiScaler's library directories.
shutil.copy2(
    package / "OptiScaler/nvngx_dlssnr.dll",
    destination / "OptiScaler/plugins/nvngx_dlssnr.dll",
)
config = configparser.ConfigParser(interpolation=None)
config.optionxform = str
config.read(package / "OptiScaler.ini", encoding="utf-8")
config["Libraries"]["OptiDllPath"] = str(destination / "OptiScaler")
config["Plugins"]["Path"] = str(destination / "OptiScaler/plugins")
config["Menu"]["OverlayMenu"] = "true"
config["Menu"]["ShortcutKey"] = "45"  # VK_INSERT; preserve explicit user choices on later launches.
config["Menu"]["FGShortcutKey"] = "35"  # VK_END; independent of Remix's native FG checkbox.
with (destination / "OptiScaler.ini").open("w", encoding="utf-8") as stream:
    config.write(stream)
libraries = sorted(
    path for path in destination.rglob("*") if path.suffix.lower() in (".dll", ".asi")
)
manifest = destination / "payload.sha256"
manifest.write_text(
    "".join(
        f"{digest(path)}  {path.relative_to(destination).as_posix()}\n"
        for path in libraries
    ),
    encoding="utf-8",
)
print(
    f"Staged {len(libraries)} pinned native files; Prism settings and shared Java unchanged"
)
print(f"-Drtxremix.mfgDevelopmentDllSha256={digest(candidate)}")
print(f"-Drtxremix.mfgOptiScalerManifestSha256={digest(manifest)}")
