# Minecraft 26.3 Community Port - Alpha 1 (Windows x64)

**Unofficial experimental community prerelease. Not an official NVIDIA release.**
This port incorporates Alex Melan's renderer migration from upstream PR #79,
including #77 and #78, preserving the original attribution and licenses.

## Requirements and installation

- Windows x64 and a supported NVIDIA RTX GPU/driver.
- Minecraft Java Edition **26.3**, **Java 25**, **Fabric Loader 0.20.1**,
  and **Fabric API 0.165.0+26.3**.
- A Microsoft account that owns Minecraft: Java Edition.

Create a **new Prism instance** for Minecraft 26.3, install Fabric Loader
0.20.1, and select a 64-bit Java 25 runtime. Put the release's `win64.jar`
and Fabric API 0.165.0+26.3 in that instance's mods folder. The packaged mod
JAR includes the matching native Remix runtime and JNI bridge and extracts
them on first launch. It is large because it includes those runtime assets.
Do not install the lightweight JAR from `build/libs/` alone.

Keep all game files, saves and runtime configuration separate from 1.21.1.
Use a fresh test world. Do not add Sodium, Iris or OptiFine to baseline tests.
The release does not include Minecraft binaries, account data, or saved worlds.

## Changes and executed checks

The renderer targets the 26.3 terrain and extract/submit entity pipelines,
SDL3 input and renderpearl/OpenGL interop. Sprite animation and atlas padding
capture are migrated. Developer and installer profiles select 26.3/Java 25
and use isolated game directories; Windows runtime fetching handles spaces.
JNI signatures and the pinned Remix API/runtime are unchanged.

- Java and Windows x64 JNI compilation, 767 JVM tests, native ABI probe, and
  packaged runtime/license inventory validation passed.
- Locked tooling formatting, lint, types, 1,135 tests and 178 subtests passed;
  one tooling test was skipped.
- Local launch logs confirm Remix initialization. User testing confirmed basic
  terrain/demo-scene rendering and hands, world reopening, and RTX off/on
  toggles. The supplied status screenshot reports renderer initialized and
  SDK available. These are smoke tests, not a complete compatibility guarantee.

## Known issues

Stained glass appears insufficiently tinted; its cause is not confirmed.
Burning-entity flames, leashes, moving-piston block submits, text backgrounds,
and arbitrary Fabric custom submit phases are incomplete in the imported port.
Weather parity, detailed transparency and material coverage, DLSS, overlay and
window transitions, long-session resource behavior and performance need further
testing. ARM64 and end-to-end installer execution are not validated here.

Use `/rtx status`, `/rtx on`, `/rtx off`, F8 and Alt+X during testing. Report
failures to the community fork with the release/commit, dependency versions,
GPU/driver, reproduction steps and sanitized logs/screenshots. Never post
accounts.json, access tokens, or full launcher command lines.

- [Development and installation guide](https://github.com/danzrikonew2/rtx-remix-minecraft/blob/feat/minecraft-26.3/docs/MINECRAFT_26_3_PORT.md)
- [Changelog](https://github.com/danzrikonew2/rtx-remix-minecraft/blob/feat/minecraft-26.3/CHANGELOG.md)
- [Original NVIDIA upstream](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft)
- [Existing upstream port PR #79](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/pull/79)

Apache-2.0 source licensing and all original copyright and third-party notices
are retained. Bundled NVIDIA runtime components retain their own license terms.
