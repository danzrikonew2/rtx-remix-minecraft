# Experimental MFG Unlocker integration

This optional community integration downloads dashdogy's
[MFG Unlocker v1.7.0](https://github.com/dashdogy/MFG-Unlocker/releases/tag/v1.7.0).
It is not an NVIDIA feature or a confirmed compatibility release.

## Automatic installation

Beta 1 includes `install-mfg.bat`: double-click it for Prism setup with the addon
selected automatically. It creates **RTX Remix Community 26.3 Beta (Experimental)**,
separate from earlier installer profiles. The standalone JAR does not install
the addon or its private Java runtime.

Alternatively select **Prism** in `install.bat` and answer
yes to the experimental addon prompt, or use:

```powershell
.\installer.ps1 -Mode Install -Launcher Prism -Unattended -EnableMfgUnlocker
```

The installer verifies pinned SHA-256 hashes for the archive and DLL, preserves
the MIT notice, and creates an instance-local Java copy. The private Java is
necessary because the addon writes configuration and diagnostic files beside
the executable. Shared Java installations and other Minecraft profiles receive
no proxy DLLs. The addon lives under `rtx-remix-addons/mfg-unlocker/`, outside
the mod-owned runtime directory that extraction can replace.

The mod explicitly loads the verified addon after launcher command-line
redaction and before Remix loads. If available, the NVIDIA neural-rendering
library already included in Remix's runtime is copied beside the addon for
discovery. No additional NVIDIA binaries are downloaded by this integration.
Loading fails back to ordinary Remix startup if validation or native loading
fails. The loader rejects shared-Java activation.

Microsoft launcher and ARM64 addon installation are not implemented. Ordinary
Minecraft installation on those launchers/platforms keeps its existing behavior.

## What is and is not verified

Local validation: automatic installation into a separate experimental Prism
instance passed archive/DLL hash checks. A private-Java smoke process loaded
the addon and its native exported status query confirmed backend ownership.
This test did not start a graphics swapchain or generate frames.

Source inspection found Vulkan NGX hooks and experimental RTX 30 paths in the
upstream addon. That does not prove compatibility with this pinned Remix build.
The recorded RTX 3070 Ti session loaded the DLL and installed NGX Vulkan
detours, but its status reported `activeFrameGeneration=none`,
`gameFrameGenerationOn=false`, `appliedFrameGenerationOn=false`, and
`universalRouteFailureReason=no active wrapper call`. Its log reported
`mainGraphicsImports=0`. No generated frames or DLSS 5 evaluations were recorded.
Backspace did not display the native menu. These observations do not establish
that resetting user data caused the failure. The menu/presentation integration
is an unresolved compatibility blocker; reinstalling or changing the key cannot
be claimed to repair it.

Use `/rtx mfg` in a world to query the native menu hook flags, Windows virtual-key
code and DXGI/Vulkan/menu frame counters. The command also records the result in
`logs/latest.log`; it does not enable FG. Key code 8 means Backspace.

A loaded DLL, visible menu or enabled checkbox does not
prove generated frames are being produced. No FG multiplier or DLSS 5 success
is claimed until confirmed in an actual game session and runtime/addon logs.

The installer does not force Remix's frame-generation config flag or change
DLSS/quality settings. Select the feature through its menus when supported.
DLSS 5 neural rendering and multi-frame generation are separate capabilities.

## Disable and rollback

To restore the default menu shortcut after changing it, close Minecraft and
Prism, then run:

```powershell
.\mfg-unlocker.ps1 -GameDir 'PATH-TO-EXPERIMENTAL-GAME-DIRECTORY' -Mode ResetMenu
```

This backs up `RTX40MFG-UI.ini` beside the private Java executable and restores
`[Overlay] ToggleKey=8` (Backspace). It preserves the addon's rendering JSON,
worlds and launcher accounts. If the native overlay is unattached, the shortcut
still cannot display it. Do not repeatedly reset graphics settings to fix that.

Close Minecraft and Prism, then run from the installer directory:

```powershell
.\mfg-unlocker.ps1 -GameDir 'PATH-TO-EXPERIMENTAL-GAME-DIRECTORY' -Mode Disable
```

This removes only the enable marker. On the next launch the mod does not load
the addon. Files and the private Java copy are retained for reversible rollback.
Removing the Fabric mod also prevents addon loading. Keep the known-good 26.3
instance and the original 1.21.1 installation separate while evaluating this.

Report the mod commit, addon version, GPU/driver, selected mode, actual addon
status and sanitized runtime logs. Do not post full launcher command lines,
account files, raw crash dumps or private paths. Installer/hash checks and Java
tests cannot validate native graphics hooks or frame pacing.
