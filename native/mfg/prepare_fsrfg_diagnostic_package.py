# SPDX-License-Identifier: Apache-2.0
"""Stage or verify an isolated, traced OptiScaler FSRFG Vulkan probe package.

All original pinned binaries remain intact. The only executable replacement is
OptiScaler.dll inside a new, disposable Package. Neither a build nor log event
constitutes GPU-completed frame generation or physical scanout evidence.
"""

import argparse
import configparser
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from verify_optiscaler_probe import PINS, require, sha256, verify as verify_baseline


PINNED_COMMIT = "aeb1f29783106b96c89ba71ce9b6db80eacdae46"
BASE_NAME = "mfg-fg-fsrfg-20261109-isolated"
CLONE_NAME = "optiscaler-fsrfg-trace-build-20261109"
OVERLAY_NAME = "optiscaler-fsrfg-trace-source-20261109-r3"
DEFAULT_NAME = "mfg-fg-fsrfg-trace-20261109-r3"
TRACED_FILES = (
    "OptiScaler/framegen/ffx/FSRFG_Vk.cpp",
    "OptiScaler/hooks/Vulkan_Hooks.cpp",
)
DIAGNOSTIC_FILE = "trace-build-manifest.json"
PROVENANCE_EXEMPT = {"OptiScaler.dll", "OptiScaler.ini", "OptiScaler.log"}


def git(path: Path, *args: str) -> str:
    # A one-process trust exception handles the different ownership of the
    # isolated sandbox clone; no persistent Git configuration is changed.
    return subprocess.run(
        ["git", "-c", f"safe.directory={path}", "-C", str(path), *args],
        check=True, capture_output=True, text=True, encoding="utf-8",
    ).stdout.rstrip("\r\n")


def within_build(root: Path, path: Path) -> Path:
    path = path.resolve()
    require(path.is_relative_to((root / "build").resolve()),
            f"Path must remain inside ignored build directory: {path}")
    return path


def verify_source(root: Path) -> dict:
    build = root / "build"
    clone = within_build(root, build / CLONE_NAME)
    overlay = within_build(root, build / OVERLAY_NAME)
    require(clone.is_dir() and overlay.is_dir(), "Missing disposable source clone or r3 overlay")
    require(git(clone, "rev-parse", "HEAD") == PINNED_COMMIT, "Diagnostic clone commit differs")
    changed = set(git(clone, "diff", "--name-only").splitlines())
    require(changed == set(TRACED_FILES), f"Unexpected modified clone source: {changed}")

    manifest = json.loads((overlay / "trace-source-manifest.json").read_text(encoding="utf-8"))
    require(manifest["pinned_commit"] == PINNED_COMMIT, "Overlay commit differs")
    expected_modules = {
        line.strip().lstrip("-").split(" ", 1)[0]: line.strip().split(" ", 1)[1]
        for line in manifest["missing_submodules"]
    }
    actual_modules = {}
    for line in git(clone, "submodule", "status").splitlines():
        require(line.startswith(" "), f"Submodule missing or at wrong revision: {line}")
        bits = line.strip().split()
        actual_modules[bits[0]] = bits[1]
    require(actual_modules == expected_modules, "Pinned diagnostic submodule revisions differ")

    pinned = within_build(root, build / "optiscaler-source-pinned")
    require(git(pinned, "rev-parse", "HEAD") == PINNED_COMMIT, "Baseline source commit differs")
    require(not git(pinned, "status", "--porcelain"), "Baseline pinned source was modified")
    for relative in TRACED_FILES:
        meta = manifest["files"][relative]
        require(sha256(pinned / relative) == meta["pinned_source_sha256"],
                f"Pinned source hash changed: {relative}")
        require(sha256(overlay / relative) == meta["instrumented_sha256"],
                f"Trace overlay hash changed: {relative}")
        require(sha256(clone / relative) == meta["instrumented_sha256"],
                f"Compiled clone source differs from trace manifest: {relative}")
    return manifest


def verify_trace_package(root: Path, package: Path, installed: Path) -> None:
    package, installed = within_build(root, package), within_build(root, installed)
    require(package.is_dir() and package.name == "Package", "Expected disposable Package")
    require(installed.name == "Package", "Published destination must be named Package")
    build = root / "build"
    baseline = within_build(root, build / BASE_NAME / "Package")
    verify_baseline(root, baseline, baseline)
    source_manifest = verify_source(root)
    manifest_file = package.parent / DIAGNOSTIC_FILE
    require(manifest_file.is_file(), f"Missing diagnostic build manifest: {manifest_file}")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    require(manifest.get("schema") == 1 and manifest.get("mode") == "disposable-traced-fsrfg",
            "Unsupported diagnostic package manifest")
    require(manifest.get("base_package") == BASE_NAME and manifest.get("clone") == CLONE_NAME,
            "Diagnostic provenance differs")
    require(manifest.get("overlay") == OVERLAY_NAME and manifest.get("pinned_commit") == PINNED_COMMIT,
            "Diagnostic source provenance differs")
    require(manifest.get("pinned_optiscaler_sha256") == PINS["optiscaler_fork_sha256"],
            "Pinned original DLL hash differs")
    require(manifest.get("trace_source_manifest_sha256") ==
            sha256(build / OVERLAY_NAME / "trace-source-manifest.json"),
            "Trace overlay manifest hash differs")
    require(manifest.get("trace_source_hashes") == {
        relative: source_manifest["files"][relative]["instrumented_sha256"]
        for relative in TRACED_FILES
    }, "Compiled source file hash manifest differs")
    binary_hash = manifest.get("diagnostic_optiscaler_sha256")
    require(isinstance(binary_hash, str) and len(binary_hash) == 64 and
            binary_hash != PINS["optiscaler_fork_sha256"], "Invalid diagnostic DLL hash")
    require(sha256(build / CLONE_NAME / "x64" / "Release" / "OptiScaler.dll") == binary_hash,
            "Original diagnostic build artifact changed")
    require(sha256(package / "OptiScaler.dll") == binary_hash,
            "Staged diagnostic OptiScaler DLL differs")
    require(sha256(package.parent / "probe-inputs.json") ==
            sha256(baseline.parent / "probe-inputs.json"), "Pinned baseline metadata changed")

    for original in baseline.rglob("*"):
        if not original.is_file():
            continue
        relative = original.relative_to(baseline)
        if relative.as_posix() in PROVENANCE_EXEMPT:
            continue
        require(sha256(original) == sha256(package / relative),
                f"Copied pinned dependency differs: {relative}")
    ini = configparser.ConfigParser(interpolation=None)
    ini.optionxform = str
    with (package / "OptiScaler.ini").open(encoding="utf-8-sig") as handle:
        ini.read_file(handle)
    settings = {
        ("FrameGen", "Enabled"): "true",
        ("FrameGen", "FGOutput"): "fsrfg",
        ("FrameGen", "FGInput"): "upscaler",
        ("DLSSG", "InterpolationCount"): "1",
        ("Plugins", "Path"): str(installed / "OptiScaler" / "plugins"),
        ("Libraries", "OptiDllPath"): str(installed / "OptiScaler"),
    }
    for (section, key), expected in settings.items():
        require(ini.get(section, key, fallback=None) == expected,
                f"Diagnostic INI differs: [{section}] {key}")
    print(f"PASS: diagnostic OptiScaler package verified: {package}")
    print(f"Diagnostic DLL SHA256={binary_hash} (GPU generated content and scanout unverified)")


def stage(root: Path, destination: Path) -> None:
    destination = within_build(root, destination)
    require(not destination.exists(), "Refusing to replace an existing diagnostic package")
    build = root / "build"
    baseline = within_build(root, build / BASE_NAME / "Package")
    verify_baseline(root, baseline, baseline)
    source_manifest = verify_source(root)
    dll = build / CLONE_NAME / "x64" / "Release" / "OptiScaler.dll"
    require(dll.is_file(), f"Missing newly built trace DLL: {dll}")
    clone_sha = sha256(dll)
    require(clone_sha != PINS["optiscaler_fork_sha256"], "Diagnostic DLL equals original pinned DLL")
    temporary = Path(tempfile.mkdtemp(prefix="mfg-fsrfg-trace-staging-", dir=build))
    try:
        staged_package = temporary / "Package"
        shutil.copytree(baseline, staged_package)
        (staged_package / "OptiScaler.log").unlink(missing_ok=True)
        shutil.copy2(dll, staged_package / "OptiScaler.dll")
        shutil.copy2(baseline.parent / "probe-inputs.json", temporary / "probe-inputs.json")
        subprocess.run([
            sys.executable, str(root / "native" / "mfg" / "configure_probe_ini.py"),
            "--ini", str(staged_package / "OptiScaler.ini"),
            "--package", str(staged_package),
            "--final-package", str(destination / "Package"),
            "--fg-state", "on", "--fg-output", "fsrfg",
        ], check=True)
        meta = {
            "schema": 1,
            "mode": "disposable-traced-fsrfg",
            "base_package": BASE_NAME,
            "clone": CLONE_NAME,
            "overlay": OVERLAY_NAME,
            "pinned_commit": PINNED_COMMIT,
            "pinned_optiscaler_sha256": PINS["optiscaler_fork_sha256"],
            "diagnostic_optiscaler_sha256": clone_sha,
            "trace_source_manifest_sha256": sha256(build / OVERLAY_NAME / "trace-source-manifest.json"),
            "trace_source_hashes": {
                relative: source_manifest["files"][relative]["instrumented_sha256"]
                for relative in TRACED_FILES
            },
            "status": "compiled and staged; GPU-completed generated content, scanout, latency, and clean shutdown UNVERIFIED",
        }
        (temporary / DIAGNOSTIC_FILE).write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        verify_trace_package(root, staged_package, destination / "Package")
        temporary.rename(destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    verify_trace_package(root, destination / "Package", destination / "Package")
    print(f"PASS: new isolated trace package published at {destination}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--probe-name", default=DEFAULT_NAME)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if not args.probe_name.startswith("mfg-fg-fsrfg-trace-") or not all(
        char.isascii() and (char.isalnum() or char == "-") for char in args.probe_name
    ):
        parser.error("Diagnostic probe name must be mfg-fg-fsrfg-trace-* (letters/numbers/hyphens)")
    root = args.repo_root.resolve(strict=True)
    target = root / "build" / args.probe_name
    try:
        if args.verify_only:
            verify_trace_package(root, target / "Package", target / "Package")
        else:
            stage(root, target)
    except (ValueError, FileNotFoundError, OSError, subprocess.CalledProcessError,
            KeyError, json.JSONDecodeError, configparser.Error) as error:
        print(f"FAIL: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
