# SPDX-License-Identifier: Apache-2.0
"""Audit an isolated FSRFG Vulkan/NGX run without inferring displayed frames.

The OptiScaler debug log has no PID or GPU-completed image identifier. This
utility validates its internal event sequence and reports that limitation.
It is intentionally not an FG certification or a video-output FPS counter.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path

from verify_optiscaler_probe import FSR_VULKAN_PROVIDER_SHA256, PINS


SOURCE_PRESENT = re.compile(r"^frame=(\d+),(\d+),VK_SUCCESS$")
SOURCE_EVALUATE = re.compile(r"^ngx_evaluate=(\d+) result=(\d+)$")
LOG_RESULT = re.compile(
    r"FSRFG_Vk::Dispatch (Configure|Prepare) result: (.+?), frame: (\d+), fIndex: (\d+)"
)
START_NEW_FRAME = re.compile(r"IFGFeature::StartNewFrame _frameCount: (\d+), fIndex: (\d+)")
SUCCESS = "The operation was successful."


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit(log: str, stdout: str, *, frames: int) -> dict:
    """Check raw records; one diagnostic callback log is never an FG count."""
    if frames < 1:
        raise ValueError("frames must be positive")
    failures = []
    errors = []
    presents = []
    evaluations = []
    for line in stdout.splitlines():
        line = line.strip()
        if match := SOURCE_PRESENT.fullmatch(line):
            presents.append(int(match[1]))
        elif match := SOURCE_EVALUATE.fullmatch(line):
            evaluations.append((int(match[1]), int(match[2])))
    expected = list(range(frames))
    if presents != expected:
        failures.append("source_present_sequence_missing_duplicate_or_out_of_order")
    if evaluations != [(n, 1) for n in expected]:
        failures.append("ngx_evaluate_sequence_missing_failed_or_out_of_order")
    if f"ngx_evaluations_completed={frames}" not in stdout.splitlines():
        failures.append("ngx_evaluation_total_not_confirmed")
    if "result=FAIL" in stdout:
        failures.append("source_probe_reported_failure")
    terminal_results = [line for line in stdout.splitlines() if line.startswith("result=")]
    if len(terminal_results) != 1 or not any(
        terminal_results[0].startswith(f"result={marker} ")
        for marker in ("NGX_EVALUATE_PRESENT_PASS", "NGX_EVALUATE_PRESENT_SHUTDOWN_SKIPPED")
    ):
        failures.append("source_probe_terminal_result_missing_or_unexpected")

    result_matches = {"Configure": [], "Prepare": []}
    new_frames = []
    for line in log.splitlines():
        if match := LOG_RESULT.search(line):
            kind, result, frame, index = match.groups()
            if result != SUCCESS:
                errors.append(f"{kind}:frame={frame}:result={result}")
            result_matches[kind].append((int(frame), int(index)))
        if match := START_NEW_FRAME.search(line):
            new_frames.append(int(match[1]))

    configured = result_matches["Configure"]
    prepared = result_matches["Prepare"]
    if configured != prepared:
        failures.append("configure_prepare_frames_or_indices_mismatch")
    if configured:
        indices = [frame for frame, _ in configured]
        if indices != list(range(indices[0], indices[-1] + 1)):
            failures.append("configuration_frames_not_strictly_contiguous")
        if indices[-1] != frames:
            failures.append("configuration_does_not_end_at_last_source_frame")
    elif frames > 10:
        failures.append("no_ffx_configure_after_expected_startup_window")

    swapchain = log.count(
        "FSRFG_Vk::CreateSwapchain Swapchain context creation result: " + SUCCESS
    )
    fg_context = log.count("FSRFG_Vk::CreateContext FG context creation result: " + SUCCESS)
    if swapchain != 1 or fg_context != 1:
        failures.append("provider_swapchain_or_context_count_not_exactly_one")
    if errors:
        failures.append("ffx_configure_or_prepare_error")

    provider_ngx = log.count("NVSDK_NGX_VULKAN_EvaluateFeature Handle:")
    if provider_ngx != frames:
        failures.append("provider_ngx_evaluate_event_count_mismatch")
    if new_frames != list(range(1, frames + 1)):
        failures.append("provider_start_new_frame_sequence_inconsistent")
    shutdown_skipped = "stage=ngx_shutdown_skipped" in stdout or (
        "result=NGX_EVALUATE_PRESENT_SHUTDOWN_SKIPPED" in stdout
    )
    clean_shutdown = "stage=ngx_shutdown_end result=1" in stdout and not shutdown_skipped
    if not clean_shutdown and not shutdown_skipped:
        failures.append("no_confirmed_normal_shutdown")

    pacing_lines = [line.strip() for line in log.splitlines()
                    if "FSRFG_Vk::ConfigureFramePaceTuning Frame pacing tuning configure result:" in line]
    pacing_errors = [line for line in pacing_lines if SUCCESS not in line]
    reset_diagnostics = log.count("FSRFG_Vk::DispatchCallback Frame id ")
    callback_cancel = log.count("FSRFG_Vk::DispatchCallback Cancel dispatch")
    callback_duplicate = log.count("FSRFG_Vk::DispatchCallback Dispatched with the same frame id")
    ffx_teardown = (
        "FSRFG_Vk::DestroyFGContext Destroy FG context result: " + SUCCESS in log
        and "FSRFG_Vk::ReleaseSwapchainContext Destroy swapchain context result: " + SUCCESS in log
    )
    if not ffx_teardown:
        failures.append("ffx_context_teardown_missing_or_unsuccessful")

    return {
        "diagnostic_valid": not failures,
        "failure_reasons": failures,
        "source_present_success": len(presents),
        "ngx_evaluate_success": len(evaluations),
        "provider_ngx_evaluate_events": provider_ngx,
        "ffx": {
            "swapchain_context_success": swapchain == 1,
            "fg_context_success": fg_context == 1,
            "configure_success_count": len(configured) - sum(e.startswith("Configure:") for e in errors),
            "prepare_success_count": len(prepared) - sum(e.startswith("Prepare:") for e in errors),
            "configure_frame_first": configured[0][0] if configured else None,
            "configure_frame_last": configured[-1][0] if configured else None,
            "configure_prepare_errors": errors,
            "callback_reset_debug_lines": reset_diagnostics,
            "callback_cancel_debug_lines": callback_cancel,
            "callback_duplicate_debug_lines": callback_duplicate,
            "callback_dispatch_attempt_count": None,
            "callback_dispatch_success_count": None,
            "num_generated_frames_gpu_completed": None,
            "frame_pacing_configuration_errors": pacing_errors,
        },
        "ngx_normal_shutdown_proven": clean_shutdown,
        "ffx_teardown_observed": ffx_teardown,
        "provider_log_matches_source_process": False,
        "distinct_generated_images_verified": False,
        "physical_scanout_verified": False,
        "fg_2x_proven": False,
        "gate_h": "BLOCKED",
        "interpretation": (
            "NGX source presents and FFX Configure/Prepare are only upstream milestones; "
            "callback reset debug messages are conditional and do not count successful "
            "interpolation dispatches, distinct images, or displayed scanout frames."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--stdout", type=Path, required=True)
    parser.add_argument("--frames", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # A valid log must be backed by the known-good binaries in this package.
    hashes = {
        "optiscaler_dll": (args.package / "OptiScaler.dll", PINS["optiscaler_fork_sha256"]),
        "ffx_vulkan_provider": (
            args.package / "OptiScaler" / "amd_fidelityfx_vk.dll", FSR_VULKAN_PROVIDER_SHA256
        ),
    }
    verified = {}
    for name, (path, expected) in hashes.items():
        actual = sha256(path)
        if actual != expected:
            raise ValueError(f"{name} SHA-256 mismatch: {actual} expected {expected}")
        verified[name] = actual
    log = args.log.read_text(encoding="utf-8-sig", errors="replace")
    stdout = args.stdout.read_text(encoding="utf-8-sig", errors="replace")
    report = audit(log, stdout, frames=args.frames)
    report["input_sha256"] = {"provider_log": sha256(args.log), "probe_stdout": sha256(args.stdout)}
    report["verified_binary_sha256"] = verified
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite previous report: {args.output}")
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"diagnostic_valid": report["diagnostic_valid"],
                      "ffx": report["ffx"], "gate_h": report["gate_h"]}, indent=2))
    return 0 if report["diagnostic_valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
