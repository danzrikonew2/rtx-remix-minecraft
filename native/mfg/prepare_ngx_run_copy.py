# SPDX-License-Identifier: Apache-2.0
"""Verify a pinned OptiScaler package, then clone it for ONE disposable NGX run.

OptiScaler can rewrite its INI and its log during teardown. Running directly
from a signed diagnostic Package invalidates its INI manifest and destroys the
previous run's log. The run copy has fresh, absolute dependency paths and
never alters the verified original package or its diagnostic manifest.
"""

import argparse
import configparser
import hashlib
import shutil
import tempfile
from pathlib import Path

from prepare_fsrfg_diagnostic_package import verify_trace_package
from prepare_shutdown_diagnostic_package import verify_package as verify_shutdown_package
from prepare_gpucontent_diagnostic_package import verify_package as verify_gpucontent_package
from prepare_motion_diagnostic_package import verify_package as verify_motion_package
from prepare_color_diagnostic_package import verify_package as verify_color_package
from verify_optiscaler_probe import verify as verify_baseline_package


def checksum(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def within_build(root: Path, path: Path) -> Path:
    root = root.resolve(strict=True)
    path = path.resolve()
    build = (root / "build").resolve(strict=True)
    if not path.is_relative_to(build):
        raise ValueError(f"Refusing package outside this repository's build directory: {path}")
    return path


def verify_original(root: Path, package: Path) -> None:
    parent = package.parent
    if (parent / "color-build-manifest.json").is_file():
        verify_color_package(root, package)
    elif (parent / "motion-build-manifest.json").is_file():
        verify_motion_package(root, package)
    elif (parent / "gpucontent-build-manifest.json").is_file():
        verify_gpucontent_package(root, package)
    elif (parent / "shutdown-build-manifest.json").is_file():
        verify_shutdown_package(root, package)
    elif (parent / "trace-build-manifest.json").is_file():
        verify_trace_package(root, package, package)
    else:
        verify_baseline_package(root, package, package)


def rewrite_paths(staged: Path, destination: Path) -> None:
    ini = staged / "OptiScaler.ini"
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str
    with ini.open(encoding="utf-8-sig") as stream:
        config.read_file(stream)
    for section, key, path in (
        ("Plugins", "Path", destination / "OptiScaler" / "plugins"),
        ("Libraries", "OptiDllPath", destination / "OptiScaler"),
    ):
        if not config.has_section(section):
            raise ValueError(f"Pinned package missing [{section}] section")
        config.set(section, key, str(path))
    temporary = ini.with_suffix(".ini.tmp")
    with temporary.open("x", encoding="utf-8", newline="\n") as stream:
        config.write(stream)
    temporary.replace(ini)


def snapshot(root: Path, source: Path, destination: Path, dll_hash: str,
             *, verify_source: bool = True) -> Path:
    source = within_build(root, source)
    destination = within_build(root, destination)
    if source.name != "Package" or destination.name != "Package":
        raise ValueError("Source and run destination must end with Package")
    if source == destination or destination.is_relative_to(source):
        raise ValueError("Source package cannot be its own run destination")
    if not source.is_dir() or destination.exists() or destination.parent.exists():
        raise ValueError("Run source missing or output already exists; refusing overwrite")
    expected = dll_hash.strip().lower()
    if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise ValueError("Expected DLL SHA-256 must be 64 hex characters")
    if verify_source:
        verify_original(root, source)
    binary = source / "OptiScaler.dll"
    if checksum(binary) != expected:
        raise ValueError("Source DLL SHA-256 does not match the requested run")
    original_ini_hash = checksum(source / "OptiScaler.ini")
    # Stage under the destination's parent folder. Do not publish a partially
    # copied package when disk space or configuration verification fails.
    temp = Path(tempfile.mkdtemp(prefix=".ngx-run-copy-", dir=destination.parent.parent))
    try:
        staged = temp / "Package"
        shutil.copytree(source, staged)
        (staged / "OptiScaler.log").unlink(missing_ok=True)
        rewrite_paths(staged, destination)
        # A baseline probe's manifest and license/source sidecars belong to its
        # package directory. Carry them into the isolated run so the normal
        # verifier can validate the new absolute INI paths before launch.
        if (source.parent / "probe-inputs.json").is_file():
            for name in ("probe-inputs.json", "LICENSE", "SOURCE.txt"):
                original = source.parent / name
                if not original.is_file():
                    raise ValueError(f"Verified baseline sidecar missing: {original}")
                cloned = temp / name
                shutil.copy2(original, cloned)
                if checksum(original) != checksum(cloned):
                    raise ValueError(f"Baseline sidecar was modified during copy: {name}")
        for file in source.rglob("*"):
            if not file.is_file() or file.name in {"OptiScaler.ini", "OptiScaler.log"}:
                continue
            rel = file.relative_to(source)
            if checksum(file) != checksum(staged / rel):
                raise ValueError(f"Run copy changed pinned input: {rel}")
        if checksum(staged / "OptiScaler.dll") != expected:
            raise ValueError("Run copy DLL changed")
        if checksum(source / "OptiScaler.ini") != original_ini_hash:
            raise ValueError("Source INI was modified concurrently")
        if destination.parent.exists():
            raise FileExistsError(f"Run directory appeared during staging: {destination.parent}")
        temp.rename(destination.parent)
    finally:
        if temp.exists():
            shutil.rmtree(temp)
    if checksum(destination / "OptiScaler.dll") != expected:
        raise ValueError("Published run copy failed DLL SHA-256 validation")
    print(f"PASS: isolated NGX run copy: {destination}")
    print(f"Pinned source DLL SHA-256={expected}; source package was not changed")
    return destination / "OptiScaler.dll"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--source-package", type=Path, required=True)
    parser.add_argument("--run-package", type=Path, required=True)
    parser.add_argument("--expected-dll-sha256", required=True)
    args = parser.parse_args()
    try:
        snapshot(args.repo_root, args.source_package, args.run_package,
                 args.expected_dll_sha256)
    except (OSError, ValueError, KeyError, configparser.Error) as error:
        print(f"FAIL: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
