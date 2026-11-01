# Minecraft 26.3 stability and performance baseline

## Headless allocation review: 2026-11-01

Removed an unused initial block-atlas GPU upload from `captureAtlas`.
`buildAtlasMaterials` uploads the final AO/padding-adjusted atlas later, and
no intervening initialization step consumes the intermediate GPU texture.
Previously both allocations stayed in `managedTextures` until cleanup.
At 16384x16384 this removes one upload of 1,073,741,824 RGBA8 base-level bytes;
that is an allocation-path observation, not a measured VRAM or FPS result.
The native runtime's mipmaps, staging and residency determine actual memory use.

Per-sprite specular conversion now allocates an RGBA SSS buffer only when
the specular map contains SSS data; non-SSS maps previously populated and
discarded that buffer. Texture quality and atlas resolution are unchanged.
The resource pack in upstream #82 has not been reproduced in a GPU session,
so its reported exhaustion is not marked fixed.

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

## First 6 GiB test follow-up

The subsequent test exited normally at 23:00:03 Asia/Jakarta. The user confirmed
the missing-terrain problem after RTX toggles no longer occurred. This is a
manual pass for that reproduction, not proof that all terrain lifetime issues
are resolved. Brief noticeable stutters while flying into new terrain remain.
The user also reported small hand/held-item vibration with RTX on, including
while stationary; RTX off appeared steady. Temporal reconstruction, motion
history and capture transforms remain investigation candidates, not diagnoses.

The saved `gc-6gb-2026-10-31_22-56-15.log` contains 178 completed GC pauses,
zero full collections, and a maximum pause of 49.118 ms. None exceeded 50 ms.
This differs from the earlier 2 GiB capture's full compactions and approximately
390 ms maximum, but the route, duration and instrumentation were not matched:
it is not a controlled speedup measurement. GC can still interrupt frames below
50 ms, and this log alone cannot assign individual terrain-loading stutters.

The local instance used a 6 GiB maximum heap with lightweight GC/safepoint
logging. Earlier JFR/Java-phase flags persisted in Prism's saved instance
configuration; they were removed with Prism stopped before this follow-up.
The release heap defaults and published release assets remain unchanged.

## JNI matrix-copy investigation

The 6 GiB GC log contains 21 lines mentioning pinned evacuation failures
(including start/detail lines; this is not a count of distinct pauses). The
bridge used four `GetPrimitiveArrayCritical` sites solely to copy 12- or
16-float matrices into native structures. These sites now use
`GetFloatArrayRegion`, checking pending exceptions before invoking the runtime
and releasing the newly allocated dome structure if its input copy fails.
The Java signatures, native structure layouts and runtime pin are unchanged.

JNI critical access can restrict GC; array-region reads copy directly into a
supplied native buffer. See the [JNI specification](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html).
The log does not identify which pinned object caused a particular pause, so
this change must not be described as a confirmed fix for all chunk stutters.

Windows x64 native compilation and the 771 JVM tests passed. A standalone
`-Xcheck:jni` smoke test passed 10,000 dome-matrix copy/free roundtrips, verified
adjacent native fields, and checked the short-array exception path. Camera and
instance runtime calls still require in-game acceptance; ARM64 was not tested.
From the repository root after building, run the smoke test with Java 25:

```powershell
javac -cp build/classes/java/main -d build/native-tests rtxremix-java/tests/MatrixCopySmoke.java
$matrixBridge = (Resolve-Path build/native/win64/remixbridge.dll).Path
java --enable-native-access=ALL-UNNAMED -Xcheck:jni -cp "build/classes/java/main;build/native-tests" MatrixCopySmoke "$matrixBridge"
```

## Hand jitter investigation

The supplied Remix settings screenshot shows DLSS Preset Enabled, DLSS Auto,
and Computed DLSS Mode Max Performance at 960x540 internal resolution. The
individual controls appear disabled under the preset. This confirms the
displayed mode, not the cause of jitter. No hand-transform fix is claimed.
Compare the same stationary item/view at a higher DLSS quality and, separately,
without temporal upscaling if available. Record the selected mode and whether
the effect changes. Do not change heap, world or camera position in that test.

### Upscaler comparison and transform probe

The user subsequently reported jitter across the tested DLSS modes and with
Upscaler Type None, with geometry/texture/shadow variation settling after
movement stops. Their screenshots show the Ray Reconstruction controls hidden
when None is selected. This rules out DLSS upscaling as the sole explanation;
it does not prove all temporal denoising is disabled. Repeating the same DLSS
comparison is not the next diagnostic step.

`-Drtxremix.debug.firstPersonHistory=true` enables a small render-thread probe
that reports every 120 first-person captures. It counts changes in fingerprints
of the camera-to-world root, used corrected bone matrices, and bone/layer counts,
plus consecutive captures with unchanged fingerprints. It ignores unused pooled
bone storage. This is not a measurement of native motion vectors, mesh identity,
lighting noise or pixel stability. Stable fingerprints with visible shimmer
would narrow investigation beyond these submitted transforms; changing ones
would identify a capture input to inspect. No jitter fix is claimed yet.

The hand pass also reuses its model-view snapshot matrix instead of allocating
a new matrix for each capture. This is a small allocation reduction with no
measured frame-time benefit claimed.

Later local GC logs have zero full collections and maximum completed pauses
of 28.757, 22.217 and 22.682 ms respectively. Pinned-evacuation messages remain.
Routes, durations and graphics differ, so these are observations, not matched
before/after optimization results.

### Stationary-hand capture result

The 38379cb diagnostic session ended normally at 23:36:26 Asia/Jakarta.
Before looking around, the probe reached 1,514 consecutive captures with
unchanged camera/bone/layout fingerprints. Movement changed both camera and
bone fingerprints. After movement stopped, the camera stabilized first and
bone changes settled by the 23:35:57 report; subsequent reports reached 1,899
consecutive unchanged captures. This does not support continuous stationary
jitter in those sampled Java transforms. It does not validate mesh/material
identity or native motion vectors, and cannot establish a denoiser defect.
The remaining investigation belongs downstream of these capture inputs.
The session log was preserved locally and the temporary probe argument removed
with Minecraft and Prism stopped. The 6 GiB heap was retained.

### Hand-history settling mitigation

The retained-instance path previously submitted a changed hand pose and then
sent nothing once the description stayed unchanged. The view-model path now
sends one additional unchanged description before returning to idle. This gives
the runtime an explicit stationary transition while preserving the same mesh
and scene-instance handles. Ordinary world geometry keeps its existing update
policy. There is no perpetual idle resubmission or global history reset.

This is a targeted mitigation, not a verified diagnosis of the visible jitter.
The public runtime source was inspected for context, but the package's pinned
71a581da commit could not be resolved in the public repository, so exact native
history behavior remains unverified. Regression tests cover the changed-pose,
single settling-update and idle sequence, and world-instance update suppression.
Manual acceptance on the installed runtime remains required. No DLSS, denoiser,
heap or graphics-quality setting is changed by this mitigation.

### Result and upstream report: 2026-11-01

The user tested 51fddfe and confirmed that the jitter persists. The settling-pose
candidate is unsuccessful and must not be described as a working jitter fix.
The user also reports the same symptom in NVIDIA's original Minecraft 1.21.1
installation; that is a user observation, without original-version logs collected
in this investigation. The root cause remains unresolved.

At the user's explicit request, reported upstream as
[NVIDIAGameWorks/rtx-remix-minecraft#83](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/83).
The report distinguishes original-version observations from 26.3 diagnostics,
documents the unsuccessful candidate, and leaves runtime/mod ownership open
for maintainer triage. No private raw logs or account data were posted.

## Consolidated chunk-performance pass: 2026-11-01

Reviewed capture allocation, ingestion/upload bursts, duplicate geometry, and
unload/resource ownership together. Changes in this pass:

- Capture ingestion now yields between captures after a default 1 ms budget.
  At least one capture is processed per frame. One expensive capture is not
  preempted, so this is not a hard frame-time cap. Pending captures retain their
  generation/chunk-token checks, including unloads between frames.
- Consumed capture slots are cleared immediately rather than retaining their
  wrapper references until the entire batch completes.
- Empty old/new light sets skip reconciliation maps/lists/tasks. Pending CREATE
  work for that section is still cancelled first. Column unloads skip the
  per-section cancellation-key walk when no reconcile tasks exist.
- `Chunk.CaptureDeferred`, `Chunk.CaptureUnchanged`, and
  `Chunk.EmptyLightTasksSkipped` expose the affected work in normal performance
  reports. Existing hash-based geometry rejection remains; lights are reconciled
  independently because the geometry hash does not include light parameters.

Existing mesh installation and resource retirement are already budgeted. No
new duplicate filter or unload ownership rule was introduced without evidence
of a missing mechanism. Orphan-column audits remain an unresolved investigation
item; their recovery is not proof of a leak or proof that unload events are lost.
No world-generation algorithm, view distance, graphics quality or release heap
default was changed. Runtime improvement remains unmeasured until the combined
test is analyzed.

For one consolidated pass, keep the current settings, fly through new terrain
and back through already visited terrain, edit/place/break blocks and lights,
toggle RTX off/on, then leave/reopen the world twice. Finish by quitting Minecraft
and Prism normally. Collect JFR, GC, normal performance reports, recapture counts,
orphan audits and cleanup messages only after exit. Raw recordings remain private.
Logs can expose stalls and workload trends; they cannot prove visual correctness
or establish a long-term native-resource leak from a short run.

### Consolidated test result

The 9fafa0b run exited normally on 2026-11-01 at approximately 00:28:28
Asia/Jakarta. The user reported the hand was fully stable without visible
jitter in this run. This is one positive observation after earlier failures,
not proof of a deterministic fix or a reason to declare upstream issue #83
resolved. Graphics settings were not independently controlled or recorded as
a matched comparison, and no comparative GPU-headroom telemetry was captured.

The JFR spans 269 seconds and contains 14,220 in-world frame ledgers, including
streaming and transitions. Median frame time was 15.46 ms, p95 18.54 ms and
p99 36.98 ms. There were 110 frames above 50 ms, 27 above 100 ms and a maximum
of 941 ms; 19 of the frames above 50 ms overlapped a GC pause. These mixed
diagnostic frames are not an FPS benchmark or a controlled before/after test.

The GC log records zero full collections and a maximum completed pause of
73.102 ms. JFR GC phase timing reports approximately 73.057 ms for its maximum;
these are separate measurements of the pause. Normal performance reports show:

- 44,710 empty-light reconciliations skipped.
- 2,874 captures rejected by the existing unchanged-geometry guard.
- Maximum local deferred-capture backlog of six; pacing was rarely engaged.
- Zero capture evictions, but 1,097 capture-capacity wait events remained.
- No orphan-column audit removals and no ERROR-level Minecraft log lines.

Zero orphan removals in this short run does not prove resource lifetimes are
leak-free. Capacity waits and long frame tails remain optimization targets.
The latest changes primarily reduce CPU allocation/ingestion work; these data
do not establish that extra GPU capacity caused the stable hand. Shader/cache
warmup, workload differences and temporal behavior remain possible confounders.

Private captures and summaries are preserved under ignored
`build/captures/chunk-pass-9fafa0b/`. The three temporary recording flags were
removed after both Minecraft and Prism stopped. The local 6 GiB heap remains.

The first session's recordings, samples and local logs are under ignored
`build/captures/stability-20261031-112641/`. Raw JFR files may contain environment
variables, process metadata and account information. They are not published.
Temporary recording flags were removed from local launcher configuration and
the instance after capture; Minecraft itself was left running for the user.
