# Experimental native MFG adapter

This is an unofficial development adapter for the 26.3 community port. It is
**not a working FG release**. The public beta installer still uses the pinned
upstream MFG 1.7.0 DLL. These sources build a separate local candidate.

## Implemented and checked

- Read-only recovery from the exact public 1.7.0 DLL: 131 CUDA resources,
  13 program descriptions and 387 kernel contracts, including 310.9.16.
- Reconstruction of three native manifests and the hash-bound resource list.
- Recovery of eight DLSS-stage SPIR-V shaders with their upstream hashes and
  three menu shaders whose generated header matches the upstream header hash.
- Native build with XeSS disabled, retaining existing kernel, shader, adapter,
  feature-lifetime and FG admission checks.
- `MfgUnlockRegisterRemixVulkanHost` registration after loading the Remix DLL
  and before renderer initialization. Only the exact pinned runtime hash is
  admitted, including outside the private Java directory. Its Vulkan imports
  and resolvers use the addon's existing gateways.
- `MfgUnlockRetireRemixVulkanHost` before Remix shutdown. The native probe
  originally hung during shutdown; retiring the menu first resolves that hang.

No CUDA instruction, provider DLL or Remix runtime binary is patched on disk.
Recovered inputs remain local build data under ignored `build/`; their original
license terms apply and they are not included in this repository. Adapted MFG
source retains [its MIT license](LICENSE-MFG). Build helpers and standalone
probes carry their own SPDX identifiers.

## Inputs and build

Use a fresh disposable MFG checkout at
[`7523faa4f804813669dab8b932d51f619641384a`](https://github.com/dashdogy/MFG-Unlocker/tree/7523faa4f804813669dab8b932d51f619641384a).
Patch helpers preserve originals in `.remix-original/`, accept repeat application
and refuse to overwrite unrecognized source edits. They modify that disposable
checkout only.

Acquire these public inputs separately, extracting SDKs under `build/`:

| Input | Version / identity |
|---|---|
| [MFG release ZIP](https://github.com/dashdogy/MFG-Unlocker/releases/tag/v1.7.0) | 1.7.0; ZIP SHA-256 `5bd19d03288e1ece1d0bb2030ac072b36758045028da192044dcaad73fd901dd` |
| MFG DLL from that ZIP | SHA-256 `e6b6e6b70a6ed3af839c9647a32fc22660ae6b2d655062c5c072246c91fc10c7` |
| [Streamline SDK](https://github.com/NVIDIA-RTX/Streamline/releases/tag/v2.14.1) | 2.14.1, x64 |
| [ImGui](https://github.com/ocornut/imgui/tree/3912b3d9a9c1b3f17431aebafd86d2f40ee6e59c) | Exact revision in the link |
| [Vulkan headers](https://github.com/KhronosGroup/Vulkan-Headers/tree/v1.2.176) | 1.2.176 |
| Python / CMake | Python 3.10+; tested with Python 3.12 and CMake 4.3.3 |
| C++ tools | Tested with VS 2026, MSVC 14.51, Windows SDK 10.0.26100.0 |

This compatibility build uses a different compiler/Windows SDK from upstream's
frozen release toolchain and reconstructs manifest formatting. It does not claim
byte-identical release reproduction. XeSS functionality is omitted with
`MFG_UNLOCK_XESS=OFF`; its program set and CUDA compiler are not required.

From the Minecraft repository root, substitute your extraction paths:

```powershell
python native/mfg/recover_inputs.py --dll PATH/TO/MFGUnlocker.dll `
    --source build/mfg-source --output build/mfg-inputs
python native/mfg/verify_headers.py --source build/mfg-source `
    --streamline build/streamline --imgui build/imgui --normalize-pinned-text
./native/mfg/build.ps1 -MfgSource build/mfg-source -Inputs build/mfg-inputs `
    -StreamlineRoot build/streamline -ImGuiRoot build/imgui `
    -VulkanInclude build/vulkan/include -BuildDirectory build/mfg-native
```

`verify_headers.py` validates all 36 upstream Streamline/ImGui source pins.
Optional normalization changes line endings only when that produces the exact
upstream byte hash. Run it on disposable SDK extractions. `build.ps1` accepts
explicit `-PythonExe`, `-CmakeExe`, `-Generator` and `-WindowsSdk` values. It does
not install the result into a launcher or change a game configuration.

Output: `build/mfg-native/Release/MFGUnlocker.dll`; the script prints its hash.
Local testing requires that hash in the instance JVM option
`-Drtxremix.mfgDevelopmentDllSha256=FULL_LOWERCASE_SHA256`. Ordinary addon
downloads retain their fixed release pin. Keep this option out of shared Java
and working 1.21.1/26.3 profiles.

## Automated native checks

```powershell
cmake -S native/mfg -B build/mfg-checks -G "Visual Studio 18 2026" -A x64 `
    -DMFG_SOURCE=ABSOLUTE_MFG_SOURCE_PATH -DMFG_INPUTS=ABSOLUTE_RECOVERED_INPUT_PATH `
    -DMFG_DLL=ABSOLUTE_CANDIDATE_DLL_PATH -DREMIX_DLL=ABSOLUTE_PINNED_RUNTIME_DLL_PATH
cmake --build build/mfg-checks --config Release
ctest --test-dir build/mfg-checks -C Release --output-on-failure
```

The contract executable uses upstream's unchanged `ValidateNativeContainer` to
check all 387 recovered contracts. The host check loads the actual pinned
runtime without starting its renderer, verifies registration and rejects null,
system and addon modules. These tests do not execute FG kernels.

`MfgRemixPresentSmoke.exe` is an additional GPU test. Run from a new disposable
directory containing a copy of `packaging/rtx.conf`; pass absolute candidate and
runtime DLL paths. It creates its own hidden window, starts the actual Remix C
API, presents 40 empty-scene frames, checks Backspace opening and closing the
menu, retires the menu and shuts down. It accesses no Minecraft account/world.
Use a process timeout for this experimental probe. Passing `none` instead of the
addon DLL runs the stock-runtime control.

Upstream `VulkanDynamicMenuTests` passed: 34 presents/menu draws, recreation,
keyboard toggles, UI pixel readback, zero reported render failures and unchanged
Vulkan-loader executable sections. Native status tests passed 29 checks. The
real-runtime menu probe passed 40 presents/menu draws with zero reported render
failures. Its stock control and corrected candidate shut down. Both report the
runtime's existing 42 undisposed common-device objects; this is not fixed here.

## Remaining FG integration

The menu adapter does not publish FG capability or satisfy MFG's Streamline
wrapper allocation contract. An original game call failed startup admission
before reaching the NVIDIA provider (failure 120). The new isolated `fg-probe`
request recorded no feature creation/active FG, and menu initialization failed
after swapchain recreation. This is a failed experiment, not a passing FG test.

A direct Remix adapter still needs startup/program preparation bound to the
Vulkan device, verified live presentation-buffer capacity, feature ownership,
resource synchronization and presentation pacing. Remix uses a different
presenter from the Streamline wrapper MFG recognizes. The matching `71a581da`
source lookup did not resolve in public upstream during this investigation.
Public `dxvk-remix/main` presenter source is reference material, not proof of
matching binary layouts. Guards remain in place. No generated frames,
multiplier, DLSS 5 image quality or game-performance improvement is claimed.

## Private Streamline Vulkan startup

`patch_private_vulkan.py` supplies the missing Vulkan counterpart of MFG's
private OptiScaler D3D12 startup path. It hotpatches the private `slInit` at
module load using the existing validated profile. Before forwarding that
initialization it installs the Vulkan setup gateway with validated relocation,
outside the loader notification. MFG's nonblocking loader installation still
prohibits relocation. A successful initialization is recorded through the
existing current-entry/generation evidence validator. Provider preparation,
CUDA program validation, capacity, ownership and evaluation guards remain active.
Upstream's private-startup policy test passes all 63 checks. The rebuilt
candidate also passes the 387 recovered contracts, host registration and the
34-present Vulkan menu regression with zero reported render failures or Vulkan
validation errors.

With the documented OptiScaler adapter and the actual pinned Remix runtime,
the RTX 3070 Ti native probe now records:

| Observation | Result |
|---|---|
| Vulkan startup decision | Admitted with verified device |
| Startup failure mask | 0 |
| Native preparation stage / cache | 14 / valid |
| Allocated presentation buffers | 6, validated by the wrapper |
| Real NVIDIA provider FG creation | Accepted; one tracked feature |
| Active/applied mode | DLSS, fixed 2x requested |
| FG evaluation attempts / successful evaluations | 785 / 785 |
| Submitted / failed FG batches | 785 / 0 |
| Rejections / first and last failure | 0 / 0 |
| Reported last presentation batch | 1 frame after focus was lost |

The foreground probe completed 1,200 C API presents, including 824 while its
window was foreground. The provider executed successfully for all 785 FG
evaluations, and Streamline logged interpolation enabled. The temporal trace
records one midpoint request per source frame with valid output descriptors.
This establishes successful FG provider execution through the actual Remix
runtime on the 3070 Ti. It does not establish unique interpolated display
images, a measured 2x frame rate or Minecraft visual/performance acceptance.

Earlier hidden and unfocused runs recorded no evaluations; Streamline logged
`DLSS-G disabled: window not focused`. A 60-frame hidden control exited normally
with feature creation but zero foreground presents and zero evaluations. The
requested 2x value is configuration, not a measured frame-rate multiplier.

### Reproduce the adapter probe

Use a new ignored test directory. Follow MFG's
[documented adapter installation](https://github.com/dashdogy/MFG-Unlocker#optiscaler-support)
there, with these exact inputs:

- [OptiScaler nightly-20261024](https://github.com/optiscaler/OptiScaler-nightly/releases/tag/nightly-20261024),
  archive SHA-256 `74f20189e0ec76288c86d69057b3feb4750f4680118a9852fb743b343274ac1d`.
- Replace its root DLL with the
  [MFG adapter fork](https://github.com/dashdogy/OptiScaler/releases/tag/mfgunlocker-v1.7.0),
  source `aeb1f29783106b96c89ba71ce9b6db80eacdae46`, DLL SHA-256
  `0b70d723f61fcf1cc38c26e4033666bd08936f435a848f624222c77dc86ca7fe`.
  Keep its GPL-3.0 license and corresponding-source notice.
- Copy the locally built MFG candidate as
  `OptiScaler/plugins/MFGUnlocker.asi`; retain its MIT notice.
- Put Streamline 2.14.1 `sl.*.dll` files, `NvLowLatencyVk.dll` and their notices
  under `OptiScaler/streamline/`. Copy the selected Remix runtime's
  `nvngx_dlss*.dll` files under both `OptiScaler/` and that Streamline directory.
  The tested FG provider is 310.9.16.
- Copy `OptiRemixProbe.exe` from the native checks build beside the root
  OptiScaler DLL. Copy `packaging/rtx.conf` into the test directory.

In the nightly INI set:

```ini
[Upscalers]
VulkanUpscaler=dlss
[FrameGen]
Enabled=true
FGInput=upscaler
FGOutput=dlssg
FGNvngxReplacement=None
[DLSSG]
InterpolationCount=1
[Plugins]
LoadAsiPlugins=true
Path=ABSOLUTE_TEST_DIRECTORY/OptiScaler/plugins
[Libraries]
OptiDllPath=ABSOLUTE_TEST_DIRECTORY/OptiScaler
[Log]
LogToFile=true
LogLevel=1
```

From that directory run, using absolute DLL paths and an external process
timeout:

```powershell
.\OptiRemixProbe.exe ABSOLUTE_OPTISCALER_DLL ABSOLUTE_REMIX_DLL visible 600
```

The probe preloads the system Vulkan loader before OptiScaler, then renders a
moving-camera triangle through the actual Remix C API. Click its own window
to focus it. It closes automatically after the requested 40–3600 frames;
`hidden` is available for startup checks. It does not open Minecraft or access
accounts/worlds. Verify the current process's `RTXMFG-Universal.status.json`
and runtime logs for successful evaluations and generated presentation batches.
An active mode or created feature alone is insufficient.

This uses the adapter's upscaler input and FG control. An additional native
Remix FG request after adapter initialization was also tested and rejected
outside the recognized wrapper's creation stack; it did not generate frames.
The public beta installer has not been changed to include this adapter.

### Opt-in Minecraft loader

`MfgOptiScalerPayload` adds a development-only loading route. It requires the
existing isolated Java installation, the exact OptiScaler DLL pin, the explicit
MFG candidate pin and a JVM-pinned manifest covering every adapter DLL/ASI.
Missing, modified, unlisted and out-of-tree native files are rejected before
loading. The ordinary installer and its original MFG loading route are unchanged.
The private-Java smoke test validates all 32 libraries, loads OptiScaler and its
MFG plugin and queries the native status export without starting Minecraft.
The first Minecraft run loaded the adapter but recorded zero FG features and
evaluations, a private Vulkan `late-boundary` rejection and eventual device loss.
The revised loader waits up to five seconds for explicit native startup
prerequisites: registered DLL notifications, an armed architecture declaration
and an early feature boundary. Backend ownership alone is insufficient.
It also checks private-device admission immediately after Remix startup and
stops renderer initialization if it failed. An initialization failure after native loading
stops renderer initialization and requires a restart, since hooks cannot be
treated as safely unloaded by a Java exception.

`MfgJavaHostProbe.dll` reuses the native probe inside the private JVM through an
FFM call to `MfgRunJavaHostProbe(wchar_t* adapter, wchar_t* runtime, wchar_t* lightingConf)`.
It passes device admission and 60 hidden presents. With the new lighting conf it
verifies 8/8 accumulation/stale frames while the layer is enabled and exact
1,000/1,024 restoration afterwards. It also verifies a foliage-query off/on
round trip. The old reset-pulse test only established option acceptance and
restoration, not that a native frame consumed the pulse.

Keep the adapter fork's `LICENSE` and `SOURCE.txt` beside the extracted test
package. Stage it into an existing experimental addon installation:

```powershell
python native/mfg/stage_optiscaler.py --package ABSOLUTE_TEST_PACKAGE `
    --candidate ABSOLUTE_CANDIDATE_DLL --candidate-sha256 FULL_CANDIDATE_SHA256 `
    --addon ABSOLUTE_EXPERIMENTAL_GAME_DIRECTORY/rtx-remix-addons/mfg-unlocker
```

The script refuses an existing `optiscaler-development` directory, preserves
license/source notices and prints two JVM properties. Add those properties only
to that experimental instance. Removing `-Drtxremix.mfgOptiScalerManifestSha256`
returns to its original MFG loading route. No shared Java installation is modified.
An enabled OptiScaler FG route supplies its own inputs; leave Remix's separate
native FG toggle off. Minecraft's GL/Vulkan synchronization, GUI, world reload,
image quality and real presentation pacing still require a game test.
