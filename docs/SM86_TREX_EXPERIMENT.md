# Experimental direct-.trex DLSS Frame Generation proxy for RTX 20/30

**Status: installer tooling only. Loading, native DLSS-G enablement, generated frames and in-game compatibility are NOT verified for Minecraft Java 26.3 / RTX Remix v0.1.1.**

This is an optional comparison to the separate, existing [OptiScaler/MFG Vulkan adapter](../native/mfg/README.md). It is **not** the default Minecraft installer or a certified FG release.

## Choice of DLL and runtime compatibility

The Reddit [October 2026 RTX Remix experiment](https://www.reddit.com/r/OptimizedGaming/comments/1x5ejsk/tip_for_those_people_using_the_rtx_2030_series/) points to the author's [`dlssg_for_sm86` sm86-7 Vulkan release](https://github.com/pipotoufikxyz-lgtm/dlssg_for_sm86-MFG-version/releases/tag/sm86-7). **That release specifies `version.dll` and `dlssg_sm86.ini`**, not the unrelated `dlssg_to_fsr3.dll` / `_nvngx.dll` pair. The optional script downloads exactly that pinned release; it does not substitute unknown DLLs or modify any existing NVIDIA provider.

GitHub-published ZIP asset SHA-256, checked 2026-11-08:

`fc394c984d77aba9948c66dc85833a22fdf264381137e921d82ca0d3520c429c`

It is **compatible with the author's stated RTX Remix/Vulkan target**, but **not yet demonstrated to be compatible with this Minecraft Java launcher**. Java runs in `javaw.exe`, while the mod loads its pinned runtime at `<gameDir>/remix-sdk/d3d9.dll`. **Merely copying a DLL into `.trex` does not cause a Java/Vulkan process to load that DLL.** NVIDIA's generic 32-bit Remix layout includes a `.trex` renderer directory, whereas newer 64-bit runtimes may use a flat layout. This script deliberately refuses to invent a missing `.trex` directory or overwrite the runtime to simulate compatibility.

The Minecraft mod's `NativeExtractor` fully replaces `remix-sdk` on first launch and runtime upgrades. Do not copy files before the new runtime is extracted. The optional installer records the current `d3d9.dll` SHA-256 and warns when the runtime changes.

## Included with developer release ZIP

The development installer archive includes these **two scripts, not a redistributed third-party DLL**:

- `install-sm86-trex.bat` — interactive/manual opt-in helper.
- `install-sm86-trex.ps1` — pinned download, install, inspect and verified removal.

`install.bat` does not call them automatically. The script writes only two pinned files, if an existing runtime `remix-sdk/.trex` directory is present:

```text
<gameDir>/remix-sdk/.trex/version.dll
<gameDir>/remix-sdk/.trex/dlssg_sm86.ini
<gameDir>/rtx-remix-addons/sm86-trex/installed.json
```

It verifies the ZIP hash before extraction, refuses an unowned existing DLL, does not change `d3d9.dll`, does not bypass antivirus, leaves known-good OptiScaler/MFG untouched, and can remove only files that still match its installation record.

## Manual install after extracting the runtime

Use **a disposable Minecraft 26.3 Prism instance** and do not combine this experiment with the custom OptiScaler/MFG route. After opening the game once to extract the runtime, close Minecraft and Prism. From the extracted development installer ZIP:

```powershell
.\install-sm86-trex.ps1 -Action Inspect -GameDir "C:\path\to\Prism\instances\Test-26.3\.minecraft"
.\install-sm86-trex.ps1 -Action Install -GameDir "C:\path\to\Prism\instances\Test-26.3\.minecraft"
```

Or `install-sm86-trex.bat "C:\path\to\Prism\instances\Test-26.3\.minecraft"`.

To remove:

```powershell
.\install-sm86-trex.ps1 -Action Remove -GameDir "C:\path\to\Prism\instances\Test-26.3\.minecraft"
```

If it reports that `remix-sdk/.trex` is missing, **stop**. The direct-.trex method does not match this runtime layout; use the main OptiScaler/MFG adapter integration instead. Do not manually copy `version.dll` beside your system `javaw.exe` or replace OS DLLs.

## GPU acceptance gate

1. Verify the exact injected module appears in **the actual Minecraft rendering process**, not just on disk. If it does not load, the method has failed for this build.
2. Verify feature creation and real NGX DLSS-G evaluations, not simply an enabled Alt+X checkbox.
3. Compare FG off/on with real presented FPS, frame pacing, input latency, VRAM, and frame uniqueness. Start at 2×.
4. Keep RTXDI temporal reuse enabled. The lighting pulsing is investigated separately in [RTXDI_TEMPORAL_STABILITY.md](RTXDI_TEMPORAL_STABILITY.md).
5. Remove the experimental proxy after the A/B test if it fails. The production MFG adapter remains the primary development route.

Do not describe the experiment as working or automatically include it in ordinary installations until those gates pass.
