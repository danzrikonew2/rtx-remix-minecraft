**Unofficial experimental community prerelease. Not an official NVIDIA release.**

Beta 2 combines the Minecraft 26.3 development updates and restrained emissive
Night Vision in `feat/minecraft-26.3`. It incorporates Alex Melan's upstream
renderer migration in PR #79 and prerequisites #77/#78, preserving original
attribution, copyright and licenses.

## Install or update

Requires Windows x64, a supported NVIDIA RTX GPU/driver, Java 25, Minecraft
26.3, Fabric Loader 0.20.1 and Fabric API 0.165.0+26.3. A Microsoft account
that owns Minecraft: Java Edition is required.

Download the **Windows x64 installer ZIP** from Assets, extract it completely,
then run **`install.bat`**. Choose Prism Launcher for a new installation, or
Upgrade for the existing community beta profile. Sign into Prism and launch
**RTX Remix Community 26.3 Beta (Experimental)**. Keep working Minecraft 1.21.1
installations separate; back up test worlds and custom settings before updating.
GitHub's automatic source-code ZIP is not the installer.

The standalone **`-win64.jar`** is an alternative for an existing isolated
26.3 Fabric instance with the dependencies above. Close Minecraft, back up the
old Remix JAR outside `mods/`, then replace it with the new JAR. Keep only one
version of the mod in `mods/`. The JAR bundles the native Remix payload, but
does not contain the batch installer or install optional MFG/private Java.

## Changes since Beta 1

- **Experimental Night Vision:** a weak albedo-colored emission floor for
  opaque/cutout block-atlas materials. Default strength is 0.10, capped at 0.20.
  Authored glow texels receive no boost; PBR descriptors and animation remain
  attached. Original materials restore when the effect ends. This accepts
  physical emission/bounce; it is not adaptive or camera-only illumination.
- **Status effects:** candidate blindness/darkness distance fog and fades,
  vanilla glowing-entity outline submission, and animated burning-entity flames.
- **Lighting and image controls:** eye-adaptation enable/speed controls with a
  gentler speed-2 default, sparse tracing controls, targeted foliage-cache query
  bypass after the user's bright-grass comparison, and clock-transition handling.
- **Background and memory handling:** minimized rendering capped at 1 FPS,
  bounded retirement of unused dynamic entity textures, removal of a redundant
  atlas upload, and retained resource owners when native destruction fails.
  FPS/VRAM improvements have not been measured across scenes.
- **Compatibility fixes:** safe save-wide zone migration, 26.3 window discovery,
  updated shipped lighting defaults that preserve edited profiles, beacon
  surface-emission corrections, and startup/glint-capture hardening.
- **Recovery and diagnostics:** `/rtx settings reset`, `/rtx mfg reset`,
  `/rtx temporal` and experimental `/rtx dlss5` status/controls. Development
  adapter menu defaults now use Insert and preserve explicitly saved keys.

## Night Vision controls and one test pass

`/rtx nightvision` reports the current setting. Use
`/rtx nightvision strength 0.05` to reduce the default, or
`/rtx nightvision strength 0` to disable this approximation. Strength is a
session-only adjustment; these commands do not grant a potion.

In a disposable world with cheats, use
`/effect give @s minecraft:night_vision 60 0 true`. Compare strength 0/0.10 in
a cave, near torches/lanterns/glowstone, daylight, night and underwater, with
and without a PBR pack. Check that ordinary blocks do not overpower real glow.
Then check removal/expiration, RTX off/on, reload, animation and memory/frame
times. Finish the [combined acceptance list](MINECRAFT_26_3_PORT.md#combined-candidate-acceptance)
and [effect checks](STATUS_EFFECTS_26_3.md#one-combined-manual-check), then report
the results together. Start with FG off before comparing DLSS/RR, sparse
tracing and any separately installed experimental adapter.

## Testing and remaining limits

- Java regression suite: **845 passed, 1 optional GPU test skipped**. New tests
  cover emission bounds/precision, authored-glow protection, material descriptors,
  animation/padding and strength/duration behavior.
- Installer archive verification checks scripts, guides, licenses and an
  identical embedded mod JAR. Full tooling checks are part of the release gate.
- The pinned native runtime accepted HDR texture creation/patches, same-handle
  material changes/restoration and 60 hidden submits/presents. The harness
  emitted the existing device-object cleanup diagnostic at DLL unload.
- These checks are not visual acceptance or a measured FPS gain. Night Vision
  adds temporary HDR atlas memory and can change bounce/reflections, shadow
  contrast and cache convergence. Fade/strength changes upload the atlas;
  performance and large PBR packs need an in-game comparison. Glass/water,
  separate entity textures and particles are outside this emission floor.
- Conduit brightening, darkness lightmap pulse and nausea/world-projection
  parity remain incomplete. Temporal shimmer and chunk-loading stutter are
  unresolved; no universal performance or ghosting fix is claimed.

## MFG and DLSS 5 scope

**This release does not certify MFG or DLSS 5 support.** `install-mfg.bat`
selects the optional checksum-pinned **standalone MFG Unlocker 1.7.0** route
with instance-local Java. Its native menu/FG were blocked in the recorded
RTX 3070 Ti game test. Its default/reset menu key is Backspace.

The separately staged **OptiScaler development adapter is not included in this
installer**. Its current defaults are Insert for the shared menu and End for
FG, with Remix native FG kept off. Provider evaluations were recorded, but
displayed interpolation and frame-rate gain remain unverified; requests above
2x encounter repeated output-image reuse and fall back to 2x.
`/rtx dlss5` exposes experimental status/controls; tested providers reject
neural feature creation. See [MFG setup and recovery](MFG_UNLOCKER.md).

Original upstream: [NVIDIA RTX Remix Minecraft](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft).
Bundled NVIDIA runtime components retain their own license terms. Optional
MFG Unlocker retains Michael Robles's MIT license and is downloaded only when
selected. No worlds, Minecraft account data or development captures are included.
