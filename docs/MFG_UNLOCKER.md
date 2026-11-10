# Experimental MFG Unlocker integration

This optional community integration downloads dashdogy's
[MFG Unlocker v1.7.0](https://github.com/dashdogy/MFG-Unlocker/releases/tag/v1.7.0).
It is not an NVIDIA feature or a confirmed compatibility release.

## Automatic installation

The installer includes `install-mfg.bat`: double-click it for Prism setup with the addon
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
The provider executes and Streamline enables interpolation. A later matched
2026-11-11 FG OFF/ON run advances this result to DWM-compositor verification:
source frame 30 onward contains 150 OFF versus 300 ON changed target states,
59.394 versus 119.202 Hz; all 150 real-frame endpoint centroids are preserved,
all 149 adjacent endpoint intervals contain exactly one ON-only state, and
143/144 measurable intermediates land within normalized midpoint 0.5 +/- 0.15.
The matching provider log loads `nvngx_dlssg.dll`, creates DLSS-G, and records
165/165 successful NVIDIA Vulkan evaluations. This verifies correctly ordered
intermediate pixels at the Windows DWM compositor for the isolated probe.
Physical monitor scanout, Minecraft presentation, latency and >2x operation
remain unverified. Source, exact dependencies, test
results and reproduction are in the
[native adapter guide](https://github.com/danzrikonew2/rtx-remix-minecraft/blob/feat/minecraft-26.3/native/mfg/README.md#private-streamline-vulkan-startup).

### 2026-11-11 Minecraft 26.3 v0.1.1 NVIDIA FG revalidation

The disposable official-launcher profile at
`C:\Users\vijja\AppData\Roaming\.minecraft-rtx-remix-26.3` reproduced the
earlier `SR None / FG Off` state while `user.conf` contained
`rtx.dlssPreset = 0`. Adding the known-working `rtx.qualityDLSS = 4` and
`rtx.rayreconstruction.preset = 6` values alone did not create a game NGX
DLSS/DLSSD feature. Removing only the saved `rtx.dlssPreset = 0` override,
with a profile-local backup first, restored the expected lifecycle on the
v0.1.1 runtime: OptiScaler observed game handle 1000000, created a DLSSD
feature successfully, accepted DLSS-G options and created NVIDIA FG feature
11. The native Remix FG flag remained disabled.

Streamline initially suppressed interpolation because the Minecraft window was
not foreground. Once the disposable Minecraft window was focused, the same
session accumulated 607 NVIDIA DLSS-G Vulkan evaluations and 607 submitted
batches with zero failed batches; later counters continued increasing. A
controlled 12-second FG-ON DWM trace recorded +362 evaluations / +362 batches,
while its 12-second FG-OFF control recorded exactly 0 / 0. Re-enabling FG then
resumed evaluations immediately (+156 in the following two seconds). The
provider therefore executes successfully from actual Minecraft 26.3 v0.1.1
frames on the RTX 3070 Ti.

The generic-window observer mode used for this diagnostic samples only the
target PID's focused window and records no image bytes. Its raw Minecraft ROI
hash-change count is deliberately **not** treated as interpolation proof because
the gameplay scene is not a deterministic OFF/ON stimulus. The isolated moving
target midpoint test above remains the compositor-level proof of generated
intermediate pixels. Physical monitor scanout, Minecraft-specific midpoint
presentation, input latency, long-session stability, >2x Dynamic MFG and DLSS 5
neural rendering remain separate acceptance items.

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
Build 34d264d migrated Insert to Backspace, including explicitly saved Insert,
which caused the reported shortcut reversion. The current loader sets only
missing/automatic keys to **Insert** (45), FG toggle to **End** (35), and
automatic overlay enable to `true`. Explicit saved keys are always preserved.
It backs up changed INIs as
`OptiScaler.ini.before-remix-menu-fix`, preserves explicit custom keys/overlay
opt-outs and leaves FG quality, multiplier and presets alone. New staging uses
the same defaults. It applies only to the manifest-pinned development adapter;
the public beta's standalone addon is unchanged.

For the **RTX Remix Community 26.3 FG Adapter (Development)** profile:

1. Close Remix's graphics/developer menu with **Alt+X** before testing.
2. Press and release **Insert** to open/close the OptiScaler menu. Use its
   Frame Generation controls, with the existing upscaler input and DLSSG output.
3. Press and release **End** to toggle adapter FG off/on. This control does not
   require Remix's native FG checkbox to be enabled.
4. If the native checkbox was enabled, close that menu and run `/rtx mfg reset`.
   This clears only the native FG request. `/rtx mfg` reports its resolved value
   (expected `false`) as well as route instructions. Startup also clears the
   conflicting saved native request before initializing the renderer.

A historical 140-present hidden test, before the Insert-default change, used
the then-configured Backspace binding for the shared menu. It verified adapter
FG disabled/enabled from End and recovery of
a seeded native FG request to `false`. Logs show two FG features across the
off/on cycle and zero failed batches. It was unfocused, so it recorded zero FG
evaluations; this control test does not establish Minecraft input handling,
visible overlay correctness, displayed interpolation or a performance gain.
The current probe and instructions use Insert; Backspace in that older test
is not the current default. The next game check should exercise the four steps and compare motion with
End off/on. Minecraft's F3 FPS alone does not count generated presentation frames.

### Neural controls and current provider limitation

These controls belong to the **MFG provider route**. They do not configure
Remix's separate built-in DLSS-NR pass. The page title and description identify
that distinction; neither control is a frame-generation multiplier.

`/rtx dlss5` or **RTX Remix Settings → DLSS 5 (Experimental)**
opens a Minecraft settings page. It exposes the enable request and Vulkan
Auto/After Upscaling hook choices while preserving other MFG JSON settings.
Writes are backed up and replaced atomically; malformed existing files are
preserved. Live status requires the current PID and a fresh heartbeat. An enable
request is not reported as successful neural rendering. F8 retains its RTX toggle.

The staging helper copies the unchanged selected `nvngx_dlssnr.dll` beside
`OptiScaler/plugins/MFGUnlocker.asi`, where provider lookup actually searches.
The copy is included in the explicit manifest/hash pin. A 150-present isolated
Vulkan run detects it but rejects neural creation with state 4 (unsupported)
and `0xBAD00001`: zero creates/evaluations, one failure. FG startup and renderer
shutdown pass. DLSS 5 remains off by default and is **not working on this tested
3070 Ti setup**. No provider/GPU admission guard was bypassed.

A second native-menu chaining experiment hung at startup on a later run and was
removed. The candidate retains the established OptiScaler presentation path and
uses the Minecraft page for neural controls. The standalone ResetMenu action now
targets `RTXMFG-UI.ini`, rather than obsolete `RTX40MFG-UI.ini`.

### Native Remix DLSS-NR and Autopilot research (2026-11-03)

The official runtime also has its own neural pass, using renderer-owned color,
depth, motion vectors, jitter and a control mask before tone mapping. Its
source-defined key is `rtx.dlssNeuralRendering.enable`; see the
[official implementation](https://github.com/NVIDIAGameWorks/dxvk-remix/blob/5ee5dc35571075c684ec50e1b28c32fe04065537/src/dxvk/rtx_render/rtx_dlss_neural_rendering.cpp).
This is distinct from MFG's feature-creation probe.

A new stock-runtime probe loads no MFG/OptiScaler, renders 60 hidden-window
frames, and verifies this key resolves false → true → false on the actual
`minecraft-rtx2-71a581da` runtime. The runtime itself reports `Available: 0`
and `0xBAD00001 / FeatureNotSupported` for DLSS-NR on the tested 3070 Ti/driver
configuration. Accepting the option is not successful neural rendering.

[DLSS5-Autopilot](https://github.com/Kizzuwatnaa/DLSS5-Autopilot/blob/d9afad186bb6751807bd98ec4a09455a8a0b9a9d/core/installer.py)
can stage a separate provider and optionally swap a `.trex` runtime for a
community fork plus its NGX bridge. Its RTX 30 mapping selects an SM86-capable
community provider; that does not prove compatibility with this Minecraft
runtime. Its discovery/layout and fork-specific option prefixes differ from
this mod's `remix-sdk` and the official native option.

The published Lunks `dlssnr-v1` runtime also has a concrete C API mismatch:
its [header](https://github.com/lunks/dxvk-remix-plus-dlssnr/blob/dlssnr-v1/public/include/remix/remix_c.h)
advertises 0.6.4, while this mod requires 0.16.0 and retained
`SceneInstanceAdd/Update/Remove` calls that the old interface lacks. Its
[version gate](https://github.com/lunks/dxvk-remix-plus-dlssnr/blob/dlssnr-v1/src/dxvk/rtx_render/rtx_remix_api.cpp)
rejects a mismatching 0.x minor version. It is not a compatible replacement
for this mod's runtime; lowering the copied header's version would not supply
the missing functions. That runtime was not installed or executed here.

One alternative was tested locally, without swapping the official runtime:
the RHI `310.8.SF-v2` provider from the publisher's
[release](https://github.com/RankFTW/rhi-repo/releases/tag/dlssnr-310.8.SF-v2).
The archive matched GitHub's SHA-256
`1da35941894994eb087e017577829e492454e9bae3a6a9397027069ceb74955c`;
the extracted DLL was
`6eb209e764f39872625debd6abaf45e2bb6322f6f270f781f70c059ae30b3927`.
It was placed beside a disposable copy of the unchanged pinned runtime, the
search location used by the official NGX wrapper. The renderer again completed
60 frames and restored its option, but feature initialization reported
`0xBAD00004 / FeatureNotFound`, `Available: 0`. There is no verified neural
evaluation or visual output. No provider module remained visible at the two
module checks; that does not establish it was never transiently loaded.
Provider/core compatibility remains unresolved, rather than proving all RTX 30
neural rendering impossible.

The community provider is not included in the mod, installer or public release;
Autopilot describes it as proprietary with no public license. No game profile,
official runtime payload or installed provider was replaced by this experiment.
A compatible, validated provider/NGX route is required before integration can
be advertised. Merely enabling a checkbox or replacing `d3d9.dll` without a
matching C API package is not a completed implementation.

### Game controls and multiplier evidence (2026-11-02)

The user now confirms the OptiScaler menu is visible and supplies captures of
Off, ON 2x and ON 6x. A process-matched live snapshot (PID 36824) records 5,834
successful provider evaluations and 5,832 submitted batches, with zero failed
batches; a later snapshot records 6,993 evaluations and 6,991 submitted batches.
There were eight rejected evaluation attempts and recovered failure 131 (last
failure 0). This supports provider execution, not a measured display multiplier.

The native log reports that the wrapper reuses one output image for multiple
generated frames (`count=5` while requesting 6x), then explicitly keeps that
feature at **2x until it is recreated**. Thus **ON 6x is a request, not verified
6x output**. Keep 2x for the current adapter; distinct multi-output resource
handling remains incomplete. Do not remove the duplicate-output/lifetime guard
to make the label succeed. Minecraft's F3 rate measures game frames, while the
OptiScaler overlay is not a unique-display-frame counter; neither screenshot
establishes how many distinct generated images reached the monitor.

MFG 1.7.0's separate **DLSS 5 / Neural Rendering** tab exists in its source.
Its provider-dependent tab and the standalone MFG UI are separate from the
OptiScaler FG page shown in the captures. This profile reports `dlss5=false`,
`dlss5Detected=false` and zero DLSS 5 evaluations. The provider is mapped from
OptiScaler's library folders, but the MFG UI's provider-location gate does not
detect it there; the profile has no working DLSS 5 menu integration yet.
Do not present the available SR/RR presets or FG multipliers as DLSS 5.
Upstream documents Auto/After upscaling for its Vulkan neural-rendering route;
that is an upstream capability, not a validated Minecraft feature. See the
[pinned MFG README](https://github.com/dashdogy/MFG-Unlocker/blob/7523faa4f804813669dab8b932d51f619641384a/README.md#v170).

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

This backs up `RTXMFG-UI.ini` beside the private Java executable and restores
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
