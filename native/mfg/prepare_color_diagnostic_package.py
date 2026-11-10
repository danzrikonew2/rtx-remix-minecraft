# SPDX-License-Identifier: Apache-2.0
"""Stage and verify a unique, immutable r7 color-mask GPU diagnostic package.

Inherits the verified r6 fixture; only the OptiScaler DLL and its absolute-path
INI may change. Diagnostic ROI data does not prove screen presentation.
"""

import argparse
import configparser
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from prepare_fsrfg_diagnostic_package import PINNED_COMMIT, PINS, git, require, sha256, within_build
from prepare_gpucontent_diagnostic_package import EXEMPT, SOURCES
from prepare_motion_diagnostic_package import (
    MOTION_SOURCE, PACKAGE_NAME as R6_PACKAGE, source_evidence as r6_source_evidence,
    verify_package as verify_r6_package,
)
from verify_optiscaler_probe import FSR_VULKAN_PROVIDER_SHA256


R7_CLONE = "optiscaler-fsrfg-color-build-20261109-r7"
PACKAGE_NAME = "mfg-fg-fsrfg-color-20261109-r7"
MANIFEST = "color-build-manifest.json"


def source_evidence(root: Path) -> dict:
    parent = r6_source_evidence(root)
    clone = within_build(root, root / "build" / R7_CLONE)
    require(git(clone, "rev-parse", "HEAD") == PINNED_COMMIT,
            "r7 source commit differs from pinned upstream")
    changed = set(git(clone, "diff", "--name-only").splitlines())
    require(changed == set(SOURCES), f"Unexpected r7 source changes: {changed}")
    modules = git(clone, "submodule", "status").splitlines()
    require(len(modules) == 9 and all(s.startswith(" ") for s in modules)
            and modules == parent["dependency_submodules"],
            "r7 submodules differ from pinned r6")
    hashes = {name: sha256(clone / name) for name in SOURCES}
    for name in SOURCES:
        if name != MOTION_SOURCE:
            require(hashes[name] == parent["source_hashes"][name],
                    f"r7 changed inherited source: {name}")
    require(hashes[MOTION_SOURCE] != parent["source_hashes"][MOTION_SOURCE],
            "r7 color instrumentation missing")
    require(sha256(clone / "external" / "FidelityFX-SDK" /
                   "PrebuiltSignedDLL" / "amd_fidelityfx_vk.dll") ==
            FSR_VULKAN_PROVIDER_SHA256, "Signed Vulkan provider differs")
    return {
        "source_hashes": hashes,
        "dependency_submodules": modules,
        "parent_r6_motion_source_sha256": parent["source_hashes"][MOTION_SOURCE],
    }


def verify_package(root: Path, package: Path, installed: Path | None = None) -> None:
    package = within_build(root, package)
    installed = within_build(root, installed if installed is not None else package)
    require(package.is_dir() and package.name == "Package", "Missing r7 Package")
    require(installed.name == "Package", "Expected final Package directory")
    parent = within_build(root, root / "build" / R6_PACKAGE / "Package")
    verify_r6_package(root, parent)
    metadata = json.loads((package.parent / MANIFEST).read_text(encoding="utf-8"))
    evidence = source_evidence(root)
    require(metadata.get("schema") == 1 and metadata.get("mode") == "isolated-r7-color",
            "Unexpected r7 manifest")
    for key, expected in (
        ("source_clone", R7_CLONE),
        ("pinned_commit", PINNED_COMMIT),
        ("pinned_optiscaler_sha256", PINS["optiscaler_fork_sha256"]),
        ("parent_r6_dll_sha256", sha256(parent / "OptiScaler.dll")),
        ("parent_r6_ini_sha256", sha256(parent / "OptiScaler.ini")),
        *evidence.items(),
    ):
        require(metadata.get(key) == expected, f"r7 manifest provenance mismatch: {key}")
    dll_hash = metadata.get("diagnostic_optiscaler_sha256")
    require(isinstance(dll_hash, str) and len(dll_hash) == 64 and
            dll_hash not in (PINS["optiscaler_fork_sha256"],
                             sha256(parent / "OptiScaler.dll")), "Invalid r7 DLL hash")
    require(sha256(package / "OptiScaler.dll") == dll_hash and
            sha256(root / "build" / R7_CLONE / "x64" / "Release" / "OptiScaler.dll") == dll_hash,
            "r7 DLL SHA-256 verification failed")
    require(sha256(package / "OptiScaler.ini") == metadata.get("diagnostic_ini_sha256"),
            "r7 diagnostic INI changed")
    require(sha256(package.parent / "probe-inputs.json") ==
            sha256(parent.parent / "probe-inputs.json"),
            "r7 probe inputs changed")
    for original in parent.rglob("*"):
        if original.is_file():
            rel = original.relative_to(parent)
            if rel.as_posix() not in EXEMPT:
                require(sha256(package / rel) == sha256(original),
                        f"r7 dependency changed: {rel}")
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str
    with (package / "OptiScaler.ini").open(encoding="utf-8-sig") as stream:
        config.read_file(stream)
    for section, key, expected in (
        ("FrameGen", "Enabled", "true"),
        ("FrameGen", "FGOutput", "fsrfg"),
        ("FrameGen", "FGInput", "upscaler"),
        ("DLSSG", "InterpolationCount", "1"),
        ("Plugins", "Path", str(installed / "OptiScaler" / "plugins")),
        ("Libraries", "OptiDllPath", str(installed / "OptiScaler")),
    ):
        require(config.get(section, key, fallback=None) == expected,
                f"r7 INI mismatch: [{section}] {key}")
    print(f"PASS: immutable r7 color package: {package}")
    print(f"SHA256={dll_hash}; physical scanout and pacing unverified")


def stage(root: Path, destination: Path) -> None:
    destination = within_build(root, destination)
    require(not destination.exists(), "Refusing to overwrite existing r7 package")
    parent = within_build(root, root / "build" / R6_PACKAGE / "Package")
    verify_r6_package(root, parent)
    evidence = source_evidence(root)
    dll = root / "build" / R7_CLONE / "x64" / "Release" / "OptiScaler.dll"
    dll_hash = sha256(dll)
    require(dll_hash not in (PINS["optiscaler_fork_sha256"], sha256(parent / "OptiScaler.dll")),
            "r7 DLL is not distinct")
    temp = Path(tempfile.mkdtemp(prefix=".r7-color-package-", dir=root / "build"))
    try:
        package = temp / "Package"
        shutil.copytree(parent, package)
        (package / "OptiScaler.log").unlink(missing_ok=True)
        shutil.copy2(dll, package / "OptiScaler.dll")
        shutil.copy2(parent.parent / "probe-inputs.json", temp / "probe-inputs.json")
        subprocess.run([
            sys.executable, str(root / "native" / "mfg" / "configure_probe_ini.py"),
            "--ini", str(package / "OptiScaler.ini"),
            "--package", str(package),
            "--final-package", str(destination / "Package"),
            "--fg-state", "on", "--fg-output", "fsrfg",
        ], check=True)
        metadata = {
            "schema": 1, "mode": "isolated-r7-color", "source_clone": R7_CLONE,
            "pinned_commit": PINNED_COMMIT,
            "pinned_optiscaler_sha256": PINS["optiscaler_fork_sha256"],
            "parent_r6_dll_sha256": sha256(parent / "OptiScaler.dll"),
            "parent_r6_ini_sha256": sha256(parent / "OptiScaler.ini"),
            "diagnostic_optiscaler_sha256": dll_hash,
            "diagnostic_ini_sha256": sha256(package / "OptiScaler.ini"),
            **evidence,
            "caveat": "GPU readbacks in fixture only; actual scanout unverified",
        }
        (temp / MANIFEST).write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        verify_package(root, package, destination / "Package")
        temp.rename(destination)
        verify_package(root, destination / "Package")
    finally:
        if temp.exists():
            shutil.rmtree(temp)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--probe-name", default=PACKAGE_NAME)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if not args.probe_name.startswith("mfg-fg-fsrfg-color-") or not all(
        c.isascii() and (c.isalnum() or c == "-") for c in args.probe_name
    ):
        parser.error("Invalid r7 package name")
    root = args.repo_root.resolve(strict=True)
    destination = root / "build" / args.probe_name
    try:
        if args.verify_only:
            verify_package(root, destination / "Package")
        else:
            stage(root, destination)
    except (OSError, ValueError, KeyError, json.JSONDecodeError,
            configparser.Error, subprocess.CalledProcessError) as error:
        print(f"FAIL: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
