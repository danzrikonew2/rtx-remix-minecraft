# SPDX-License-Identifier: Apache-2.0
"""Read-only checks for a staged or published, pinned MFG OptiScaler probe."""

import argparse
import configparser
import hashlib
import json
import re
from pathlib import Path

PINS = {
    "nightly_archive_sha256": "74f20189e0ec76288c86d69057b3feb4750f4680118a9852fb743b343274ac1d",
    "optiscaler_fork_sha256": "0b70d723f61fcf1cc38c26e4033666bd08936f435a848f624222c77dc86ca7fe",
    "mfg_candidate_sha256": "017a80c6e82bf275eb6ef6c852a4cc8fb38c933647f6546b1fc231f8c87409cd",
    "remix_runtime_sha256": "a8365272734cf5541e3600aeacb445c0fd102187dc3a167495a56809ce5891d9",
}
FSR_VULKAN_PROVIDER_SHA256 = "a1624cc4238fef046f30c4d80ce3f47be63fc5f5373f49e3ee9edb9960f54c78"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256(path: Path) -> str:
    require(path.is_file(), f"Required file missing: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def same_bytes(left: Path, right: Path) -> None:
    require(sha256(left) == sha256(right), f"Content mismatch: {left} != {right}")


def pinned_file(path: Path, expected: str) -> None:
    actual = sha256(path)
    require(actual == expected, f"SHA-256 mismatch: {path} expected {expected}, got {actual}")


def verify(root: Path, package: Path, installed: Path) -> None:
    require(package.is_dir() and package.name == "Package", f"Not a probe package: {package}")
    require(installed.name == "Package", f"Invalid published package path: {installed}")
    metadata_path = package.parent / "probe-inputs.json"
    require(metadata_path.is_file(), f"Missing probe metadata: {metadata_path}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
    require(metadata.get("schema") == 1, "Unknown probe metadata schema")
    require(metadata.get("streamline_sdk") == "2.14.1", "Unexpected Streamline version")
    fg_state = metadata.get("frame_generation_requested", "on")
    require(fg_state in ("on", "off"), "Unknown Frame Generation baseline mode")
    fg_output = metadata.get("frame_generation_output", "dlssg")
    require(fg_output in ("dlssg", "fsrfg"), "Unknown Frame Generation output mode")
    if fg_output == "fsrfg":
        pinned_file(package / "OptiScaler" / "amd_fidelityfx_vk.dll", FSR_VULKAN_PROVIDER_SHA256)
    for name, expected in PINS.items():
        require(metadata.get(name) == expected, f"Probe metadata pin mismatch: {name}")

    downloads = root / "build" / "mfg-downloads"
    pinned_file(downloads / "OptiScaler_v10.0.0-pre1_20261024.7z", PINS["nightly_archive_sha256"])
    pinned_file(root / "remix-runtime" / "win64" / "d3d9.dll", PINS["remix_runtime_sha256"])
    pinned_file(package / "OptiScaler.dll", PINS["optiscaler_fork_sha256"])
    pinned_file(package / "OptiScaler" / "plugins" / "MFGUnlocker.asi", PINS["mfg_candidate_sha256"])
    same_bytes(downloads / "MFG-OptiScaler-v1.7.0.dll", package / "OptiScaler.dll")
    same_bytes(root / "build" / "mfg-native" / "Release" / "MFGUnlocker.dll",
               package / "OptiScaler" / "plugins" / "MFGUnlocker.asi")

    native_dir = metadata.get("native_probe_dir", "build/mfg-profile-checks/Release")
    require(isinstance(native_dir, str) and bool(re.fullmatch(
        r"build[/\\][A-Za-z0-9_-]+(?:[/\\](?:Release|Debug))?", native_dir)),
        f"Invalid native probe build directory: {native_dir!r}")
    native_root = (root / native_dir).resolve()
    require(native_root.is_relative_to((root / "build").resolve()),
            "Native probe build directory is outside isolated build outputs")
    probe_hashes = metadata.get("native_probe_sha256")
    bundled_probe_names = {"OptiRemixProbe.exe", "MfgJavaHostProbe.dll"}
    observer_probe_name = "MfgDisplayFrameObserver.exe"
    if "native_probe_dir" in metadata:
        require(isinstance(probe_hashes, dict), "Missing native probe source hashes")
        expected_probe_names = bundled_probe_names | ({observer_probe_name} if "frame_generation_requested" in metadata else set())
        require(set(probe_hashes) == expected_probe_names,
                "Unexpected native probe source hash manifest")
    for filename in sorted(probe_hashes if probe_hashes is not None else bundled_probe_names):
        source = native_root / filename
        bundled = package / filename
        same_bytes(source, bundled)
        if probe_hashes is not None:
            expected = probe_hashes.get(filename)
            require(isinstance(expected, str) and bool(re.fullmatch(r"[0-9a-f]{64}", expected)),
                    f"Invalid pinned native probe hash for {filename}")
            pinned_file(source, expected)
            pinned_file(bundled, expected)
    same_bytes(root / "packaging" / "rtx.conf", package / "rtx.conf")
    conf_text = (package / "rtx.conf").read_text(encoding="utf-8-sig")
    require(bool(re.search(r"(?m)^\s*rtx\.dlfg\.enable\s*=\s*false\s*$", conf_text)),
            "Native Remix FG must stay disabled for OptiScaler testing")

    source_licenses = {
        "MFG-OptiScaler-v1.7.0-LICENSE": "MFG-OptiScaler-GPL3-LICENSE.txt",
        "MFG-OptiScaler-v1.7.0-SOURCE.txt": "MFG-OptiScaler-SOURCE.txt",
    }
    for download, notice in source_licenses.items():
        same_bytes(downloads / download, package.parent / ("LICENSE" if "LICENSE" in download else "SOURCE.txt"))
        same_bytes(downloads / download, package / "Licenses" / notice)

    sdk = root / "build" / "streamline" / "bin" / "x64"
    sl_files = sorted(sdk.glob("sl.*.dll"))
    require({"sl.common.dll", "sl.interposer.dll", "sl.dlss_g.dll"}.issubset({p.name for p in sl_files}),
            "Missing essential Streamline components")
    for src in (*sl_files, sdk / "NvLowLatencyVk.dll"):
        same_bytes(src, package / "OptiScaler" / "streamline" / src.name)

    providers = sorted((root / "remix-runtime" / "win64").glob("nvngx_dlss*.dll"))
    require(bool(providers), "No pinned Remix NGX providers found")
    require(any(p.name.lower() == "nvngx_dlssnr.dll" for p in providers), "Missing pinned neural provider")
    for src in providers:
        for subfolder in ("OptiScaler", "OptiScaler/streamline"):
            same_bytes(src, package / subfolder / src.name)

    ini = package / "OptiScaler.ini"
    ini_text = ini.read_text(encoding="utf-8-sig")
    require("mfg-opti-staging-" not in ini_text.lower(), "INI references a deleted temporary staging directory")
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str
    with ini.open("r", encoding="utf-8-sig") as stream:
        config.read_file(stream)
    requirements = {
        ("Upscalers", "VulkanUpscaler"): "dlss",
        ("FrameGen", "Enabled"): "true" if fg_state == "on" else "false",
        ("FrameGen", "FGInput"): "upscaler",
        ("FrameGen", "FGOutput"): fg_output,
        ("FrameGen", "FGNvngxReplacement"): "None",
        ("DLSSG", "InterpolationCount"): "1",
        ("Menu", "OverlayMenu"): "true",
        ("Menu", "ShortcutKey"): "45",
        ("Menu", "FGShortcutKey"): "35",
        ("Plugins", "LoadAsiPlugins"): "true",
        ("Plugins", "Path"): str(installed / "OptiScaler" / "plugins"),
        ("Libraries", "OptiDllPath"): str(installed / "OptiScaler"),
    }
    for (section, key), expected in requirements.items():
        actual = config.get(section, key, fallback=None)
        require(actual == expected, f"OptiScaler INI mismatch: [{section}] {key}={actual!r}, expected {expected!r}")

    print(f"PASS: pinned OptiScaler probe validated: {package}")
    print(f"Verified {len(sl_files)} Streamline DLLs, {len(providers)} replicated NGX providers, "
          "native probes, license/source notices, config and exact final paths.")
    print(f"Vulkan FG {fg_state.upper()} output={fg_output} baseline verified; actually displayed frames remain unverified.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--installed-package", required=True, type=Path)
    args = parser.parse_args()
    try:
        verify(args.repo_root.resolve(strict=True), args.package.resolve(strict=True),
               args.installed_package.resolve(strict=False))
    except (ValueError, OSError, KeyError, configparser.Error, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
