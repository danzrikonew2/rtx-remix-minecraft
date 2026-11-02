# Minecraft 26.3 stability and performance baseline

## Combined settings candidate: 2026-11-02

- Insert is the default OptiScaler menu key. The old migration replaced explicit
  Insert with Backspace at startup. Explicit saved keys are now preserved.
- Eye adaptation enable/speed controls use existing native options. A pinned
  renderer test verifies enable + speed 2 and exact restoration. The default
  speed is 2 instead of 10; manual exposure and EV bounds remain unchanged.
  Visual acceptance remains pending.
- DLSS 5 discovery succeeds with the unchanged DLL beside the ASI, but neural
  creation is rejected as unsupported (`0xBAD00001`), with zero evaluations.
  The 150-present hidden test exits normally. Minecraft controls report actual
  provider status rather than treating an enable request as success.
- A second native-menu chaining experiment hung at startup and was removed.
  The existing presentation route remains. Higher MFG output and unique
  displayed interpolation are not validated.
- The latest user log completes native shutdown at 19:58:42 and the addon's
  log records Session end at 19:58:43. An OpenGL DxPresent(createDevice) warning
  occurs during exit. The prior archive records a stop at 19:31:38; no matching
  Java crash report/Windows Java application-error event was found. The oldest
  inspected archive lacks enough exit evidence. No crash cause/fix is claimed.

## User comparison and FG controls: 2026-11-02, build 34d264d

The user reports that `/rtx lighting cache off` fixes the bright-grass artifact.
The next packaged default bypasses primary thin-opaque SHaRC queries; this is a
scene-verified workaround, without a measured performance comparison or a claim
to fix the native cache implementation. Existing 34d264d instances can keep the
command's runtime setting. No running instance files were replaced for this change.

User captures show the shared menu working with FG Off, 2x and 6x requests.
F3 stays near the game's base rendering rate. A process-matched live snapshot
(PID 36824) records 5,834 successful FG evaluations / 5,832 submitted batches;
a subsequent snapshot records 6,993 / 6,991. Eight evaluation rejections occurred,
with first failure 131 and last failure 0, and zero failed submitted batches.
These are live snapshots during testing, not a final session/benchmark report.

At 19:22:22 and 19:22:50 Jakarta time the native log explicitly reports repeated
generated-output image reuse for `count=5` and latches the feature to 2x until
recreation. This explains why an ON 6x request cannot be treated as 6x output.
Distinct multi-output handling remains unresolved; guards stay active. Present
batch metadata and overlay FPS do not verify unique displayed interpolation or
a measured frame-rate multiplier. DLSS 5 is disabled/undetected with zero
evaluations in the same profile; its menu/provider integration remains incomplete.

## Adapter control diagnosis: 2026-11-02

The user reports that build 931391c still does not open a menu with Backspace
and that enabling Remix's native FG checkbox leaves it checked/greyed with
preset selectors. The adapter's shared OptiScaler INI had `ShortcutKey=auto`
(Insert), independently of the standalone MFG UI INI's Backspace setting.
This establishes a shortcut mismatch, not user error. The adapter's upscaler
input/DLSSG output also does not require Remix's native FG presenter.

Automatic menu settings now migrate before native loading with a preserved
backup, and a conflicting native FG request is cleared before startup.
`/rtx mfg reset` provides explicit recovery; `/rtx mfg` reads the resolved native
flag and explains the independent controls. Quality/preset settings are retained.

A hidden 140-present pinned-runtime probe sends key messages only to its own
window. Fresh OptiScaler logs confirm Backspace opens then closes the shared
menu and End changes `FGEnabled` false then true. The resolved native FG flag
is false after seeding and repairing a true request before startup. Two features
are created across the off/on cycle, with zero failed batches. Zero evaluations
are expected in this unfocused run; these data validate controls and recovery,
not Minecraft overlay visibility, display output or a frame-rate gain.

## Foliage lighting retest: 2026-11-01, build 931391c

The user still observed bright foliage patches after natural midnight followed
by day/night commands. The log confirms clock-change detection, so the previous
reset pulse did not resolve the reported artifact. Reading both flags back as
false proved configuration restoration, not that a native frame consumed the
short pulse: the SDK documents option resolution trailing the application by
several frames. A full reset also discards warm lighting samples.

The revised candidate uses a dedicated `mc.lighting.settling` layer. For an
abrupt clock change or moving weather it limits SHaRC accumulation/stale age to
8/8 frames, holds for 0.75 seconds after the change, then restores the normal
profile. It leaves warm cache entries in place and does not clear NRC or SHaRC.
The original profile uses 1,000/1,024 frames. The pinned-runtime probe verifies
8/8 while enabled and exact default restoration while disabled. This is a
targeted convergence mitigation; the visual cause remains unconfirmed.

`/rtx lighting cache off` bypasses SHaRC queries for primary thin-opaque foliage
for comparison; `on` restores them. `/rtx lighting cache` prints the resolved
query and history settings. Commands affect a runtime setting, not pack assets.
Compare the same view and time commands in both modes, then restore `on`.

The same game session records 26,794 successful FG evaluations/submitted batches
across three created features, zero failed batches, and a recovered first failure
171 (last failure 0). It completed native shutdown; the final mode was `none`.
That establishes successful FG provider execution in Minecraft, not unique
generated display images, a measured multiplier or artifact-free presentation.
The shutdown OpenGL warning and 42 undisposed common-device objects remain.
No foliage/resource-pack assets were changed.

## Experimental adapter failure: 2026-11-01, build b603d0a

The 22:45–22:50 Jakarta session loaded OptiScaler and MFG, but generated no
frames: zero created FG features/evaluations, Ampere failure 120 and a private
Vulkan `late-boundary` rejection. Backend ownership alone did not establish
that the patch worker had armed its early-load declaration. The final runtime
error was `DxvkSubmissionQueue: Command submission failed: VK_ERROR_DEVICE_LOST`.
OptiScaler repeatedly reported `eWarnOutOfVRAM` and failed FG creation before
that error. These messages do not establish VRAM exhaustion as the sole cause.
There is no Java crash report; native Sentry initialization also failed.

The revised loader waits for an explicit native readiness export covering DLL
notifications, the armed architecture declaration and the early feature boundary.
After Vulkan startup it verifies device admission; failure tears down renderer
initialization before the ordinary render loop can retry FG creation continuously.
A private-JVM C API probe passes device admission and 60 hidden presents. This
does not repeat the Minecraft workload or prove the device-loss problem fixed.

Day/night commands were detected in this session. The previous envelope only
shortened volumetric history; surface caches could retain old lighting. The new
candidate pulses the SHaRC and NRC `resetHistory` options for one rendered frame
on a discontinuous Overworld clock change, then explicitly clears both. Both
options are accepted by the pinned runtime, and its 60-frame probe verifies
that both return to false. Tests cover a frozen clock, ordinary ticks,
midnight wraparound, world identity changes and world-exit cleanup. Visual
settling time still needs a game check; no global accumulation limits changed.

The user clarified that missing terrain loaded after a few seconds, so this
capture records a loading delay rather than a persistent terrain loss. The
sapling pack contains its base/normal/specular/SSS textures. Its reported
glass-like appearance is unresolved and deferred at the user's request; no
pack assets or plant-material settings were changed.

## User acceptance session: 2026-11-01, build 4b70d9b

The user reported no major problems, leaves rendering correctly without the
experimental leaf overlay, and beacon colour following stained glass. The
selected pack was `RTX-Remix-Materials-0.58.0 (2).zip`; its SHA-256 exactly
matches the earlier `RTX-Remix-Materials-0.58.0.zip`. The overlay was not selected.
These are user observations, not proof that every material or scene is fixed.

Remaining reported symptoms: Backspace cannot open MFG's menu, enabling FG
then greys the control without an apparent frame-rate increase, and abrupt
day/night commands leave residual ground illumination/sparkles that settle
after standing still. Static screenshots cannot measure the settling duration.

Saved log evidence (17:31–17:46 local session):

- Native FG creation failed with `NVSDK_NGX_Result_FAIL_FeatureNotSupported`.
  Addon status reports `activeFrameGeneration=none`, game/applied FG false,
  `no active wrapper call`, zero DLSS 5 evaluations and Ampere failure 120.
  No generated-frame success is claimed; do not infer success from a checkbox.
- A 160 MB water-normal flipbook exceeded the 96 MB streaming staging budget,
  forcing synchronous upload. This is recorded as a startup allocation/upload
  limitation, not a confirmed explanation for continuous gameplay stutters.
- Orphan-column audits removed 60 columns in total. They recovered stale
  entries, but zero orphaning cannot be claimed for this session.
- Shutdown logged 42 undisposed common device objects. The responsible layer
  is not established; this is not a Java leak diagnosis.

The code already drives time-profile strengths without Java-side smoothing.
However, its existing short volumetric-history envelope covered weather,
biome and zone changes but omitted clock jumps. The candidate now includes
abrupt clock changes (over 200 ticks by shortest circular day distance),
excluding normal ticks, paused clocks and ordinary midnight wraparound.
It does not reset native surface-denoising or radiance-cache history. Surface
sparkles and exposure/lighting convergence remain unconfirmed causes requiring
further evidence. No speculative global denoiser settings were changed.

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

### Code and upstream research audit: 2026-11-03

The audit traced startup, configuration, camera/presentation, retained entity
identity, texture ownership, save migration, diagnostic discovery and packaging.
It did not establish a new Java transform/history defect or a complete ghosting
fix. Review of the retained registry, block-damage owners and transient-mesh
normal paths found consistent reuse/retirement ordering. The camera/present
path remains on the matching pinned C API; no speculative native ABI changes
or unverified denoiser-key overrides were introduced.

A concrete residency problem was found: dynamic map/skin textures and their
materials were only released on full world/material cleanup. Cold pooled mesh
eviction did not release their texture sets. `EntityTextureResidency` reuses the
once-per-layer refresh stamp to retire owned dynamic IDs unused for more than
600 capture frames, checking every 60 frames with at most four sets per sweep.
The existing invalidation path destroys dependent instances and meshes before
materials and textures. Shared/current-frame use protects a texture. CPU
snapshots remain available so a returning downloaded skin can be recreated;
borrowed atlas and static resource materials are not part of this retirement.
Refresh stamps are also cleared on reload. Destroy failures now preserve the
owner/cache entry for retry rather than forgetting an allocated native handle.
These are lifecycle fixes, not measured VRAM/FPS gains or a shimmer diagnosis.
Returning cold assets are recreated from retained CPU snapshots. A summary of
cold sets retired and cached dynamic sets is logged during material/world
cleanup, so the next normal session can be checked after exit without a
continuous profiler or a long recording.

The audit also found diagnostic window matching restricted to `Minecraft 1.*`;
26.3 titles now match without dropping 1.x support. Tests cover the new titles.
The follow-up to upstream port PR #79 revealed a save-wide zone-path correction;
this fork's migration also imports its previously used 26.3 dimension file
before falling back to 1.21.1, preserving source and current/future-schema data.

Two superficially related runtime reports were researched:
[eye adaptation/DLSS ghosting #391](https://github.com/NVIDIAGameWorks/rtx-remix/issues/391)
was closed by its reporter in 2025, and
[Preserve Path jitter #1058](https://github.com/NVIDIAGameWorks/rtx-remix/issues/1058)
was closed following runtime hash improvements in 2026. Neither establishes
the cause of this Minecraft report or proves the pinned private-source build
contains a particular fix. A regression cannot be inferred from title similarity.

The audit's 830 Java tests pass, including shared-use/grace/budget/failure-retry
coverage and zone-file priority/preservation tests. The separate native neural
probe and its alternative-provider trial are documented in
[MFG research](MFG_UNLOCKER.md#native-remix-dlss-nr-and-autopilot-research-2026-11-03).
Both renderer smoke runs completed; neither established neural feature success.
Manual acceptance remains necessary for visual stability, returning dynamic
textures and the memory/performance tradeoff in a real play session.
Required tooling checks pass with 1,147 tests and 178 subtests; one test is
skipped. No native runtime, API header or provider in the game installation
was changed by the neural experiments.

### Latest temporal-quality candidate: 2026-11-02

The user reports renewed stationary held-item shimmer and strong motion blur/
ghosting, including while chopping logs. The supplied 10-second, 30 FPS video
shows moving/swinging geometry with soft detail; it cannot measure motion vectors
or distinguish reconstruction artifacts from video compression by itself.
The matching 23:21:16 adapter heartbeat reports `gameFG=0`, `appliedFG=0`,
and unchanged NGX evaluation counters since FG was disabled at 23:13:26.
Generated frames therefore do not explain all of the reported artifacts.
The session also records RR creation at 853x456 for a 2560x1369 output after
the earlier Balanced 1505x805 selection. Comparisons must hold the internal
resolution fixed. No new Java hand-transform fix is claimed.

The shipped sparse-sampling quality was 0.3. The
[official runtime option documentation](https://github.com/NVIDIAGameWorks/dxvk-remix/blob/main/src/dxvk/rtx_render/rtx_sparse_rendering.h)
recommends 0.5 and explicitly describes the detail/temporal-stability cost of
lower sampling rates. The candidate restores 0.5 and adds a saved **Sparse
Tracing** control under Image & Exposure. `/rtx temporal` reads resolved sparse
enable/quality and the separate native FG request; `/rtx temporal sparse off|on`
uses the same persisted setting as the menu. Off requests full sampling while
leaving DLSS and denoising enabled. It can increase GPU time substantially;
neither a ghosting fix nor an FPS gain is established before visual comparison.
Native C API checks exercise off/on/restore against the pinned runtime rather
than assuming the public runtime source exactly matches that binary.
Validation: 817 Java tests pass; tooling checks pass with 1,144 tests and 178
subtests (one skipped test). A 60-frame isolated native probe
verifies both sampling modes, quality 0.5 and exact restoration. The private-Java
loader validates all 33 pinned files and a fresh process-matched status. Its
renderer also completes 60 frames, but a status check made after SDK shutdown
is correctly rejected once its last heartbeat is six seconds old; this does
not establish a live rendering failure or justify relaxing the freshness guard.

The screenshots show about 5,558 MiB of a changing 6,495-6,639 MiB budget,
leaving roughly 937-1,081 MiB in that displayed budget. The card still reports
8,192 MiB physical capacity. A dynamic process budget is not physical capacity;
the [Vulkan memory-budget contract](https://docs.vulkan.org/refpages/latest/refpages/source/VkPhysicalDeviceMemoryBudgetPropertiesEXT.html)
allows it to change with other system activity. Neither the screenshot nor one
board-wide utilization sample proves exhaustion or GPU underuse caused shimmer.
The native session reports an oversized water-texture synchronous upload and a
failed native DLFG feature creation, with no logged device-lost or out-of-memory
failure in this run. Those are separate observations, not a memory diagnosis.

F8 turns off scene capture/submission and returns world drawing to vanilla;
it does not shut down the Remix runtime. Terrain is cleared, but runtime caches,
render targets, other asset stores, the adapter and vanilla resources can stay
allocated. Alt-tabbing/minimizing similarly does not unload VRAM. The candidate
caps a minimized initialized Remix client at 1 FPS; an unfocused visible client
retains its configured cap (default 10). Benchmarks bypass these extra caps.
Lower submission rates reduce background work, but concurrent games still
share GPU time and memory. Exiting Minecraft releases its process resources.

One consolidated comparison: keep the same view and DLSS Balanced setting,
with both FG routes off; compare held stone, a slow pan and log breaking with
sparse off/on. Report trails/shimmer and FPS for each. Then minimize Minecraft,
check whether competing-game performance improves, and return to confirm
rendering resumes. A qualitative report is sufficient; no continuous capture
or new world is required. Close Minecraft and Prism before installing changes.

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
