# Minecraft 26.3 community port

This is an **unofficial, experimental community port**, not an NVIDIA release.
The current installer release is `v0.2.0-beta.1` in the community fork;
alpha 1 provided only a standalone JAR.
Beta 1 includes automatic optional MFG setup and `/rtx mfg` diagnostics.
The recorded RTX 3070 Ti session could not display the addon's native menu and
reported no active frame generation or DLSS 5 evaluations. This is an open
compatibility blocker, not a verified feature; see [MFG details](MFG_UNLOCKER.md).
An unreleased native candidate now builds from recovered, validated inputs and
passes isolated tests for actual-runtime menu drawing, Backspace and shutdown.
The private OptiScaler Vulkan path also passes startup and creates a real FG
feature on the 3070 Ti. A focused native probe completes 785 successful FG
evaluations with zero failed batches. An opt-in development loader passes its
private-Java smoke test; Minecraft presentation and visual validation are pending.
The first game run then failed early FG admission and ended in Vulkan device
loss. A revised native readiness gate passes a 60-frame private-JVM renderer
probe; game stability remains unverified. See [session evidence](PERFORMANCE_26_3.md).
The next game session records 26,794 successful FG evaluations with zero failed
batches and completed native shutdown. Display quality and frame-rate gains
remain unverified. Bright foliage after clock changes remains an open rendering
problem; the latest candidate keeps SHaRC warm with a brief shorter-history layer
and provides reversible foliage-cache diagnostics.
The development adapter now defaults its shared menu to Insert, preserves explicit saved keys, and
uses End for FG off/on. Startup and `/rtx mfg reset` clear the competing native
Remix FG request. The user now confirms the shared menu works. Provider
evaluations execute, but requests above 2x encounter repeated output-image reuse
and fall back to 2x; displayed interpolation remains unmeasured. `/rtx dlss5`
now exposes controls/status, but the tested provider rejects neural creation.
See [adapter evidence](MFG_UNLOCKER.md#neural-controls-and-current-provider-limitation).
The user also confirms `/rtx lighting cache off` removes bright grass in their
scene. The next packaged default uses that targeted foliage-query bypass;
performance impact and other scenes remain unmeasured.
A standalone direct-Remix FG adapter and Minecraft interpolation validation
remain incomplete; see the
[native adapter development guide](https://github.com/danzrikonew2/rtx-remix-minecraft/blob/feat/minecraft-26.3/native/mfg/README.md).
The objective is to preserve RTX Remix terrain, entities, materials, lighting,
and controls on Minecraft Java Edition 26.3 without changing a working 1.21.1
installation. Compilation is not proof of correct rendering.

## Combined candidate acceptance

Use only **RTX Remix Community 26.3 FG Adapter (Development)** and the existing
test world. Complete one pass, then quit Minecraft and Prism and report the rows
together. F8 remains the RTX rendering toggle. No long-running capture is needed.

| Check | Expected result |
|---|---|
| Insert persistence | Insert opens OptiScaler. Save that key, leave/reopen Minecraft once, and confirm it remains Insert. Other explicitly saved keys must also persist. |
| Grass/day-night | `/rtx lighting cache` reports false. Change day → midnight in the same view; the previously bright grass patches should stay fixed. |
| Exposure | In Image & Exposure enable Eye Adaptation, start with speed 2, and move from daylight into a dim, lit space and back. Report harsh jumps, pumping, excessive darkness or washed-out shadows. Completely unlit spaces still need a light. |
| FG controls/hand | Keep Remix native FG off. In OptiScaler use 2x, compare motion and the held item with End off/on. F3 need not double. Do not use 6x as a success test: repeated output reuse remains unresolved. |
| Reset | Change one mod option, run `/rtx settings reset`, then click Delete All User Settings in the opened native menu. Confirm mod defaults and native graphics defaults, with worlds/packs and the saved Insert shortcut preserved. |
| Neural page | `/rtx dlss5` opens the Minecraft page. Default is off. The isolated 3070 Ti provider reports unsupported if enabled, not Running. Restore off after any check. Report stale status, save errors, or an unexpected result. |
| Exit | Leave/reopen the world once, then quit the game and Prism normally. Report any crash/freeze and roughly when it occurred. Logs are reviewed after exit. |

This test validates the combined candidate, not an unsupported DLSS 5 rendering
claim or a measured MFG multiplier. Public beta assets remain separate until
the development candidate receives visual/stability acceptance.

## Source and collaboration

- Original upstream: <https://github.com/NVIDIAGameWorks/rtx-remix-minecraft>
- Public fork: <https://github.com/danzrikonew2/rtx-remix-minecraft>
- Development branch: `feat/minecraft-26.3`; upstream baseline: `72e5dce`.
- This branch incorporates Alex Melan's existing
  [PR #79](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/pull/79),
  including prerequisite PRs #77 and #78. Original authorship, sign-offs,
  licensing, and copyright notices are retained. The imported port head was
  `8ac3530c1a230ab8e6f2b876ea0219a4bd4c2c37`.

Work here builds on that effort: Windows paths with spaces, isolated 26.3
installation and developer profiles, Java 25 launch selection, consistency
checks, licensing repair, packaging validation, and public development guidance.
Coordinate with #79 rather than opening a competing full-port PR. A proposed
follow-up description is in [the draft PR document](MINECRAFT_26_3_DRAFT_PR.md).
No PR, issue, or comment has been submitted by this development session.

## Verified target dependencies

| Component | Version |
|---|---|
| Minecraft | 26.3, exact Fabric metadata constraint |
| Java | 25, 64-bit JDK and game runtime |
| Fabric Loader | 0.20.1 |
| Fabric API | 0.165.0+26.3 |
| Fabric Loom | 1.19.3, `net.fabricmc.fabric-loom` plugin |
| Gradle wrapper | 9.8.2 with pinned SHA-256 |
| Names | Unobfuscated game names; access widener uses `official` |
| Native runtime | Existing `packman/remix-sdk.packman.xml` pin |

Dependency artifacts resolved from the official Minecraft and Fabric services.
The JNI signatures, C API header, and native runtime pin are unchanged. The
renderer requires Windows and an NVIDIA RTX GPU supported by the upstream
runtime. Minecraft is forced onto OpenGL 4.5 for Remix image interoperability.

## Implementation and validation status

Checked entries describe completed implementation or executed checks, as named.
Unchecked runtime checks have not passed locally merely because code exists.

- [x] Clone official upstream; use a separate development branch and public fork.
- [x] Disable pushes through the NVIDIA `upstream` remote; leave `main` unchanged.
- [x] Establish 1.21.1 baseline: Java/JNI build and 800 JVM tests passed after
  correcting the runtime fetch command for Windows paths containing spaces.
- [x] Integrate existing 26.3 terrain capture through `SectionCompiler`, model
  parts and per-quad materials, with visibility supplied by `LevelExtractor`.
- [x] Integrate entity, block entity, hand, and item submit collection.
- [x] Integrate SDL3 keyboard/mouse gating and renderpearl/OpenGL presentation.
- [x] Integrate GPU animation forwarding and padded atlas texture capture.
- [x] Compile Java 25 and Windows x64 JNI bridge; pass 767 JVM tests, no failures.
- [x] Build Windows x64 package and pass `verifyPackageJar` inventory/license checks.
- [x] Native ABI probe returns success (`0`) through the built bridge.
- [x] Version-specific Prism instance, managed JDK, portable launcher, and
  Microsoft game directories; no adoption of 1.21.1 Prism instance names.
- [x] Local 26.3 Fabric startup; logs confirm RTX Remix API startup and GL interop.
- [x] User-confirmed terrain, hands and basic demo-scene rendering; screenshots
  show mobs, glass, vegetation, emissive lighting and smoke.
- [x] User-confirmed world reopening and RTX toggling without observed failures.
- [x] User-supplied `/rtx status` screenshot reports renderer initialized, SDK
  available, and world/entity/block-entity/particle/sky capture active.
- [x] Alpha 2 locked tooling checks: formatting, lint and types pass; 1,137
  tests and 178 subtests pass with the public commit-range check enabled.
- [x] Installer ZIP inventory and embedded mod identity verified by
  `verifyReleaseArchive`.
- [x] Extracted Windows batch installer passed Install, Repair and Upgrade
  in disposable x64 Prism folders, downloading real Java/Prism/Fabric API,
  pinning Java 25, selecting Minecraft/Fabric, and preserving 1.21.1 sentinels.
- [ ] Complete explicit overlay, fullscreen, focus and resize acceptance tests.
- [ ] Complete repeated world-transition and resource-lifetime testing.
- [ ] Measure GPU memory, frame pacing, and chunk-rebuild behavior on 8 GB VRAM.
- [ ] Complete Microsoft launcher end-to-end installation testing.

Build logs are retained locally under `build/port-validation/`, JVM XML results
under `build/test-results/test/`, and the HTML report under
`build/reports/tests/test/`. These are ignored outputs, not published source.
The imported PR author reports in-game validation; those results are separate
from this fork's local validation.

A first manual stability/VRAM diagnostic is recorded in
[the performance baseline](PERFORMANCE_26_3.md). It found Java heap compaction
pressure and limited VRAM headroom at 32 chunks. Controlled comparisons and
long-session leak validation remain incomplete.

The user subsequently reported stutters, uneven flying and worsening perceived
FPS. The stopped world's weather data also confirmed an active thunderstorm
during the dark-daytime report. Clear-noon visual acceptance remains pending;
use [daylight diagnostics](RENDERING_DIAGNOSTICS.md#dark-daytime-and-weather)
and `/rtx sky status` in a build containing that command.

Follow-up: clearing weather restored daylight. The user reported large terrain
gaps after RTX off/on and reloads. A deferred geometry-invalidation ordering
fix is implemented with 771 JVM tests passing; manual toggle/reload acceptance
is still pending. Stutter with RTX off was also reported and does not by itself
identify vanilla Minecraft as the cause, since the mod remains loaded.

The installer smoke test used temporary APPDATA, LOCALAPPDATA and TEMP roots
inside ignored build outputs. It ran the archive's actual `install.bat` under
Windows PowerShell 5.1 with `-Unattended -Launcher Prism`. No sign-in or game UI
was automated. Fresh install downloaded the official prerequisites; Repair and
Upgrade reused the instance and selected Java 25. This verifies installer
staging, not a new authenticated game launch from that disposable profile.

The user performed the demo-scene, reopen and toggle checks on 2026-10-31
using the isolated Prism development instance and supplied screenshots. These
are manual smoke-test results, not automated coverage or a long-duration soak.
The status screenshot reports 1,372 loaded chunks and 4,212 retained pages;
these are one scene's counters, not evidence of stable resource use over time.

## Known incomplete behavior

The imported `RemixSubmitCollector` currently leaves burning-entity flames,
leashes, moving-piston block submits, text background quads, and arbitrary
Fabric custom submit phases uncaptured. Debug outlines and vanilla shadow
submits also have empty handlers: Remix traces shadows, and the block-damage
pass handles breaking cracks separately. Do not infer all empty submit handlers
are equivalent or suppress missing geometry to make a test pass.

Stained glass appears insufficiently tinted in the user's demo scene. This is
accepted as a deferred visual issue; resource-pack/material tuning is a possible
remedy, not a confirmed cause. No tint changes were made for this milestone.

The 1.21.1 custom weather renderer was removed by the imported migration;
weather appearance and parity need review. Detailed water, glass, underwater views,
armor, animated textures, shadows, DLSS, and window/input transitions still
require a local visual acceptance pass. The imported port describes the new
redstone torch shell as looking like a glowing cube under path tracing.

No performance optimization or leak-free stability claim has been established
for this fork. No GPU restrictions or frame-generation behavior were bypassed.
ARM64 packaging has not been tested here.

## Build and package

Install a 64-bit JDK 25, Git, and Visual Studio C++ Build Tools. Set `JAVA_HOME`
for this shell to that JDK; keep Java 21 available for separate 1.21.1 work.
From the repository root on the development branch:

```powershell
git switch feat/minecraft-26.3
.\gradlew.bat build test -Parch=win64 --console=plain
.\gradlew.bat verifyReleaseArchive -Parch=win64 --console=plain
.\tools\rtx.bat check --tests
```

Gradle obtains the pinned runtime and runtime textures through public Packman
packages. Runtime staging may create a read-only junction into the shared
Packman cache; never modify its target. Build commands stage only this
checkout's `run/` directory. Stop this checkout's game before building again.

`build/libs/` contains lightweight development JARs; they require staged native
files. **Use the packaged JAR in `build/distributions/` for manual installation**;
it contains the matching bridge, runtime, textures, and licenses. Fabric API
is a separate dependency. Do not upload game binaries, launcher accounts, saves,
or proprietary runtime files to Git. This fork publishes source only.

## Separate installation

**Recommended installer:** download the Windows x64 installer ZIP from the
[community releases](https://github.com/danzrikonew2/rtx-remix-minecraft/releases),
extract it completely, and run `install.bat`. Select Install and Prism Launcher.
The ZIP includes the scripts, verified mod under `mods/`, player/developer docs,
changelog and license notices. The standalone JAR and GitHub source-code archives
do not contain this installer. The installer pins Java 25 in its isolated
instance rather than inheriting an existing launcher's Java 21 setting.

**Manual JAR alternative:**

1. In Prism, create a **new** instance named `RTX Remix Community 26.3 Test`.
   Select Minecraft 26.3 and Fabric Loader 0.20.1; select a 64-bit Java 25 runtime.
2. Add Fabric API 0.165.0+26.3 and the Windows x64 packaged JAR from
   `build/distributions/` to that instance's mods. Use no other rendering mods.
3. Launch using a Microsoft account that owns Minecraft. Keep the new game
   directory, saves, configs, and runtime separate from 1.21.1. Create a fresh
   creative test world; do not upgrade original worlds in place.
4. Development alternative: `tools\rtx.bat prism signin`, close Prism after
   signing in, then `tools\rtx.bat launch`. The portable profile lives in
   `run-prism/instances/rtx-remix-26.3-dev/.minecraft`; installed Prism uses a
   checkout-specific instance with the same versioned prefix.

For a custom Prism executable set `prism.executable` in ignored
`tools/config.local.json`. Do not commit that personal path. The developer
`install` command defaults to `%APPDATA%\.minecraft-rtx-remix-26.3`; explicit
`--game-dir` must name a disposable 26.3 directory. The public installer uses
`RTX Remix Community 26.3 Beta (Experimental)` in Prism, and a separate
`.minecraft-rtx-remix-26.3` game directory in the Microsoft launcher. Its
installer validation scope is recorded in the checklist above.

## Runtime acceptance and bug reports

Record actual results for each check; a launch alone is insufficient:

1. Confirm log versions, no mixin failures, and successful renderer/SDK init.
   Run `/rtx status` in a loaded world.
2. Inspect terrain near/far, chunk loading, edits/rebuilds, unloads, caves, and
   frustum edges while moving. RTX must show actual blocks and terrain.
3. Place opaque blocks, glass, water, leaves, emissive blocks, signs, chests,
   armor stands, mobs, items, and animated blocks in a fresh creative world.
4. Check first-person hands, equipment, particles, day/night sky, sunlight,
   material animation, reflections, refraction, underwater views, and DLSS.
5. Test Alt+X open/close, mouse capture, normal input after closing, `/rtx on`,
   `/rtx off`, F8, resizing, focus, fullscreen, and settings changes.
6. Repeat world exits/joins and chunk rebuilds. Monitor VRAM, resource counts,
   allocation failures, device loss, stalls, and process shutdown.

Report failures in this fork with the commit, exact dependency versions,
reproduction steps, expected/actual result, GPU/driver, screenshots, and
sanitized relevant portions of `logs/latest.log` or crash reports. Remove
account identifiers, tokens, personal paths, and server addresses before posting.
Do not publish full launcher command lines or accounts.json. Use the matching
JDK's `javap -p -c` to inspect the actual 26.3 injection targets before changing
mixins. JVM tests do not exercise mixin injection or prove visual correctness.

## Contributing

An [experimental MFG Unlocker integration](MFG_UNLOCKER.md) adds automatic,
opt-in installation and private-Java loading for Prism. Native loading has a
standalone smoke pass; actual Minecraft FG/DLSS 5 rendering is not verified.
It is separate from the established 26.3 rendering acceptance and does not
alter existing Alpha 2 release assets.

Branch from `feat/minecraft-26.3` in your own fork and open review against this
fork's development branch. Read [CONTRIBUTING.md](../CONTRIBUTING.md) and the
nearest `AGENTS.md`; preserve render-thread ownership, bounded queues, mesh
reference counts, and Java/JNI ABI contracts. Sign off meaningful commits and
include executed test results with limitations. Keep changes focused on a
reproduced problem. Coordinate with upstream PR #79 before proposing duplicated
work to NVIDIA. Original Apache-2.0 licensing and third-party notices apply.
