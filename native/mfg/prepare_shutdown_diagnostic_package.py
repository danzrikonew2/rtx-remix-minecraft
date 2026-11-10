# SPDX-License-Identifier: Apache-2.0
"""Build/verify a disposable r4 OptiScaler shutdown-trace package.

Preserves the pinned original binaries, r3 trace package and r4 build DLL.
Verification covers all four changed sources, nine submodules, dependencies,
the staged DLL and the resulting INI. No GPU frame generation is asserted.
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

from prepare_fsrfg_diagnostic_package import (
    BASE_NAME, PINNED_COMMIT, PINS, TRACED_FILES, git, require,
    sha256, verify_baseline, verify_source, within_build,
)
from prepare_shutdown_trace import INPUT, PROVIDER, R3_CLONE, R4_CLONE, R4_OVERLAY


ROOT = Path(__file__).resolve().parents[2]
NAME = "mfg-fg-fsrfg-shutdown-20261109-r4"
MANIFEST = "shutdown-build-manifest.json"
ALL_TRACED = (*TRACED_FILES, INPUT, PROVIDER)
EXEMPT = {"OptiScaler.dll", "OptiScaler.ini", "OptiScaler.log"}


def verify_r4_source(root: Path) -> dict:
    root = root.resolve()
    r3_source = verify_source(root)
    clone = within_build(root, R4_CLONE)
    overlay = within_build(root, R4_OVERLAY)
    require(clone.is_dir() and overlay.is_dir(), "r4 source checkout or overlay missing")
    data = json.loads((overlay / "shutdown-source-manifest.json").read_text(encoding="utf-8"))
    require(data.get("schema") == 1 and data.get("parent_commit") == PINNED_COMMIT,
            "Unexpected r4 source manifest or commit")
    require(data.get("preserves_r3_fsrfg_instrumentation") is True and
            set(data.get("files", {})) == {INPUT, PROVIDER}, "r4 trace source scope differs")
    require(Path(data["parent_checkout"]).resolve() == R3_CLONE.resolve(),
            "r4 source origin differs")
    require(git(clone, "rev-parse", "HEAD") == PINNED_COMMIT,
            "Compiled checkout differs from pinned commit")
    require(git(clone, "submodule", "status") == git(R3_CLONE, "submodule", "status"),
            "One of nine r4 source submodules differs")
    require(set(git(clone, "diff", "--name-only").splitlines()) == set(ALL_TRACED),
            "Unexpected compiled source modifications")
    hashes = {}
    for relative in TRACED_FILES:
        expected = r3_source["files"][relative]["instrumented_sha256"]
        require(sha256(clone / relative) == expected,
                f"r4 lost verified r3 FSRFG instrumentation: {relative}")
        hashes[relative] = expected
    for relative in (INPUT, PROVIDER):
        meta = data["files"][relative]
        require(sha256(R3_CLONE / relative) == meta["r3_source_sha256"],
                f"r3 source changed: {relative}")
        expected = meta["r4_source_sha256"]
        require(sha256(overlay / relative) == expected and
                sha256(clone / relative) == expected,
                f"r4 shutdown trace changed: {relative}")
        hashes[relative] = expected
    return hashes


def verify_package(root: Path, package: Path, installed: Path | None = None) -> None:
    package = within_build(root, package)
    installed = within_build(root, installed if installed is not None else package)
    require(package.is_dir() and package.name == "Package", "Missing r4 Package")
    require(installed.name == "Package", "Unexpected published package name")
    parent = package.parent
    baseline = within_build(root, root / "build" / BASE_NAME / "Package")
    verify_baseline(root, baseline, baseline)
    hashes = verify_r4_source(root)
    meta = json.loads((parent / MANIFEST).read_text(encoding="utf-8"))
    require(meta.get("schema") == 1 and meta.get("mode") == "isolated-r4-shutdown-trace",
            "Unsupported r4 package manifest")
    require(meta.get("base_package") == BASE_NAME and
            meta.get("clone") == R4_CLONE.name and
            meta.get("overlay") == R4_OVERLAY.name and
            meta.get("pinned_commit") == PINNED_COMMIT,
            "r4 package provenance mismatch")
    require(meta.get("pinned_optiscaler_sha256") == PINS["optiscaler_fork_sha256"],
            "Pinned OptiScaler SHA-256 mismatch")
    require(meta.get("r4_source_manifest_sha256") ==
            sha256(R4_OVERLAY / "shutdown-source-manifest.json"),
            "r4 source manifest altered")
    require(meta.get("source_hashes") == hashes, "Four compiled source hashes differ")
    require(meta.get("dependency_submodules") ==
            git(R4_CLONE, "submodule", "status").splitlines(),
            "Nine submodule revisions differ")
    binary = meta.get("diagnostic_optiscaler_sha256")
    require(isinstance(binary, str) and len(binary) == 64 and
            binary != PINS["optiscaler_fork_sha256"], "Invalid diagnostic DLL hash")
    require(sha256(R4_CLONE / "x64" / "Release" / "OptiScaler.dll") == binary and
            sha256(package / "OptiScaler.dll") == binary, "Diagnostic DLL differs")
    require(sha256(parent / "probe-inputs.json") ==
            sha256(baseline.parent / "probe-inputs.json"), "Probe metadata changed")
    require(sha256(package / "OptiScaler.ini") == meta.get("diagnostic_ini_sha256"),
            "Diagnostic INI SHA-256 changed")
    for original in baseline.rglob("*"):
        if original.is_file():
            rel = original.relative_to(baseline)
            if rel.as_posix() not in EXEMPT:
                require(sha256(original) == sha256(package / rel),
                        f"Pinned dependency modified: {rel}")
    ini = configparser.ConfigParser(interpolation=None)
    ini.optionxform = str
    with (package / "OptiScaler.ini").open(encoding="utf-8-sig") as handle:
        ini.read_file(handle)
    for section, key, expected in (
        ("FrameGen", "Enabled", "true"),
        ("FrameGen", "FGOutput", "fsrfg"),
        ("FrameGen", "FGInput", "upscaler"),
        ("DLSSG", "InterpolationCount", "1"),
        ("Plugins", "Path", str(installed / "OptiScaler" / "plugins")),
        ("Libraries", "OptiDllPath", str(installed / "OptiScaler")),
    ):
        require(ini.get(section, key, fallback=None) == expected,
                f"OptiScaler.ini [{section}] {key} mismatch")
    print(f"PASS: r4 shutdown-trace package verified: {package}")
    print(f"SHA256: {binary}; GPU FG/display/clean shutdown unverified")


def stage(root: Path, destination: Path) -> None:
    destination = within_build(root, destination)
    require(not destination.exists(), "Refusing to overwrite existing diagnostic package")
    baseline = within_build(root, root / "build" / BASE_NAME / "Package")
    verify_baseline(root, baseline, baseline)
    hashes = verify_r4_source(root)
    dll = R4_CLONE / "x64" / "Release" / "OptiScaler.dll"
    require(dll.is_file(), "No compiled r4 diagnostic OptiScaler.dll")
    dll_sha = sha256(dll)
    require(dll_sha != PINS["optiscaler_fork_sha256"], "Diagnostic DLL equals original")
    temporary = Path(tempfile.mkdtemp(prefix=".r4-shutdown-package-", dir=root / "build"))
    try:
        staged = temporary / "Package"
        shutil.copytree(baseline, staged)
        (staged / "OptiScaler.log").unlink(missing_ok=True)
        shutil.copy2(dll, staged / "OptiScaler.dll")
        shutil.copy2(baseline.parent / "probe-inputs.json", temporary / "probe-inputs.json")
        subprocess.run([
            sys.executable, str(root / "native" / "mfg" / "configure_probe_ini.py"),
            "--ini", str(staged / "OptiScaler.ini"),
            "--package", str(staged),
            "--final-package", str(destination / "Package"),
            "--fg-state", "on", "--fg-output", "fsrfg",
        ], check=True)
        meta = {
            "schema": 1, "mode": "isolated-r4-shutdown-trace",
            "base_package": BASE_NAME, "clone": R4_CLONE.name,
            "overlay": R4_OVERLAY.name, "pinned_commit": PINNED_COMMIT,
            "pinned_optiscaler_sha256": PINS["optiscaler_fork_sha256"],
            "diagnostic_optiscaler_sha256": dll_sha,
            "diagnostic_ini_sha256": sha256(staged / "OptiScaler.ini"),
            "r4_source_manifest_sha256": sha256(R4_OVERLAY / "shutdown-source-manifest.json"),
            "source_hashes": hashes,
            "dependency_submodules": git(R4_CLONE, "submodule", "status").splitlines(),
            "status": "compiled; GPU frame content, scanout, latency and clean shutdown unverified",
        }
        (temporary / MANIFEST).write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        # Verify every copied dependency, manifest entry, source pin and INI
        # BEFORE publishing. Its paths refer to the as-yet-uncreated destination.
        verify_package(root, staged, destination / "Package")
        temporary.rename(destination)
        verify_package(root, destination / "Package")
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--probe-name", default=NAME)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if not args.probe_name.startswith("mfg-fg-fsrfg-shutdown-") or not all(
        character.isascii() and (character.isalnum() or character == "-")
        for character in args.probe_name
    ):
        parser.error("Probe name must be mfg-fg-fsrfg-shutdown-* (alphanumeric and hyphen)")
    root = args.repo_root.resolve(strict=True)
    target = root / "build" / args.probe_name
    try:
        if args.verify_only:
            verify_package(root, target / "Package")
        else:
            stage(root, target)
    except (ValueError, FileNotFoundError, OSError, subprocess.CalledProcessError,
            KeyError, json.JSONDecodeError, configparser.Error) as error:
        print(f"FAIL: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
