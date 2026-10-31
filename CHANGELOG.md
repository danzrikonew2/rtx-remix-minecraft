# Changelog

Notable changes to RTX Remix for Minecraft, newest first. Changes that a
player, a map author, or a contributor would notice go here; internal
refactoring does not.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
The version in a release is the `mod_version` in `gradle.properties`, and it is
also part of every mod file name.

## Unreleased

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
