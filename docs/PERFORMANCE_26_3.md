# Minecraft 26.3 stability and performance baseline

## Diagnostic session: 2026-10-31

Baseline source: `5369f65`, community alpha 2. The user manually played the
isolated development instance, flew to load terrain and rejoined the same world.
No computer-use tools, scripted window input, global process cleanup, forced
GC, or rendering-feature reductions were used for this session.

Environment: Windows x64, RTX 3070 Ti with 8,192 MiB VRAM and driver 621.01,
Java 25, 2 GiB maximum Java heap, render distance 32, simulation distance 12,
1920x1080 requested size, VSync off, configured maximum framerate 260.
Renderer JFR phases and the JFR profile preset were enabled for diagnosis.

Process telemetry was collected every five seconds for 900.64 seconds (180
samples), from 11:30:18 to approximately 11:45:19 Asia/Jakarta. JFR started
earlier, at 11:26:53. Prism identifies this instance through its natives path;
its game directory is passed on standard input, so a process-name or game-dir
substring match alone is insufficient. Only the verified game PID was sampled.

## Results

| Measurement | Observation |
|---|---|
| World lifecycle | Four joins and three disconnects logged; Remix cleanup reported on exits |
| Crash/device-loss/allocation-failure patterns | None found in the captured Minecraft and Remix logs |
| Board-wide VRAM | 5,996-7,768 MiB; average 7,504.62 MiB |
| Minimum sampled VRAM headroom | 424 MiB, about 5.2% of the card |
| Game process working set | 7,487.68-9,606.47 MiB; final sample 7,819.87 MiB |
| Game process private committed memory | 12,621.91-15,673.88 MiB; final sample 13,967.48 MiB |
| Last five minutes of private committed memory | 13,963.88-13,967.48 MiB, approximately flat compared with earlier load/unload changes |
| Terrain safety audit | 16 audits removed a total of 136 orphaned columns |

VRAM covers the whole NVIDIA board, including the desktop and other programs.
Private committed bytes, working set and Java heap measure different things.
The process's final memory use was below its first sampled use. This does not
show an unbounded increase in this short session, but it is not proof of
leak-free native resources or long-term stability. The orphan-column audits
deserve a focused unload/capture lifetime investigation; they also demonstrate
that the existing safety cleanup was recovering those columns.

## Java heap pressure and frame diagnostics

The first JFR snapshot covers 335 seconds from 11:26:53, including startup,
terrain generation/streaming and world transitions. It reports:

- 20 `G1Full` collections with cause `G1 Compaction Pause`.
- 930 GC pause events totaling about 12.46 seconds; maximum pause 389.65 ms.
- Sampled allocation leaders include `PalettedContainer.reencodeContents` and
  `DensityBuffer` construction. These are allocation estimates, not retained
  memory or evidence that either method itself leaks.
- 17,792 in-world frame-ledger events: median 14.10 ms, p95 20.43 ms,
  p99 42.47 ms. The 3.23-second maximum includes transitional work and is not
  a steady-gameplay frame-time claim.

The final JFR is a rolling recording: its retained window begins at 11:30:58
and lasts 864 seconds. It contains six full compactions and 542 GC pause events,
totaling about 4.86 seconds. The windows overlap; do not add their counts.
In that window 70 of 1,351 frames over 50 ms overlapped a GC pause. GC therefore
explains some hitches, not every slow frame. Many later frames cluster near
33.3 or 100 ms, consistent with frame limiting/inactivity. Focus and manual
activity were not recorded as controlled experimental variables.

This is a diagnostic smoke test, **not an FPS benchmark or an optimization
comparison**. It mixes loading, movement, menus, transitions and idle periods.
Interim JFR inspection also ran during play and is an additional CPU workload.
Use a repeatable route and quiet analysis-free recording windows for A/B claims.

## Changes supported by this investigation

- GPU benchmark telemetry now records board VRAM used/total and GPU utilization,
  plus recording-window memory headroom. Unsupported fields are missing, not zero.
- JFR's `jdk.PhysicalMemory` event is OS-wide memory. The profiler previously
  labeled it RSS, which could misidentify all system RAM as Minecraft memory.
  It is now labeled system memory; summary JSON uses `system_memory`.
  `jfr_gc --system-memory` is the explicit option (`--rss` remains an alias).
- Per-PID working set and private committed memory were sampled separately.

No heap, graphics-quality or render-distance defaults were changed. No speedup
is claimed from the telemetry and labeling corrections.

## Next controlled tests

### User symptoms and daylight follow-up

The user reported stutters, worsening perceived FPS and uneven flying speed,
as well as weak daylight after both `/time set day` and `/time set noon`.
These are reported symptoms, not proof of a particular bottleneck. View bobbing
was not isolated, and server tick pacing was not measured independently.

Read-only inspection of the stopped test world's 26.3 `weather.dat` found
`raining=1` and `thundering=1`. This provides a concrete weather explanation
for heavily attenuated direct sunlight; changing the clock does not clear the
storm. Clear-noon rendering still needs visual confirmation. The inspection
did not modify the save. See [daylight diagnostics](RENDERING_DIAGNOSTICS.md#dark-daytime-and-weather).

The game subsequently shut down normally at 11:53:15, after the bounded
capture ended. The later log contains an NVIDIA OpenGL `DxPresent
(createDevice)` debug error during shutdown; there was no corresponding crash
report observed in this inspection. Track it separately from the capture's
earlier no-device-loss result and verify shutdown in later testing.

### Comparisons still needed

1. Compare `/rtx off` and `/rtx on` on the same warmed route, at matching time
   and weather. Keep movement, graphics, world and heap fixed. Capture server
   tick pacing as well as frame times. Repeat with reversed order to reduce
   chunk-generation and cache bias. Vanilla-only and integrated rendering
   share CPU work, so this comparison does not isolate every native cost.
   Sodium/OptiFine compatibility is unverified; adding either changes the
   experiment and requires a separate rendering compatibility investigation.
2. Compare the existing 2 GiB heap with a local 6 GiB heap on this user's
   64 GiB system, keeping graphics, resource packs, view distance, world and
   route identical. Record GC compactions and frame tails after equal warmup.
   More heap is a candidate for reducing compactions, not a verified fix yet.
3. At the selected heap, compare render distances on the same saved fixture
   and camera route to establish an 8 GiB VRAM budget. This is an explicit
   quality/performance comparison, not a silent reduction in shipped settings.
4. Repeat longer world-exit/rejoin cycles and resource reloads, with settled
   measurements at matching points. Check native handles, retained pages and
   memory high-water marks, not only whether the process stays alive.
5. Investigate the repeated orphan-column audits using the actual 26.3 unload
   and capture lifecycle before changing queue or resource ownership rules.

The user deferred the second heap comparison; it has not been run. No
performance improvement is claimed for the current changes.

## Validation of diagnostic changes

- `gradlew.bat build -Parch=win64` passed using cached dependencies; 767 JVM tests, zero failures
  or errors. This compiles the new sky-status command but does not exercise it
  through Fabric in a live game.
- `tools\rtx.bat check --tests` passed formatting, lint and type checks, plus
  1,140 tests and 178 subtests. One commit-message scan was skipped because no
  commit range was supplied on that invocation.
- At that milestone, clear-noon visual acceptance, the new command in game and
  the larger-heap comparison were untested. Public alpha 2 release assets are
  unchanged. The daylight follow-up is recorded below.

## Manual RTX toggle follow-up

The later manual session ended normally at 22:43:20 Asia/Jakarta. The user
confirmed clear weather restored bright daylight. They still noticed some
stutter and uneven movement with RTX off, and reported large missing terrain
areas after enabling RTX again and after reloads. Screenshots show intact
vanilla terrain and fragmented RTX terrain at the same location. These are
qualitative observations, not controlled frame-time measurements. RTX off
still runs this mod and Fabric; it is not an unmodified vanilla comparison.

The log queued 9,072 sections when RTX was re-enabled at 22:40:36, and further
recapture requests followed reloads. Inspection of the installed 26.3 classes
found that `LevelExtractor.allChanged()` defers geometry invalidation until
extraction. `LevelRenderer.invalidateCompiledGeometry()` then releases section
buffers and clears the compile queue. The port was submitting recapture before
this cancellation. The fix retains eligible positions and submits them after
invalidation, with world and capture-mode guards. This addresses a concrete
ordering error; it does not establish that every missing item or terrain hole
has the same cause.

The updated Java build and 771 JVM tests passed, including four recapture
lifecycle regressions. Manual acceptance is pending: repeat off/on and reloads
while stationary and moving, wait for builds to settle, then check the same
terrain and held blocks. Keep heap and graphics settings unchanged for this
test. A 6 GiB heap experiment remains separate and has not been run.

The first session's recordings, samples and local logs are under ignored
`build/captures/stability-20261031-112641/`. Raw JFR files may contain environment
variables, process metadata and account information. They are not published.
Temporary recording flags were removed from local launcher configuration and
the instance after capture; Minecraft itself was left running for the user.
