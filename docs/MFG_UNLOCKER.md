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

### Native port investigation: 2026-11-01

The RTX 30 implementation is more than a hardware-capability override.
`ampere_cuda_program.cpp` validates translated programs against the selected
CUDA adapter/LUID and SM target; `ampere_native_cache.cpp` selects and verifies
embedded kernel programs. `ampere_backend.cpp` admits startup only after
runtime/provider entry coverage, adapter/device identity, capacity and program
readiness checks pass. Its Vulkan path validates NGX resources and the output
image identity before evaluating a feature.

In the recorded Remix session, `ampereCreateAttempts=1`,
`ampereCreateBlockedBeforeProvider=1`, `amperePreparationStage=0` and
`ampereFirstFailure=120`. Source shows that 120 includes refusal before a
completed startup admission. A zero startup-failure mask does not indicate
success when startup admission has never completed. The log's resulting
`FeatureNotSupported` therefore does not independently prove that the NVIDIA
provider executed and rejected this GPU. Do not bypass this guard and claim FG.

Menu admission is separate. Read-only PE import inspection found no graphics
imports in `javaw.exe`; the installed `d3d9.dll` imports Vulkan entry points,
including `vkGetInstanceProcAddr`. MFG's `overlay_application_imports.cpp`
restricts renderer DLLs to the executable subtree and qualifies graphics
hosts via DXGI factory/D3D12 imports. The isolated Java executable and Remix
DLL also reside in different directory subtrees. Renaming the addon or
changing Backspace does not supply the missing host adapter.

A direct native port needs compatible startup admission, translated program
resources, live Vulkan device/queue and NGX frame inputs, feature lifetime
handling, generated-image ownership/synchronization and paced presentation.
The current Remix C API exposes shared color/depth memory and synchronization
handles for GL interop; it does not expose a complete external FG device,
motion-vector and presentation integration. Adding header declarations alone
cannot provide that implementation. The package pin's `71a581da` source lookup
did not resolve in the public dxvk-remix repository during this investigation.

The public MFG build additionally requires separately prepared kernel caches
and XeSS program inputs which its source checkout does not include. Reusing
its MIT source requires retaining its attribution; installing its existing DLL
does not expose an API that replaces the missing native integration.

The kernel inputs have now been recovered locally from the verified public
release DLL and checked with upstream's unchanged validator: 131 resources,
13 programs and 387 contracts. Eight DLSS-stage shaders and the three-shader
menu header match upstream pins. A native candidate builds with XeSS disabled,
using source-only helpers under
[`native/mfg/`](https://github.com/danzrikonew2/rtx-remix-minecraft/blob/feat/minecraft-26.3/native/mfg/README.md).
The separate XeSS inputs remain absent.

The candidate adds explicit, runtime-hash-bound Vulkan host registration and
menu retirement through optional JNI notifications. A standalone test using
the actual pinned Remix runtime passed 40 presents/menu draws, Backspace
open/close checks and shutdown with zero reported render failures. Early probe
teardown failures were investigated before installation; retiring menu resources
before native shutdown resolves the observed hang. Minecraft visual acceptance
remains pending. A separate native-FG request still recorded no feature creation
or active FG and failed menu initialization after swapchain recreation. This
does not complete the FG startup/presenter adapter.

A subsequent private-Streamline Vulkan startup patch now passes startup and
creates one real NVIDIA DLSS FG feature on the RTX 3070 Ti through the documented
OptiScaler adapter. Its native cache/program and six presentation buffers pass
the existing checks. A focused native run now completes 785 successful FG
evaluations and 785 submitted batches with no batch failures or rejections.
The provider executes and Streamline enables interpolation; unique displayed
images, a measured frame-rate multiplier and Minecraft compatibility remain
unverified. Source, exact dependencies, test
results and reproduction are in the
[native adapter guide](https://github.com/danzrikonew2/rtx-remix-minecraft/blob/feat/minecraft-26.3/native/mfg/README.md#private-streamline-vulkan-startup).

The isolated adapter probe above uses DLSS FG output. OptiScaler also documents
a Vulkan XeFG output route, which has not been tested here. These are separate
backends; XeFG results would not establish DLSS FG compatibility. Neither
adapter has been added to the public beta installer. A JVM-pinned development
loading route and local staging helper are available for the isolated test
profile; its private-Java loading/status smoke test passes. This is not a
verified Minecraft release.

The first Minecraft adapter session (`b603d0a`) recorded zero FG features and
evaluations, late startup admission and eventual `VK_ERROR_DEVICE_LOST`.
The revised candidate waits for actual early-hook readiness rather than just
backend ownership and checks Vulkan device admission before the render loop.
A private-JVM C API test passes admission and 60 hidden presents. Minecraft
stability and generated display output still require validation; see the
[session evidence](PERFORMANCE_26_3.md#experimental-adapter-failure-2026-11-01-build-b603d0a).

The subsequent `931391c` game session records 26,794 successful FG evaluations
and submitted batches across three features, zero failed batches and a recovered
first failure 171 (last failure 0). Native shutdown completed. This establishes
provider execution in Minecraft; displayed interpolation quality and a measured
frame-rate gain remain unverified. The reported bright foliage is still unresolved;
see the [latest lighting comparison](RENDERING_DIAGNOSTICS.md#bright-foliage-after-time-changes).

### Development adapter controls (after 931391c)

The development profile uses **OptiScaler FG**, independently of Remix's native
**Enable DLSS Frame Generation** checkbox. Keep that native checkbox **off**.
Checking it requests a different presenter and can leave an unsupported request
checked and greyed out. A/C preset selectors are not evidence of interpolation
or a frame-rate gain.

The old adapter INI left its shared menu on `ShortcutKey=auto`, which resolves
to **Insert**. The standalone MFG UI's `ToggleKey=8` did not configure that menu.
The new loader migrates automatic/default Insert to **Backspace**, automatic
FG toggle to **End**, and automatic overlay enable to explicit `true` before
loading OptiScaler. It backs up the INI as
`OptiScaler.ini.before-remix-menu-fix`, preserves explicit custom keys/overlay
opt-outs and leaves FG quality, multiplier and presets alone. New staging uses
the same defaults. It applies only to the manifest-pinned development adapter;
the public beta's standalone addon is unchanged.

For the **RTX Remix Community 26.3 FG Adapter (Development)** profile:

1. Close Remix's graphics/developer menu with **Alt+X** before testing.
2. Press and release **Backspace** to open/close the OptiScaler menu. Use its
   Frame Generation controls, with the existing upscaler input and DLSSG output.
3. Press and release **End** to toggle adapter FG off/on. This control does not
   require Remix's native FG checkbox to be enabled.
4. If the native checkbox was enabled, close that menu and run `/rtx mfg reset`.
   This clears only the native FG request. `/rtx mfg` reports its resolved value
   (expected `false`) as well as route instructions. Startup also clears the
   conflicting saved native request before initializing the renderer.

A 140-present hidden test against the pinned runtime verified shared-menu
open/close from Backspace, adapter FG disabled/enabled from End, and recovery of
a seeded native FG request to `false`. Logs show two FG features across the
off/on cycle and zero failed batches. It was unfocused, so it recorded zero FG
evaluations; this control test does not establish Minecraft input handling,
visible overlay correctness, displayed interpolation or a performance gain.
The next game check should exercise those four steps and compare motion with
End off/on. Minecraft's F3 FPS alone does not count generated presentation frames.

Primary references:

- [MFG RTX 30 backend](https://github.com/dashdogy/MFG-Unlocker/blob/main/source/native/ampere_backend.cpp)
- [CUDA program validation](https://github.com/dashdogy/MFG-Unlocker/blob/main/source/native/ampere_cuda_program.cpp)
- [Kernel-cache selection](https://github.com/dashdogy/MFG-Unlocker/blob/main/source/native/ampere_native_cache.cpp)
- [Renderer admission](https://github.com/dashdogy/MFG-Unlocker/blob/main/source/native/overlay_application_imports.cpp)
- [Build inputs](https://github.com/dashdogy/MFG-Unlocker/blob/main/BUILD.md)
- [Documented adapter route](https://github.com/dashdogy/MFG-Unlocker#optiscaler-support)

### Existing installation checks

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

Use `/rtx mfg` in a world to query the standalone native menu hook flags, Windows
virtual-key code and DXGI/Vulkan/menu frame counters, or the adapter route's
instructions/native FG setting when that route is loaded. The command also records the result in
`logs/latest.log`; it does not enable FG. Key code 8 means Backspace.

A loaded DLL, visible menu or enabled checkbox does not
prove generated frames are being produced. No FG multiplier or DLSS 5 success
is claimed until confirmed in an actual game session and runtime/addon logs.

The public installer does not force Remix's frame-generation config flag or
change DLSS/quality settings. The development adapter clears the competing
native FG flag as described above. Select adapter FG through its own controls.
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
