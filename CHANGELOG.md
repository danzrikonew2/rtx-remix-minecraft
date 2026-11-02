# Changelog

Notable changes to RTX Remix for Minecraft, newest first. Changes that a
player, a map author, or a contributor would notice go here; internal
refactoring does not.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
The version in a release is the `mod_version` in `gradle.properties`, and it is
also part of every mod file name.

## Unreleased

- Correct the development adapter's shared-menu shortcut from automatic Insert
  to Backspace, with End as the independent adapter FG toggle. Preserve custom
  shortcuts and back up migrated INIs. Clear conflicting native Remix FG at
  startup and add `/rtx mfg reset` recovery plus route-specific help. A hidden
  pinned-runtime test verifies menu open/close and FG off/on; game display and
  performance acceptance remain pending.
- Wait for MFG's actual early Vulkan startup prerequisites before loading Remix,
  and stop renderer initialization if private-device admission fails. The first
  Minecraft adapter run generated no frames and ended in device loss; a revised
  private-JVM renderer probe passes admission and 60 hidden presents. Game
  stability remains unverified.
- Retain warm surface-lighting caches after abrupt Overworld clock or weather
  changes. A short settling layer uses 8-frame SHaRC accumulation/stale age,
  then restores the authored settings. It replaces the ineffective reset-pulse
  experiment; visual confirmation remains pending. Add `/rtx lighting cache
  off|on` and resolved status for an in-place foliage-cache comparison.
- Record 26,794 successful FG evaluations in the experimental Minecraft session
  with zero failed batches. Generated display quality and frame-rate gain remain
  unverified. Sapling/resource-pack behavior is deferred and unchanged.

- Verify 785 successful FG provider evaluations and 785 submitted batches on
  RTX 3070 Ti in the focused native Remix probe, with zero failed batches.
  Add an opt-in, manifest-pinned OptiScaler/MFG development loader and local
  staging helper. Private-Java loading/status checks pass; Minecraft display
  behavior and any frame-rate multiplier remain unverified.

- Add guarded private Streamline Vulkan startup for the experimental MFG adapter.
  An isolated 3070 Ti probe passes startup/program/buffer checks and creates a
  real NVIDIA FG feature. Streamline suppresses interpolation while the probe
  is unfocused; the public installer
  and working game profiles are unchanged.

- Add source-only native MFG build-input recovery and a runtime-bound Vulkan
  menu adapter, with explicit registration and retirement through the JNI bridge.
  Isolated tests against the pinned runtime verify menu drawing, Backspace and
  shutdown. FG/DLSS 5 remains unverified and the native FG adapter is incomplete;
  this candidate is not substituted into the public beta installer.

- Include abrupt Overworld clock changes in the short volumetric-history
  settling window. Ordinary ticks and midnight wraparound keep normal history.
  This is a volumetric mitigation; surface sparkle and delayed ground-lighting
  convergence after time commands remain pending native/visual validation.

- Track shipped lighting-profile hashes so unchanged recorded defaults receive
  updates without replacing edited or unrecognized legacy files (#20).
- Remove an unused intermediate full-atlas GPU upload and avoid creating
  per-sprite SSS buffers for specular maps with no SSS data (#82 investigation).
  Actual GPU-memory impact still needs measurement with the reported pack.
- Classify both vanilla beacon beam surface pipelines as emissive (#29, partial).
  Dynamic beam lights and radiance tuning remain unimplemented.

- Fix upstream #69: skylight snapshots capture each publication's current
  minimum section height, including removed columns and immutable older views.
- Mitigate upstream #54: failed renderer initialization disables RTX capture,
  keeps SDK file availability distinct from startup success and rejects
  re-enabling an unavailable renderer instead of hiding vanilla terrain.
- Mitigate upstream #65/#80: skip standalone GLINT-blended overlay geometry.
  Base item surfaces remain captured; standalone enchantment glint is omitted
  until its decal semantics are supported. Visual acceptance remains pending.

## 0.2.0-beta.1 - 2026-11-01

### Installation and diagnostics

- Add `install-mfg.bat` for automatic opt-in Prism addon setup and isolate beta
  installations from earlier installer profiles.
- Add `/rtx mfg` native menu diagnostics and a reversible `ResetMenu` repair
  action that backs up the UI INI and restores Backspace without resetting
  rendering preferences.
- Document the observed MFG compatibility blocker: the DLL loads on the test
  RTX 3070 Ti, but its native menu does not attach and no frame generation or
  DLSS 5 evaluations were recorded. Beta 1 does not claim these features work.

### Experimental integrations

- Add opt-in, pinned MFG Unlocker 1.7.0 installation for Prism, with checksum
  validation, private Java, explicit pre-Remix loading and a reversible enable
  marker. Actual FG/DLSS 5 compatibility remains unverified; this is not bundled
  into already published Alpha 2 assets.

### Fixed

- Send one final unchanged retained view-model pose after a changed description,
  providing an explicit stationary transition to the runtime. This is a targeted
  hand-history mitigation pending in-game validation, not a confirmed jitter fix.

- Copy fixed-size JNI camera, instance and dome matrices with array-region
  reads instead of critical heap pointers. This removes unnecessary critical
  array access; its effect on gameplay stutters remains unmeasured.

- Defer terrain recapture until Minecraft 26.3 finishes geometry invalidation.
  Previously the next extraction cancelled rebuilds queued by RTX re-enabling
  or terrain/material reloads, potentially leaving large terrain gaps. JVM
  regression tests pass; in-game acceptance of this fix remains pending.

### Added

- `/rtx sky status` reports weather, clock, sun angle and submitted direct sunlight
  to help distinguish storm-darkened daytime from a sky rendering problem.

### Developer tooling

- Pace terrain capture ingestion between sections, release consumed batch references
  promptly, and skip reconciliation allocations for sections with no old or new
  lights after cancelling any pending task. Add deferred/unchanged capture and
  empty-light-work counters for consolidated performance testing.

- Add opt-in first-person transform fingerprint diagnostics to distinguish
  captured transform changes from visual shimmer. Reuse the hand model-view
  snapshot matrix; no measured frame-time improvement or jitter fix is claimed.

- Record board-wide VRAM used/total, GPU utilization and minimum recording-window
  memory headroom in benchmark telemetry.
- Correct JFR physical-memory reporting: OS-wide RAM is not Minecraft RSS.
  Summary JSON now uses `system_memory`; the memory CLI documents its scope.
- Document the first manual 26.3 stability and 8 GiB VRAM diagnostic, including
  observed Java heap compactions, memory trends and limitations. No renderer
  performance or quality defaults are changed by this diagnostic milestone.

## 0.2.0-alpha.2 - 2026-10-31

### Added

- Windows x64 installer ZIP containing `install.bat`, PowerShell installer,
  migration helper, verified packaged JAR, documentation and license notices.
- `verifyReleaseArchive` checks required archive contents and verifies that its
  mod JAR is identical to the package that passed runtime inventory checks.

### Fixed

- Player guides now distinguish the installer ZIP, standalone manual-install
  JAR, and GitHub's source-code archives, and link to the community releases.
- Corrected profile names, isolated game paths, platform support, Java versions
  and outdated claims that the Microsoft launcher shares existing worlds.
- Pin the isolated x64 Prism instance to Java 25 so global Java 21 settings
  from a working 1.21.1 installation cannot prevent it from starting.

Rendering implementation and known visual limitations are unchanged from alpha 1.

### Validation

- Extracted batch installer Install, Repair and Upgrade passed in disposable
  x64 Prism user folders using real prerequisite downloads. Correct game/loader
  versions, Java 25 pin, mod identity and preservation of 1.21.1 sentinels passed.
- Tooling checks passed 1,137 tests and 178 subtests. Microsoft launcher
  end-to-end installation remains untested.

## 0.2.0-alpha.1 - 2026-10-31

Unofficial community Minecraft 26.3 port, published as an experimental
Windows x64 prerelease in the community fork. This is not an NVIDIA release.
The renderer migration incorporates Alex Melan's upstream PR #79 and its
prerequisites #77 and #78, with attribution and sign-offs preserved.

### Changed

- Targets Minecraft Java Edition 26.3 on Fabric Loader 0.20.1, Fabric API
  0.165.0+26.3 and Java 25, through the OpenGL backend that RTX Remix interop
  needs. Entities, block entities, held items and the breaking crack are
  captured from 26.x's extract and submit pipeline, and animated sprites are
  forwarded from the GPU-side animation tick.
- The Copper Beacon lens textures are 48 pixels square, the same six texels
  drawn 8 by 8, so they no longer cap the block atlas at one mip level.
- Installer and development tooling use Java 25 and version-specific profiles
  and game directories, preserving existing 1.21.1 installations.

### Added

- Block lights for the copper torch and copper wall torch, and glowing flames
  for the copper lantern in every oxidation stage.
- Community [development and test report](docs/MINECRAFT_26_3_PORT.md), isolated
  installation instructions, and an unsubmitted draft PR description.
- Regression coverage that installation and instance removal preserve a
  neighboring 1.21.1 installation.

### Fixed

- Distant blocks no longer pick up dark outlines and colour from their atlas
  neighbours: every atlas the mod copies fills the padding vanilla 26.x leaves
  around each sprite.
- Runtime fetching from Windows checkout paths containing spaces.
- Restored the access-widener license header and aligned build/launcher checks
  with the unobfuscated game and exact Minecraft 26.3 dependency.

### Validation

- Java/native Windows x64 build, 767 JVM tests, native compatibility probe,
  and packaged runtime/license inventory checks passed.
- Locked tooling checks passed: 1,135 tests, 178 subtests, and one skip.
- Local startup logs confirm RTX Remix initialization. The user confirmed
  basic scene rendering including hands, reopening the world, and RTX toggles;
  their status screenshot reports the renderer initialized and SDK available.

### Known limitations

- Stained glass appears weakly tinted; deferred with the user's agreement.
- Burning-entity flames, leashes, moving-piston block submits, text backgrounds,
  and arbitrary Fabric custom submit phases remain incomplete.
- Extended stability, detailed transparency/weather parity, DLSS, window/input
  transitions, ARM64, and full installer execution are not fully validated.

## 0.1.0 - 2026-10-23

The first public release, a beta.

### Added

- Path-traced rendering of Minecraft Java Edition 1.21.1 through RTX Remix:
  terrain, entities and block entities, particles, the sky, and clouds, with
  baseline LabPBR textures built into the mod JAR through Fabric's `fabric` pack.
- Lighting that follows the game: time of day, weather, being underwater, and
  per-dimension skies, with the End's constant dark dome and a black sky with
  no ambient where a dimension has none. Map authors can give zones and biomes
  their own looks through gameplay-driven conf profiles installed beside the
  mod, with an authoring guide.
- Block lights from resource-pack rules, a Light Reach setting and an Auto
  light cull distance, flames and lights on hand-held items, and the `G` key
  to put out and relight what the local player holds.
- The Copper Beacon, a placeable and craftable directional lamp: dye and
  saturation, intensity, cone angle, redstone control, and static, rotating,
  oscillating, or patrolling motion that every player sees the same way.
- An RTX Remix settings screen in Options, a button into Remix's own Graphics
  Settings, the `/rtx` command tree, `F8` to toggle path tracing, and
  session-only quality presets through `/rtx preset <name>` or
  `-Drtxremix.preset=<name>`.
- Camera paths: record a flythrough by walking it and replay it on wall-clock
  time or one fixed step per frame. Still shots keep a pose together with its
  time of day, weather, path-tracing state, and cloud style.
- Procedural clouds, selectable in place of vanilla's.
- Steadier frames at high render distance: paced chunk delivery and unloads
  in single-player, a hold behind the loading screen after joining a world,
  and allocation-free hot paths that keep garbage collection out of the frame.
- A self-contained mod JAR that any Fabric launcher can install on its own,
  and a Windows installer for Prism Launcher and the Microsoft launcher that
  sets up Java, Fabric, the mod, and tuned JVM arguments, and repairs,
  upgrades, uninstalls, or exports an install.
- Developer tools under `tools/` through the `rtx` CLI: launching, benchmarks
  on the pinned demo world, built by [BlockWorks](https://www.blockworks.uk/),
  and the LabPBR art pack, created by an art team at NVIDIA, or on locally
  staged fixtures, JFR and Tracy profiling, and the contributor checks.
- Developer tools launch Minecraft through a Prism Launcher data folder for
  each checkout, signed in to a Microsoft account that owns Minecraft: Java
  Edition. `tools\rtx.bat prism signin` signs a checkout in, and
  `launch.jvmArgs` carries developer JVM options.
