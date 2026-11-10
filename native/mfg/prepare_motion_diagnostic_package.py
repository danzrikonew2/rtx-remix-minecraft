# SPDX-License-Identifier: Apache-2.0
"""Stage and verify an immutable r6 FSRFG ROI-motion diagnostic package.

The binary adds fixture-specific pixel masks to the existing bounded r5 GPU
readbacks. This evidence cannot establish displayed frames or 2x presentation.
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
from prepare_gpucontent_diagnostic_package import (
    EXEMPT, R5_CLONE, SOURCES, source_evidence as r5_source_evidence,
    verify_package as verify_r5_package,
)
from verify_optiscaler_probe import FSR_VULKAN_PROVIDER_SHA256


R6_CLONE = "optiscaler-fsrfg-motion-build-20261109-r6"
PACKAGE_NAME = "mfg-fg-fsrfg-motion-20261109-r6"
MANIFEST = "motion-build-manifest.json"
MOTION_SOURCE = "OptiScaler/framegen/ffx/FSRFG_Vk.cpp"


def source_evidence(root: Path) -> dict:
    r5 = r5_source_evidence(root)
    clone = within_build(root, root / "build" / R6_CLONE)
    require(git(clone, "rev-parse", "HEAD") == PINNED_COMMIT,
            "r6 source commit differs from pinned upstream")
    changed = set(git(clone, "diff", "--name-only").splitlines())
    require(changed == set(SOURCES), f"Unexpected r6 source changes: {changed}")
    modules = git(clone, "submodule", "status").splitlines()
    require(len(modules) == 9 and all(s.startswith(" ") for s in modules),
            "r6 submodules are incomplete or dirty")
    require(modules == r5["dependency_submodules"],
            "r6 dependency revisions differ from r5")
    hashes = {name: sha256(clone / name) for name in SOURCES}
    for name in SOURCES:
        if name != MOTION_SOURCE:
            require(hashes[name] == r5["source_hashes"][name],
                    f"r6 unexpectedly modified inherited source: {name}")
    require(hashes[MOTION_SOURCE] != r5["source_hashes"][MOTION_SOURCE],
            "r6 motion instrumentation missing")
    require(sha256(clone / "external" / "FidelityFX-SDK" /
                   "PrebuiltSignedDLL" / "amd_fidelityfx_vk.dll") ==
            FSR_VULKAN_PROVIDER_SHA256, "Signed FFX Vulkan provider differs")
    return {
        "source_hashes": hashes, "dependency_submodules": modules,
        "parent_r5_motion_source_sha256": r5["source_hashes"][MOTION_SOURCE],
    }


def verify_package(root: Path, package: Path, installed: Path | None = None) -> None:
    package = within_build(root, package)
    installed = within_build(root, installed if installed is not None else package)
    require(package.is_dir() and package.name == "Package", "Missing r6 Package")
    require(installed.name == "Package", "Expected installed Package destination")
    baseline = within_build(root, root / "build" / BASE_NAME / "Package")
    verify_baseline(root, baseline, baseline)
    parent = root / "build" / "mfg-fg-fsrfg-gpucontent-20261109-r5"
    verify_r5_package(root, parent / "Package")
    evidence = source_evidence(root)
    metadata = json.loads((package.parent / MANIFEST).read_text(encoding="utf-8"))
    require(metadata.get("schema") == 1 and metadata.get("mode") == "isolated-r6-motion",
            "Unexpected r6 diagnostic manifest")
    for key, expected in (
        ("source_clone", R6_CLONE), ("baseline", BASE_NAME),
        ("pinned_commit", PINNED_COMMIT),
        ("pinned_optiscaler_sha256", PINS["optiscaler_fork_sha256"]),
        ("parent_r5_dll_sha256", sha256(parent / "Package" / "OptiScaler.dll")),
        *evidence.items(),
    ):
        require(metadata.get(key) == expected, f"r6 manifest provenance mismatch: {key}")
    dll_hash = metadata.get("diagnostic_optiscaler_sha256")
    require(isinstance(dll_hash, str) and len(dll_hash) == 64 and
            dll_hash != PINS["optiscaler_fork_sha256"], "Invalid r6 DLL hash")
    require(sha256(package / "OptiScaler.dll") == dll_hash and
            sha256(root / "build" / R6_CLONE / "x64" / "Release" / "OptiScaler.dll") == dll_hash,
            "r6 DLL SHA-256 verification failed")
    require(sha256(package / "OptiScaler.ini") == metadata.get("diagnostic_ini_sha256"),
            "r6 diagnostic INI changed")
    require(sha256(package.parent / "probe-inputs.json") ==
            sha256(baseline.parent / "probe-inputs.json"),
            "r6 pinned probe metadata changed")
    for original in baseline.rglob("*"):
        if original.is_file():
            relative = original.relative_to(baseline)
            if relative.as_posix() not in EXEMPT:
                require(sha256(package / relative) == sha256(original),
                        f"r6 dependency changed: {relative}")
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
                f"r6 diagnostic INI mismatch: [{section}] {key}")
    print(f"PASS: immutable r6 motion package verified: {package}")
    print(f"SHA256={dll_hash}; physical scanout and pacing unverified")


def stage(root: Path, destination: Path) -> None:
    destination = within_build(root, destination)
    require(not destination.exists(), "Refusing to overwrite existing r6 package")
    baseline = within_build(root, root / "build" / BASE_NAME / "Package")
    verify_baseline(root, baseline, baseline)
    evidence = source_evidence(root)
    parent = root / "build" / "mfg-fg-fsrfg-gpucontent-20261109-r5"
    verify_r5_package(root, parent / "Package")
    dll = root / "build" / R6_CLONE / "x64" / "Release" / "OptiScaler.dll"
    dll_hash = sha256(dll)
    require(dll_hash not in (PINS["optiscaler_fork_sha256"],
                             sha256(parent / "Package" / "OptiScaler.dll")),
            "r6 compiled artifact is not a distinct diagnostic DLL")
    temp = Path(tempfile.mkdtemp(prefix=".r6-motion-package-", dir=root / "build"))
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
        metadata = {
            "schema": 1, "mode": "isolated-r6-motion", "source_clone": R6_CLONE,
            "baseline": BASE_NAME, "pinned_commit": PINNED_COMMIT,
            "pinned_optiscaler_sha256": PINS["optiscaler_fork_sha256"],
            "parent_r5_dll_sha256": sha256(parent / "Package" / "OptiScaler.dll"),
            "diagnostic_optiscaler_sha256": dll_hash,
            "diagnostic_ini_sha256": sha256(package / "OptiScaler.ini"),
            **evidence,
            "caveat": "Fixture color mask from GPU-completed readback; scanout unverified",
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
    if not args.probe_name.startswith("mfg-fg-fsrfg-motion-") or not all(
        char.isascii() and (char.isalnum() or char == "-") for char in args.probe_name
    ):
        parser.error("Invalid r6 package name")
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
