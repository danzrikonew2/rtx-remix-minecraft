**Unofficial experimental community prerelease. Not an official NVIDIA release.**

Minecraft Java 26.3 compatibility beta, incorporating Alex Melan's upstream
renderer migration in PR #79 and prerequisites #77/#78, with original attribution
and licenses preserved.

## Install

Requires Windows x64, a supported NVIDIA RTX GPU/driver, Java 25, Minecraft 26.3,
Fabric Loader 0.20.1 and Fabric API 0.165.0+26.3. You need a Microsoft account
that owns Minecraft: Java Edition.

Download the **Windows x64 installer ZIP** from Assets and extract it completely.
Run `install.bat` for ordinary setup, or **`install-mfg.bat`** for Prism setup
with the experimental MFG Unlocker addon selected automatically. The installer
sets up the dependencies and creates **RTX Remix Community 26.3 Beta (Experimental)**.
Sign into Prism, then launch that instance. Earlier profiles remain separate.
Keep your working 1.21.1 installation and worlds separate too.

The standalone JAR is an alternative for an existing isolated 26.3 Fabric
installation with those dependencies already installed. Put it in `mods/`;
it does not contain batch installers and does not set up MFG's private Java.
Do not install both formats into the same instance.

## Changes

- Terrain recapture fix after RTX toggles and geometry invalidation.
- Terrain ingestion pacing, empty-light reconciliation skips and JNI matrix-copy
  changes. Some chunk-loading stutter remains; no universal FPS gain is claimed.
- Automatic, checksum-pinned MFG Unlocker 1.7.0 setup using private Java.
- `/rtx mfg` reports native graphics hook flags, shortcut code and menu frame
  counters. The addon's `ResetMenu` installer action backs up its UI preferences
  and restores Backspace without resetting rendering preferences.

## Important MFG limitation

**MFG/DLSS 5 is not confirmed working. The native MFG menu is unavailable in
the recorded RTX 3070 Ti test.** The DLL loads and NGX detours install, but status
reports no active wrapper call and no active frame generation; DLSS 5 evaluations
are zero. Resetting the shortcut cannot attach a missing native overlay.
This beta publishes the integration for testing and collaboration, not as a
working frame-generation unlock. Disable it if it causes problems.

Manual earlier tests confirmed world reopening and RTX toggling; a later
performance pass reported a stable hand. These observations do not certify all
scenes, hardware, or temporal effects. Package/build and automated checks do not
validate generated frames or native overlay rendering.

See [MFG setup, observed blocker and recovery](https://github.com/danzrikonew2/rtx-remix-minecraft/blob/v0.2.0-beta.1/docs/MFG_UNLOCKER.md),
[port status](https://github.com/danzrikonew2/rtx-remix-minecraft/blob/v0.2.0-beta.1/docs/MINECRAFT_26_3_PORT.md)
and [changelog](https://github.com/danzrikonew2/rtx-remix-minecraft/blob/v0.2.0-beta.1/CHANGELOG.md).
Original upstream: [NVIDIA RTX Remix Minecraft](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft).
Bundled NVIDIA runtime components retain their own license terms; MFG Unlocker
retains Michael Robles's MIT license and is downloaded only when selected.
