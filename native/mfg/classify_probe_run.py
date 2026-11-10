# SPDX-License-Identifier: Apache-2.0
"""Classify isolated Remix probe completion independently of renderer shutdown.

An explicit stock-Remix Shutdown timeout can follow a completely instrumented
frame loop. This classifier preserves that distinction for diagnostic analysis;
it never certifies actual displayed or interpolated frames.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path


def sha256_file(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def single_record(pattern: str, output: str) -> tuple[int, ...] | None:
    matches = re.findall(pattern, output, flags=re.MULTILINE)
    if len(matches) != 1:
        return None
    match = matches[0]
    return tuple(int(value) for value in (match if isinstance(match, tuple) else (match,)))


def classify(output: str, requested_frames: int, timed_out: bool,
             exit_code: int | None, *, process_pid: int | None = None,
             process_birth: int | None = None, observer_required: bool = False,
             observer_exit_code: int | None = None,
             observer_timed_out: bool = False) -> dict:
    if requested_frames < 40 or requested_frames > 3600:
        raise ValueError("Expected source frame count outside probe bounds")
    if (process_pid is not None and process_pid <= 0 or
            process_birth is not None and process_birth <= 0):
        raise ValueError("Invalid native process identity")
    source = single_record(r"^Probe presents=(\d+) foreground presents=(\d+)\r?$", output)
    remix = single_record(
        r"^Real Remix: Vulkan hooked=(\d+) presents=(\d+) menu draws=(\d+) failures=(\d+)\r?$",
        output,
    )
    host_retired = len(re.findall(r"^Remix Vulkan host retired\r?$", output, re.MULTILINE)) == 1
    shutdown_started = len(re.findall(r"^Beginning Remix Shutdown\r?$", output, re.MULTILINE)) == 1
    shutdown_count = len(re.findall(r"^Remix Shutdown completed\r?$", output, re.MULTILINE))
    shutdown_done = shutdown_count == 1
    failure_marker = bool(re.search(r"^FAIL:", output, re.MULTILINE))
    complete_render = bool(
        source is not None and remix is not None
        and source[0] == requested_frames and source[0] == remix[1]
        and 0 <= source[1] <= source[0] and remix[0] == 1
        and remix[3] == 0 and host_retired and shutdown_started
        and shutdown_count <= 1
        and not failure_marker
    )
    clean = complete_render and not timed_out and exit_code == 0 and shutdown_done
    shutdown_timeout = (complete_render and timed_out and not shutdown_done
                        and exit_code != 0)
    observer_passed = (not observer_timed_out and observer_exit_code == 0
                       if observer_required else None)
    if clean:
        result = "clean_shutdown"
    elif shutdown_timeout:
        result = "shutdown_timeout_after_complete_render"
    else:
        result = "incomplete_or_failed"
    return {
        "schema": "remix-native-probe-termination-v1",
        "result": result,
        "requested_frames": requested_frames,
        "rendered_frames": source[0] if source else None,
        "foreground_frames": source[1] if source else None,
        "remix_render_failures": remix[3] if remix else None,
        "frame_loop_complete": complete_render,
        "host_retired": host_retired,
        "shutdown_started": shutdown_started,
        "shutdown_completed": shutdown_done,
        "process_timed_out": timed_out,
        "exit_code": exit_code,
        "process_pid": process_pid,
        "process_birth": process_birth,
        "observer_required": observer_required,
        "observer_exit_code": observer_exit_code,
        "observer_timed_out": observer_timed_out,
        "observer_passed": observer_passed,
        "eligible_for_diagnostic_analysis": clean or shutdown_timeout,
        "rendering_and_shutdown_both_passed": clean,
        "actual_interpolated_display_frames_verified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stdout", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frames", type=int, required=True)
    parser.add_argument("--timed-out", action="store_true")
    parser.add_argument("--exit-code", type=int)
    parser.add_argument("--pid", type=int)
    parser.add_argument("--process-birth", type=int)
    parser.add_argument("--observer-required", action="store_true")
    parser.add_argument("--observer-exit-code", type=int)
    parser.add_argument("--observer-timed-out", action="store_true")
    parser.add_argument("--source-trace", type=Path)
    parser.add_argument("--desktop-trace", type=Path)
    parser.add_argument("--status-trace", type=Path)
    parser.add_argument("--observer-log", type=Path)
    args = parser.parse_args()
    result = classify(args.stdout.read_text(encoding="utf-8-sig"), args.frames,
                      args.timed_out, args.exit_code, process_pid=args.pid,
                      process_birth=args.process_birth,
                      observer_required=args.observer_required,
                      observer_exit_code=args.observer_exit_code,
                      observer_timed_out=args.observer_timed_out)
    # Bind independently generated telemetry to this exact runner record. A
    # stale/swapped CSV cannot be accepted just because its timestamps overlap.
    result["trace_sha256"] = {
        "source": sha256_file(args.source_trace),
        "desktop": sha256_file(args.desktop_trace),
        "status": sha256_file(args.status_trace),
        "observer_log": sha256_file(args.observer_log),
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Probe termination classification: {result['result']}: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
