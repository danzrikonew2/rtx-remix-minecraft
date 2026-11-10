# SPDX-License-Identifier: Apache-2.0
"""Stage/verify an immutable r5 GPU-content diagnostic package.

The package is only an input to an independently verified, disposable NGX
probe copy. No generated GPU content or displayed frames are assumed.
"""

import argparse
import configparser
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from prepare_fsrfg_diagnostic_package import (
    BASE_NAME, PINNED_COMMIT, PINS, git, require, sha256,
    verify_baseline, within_build,
)
from prepare_shutdown_diagnostic_package import R4_CLONE, verify_r4_source
from verify_optiscaler_probe import FSR_VULKAN_PROVIDER_SHA256


R5_CLONE = "optiscaler-fsrfg-gpucontent-build-20261109-r5"
PACKAGE_NAME = "mfg-fg-fsrfg-gpucontent-20261109-r5"
MANIFEST = "gpucontent-build-manifest.json"
SOURCES = (
    "OptiScaler/framegen/ffx/FSRFG_Vk.cpp",
    "OptiScaler/framegen/ffx/FSRFG_Vk.h",
    "OptiScaler/framegen/nvngx/Nvngx_FG.cpp",
    "OptiScaler/hooks/Vulkan_Hooks.cpp",
    "OptiScaler/inputs/NVNGX_DLSS_Vk.cpp",
)
INHERITED = (
    "OptiScaler/framegen/nvngx/Nvngx_FG.cpp",
    "OptiScaler/hooks/Vulkan_Hooks.cpp",
    "OptiScaler/inputs/NVNGX_DLSS_Vk.cpp",
)
EXEMPT = {"OptiScaler.dll", "OptiScaler.ini", "OptiScaler.log"}


def source_evidence(root: Path) -> dict:
    clone = within_build(root, root / "build" / R5_CLONE)
    r4_hashes = verify_r4_source(root)
    require(git(clone, "rev-parse", "HEAD") == PINNED_COMMIT,
            "r5 source commit changed")
    changed = set(git(clone, "diff", "--name-only").splitlines())
    require(changed == set(SOURCES), f"Unexpected r5 source changes: {changed}")
    submodules = git(clone, "submodule", "status").splitlines()
    require(len(submodules) == 9 and all(s.startswith(" ") for s in submodules),
            "Missing or dirty r5 dependency submodules")
    require(submodules == git(R4_CLONE, "submodule", "status").splitlines(),
            "r5 submodules differ from pinned r4")
    hashes = {name: sha256(clone / name) for name in SOURCES}
    for name in INHERITED:
        require(hashes[name] == r4_hashes[name],
                f"Existing r4 instrumentation unexpectedly changed: {name}")
    require(sha256(clone / "external" / "FidelityFX-SDK" /
                   "PrebuiltSignedDLL" / "amd_fidelityfx_vk.dll") ==
            FSR_VULKAN_PROVIDER_SHA256, "FFX Vulkan provider changed")
    return {"source_hashes": hashes, "dependency_submodules": submodules}


def verify_package(root: Path, package: Path, installed: Path | None = None) -> None:
    package = within_build(root, package)
    installed = within_build(root, installed if installed is not None else package)
    require(package.is_dir() and package.name == "Package", "Missing r5 Package")
    require(installed.name == "Package", "Invalid run-package destination")
    baseline = within_build(root, root / "build" / BASE_NAME / "Package")
    verify_baseline(root, baseline, baseline)
    evidence = source_evidence(root)
    meta = json.loads((package.parent / MANIFEST).read_text(encoding="utf-8"))
    require(meta.get("schema") == 1 and meta.get("mode") == "isolated-r5-gpucontent",
            "Unexpected r5 manifest schema")
    require(meta.get("source_clone") == R5_CLONE and
            meta.get("baseline") == BASE_NAME and
            meta.get("pinned_commit") == PINNED_COMMIT and
            meta.get("pinned_optiscaler_sha256") == PINS["optiscaler_fork_sha256"],
            "r5 source / baseline provenance mismatch")
    for key, actual in evidence.items():
        require(meta.get(key) == actual, f"r5 manifest mismatch: {key}")
    dll_hash = meta.get("diagnostic_optiscaler_sha256")
    require(isinstance(dll_hash, str) and len(dll_hash) == 64 and
            dll_hash != PINS["optiscaler_fork_sha256"], "Invalid r5 DLL hash")
    require(sha256(package / "OptiScaler.dll") == dll_hash and
            sha256(root / "build" / R5_CLONE / "x64" / "Release" /
                   "OptiScaler.dll") == dll_hash, "r5 DLL failed SHA-256 verification")
    require(sha256(package / "OptiScaler.ini") == meta.get("diagnostic_ini_sha256"),
            "r5 immutable diagnostic INI was changed")
    require(sha256(package.parent / "probe-inputs.json") ==
            sha256(baseline.parent / "probe-inputs.json"),
            "Pinned native probe inputs changed")
    for original in baseline.rglob("*"):
        if original.is_file():
            relative = original.relative_to(baseline)
            if relative.as_posix() not in EXEMPT:
                require(sha256(original) == sha256(package / relative),
                        f"Pinned dependency changed: {relative}")
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
                f"r5 diagnostic INI mismatch: [{section}] {key}")
    print(f"PASS: immutable r5 GPU-content package verified: {package}")
    print(f"SHA256={dll_hash}; scanout and functioning FG remain unproven")


def stage(root: Path, destination: Path) -> None:
    destination = within_build(root, destination)
    require(not destination.exists(), "Refusing to replace existing r5 package")
    baseline = within_build(root, root / "build" / BASE_NAME / "Package")
    verify_baseline(root, baseline, baseline)
    evidence = source_evidence(root)
    dll = root / "build" / R5_CLONE / "x64" / "Release" / "OptiScaler.dll"
    dll_hash = sha256(dll)
    require(dll_hash != PINS["optiscaler_fork_sha256"],
            "Diagnostic DLL equals pinned baseline")
    temp = Path(tempfile.mkdtemp(prefix=".r5-gpucontent-package-", dir=root / "build"))
    try:
        package = temp / "Package"
        shutil.copytree(baseline, package)
        (package / "OptiScaler.log").unlink(missing_ok=True)
        shutil.copy2(dll, package / "OptiScaler.dll")
        shutil.copy2(baseline.parent / "probe-inputs.json", temp / "probe-inputs.json")
        subprocess.run([
            sys.executable, str(root / "native" / "mfg" / "configure_probe_ini.py"),
            "--ini", str(package / "OptiScaler.ini"),
            "--package", str(package),
            "--final-package", str(destination / "Package"),
            "--fg-state", "on", "--fg-output", "fsrfg",
        ], check=True)
        meta = {
            "schema": 1, "mode": "isolated-r5-gpucontent",
            "source_clone": R5_CLONE, "baseline": BASE_NAME,
            "pinned_commit": PINNED_COMMIT,
            "pinned_optiscaler_sha256": PINS["optiscaler_fork_sha256"],
            "diagnostic_optiscaler_sha256": dll_hash,
            "diagnostic_ini_sha256": sha256(package / "OptiScaler.ini"),
            **evidence,
            "caveat": "Opt-in GPU pixel capture; physical scanout unverified",
        }
        (temp / MANIFEST).write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        verify_package(root, package, destination / "Package")
        temp.rename(destination)
        verify_package(root, destination / "Package")
    finally:
        if temp.exists():
            shutil.rmtree(temp)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--probe-name", default=PACKAGE_NAME)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if not args.probe_name.startswith("mfg-fg-fsrfg-gpucontent-") or not all(
        c.isascii() and (c.isalnum() or c == "-") for c in args.probe_name
    ):
        parser.error("Invalid isolated r5 package name")
    root = args.repo_root.resolve(strict=True)
    target = root / "build" / args.probe_name
    try:
        if args.verify_only:
            verify_package(root, target / "Package")
        else:
            stage(root, target)
    except (OSError, ValueError, KeyError, json.JSONDecodeError,
            configparser.Error, subprocess.CalledProcessError) as exc:
        print(f"FAIL: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
