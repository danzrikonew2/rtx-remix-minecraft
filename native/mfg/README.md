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
  and before renderer initialization. Exact x64 image identity and SHA-256
  profiles admit the previously validated `minecraft-rtx2-71a581da` runtime
  (`44A313F6D2A6FFA3ECCAAB683C472D14F22080BE7C61D07342D8E199A039D1AD`) and
  the verified v0.1.1 `minecraft-rtx2-a00da12a` runtime
  (`A8365272734CF5541E3600AEACB445C0FD102187DC3A167495A56809CE5891D9`).
  Unknown images and non-x64 binaries remain rejected. The runtime DLL may be
  outside the private Java directory; its Vulkan imports and resolvers use the
  addon's existing gateways.
- `MfgUnlockRetireRemixVulkanHost` before Remix shutdown. This retires the
  adapter's Vulkan host callbacks; it does not guarantee that Remix's own
  `Shutdown` completes. Recent bounded stock-runtime controls, including one
  with zero rendered frames and no adapter, also hung inside `Shutdown`.

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

From the Minecraft repository root, first recover the pinned 1.7.0
resources without loading or executing the upstream DLL:

```powershell
.\\native\\mfg\\recover_verified_release.ps1
```

This helper uses the exact upstream GitHub asset SHA-256 and inner DLL SHA-256,
requires the existing pinned `build/mfg-source` checkout, generates kernel
manifests and SPIR-V assets in `build/mfg-inputs`, and preserves existing
outputs instead of overwriting an incomplete recovery. It does **not** install
the addon, build the custom adapter, or modify Prism. The input DLL is local
build data, not an approved installable MFG candidate. The `python` executable
must be available, or supply `-PythonExe` with an absolute path.

Restore the remaining SDK dependencies with the separate pinned-fetch helper:

```powershell
.\native\mfg\prepare_pinned_sdks.ps1 -RepoRoot (Get-Location).Path -PythonExe "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
```

It verifies the GitHub-published SHA-256 of the official **Streamline 2.14.1
Windows ZIP (~276 MB)**, then checks out the exact ImGui commit
`3912b3d9a9c1b3f17431aebafd86d2f40ee6e59c` and Vulkan-Headers
v1.2.176 commit `074fa3055cfee530992bcbfa0fcb23106a82c1ab` into
ignored `build/` directories. Streamline and ImGui's 36 source file pins
are verified against the upstream build script. Existing vendor directories
are **not replaced**. The helper never starts the game or installs any DLL.

After SDK restoration, continue the native adapter build:

```powershell
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

## Local experimental installer ZIP (after the native build)

A successful `native/mfg/build.ps1` produces the locally compiled adapter at
`build/mfg-native/Release/MFGUnlocker.dll`. The native host-registration test
is still required; compilation alone is not compatibility certification.

From the repo root, **after** `verifyReleaseArchive -Parch=win64` and native
candidate compilation, run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\\native\\mfg\\package_validated_candidate.ps1 -RepoRoot (Get-Location).Path
```

The helper checks the expected v0.1.1 runtime SHA, local MFG candidate hash,
rebuilds and runs the recovered-contract, runtime-profile and
`remix_host_registration` tests including fake runtime negative controls,
then creates **a separate ZIP under `build/distributions/`** containing the
existing, unmodified verified Minecraft installation files plus:

```text
experimental/mfg/MFGUnlocker.dll
experimental/mfg/LICENSE-MFG
experimental/mfg/stage_optiscaler.py
experimental/mfg/manifest.json
experimental/mfg/README.txt
```

The candidate is not committed, uploaded to GitHub, automatically deployed,
or treated as a proven working FG implementation. The normal `install.bat`
and `install-mfg.bat` still install the stock, pinned path. The experimental
ZIP's README documents how to stage into a disposable Prism test instance
with the separately pinned OptiScaler package and private Java. The private
loader requires an explicit candidate pin and a separately hash-pinned
OptiScaler payload manifest. Do not copy the adapter into `.trex` or
overwrite `remix-sdk/d3d9.dll`. GPU evaluation, unique output frames and
Minecraft integration are **still pending** after a passing test.

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
system and addon modules. With a locally rebuilt adapter, it also checks that a
loadable `d3d9.dll` fixture lacking the Remix export is rejected and that a
separate impostor `d3d9.dll` **with** that export still fails the exact runtime
identity gate. Both fixtures are generated only inside the native test build,
not staged with the runtime or released as Remix DLLs. These tests do not
execute FG kernels.

**Current-runtime identity coverage:** The `remix_runtime_profiles` CTest is
registered whenever `-DREMIX_DLL=ABSOLUTE_NEW_A00DA12A_D3D9_DLL` is supplied,
even if the old DLL is not available. It verifies the exact SHA-256 and AMD64
PE32+ image and rejects one-byte modification, architecture substitution,
truncation and null input. Optionally supply
`-DOLD_REMIX_DLL=ABSOLUTE_71A581DA_D3D9_DLL` to add the previously validated
runtime profile regression. Run `ctest --test-dir build/mfg-checks -C Release
-R "^remix_runtime_profiles$" --output-on-failure`. A passing profile test
means only runtime identity validation, **not** successful MFG registration,
provider FG evaluation, unique output images, or displayed frame pacing.

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
failures. In that earlier configuration, stock control and corrected candidate
shut down, but newer isolated stock controls (including zero frames) hang during
`Shutdown` and require a hard timeout. This behavior has not been attributed
to the adapter. Both earlier runs reported the runtime's existing 42
undisposed common-device objects; this is not fixed here.

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

A later bounded visible 360-present probe had **zero foreground presents**;
its process-matched status samples showed no FG feature creation, evaluations
or presentation batches. This does not contradict the earlier focused-run
provider results. It demonstrates that merely showing a window does not prove
the foreground requirement was satisfied. The latest bounded GPU runs stalled
at `Beginning Remix Shutdown` and were externally terminated. Wait-chain
capture found blocked threads; raw addresses near NVIDIA telemetry modules
are diagnostic candidates, not authoritative stack traces or a proven cause.

**2026-11-09 repeat with explicit own-window foreground request:** the newly
rebuilt visible probe completed 600/600 real Remix presents with zero reported
render failures, but Windows rejected `SetForegroundWindow`; all 600 presents
were unfocused. Across 146 process-matched status samples, FG creation,
evaluation, presentation buffers and presentation batches remained zero. The
final route was `pending` with reason `awaiting first game FG options request`.
After host retirement, `Shutdown` again hung and the runner terminated the
process at 120 seconds. The package's 11 Streamline DLLs, four NGX provider
copies, MFG/Remix hashes and license/source notices were reverified; all three
native CTests passed. The evidence is under ignored
`build/mfg-optiscaler-probe-focus-20261109-1250/probe-logs/`. This run did
not advance the displayed-frame gate.

Earlier hidden and unfocused runs recorded no evaluations; Streamline logged
`DLSS-G disabled: window not focused`. A 60-frame hidden control exited normally
with feature creation but zero foreground presents and zero evaluations. The
requested 2x value is configuration, not a measured frame-rate multiplier.

### Reproduce the adapter probe

For a disposable local probe package, use the pinned staging helper from the
repository root, after compiling `OptiRemixProbe` and `MfgJavaHostProbe`:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\native\mfg\prepare_optiscaler_probe.ps1 -RepoRoot (Get-Location).Path -PythonExe "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
```

This downloads the exact nightly (SHA-256 `74f20189...`) and the MFG
OptiScaler fork (SHA-256 `0b70d723...`), verifying the official fork's GPL
license and source notice. It extracts to a disposable staging directory,
combines the exact previously pinned local MFG candidate with Streamline 2.14.1
`bin/x64` and any Remix runtime `nvngx_dlss*.dll` providers, copies the
native probes, and configures **only** its local `OptiScaler.ini`. It refuses
an existing test folder and does not invoke the GPU, install a game, touch
Prism, or deploy a proxy in `.trex`.

The prepared root is `build/mfg-optiscaler-probe/Package`. The fork's
`LICENSE` and `SOURCE.txt` stay in its parent for later use by
`stage_optiscaler.py`. The helper prefers Windows `tar.exe` to extract
the official 7z archive; if that fails, install the ordinary 7-Zip application
and retry. Its downloads are cached and always re-hashed.

**The next stage must be a foreground visible GPU probe with a hard process
timeout, followed by checks for FG feature creation, successful evaluation,
actual presentation batches, unique displayed frames, and device-loss-free
shutdown.** A configured x2 mode, an on-screen menu or a passing CPU native
test alone does not demonstrate real frame generation.

If you need to prepare the same package manually, use a new ignored test directory. Follow MFG's
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
[Menu]
OverlayMenu=true
ShortcutKey=45
FGShortcutKey=35
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

For reproducible, bounded diagnostics the runner verifies package hashes first,
captures process-matched status samples, and can request foreground activation
of **only its own window**. Windows may deny that request; the stdout focus
checkpoints and `foreground presents` count are authoritative for whether the
probe actually owned the foreground. Use a freshly staged `ProbeName`, for
example (after rebuilding the current native probes):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\native\mfg\run_optiscaler_probe.ps1 `
    -RepoRoot (Get-Location).Path -ProbeName UNIQUE_STAGED_PROBE_NAME `
    -Mode visible -Frames 600 -AwaitFocusSeconds 45 -CaptureStatus `
    -CaptureDisplayFrames `
    -CaptureWaitChain -CaptureStacks -TimeoutSeconds 120 `
    -DiagnosticsLeadSeconds 30 -StatusIntervalMs 700
```

The runner kills a hung probe at its timeout, preserves stdout/stderr, status
NDJSON and optional wait-chain diagnostics under `build/`. An FG provider's
successful evaluation and an internal presentation count still require
independent evidence of distinct, actually displayed intermediate frames,
OFF/ON frame pacing, latency and VRAM before claiming working 2x generation.

### 2026-11-09 FG OFF/ON interactive comparison

The isolated, newly rebuilt and checksum-verified baseline packages are
`build/mfg-fg-off-20261109-vram/Package` and
`build/mfg-fg-on-20261109-vram/Package`. Both preserve the pinned Remix,
Streamline, OptiScaler and MFG DLL hashes. The native probe and observer
executables are independently hashed per package. Run this **from a local,
interactive Windows PowerShell session at the physical display**, with access
to the test window and monitor. Do not run from Codex's isolated process
account, a disconnected desktop, or a remote session without display access:

```powershell
cd 'D:\Projects\RTX Remix\rtx-remix-v011'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\native\mfg\run_fg_comparison.ps1 `
    -RepoRoot (Get-Location).Path -Frames 600 -AwaitFocusSeconds 45 -TimeoutSeconds 240
```

Click **each isolated test window** when it opens and keep it in the foreground
until the test completes; the OFF and ON runs execute sequentially. If
Desktop Duplication fails with `0x80070005`, record the observer log and stop
at Gate H BLOCKED. Do not alter Windows security settings to bypass it.
The comparison report is written to a unique `build/mfg-fg-off-on-compare-*.json`
path and contains source FPS, compositor-update FPS, overlapping sample
intervals, source `Present` call duration, and any available per-process DXGI
local-video-memory usage/budget (a WDDM estimate, **not total GPU VRAM**).
Each run gets a unique trace ID. Provider statuses must match the launched
process's PID **and process-creation FILETIME**, have a matching QPC clock,
and show positive FG evaluation/success/batch counter deltas **during the
measured foreground source/DWM overlap**, within **one contiguous run of at
least two snapshots where both `fgEnabled` and `fgApplied` are true**.
The report retains total overlap `counter_delta` while
`provider_measured_windows.on.enabled_activity.intervals` details each active
run and its counter increases. Deltas crossing disabled snapshots or separate
active runs cannot qualify. The OFF trial must keep both flags false and
evaluation/success/batch/failure counters at zero. Snapshot states are only
observed at polling instants; they do not prove continuous FG application.
The comparison polls these snapshots every 250 ms by default; use
`-StatusIntervalMs 200` or a higher `-Frames` value if the render interval is
too short for provider deltas to be observed. Counter increases during startup
or shutdown cannot satisfy the controlled diagnostic.
These counters do not measure physical scanout or end-to-end input latency.
Even apparently doubled compositor FPS requires independent verification of
generated Vulkan image identity, monitor display output and stability.

Earlier direct Codex-runtime attempt on the FG ON package at 13:38 WIB failed
the interactive foreground gate (`exit 4`), and the desktop observer returned
`0x80070005` (`exit 3`). There were 0 source frames, 0 desktop samples and
0 FG provider evaluations. The staged packages, 57 Python regression tests and
both native 3-test CTest configurations and isolated verification passed;
**Gate H remains BLOCKED**.

### 2026-11-10 independent run identity and trace-hash revalidation

The native runner now records a unique `.termination.json` for each invocation,
including the real process PID and Windows process-creation FILETIME, whether
the requested render loop finished, the exit/timeout outcome, and SHA-256
digests of each collected source-present CSV, DWM CSV, status NDJSON, and
observer log. Uncollected artifacts have `null` hashes. The OFF/ON analyzer
requires all four populated, matching hashes for each visible run, plus the
observer's target PID and the process identity in its provider status. Swapped,
modified, missing, or stale traces fail closed; they cannot establish Gate H.

An isolated hash-binding confirmation used the **unchanged, verified NVIDIA ON
baseline** `build/mfg-fg-on-20261109-vram/Package` and a fresh disposable copy
at `build/mfg-fg-on-hashcheck-91e51f53648e/Package`. The 2026-11-10 01:41 WIB
hidden trial (real PID **20856**, process birth **134387232961432322**)
completed **40/40** native source presents with zero Remix render failures and
retired the Vulkan host. It then hung after `Beginning Remix Shutdown`, was
terminated at the enforced **30-second** deadline, and returned runner exit **1**.
Its termination result is `shutdown_timeout_after_complete_render`, **not**
`clean_shutdown`; it remains eligible only for tightly checked diagnostics.
The **95** matching provider-status snapshots reported **zero** FG feature
creations, evaluations, successful evaluations, and batches, with both FG
enabled/applied flags false; there were **15** transient status-read races and
**zero** process-birth mismatches. The real `.status.ndjson` SHA-256 matched
the termination's `trace_sha256.status` field exactly:
`e1d853fcfb5a476e6c0032ec44fa712056c1b5401e17c675558bab75299b59c9`.
The exact record is in `build/mfg-fg-on-hashcheck-91e51f53648e/probe-logs/`.
No foreground, DWM, or physical scanout evidence was collected in this hidden
trial. A separate preceding 70/70 hidden trial also timed out during shutdown
after 45 seconds with zero FG evaluations. The fresh OptiScaler log still says
`Dynamic MFG not supported: driver missing required components`; this message
is evidence of a provider limitation on this tested configuration, not a
verified repairable missing DLL or proof that replacing a DLL enables FG.

The analyzer's tamper/mixed-run tests, Python test suite (**83 run, 80 passed, 3 skipped**) and both PowerShell script parser checks have passed at this stage;
the skipped cases belong to already archived, optional diagnostic code. Gate H
remains **BLOCKED**, as does Gate E (RTXDI stationary pulsing). Native source
rendering plus a watchdog termination is no substitute for working NVIDIA FG.
For the next acceptance attempt, use this exact bounded command **locally at
the physical, interactive Windows desktop**; click and keep each native probe
window in the foreground when it appears:

```powershell
cd 'D:\Projects\RTX Remix\rtx-remix-v011'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\native\mfg\run_fg_comparison.ps1 `
    -RepoRoot (Get-Location).Path -Frames 600 -AwaitFocusSeconds 45 `
    -TimeoutSeconds 240 -PythonExe 'C:\Users\vijja\miniconda3\python.exe'
```

Any nonzero observer exit, absent genuine provider evaluations/batches, or
failure to acquire focus leaves comparison blocked. Even a passing controlled
provider/DWM comparison still needs GPU-completed intermediate-image identity,
physical scanout, latency, dedicated/shared GPU VRAM, and frame-pacing tests
before FG can be certified on the RTX 3070 Ti. Preserve the immutable OFF/ON
baseline packages; rollback is to stop using the disposable test directories
and disable the opt-in development adapter without modifying the Minecraft
profile or pinned binaries.

### Vulkan FSRFG callback, GPU readback and shutdown traces (2026-11-09)

The isolated Vulkan WSI + NGX test completed 64 source presents and NGX
evaluations. Compiled, pinned r3/r4 OptiScaler diagnostic DLLs now record 54
successful FFX callback Dispatch begin/end pairs (frames 11–64), 54 requested
generated frames, 118 `VK_SUCCESS` provider output-present calls, 118
output-image slot events, and nine adapter image-handle events. The successful
64-frame r4b repeat used PID 7504; its log SHA-256 is
`732e0ddd3159e86ea9796469157fc40c9e71e90197c5e4a5ae7a9339f5407c5d`.
The audit reported no callback duplicates, cancels, or Dispatch failures.
FFX frame-pacing-tuning Configure previously returned an independent runtime
error; that optional path remains unresolved. The r5 section below records
bounded GPU-completed pixels; actual monitor scanout, latency, VRAM and useful
2x FG remain unproven.

The compiled r4 shutdown trace shows `plain` NGX shutdown, feature release,
parameter destruction and Vulkan WSI teardown all completed in 4-frame and
64-frame isolated runs. The `device` variant crashed with `0xC0000005` inside
the original forwarded `NVNGXProxy::VULKAN_Shutdown1(VkDevice)` before
`Nvngx_FG::VULKAN_Shutdown1`. The source delegates from Shutdown1 to plain
Shutdown, so any future fix must also audit double-cleanup semantics. The
original vendor DLL is deliberately not detached in this disposable fixture;
normal production unload is not yet verified.

`prepare_fsrfg_trace.py` checks pinned OptiScaler commit
`aeb1f29783106b96c89ba71ce9b6db80eacdae46`, and emitted the original r2
source-only overlay without changing upstream inputs. Its exact-revision nine
submodules were then initialized in separate disposable r3/r4 clones; the r3
callback/present and r4 shutdown diagnostic DLLs were compiled and hashed.
Both keep PID-scoped callback entry/cancellation/Dispatch results and Vulkan
present results and slot hashes. These are CPU observations; slot hashes do
not establish GPU completion, image content, or physical monitor scanout.

The r4 DLL SHA-256 is
`40a997387cc6f219fbc5fb2b5a123e1ff2e5eeb6c996c54b69930ddf597fd7af`;
the untouched upstream OptiScaler DLL is
`0b70d723f61fcf1cc38c26e4033666bd08936f435a848f624222c77dc86ca7fe`.
OptiScaler rewrites its own INI and log when executed. Running inside the first
r4 diagnostic package invalidated its original INI hash in the manifest. Keep
that evidence unchanged. A new verified package was staged at
`build/mfg-fg-fsrfg-shutdown-20261109-r4b/Package` and is **never run directly**;
`run_ngx_wsi_probe.ps1` first invokes `prepare_ngx_run_copy.py` to verify its
manifest and clone it to a fresh unique `build/` path. The source r4b manifest
still passes verification after both completed probes.

Reproduce a bounded NGX dispatch and cleanup diagnostic using a **new** tag:

```powershell
cd 'D:\Projects\RTX Remix\rtx-remix-v011'
& .\native\mfg\run_ngx_wsi_probe.ps1 -RepoRoot (Get-Location).Path `
    -Dll '.\build\mfg-fg-fsrfg-shutdown-20261109-r4b\Package\OptiScaler.dll' `
    -ExpectedSha256 '40a997387cc6f219fbc5fb2b5a123e1ff2e5eeb6c996c54b69930ddf597fd7af' `
    -ShutdownMode plain -Frames 64 -IntervalMs 20 -TimeoutSeconds 38 `
    -PythonExe 'C:\Users\vijja\miniconda3\python.exe' -Tag UNIQUE-RUN-TAG
& 'C:\Users\vijja\miniconda3\python.exe' `
    native/mfg/prepare_shutdown_diagnostic_package.py --repo-root . `
    --probe-name mfg-fg-fsrfg-shutdown-20261109-r4b --verify-only
```

Use the `Probe PID` and `providerLog` printed by that run for the separate
`analyze_fsrfg_trace.py` audit. Four frames cover only warm-up and therefore
have no Dispatch events; use 64 frames for an audit expecting FG callback
Dispatch. The previous r4b 64-frame audit is
`build/mfg-profile-ngx-ninja/validation-20261109/r4b-copy-plain64-20261109-a.trace-audit.json`.

When a new isolated diagnostic run completes, audit its log using the actual
process PID:

```powershell
python native/mfg/analyze_fsrfg_trace.py --log ABSOLUTE_TRACE_LOG `
    --expected-pid ACTUAL_PROBE_PID --output ABSOLUTE_NEW_AUDIT_JSON
```

The audit rejects mismatched or out-of-order callbacks, requested-count
changes, duplicate skips, failed FFX dispatch, failed output present and mixed
PIDs without an explicit target. It also checks opt-in GPU-copy/completion
matching, SHA-256 syntax, uniqueness and per-frame distinctness. Unattributed
GPU readbacks in mixed-PID logs are rejected. Even a valid audit leaves Gate H
**BLOCKED** pending independent displayed-frame evidence, OFF/ON frame pacing,
VRAM, latency, useful interpolation and fully validated normal shutdown.

### r5 isolated GPU-content diagnostic (2026-11-09)

The separately built `build/optiscaler-fsrfg-gpucontent-build-20261109-r5`
OptiScaler fork is pinned to `aeb1f29783106b96c89ba71ce9b6db80eacdae46`
and the same nine submodule revisions. Its diagnostic DLL SHA-256 is
`a8e0d5b2bb4f5e13baa5a7694573c78a1187afbc1063974281368150320e6e7f`.
`native/mfg/prepare_gpucontent_diagnostic_package.py --repo-root .
--probe-name mfg-fg-fsrfg-gpucontent-20261109-r5 --verify-only` checks the
immutable `build/mfg-fg-fsrfg-gpucontent-20261109-r5/Package` without modifying
it. `-GpuContent` on `run_ngx_wsi_probe.ps1` enables up to 12 paired, 64x64
image-to-staging copies and GPU-event completion checks, with SHA-256 of the
generated and real output regions. This instrumentation changes pacing and
is suitable only for isolated content probes.

The first r5 run (PID 38720) completed 12/12 copies, 12 generated-vs-real
distinct samples, 11 unique generated hashes and 11 unique real hashes. Its
sampled center region **did not cover the moving object**, so it cannot prove
useful motion interpolation. An opt-in-only native NGX fixture change positions
the moving 90x70 source box across the output's center ROI, while preserving
ordinary test stimulus and per-frame motion vectors. The fresh aligned r5
run, `gpucontent-r5-roialigned-20261109-2321` (PID 6808), exited 0 with 64
NGX evaluations, 54 successful FFX Dispatch callbacks, 118 successful provider
present calls, and 12/12 GPU-completed samples. All 12 generated hashes are
different from their corresponding real hashes; each of the generated and real
series has 12 unique hashes. Its provider log SHA-256 is
`1b895a79086ae0199d4790874885d60a52fda8cb70da55baeac409591f454b51`.
Its native stimulus log SHA-256 is
`0936fb0e409461dcc4f04cedb88c24ec9e6c04d97ea28354f1b9b76979c32d70`.
The correlated audit confirms that the **source box projects into all 12
sampled regions** and its moving left edge crosses the mapped region; it does
not prove the upscaler's generated pixels actually represent the intended
intermediate motion. Both traces leave independently composited/displayed
frames, physical scanout, pacing and useful 2x FG **BLOCKED**.

To reproduce, use a NEW unique tag and the verified r5 DLL above with
`run_ngx_wsi_probe.ps1 -GpuContent -ShutdownMode plain -Frames 64
-IntervalMs 20 -TimeoutSeconds 38`. Give the fresh provider log and stdout
to `analyze_fsrfg_trace.py --log PROVIDER_LOG --stimulus-log SOURCE_STDOUT
--expected-pid ACTUAL_PID --output NEW_AUDIT_JSON`. The successful audited
result is in `build/mfg-profile-ngx-ninja/validation-20261109/
gpucontent-r5-roialigned-20261109-2321.stimulus-gpu-audit.json` (line wrap
omitted in the actual filename). The `plain` NGX path finished the disposable
Vulkan teardown; final vendor DLL detach remains intentionally skipped. The
`device` shutdown crash is still unresolved. The r5 source/package and pinned
baseline have not been modified.

Nine dependency submodules are installed at their exact revisions in the
diagnostic clones only; both r3/r4 instrumented DLLs compiled successfully.
Keep the pinned upstream checkout, original `OptiScaler.dll`, r3/r4/r5 logs,
and original r4 INI/manifest evidence unchanged. Gate H stays **BLOCKED**
until useful motion interpolation, foreground OFF/ON testing and independent
physical displayed-frame and stability measurements succeed.

`-AwaitFocusSeconds` requests foreground activation for the native probe's own
window and waits for the user to click it if Windows rejects the request. An
unfocused run exits before rendering and cannot verify FG. `-CaptureDisplayFrames`
requires `-Mode visible` and the built `MfgDisplayFrameObserver.exe`. It records
one CSV of source `api.Present` QPC timestamps and one independent CSV of 256x256
desktop-composed pixel hashes with DWM presentation times, only while this
specific test window owns the foreground. Its observer log records unsupported
desktop duplication (for example remote desktop/HDR) explicitly. Neither
successfully duplicated DWM pixels nor distinct pixel hashes proves that FG
interpolated those pixels or that they reached physical monitor scanout. Use
controlled FG OFF/ON testing and independent displayed-frame validation before
certifying the feature; do not count CPU process memory as GPU VRAM.

Insert (`VK_INSERT=45`) opens the shared OptiScaler menu; End (`VK_END=35`)
toggles its FG. The standalone `RTXMFG-UI.ini` does not configure these shared
controls. Keep Remix's native `rtx.dlfg.enable=false`: that checkbox requests a
different presenter. The development loader clears a saved conflicting request
before startup, and `/rtx mfg reset` clears it in-game without changing adapter
FG or quality. Explicit custom INI shortcuts/overlay opt-outs are preserved;
only missing/automatic settings migrate, with an adjacent backup.

For an isolated control regression, append the absolute shipped lighting-conf
path and `controls` after `hidden 140`. The probe posts Insert twice and End
twice only to its own window, and verifies a seeded native FG request was cleared.
Inspect that process's fresh OptiScaler log for menu opening/closing and
`FGEnabled` false/true. This passed with two FG features and zero failed batches;
the hidden window has zero evaluations, so the result does not measure FG gain.

For neural discovery, keep the selected unchanged `nvngx_dlssnr.dll` beside the
ASI and include it in the manifest. The 150-present hidden probe detects it but
creation returns unsupported (`0xBAD00001`) with zero evaluations on the tested
3070 Ti. `/rtx dlss5` exposes controls/status in Minecraft without bypassing
provider admission. The second native-overlay chain was removed after a startup
hang; the earlier standalone menu test does not establish safe ASI chaining.
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

## Stock-runtime neural option probe

`RemixNeuralProbe` tests the runtime's own neural path independently of MFG and
OptiScaler. Build that target with the configured native CMake project, then run
`RemixNeuralProbe.exe ABSOLUTE_RUNTIME_DLL` from a fresh disposable working
directory containing a copy of the shipped `rtx.conf`. It loads only the runtime
and its dependencies, owns a hidden window, submits a triangle for 60 presents,
and requests/restores `rtx.dlssNeuralRendering.enable`. It prints exact C API
failures and the provider path if a provider is loaded at its module checks.
Never interpret option acceptance as feature creation or evaluation success.

The 2026-11-03 stock test completed and restored False after requesting True;
the actual NGX support result was Available 0 / FeatureNotSupported. A disposable
same-runtime trial with the checksum-verified community SF-v2 provider instead
reported FeatureNotFound. Neither produced verified neural evaluations. See
[research, exact hashes and limitations](../../docs/MFG_UNLOCKER.md#native-remix-dlss-nr-and-autopilot-research-2026-11-03).
The alternate provider is not a tracked or redistributed build dependency.
