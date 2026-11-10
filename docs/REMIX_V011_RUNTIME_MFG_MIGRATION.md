# RTX Remix v0.1.1 / MFG adapter migration  -  26.3 development branch

Status (2026-11-11): **v0.1.1 x64 bridge/build/tests/archive and runtime ABI probe PASS; exact new runtime hash verified. Isolated NVIDIA MFG OFF/ON packages remain staged and hash-verified. The native MFG Python suite now runs 92 tests: 89 passed and 3 skipped; the earlier native NGX CTests passed. A matched foreground RTX 3070 Ti comparison now verifies NVIDIA DLSS-G interpolation at the DWM-compositor level: after source frame 30 the FG-OFF trace contains 150 changed orange-target states at 59.394 Hz and FG-ON contains 300 at 119.202 Hz (2.000x state count, 2.007x state rate). All 150 OFF endpoint centroids reappear in ON within 0.01 px (maximum error 0.002 px); every one of the 149 adjacent endpoint intervals contains exactly one additional ON state; 144 intervals have enough motion for normalized midpoint measurement, and 143/144 (99.31%) land within 0.5 +/- 0.15, with 0.063 px median and 0.300 px p95 midpoint error. The same proof remains PASS when the analysis starts at source frame 40 or 60. Bound source/DWM/provider/observer SHA-256 identities pass, the measured provider window records 112 evaluations / 112 successes / 112 batches / 0 failures, and the matching OptiScaler log loads `nvngx_dlssg.dll`, creates DLSS-G successfully, reports max supported interpolations=5, and records 165/165 successful DLSS-G Vulkan evaluations. This establishes correctly ordered intermediate pixels in DWM composition for the isolated deterministic probe. Physical monitor scanout, Minecraft gameplay presentation, input latency, long-session stability, >2x MFG and DLSS 5 neural rendering remain unverified. The OFF run was manually stopped after complete render evidence and the ON run timed out during Remix shutdown, so shutdown remains a separate unresolved issue. Gate H remains BLOCKED because it requires physical scanout/game acceptance; Gate E RTXDI repair remains BLOCKED pending matching runtime source and controlled reproduction.**
This is a developer-only branch. Do **not** merge or ship it until every required gate passes. The original `feat/minecraft-26.3` branch and known-working MFG development profile are intentionally untouched.

## 2026-11-11 NVIDIA DLSS-G DWM compositor midpoint proof

The visible isolated probe was changed to move the rendered triangle instance
instead of the camera and to record its deterministic expected crop centroid.
The independent Desktop Duplication observer now records orange-target centroid,
bounds, edge and mean-color features in addition to the original ROI hash. The
runner suppresses Remix's blocking first-use dialog process-locally and disables
shader prewarming/asynchronous compilation for this diagnostic so the measured
window begins only after the required shader is synchronously available.

Matched 180-source-present OFF/ON captures use identical source motion. From
source frame 30 onward, OFF produced 150 changed orange-target DWM states and ON
produced 300. The ON sequence contains the complete OFF endpoint sequence plus
one state between every adjacent endpoint. Endpoint matching is 150/150 within
0.01 px; 145/150 are identical at CSV precision and the worst mismatch is
0.002 px. Of 149 endpoint intervals, all 149 contain exactly one extra ON state.
Five near-turning-point intervals are excluded because endpoint motion is under
0.15 px. In the remaining 144 intervals the generated state's normalized
position has median 0.5271, p05 0.4512 and p95 0.6246; absolute midpoint error
has median 0.0628 px and p95 0.300 px. 143/144 intervals are within the explicit
0.5 +/- 0.15 acceptance band. Sensitivity windows beginning at frames 40 and 60
remain PASS with 99.26% and 99.13% respectively inside that band.

`native/mfg/analyze_dlssg_compositor_motion.py` reproduces this result and
fails closed if the OFF/ON source motion differs, endpoint correspondence is
missing, the state-rate multiplier is absent, or doubled states merely repeat
an endpoint instead of landing near the midpoint. When given the bound status,
termination and observer artifacts it also verifies their recorded SHA-256
identities without treating shutdown completion as part of the already-flushed
render proof. With the matching OptiScaler log it additionally requires the
DLSS-G output configuration, `nvngx_dlssg.dll`, successful feature creation,
successful NVIDIA Vulkan evaluations, and Streamline's enabled interpolation
state. The resulting report is `build/mfg-syncshader-dlssg-compositor-proof.json`.

This is a major Gate D milestone but is deliberately narrower than physical
display certification. Desktop Duplication observes DWM-composited pixels; it
does not prove panel scanout, motion-to-photon latency, VRR behavior or Minecraft
integration. Those remain separate acceptance work.

## 2026-11-10 Vulkan synchronization2 diagnostic and NVIDIA FG blocker

A new opt-in native WSI `--verify-sync2` mode explicitly enables
`VK_KHR_synchronization2` on Vulkan 1.2, confirms its device command is
resolved, and performs real image-layout transitions through
`vkCmdPipelineBarrier2KHR`. On the RTX 3070 Ti with driver 621.01, the
extension and feature were supported. Legacy and explicit-sync2 source-only
probes each passed 20/20 source presents and clean shutdown; the latter
confirmed `sync2_exercised=1`. The probe executable hash is
`47187e27f80e2d9254f2db3d5e6a288fb52f57212f070eb41a6477702549be0b`.

In two **isolated, hash-verified** pinned OptiScaler copies (vendor DLL
SHA-256 `0b70d723f61fcf1cc38c26e4033666bd08936f435a848f624222c77dc86ca7fe`),
NGX init and four source presents succeeded for both legacy and explicit
sync2. Neither created an FG feature nor evaluated FG. Both hung in plain NGX
shutdown and their own processes were terminated by a 25-second watchdog.
The provider reported a maximum of **one** supported generated frame and
`Dynamic MFG not supported: multi-frame not available` in both runs.
An earlier full ON probe independently reported missing driver components.

The OptiScaler `No Vulkan 1.3 features ... synchronization2` warning also
appeared in the explicitly enabled case: the pinned source checks for a
monolithic Vulkan 1.3 feature struct before later spoof/feature processing.
That message alone does not establish the final feature state, and enabling
the feature in the WSI host did not unlock Dynamic MFG. No NVIDIA generated
output, 2x throughput, 3x–6x support, DLSS 5 neural evaluation, monitor
scanout or FG end-to-end latency is established. **Gate H remains BLOCKED**.
The complete commands, hashes and original run logs are documented in the
[native MFG README](../native/mfg/README.md). Original OFF/ON package pins
and rollback remain unchanged.

## 2026-11-10 real Minecraft desktop verification and NVIDIA-only preflight

An isolated, disposable Creative world was launched from the official Minecraft
Launcher using the existing **Minecraft RTX Remix Community 26.3 Beta
(Experimental)** Fabric profile (game directory
`C:\Users\vijja\AppData\Roaming\.minecraft-rtx-remix-26.3`). The other two
existing worlds and all 1.21.1/vanilla profiles remained untouched. Minecraft
26.3 rendered terrain on RTX 3070 Ti, driver 621.01; Alt+X reported raytracing
enabled and **2423 / 7249 MiB** video memory allocated at one observed instant.
The in-game DLSS Frame Generation checkbox was disabled, DLSS Preset was
Disabled, Upscaler was None and Reflex was Disabled. The F3 display showed
roughly 73 FPS in one sampled scene, which is not verified FG throughput.
The new world was saved and exited to the launcher normally.

This is evidence that **the existing installed experimental profile runs with
RTX**. Its binary identity has not been matched to the newest isolated MFG
packages, so it does not establish NVIDIA FG, DLSS 5 or this branch's latest
native adapter functionality. The separate visible native comparison could
not focus its probe window, returned exit 4 before source frames, and Desktop
Duplication returned `0x80070005`/exit 3 with zero DWM samples. No NVIDIA FG
interpolated/displayed frames or neural evaluations were verified; Gate H
remains **BLOCKED**.

The pinned metadata of both NVIDIA FG OFF/ON baselines passed the new
`run_fg_comparison.ps1 -ValidateBaselinesOnly` check. Missing legacy
`frame_generation_output` defaults to `dlssg`, while explicit null or any
non-`dlssg` value is rejected before launching either test. Full Python
regression verification on 2026-11-10: **89 tests run, 86 passed, 3 skipped**;
the skips are archived optional FSR diagnostic source fixtures. Three native
CTest configurations passed 3/3 tests each. Both full NVIDIA OFF/ON package
verifications passed, including all pinned binary dependencies. Hash-based
package validation and rollback controls remain mandatory. See
[native MFG README](../native/mfg/README.md) for exact test commands and
observed results.

## Identified upstream delta (NVIDIA 2026-11-06)

- Official tag: https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/releases/tag/v0.1.1
- Relevant diff: https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/pull/89
- New runtime: `minecraft-rtx2-a00da12a-win64-release` (previous: `minecraft-rtx2-71a581da-win64-release`).
- C API: 0.16.1 (previous 0.16.0).
- New `remixapi_StartupInfo.useRemixOwnedChildWindow` at the **end** of the startup struct. JNI/Java must pass the field. This flag must remain **false** until the 26.3 RenderPearl offscreen copy is independently verified.
- Zero `PresentInfo.hwndOverride` must still pass a populated native `remixapi_PresentInfo`, **not** `Present(nullptr)`, otherwise external GL semaphore timing arguments can be discarded.

## Changes staged in this branch

- Updated `packman/remix-sdk.packman.xml`, Remix C API header, `RemixAPI`, `RemixBridge`, `StartupInfo`, and native JNI startup/present implementation.
- Added stricter GL/Vulkan semaphore-handle and timeline validation. Preserved old presentation to avoid exposing the overlapped host default framebuffer as a child-window source.
- Updated renderer initialization for the 0.16.1 ABI. The Windows x64 native bridge and Java build pass; rendering remains a **candidate** pending manual GPU acceptance.
- No public installer, production MFG addon, or 1.21.1 profile was modified.

## Gate A: rebuild & verify stock renderer FIRST

1. Stop any Minecraft instance using this checkout. Use a new worktree/profile; preserve saves, `remix-sdk/`, `rtx.conf` and your existing known-good build.
2. On Windows x64 with Java 25 and C++ build tools, fetch the exact new Packman runtime with the repo's build scripts. Record **SHA-256 of the actual extracted new `d3d9.dll`** and package reference; do not infer the binary hash from the package label.
3. Run `./gradlew.bat build test -Parch=win64 --console=plain` and `./gradlew.bat verifyReleaseArchive -Parch=win64 --console=plain`; build/payload inventories and runtime ABI probing must pass.
4. Test a clean **separate** 26.3 Prism profile **without** any MFG/OptiScaler addon. Run `/rtx status`, inspect world, GUI, chat, hands, translucency and HUD. Check fullscreen/borderless, resize, minimize/restore, RTX toggle, world join/leave, and shutdown.
5. Validate that `GlInterop` semaphores neither regress nor deadlock. If the new runtime itself fails, fix the base C API/renderer first: no MFG troubleshooting until the stock baseline is stable.
6. Record exact new runtime SHA, app commit, process-relative DLL location, C API probe result, and any renderer/validation errors.

## Gate B: opt-in child-window presentation, separately

Official 1.21.1 code copies from the Minecraft GL offscreen main framebuffer, **not** from default FBO 0; its `interopFlipY`, semaphore waits and zero HWND override are intentional. In **26.3**, Minecraft uses RenderPearl and SDL3; do not paste `MinecraftClient.getInstance().getFramebuffer().fbo` from the 1.21.1 branch.

Before setting `useRemixOwnedChildWindow(true)`:
- Resolve the **actual 26.3** `GameRenderer.mainRenderTarget()` color texture/backing OpenGL resource and its FBO binding through the supported RenderPearl backend or an explicit audited OpenGL interop adapter.
- Prove framebuffer dimensions, MSAA/resolve status, color space and GUI/HUD inclusions; retain correct GL read/draw binding restoration. Avoid per-frame framebuffer allocations.
- Use the offscreen main target for the GL-to-Remix copy; source FBO 0 is forbidden in child mode. Set `PresentInfo.hwndOverride = 0` only after verified child presentation owns the window.
- Retain synchronization: wait on the Remix Vulkan-done timeline once per value, blit, signal the client-done timeline, then present. Acquire fresh images/handles on swapchain recreation and retire stale ones safely.
- Validate input/cursor ownership, overlays, F8, fullscreen/resizing, minimizing, and Windows HWND lifecycle. Keep a rollback switch until game acceptance.

Child HWND should be optional only for testing until it passes. **Do not claim PR #89 was fully ported simply because the struct exists.**

## Gate C: rebuild/re-pin MFG private Vulkan adapter

The existing known-working adapter remains **hard-bound** to the old `d3d9.dll` SHA-256 (`44A313F6D2A6FFA3ECCAAB683C472D14F22080BE7C61D07342D8E199A039D1AD`). The new extracted runtime hash is `A8365272734CF5541E3600AEACB445C0FD102187DC3A167495A56809CE5891D9`. The development adapter source has a separate AMD64/PE32+ profile for this exact image; old installed adapters still reject it. Hash admission alone is not FG or presentation acceptance.

- Validate the exact `a00da12a` binary, exported C API, image identity, and Vulkan interception timing. Audit whether the existing OptiScaler and MFG hook assumptions still hold in the new DLL.
- Make a narrowly scoped, tested **version-specific host-registration profile** for the new runtime with its actual hash; keep the prior `71a581da` profile intact. Reject any unknown hash, architecture or unsupported binary pattern. Do not weaken `MfgUnlockRegisterRemixVulkanHost` / `MfgUnlockPrivateVulkanStartupReady` / device admission merely to start FG.
- Rebuild the local MFG native source via `native/mfg/build.ps1` using its pinned MFG 1.7.0, Streamline, CUDA input manifests, Vulkan headers and OptiScaler fork inputs. Check all upstream source pins, kernel contracts, ABI, notices and output SHA-256. Never ship an unlicensed third-party binary.
- Stage only into an **isolated development** addon directory with `native/mfg/stage_optiscaler.py` using new manifest hashes; never patch system Java or the public beta's existing addon.
- Verify private Java loader/registration and `OptiRemixProbe.exe` with the new runtime first. Fail closed on missing/mismatched files or unexpected hooks.
- Keep Remix's native `rtx.dlfg.enable=false` for the OptiScaler route; independently test FG disabled vs enabled, native feature creation, status heartbeat, foreground evaluation counts and clean shutdown.

## Optional independent comparison: direct-.trex sm86 Vulkan proxy

A Reddit-suggested RTX 20/30-series method stages the author's `dlssg_for_sm86` sm86-7 `version.dll` and `dlssg_sm86.ini` in the native renderer's `.trex` folder. The release ZIP now includes **manual opt-in** scripts `install-sm86-trex.ps1` and `install-sm86-trex.bat` and the full [SM86_TREX_EXPERIMENT.md](SM86_TREX_EXPERIMENT.md) contract. The helper downloads a pinned SHA-256-checked upstream ZIP only when invoked and refuses unknown/missing runtime layouts or existing files.

**This is not a proven Minecraft 26.3 solution.** Our mod explicitly loads `remix-sdk/d3d9.dll` from Java, and mere placement of a `version.dll` in `.trex` does not guarantee the Java/Vulkan rendering process loads that proxy. Never advertise working FG without module-load, NGX feature, unique-image and presentation evidence. Do **not** automatically invoke this in the ordinary installer or combine it with the existing development OptiScaler/MFG route. The pinned rebuilt adapter remains the primary engineering path.

## Gate D: actual presentation & resource acceptance

**2026-11-09 isolated Vulkan diagnostic (source-side evidence only):** The
64-frame NGX WSI test completed 64 source presents/evaluations, 54 successful
FFX callback Dispatch calls (all requested one generated frame), 118
`provider_output_present` calls returning `VK_SUCCESS`, 118 output-image slot
events, and nine adapter image-handle events. There were zero duplicate,
canceled, or failed callback events. A second run from a fresh copy (PID 7504,
trace SHA-256 `732e0ddd3159e86ea9796469157fc40c9e71e90197c5e4a5ae7a9339f5407c5d`)
matched those counts. Callback return, image-slot reuse, and CPU-side queue
present success do **not** prove GPU completion, unique generated image content,
the monitor's physical scanout, actual 2x speed, or stable frame pacing.
Optional FFX frame-pacing-tuning Configure previously returned a separate
underlying runtime error.

All nine exact-revision OptiScaler dependencies are present in isolated clones;
the checksummed r3 FSRFG callback trace and r4 shutdown trace have been compiled
into separate disposable DLLs. The r4 DLL SHA-256 is
`40a997387cc6f219fbc5fb2b5a123e1ff2e5eeb6c996c54b69930ddf597fd7af`.
The unmodified original DLL remains pinned at
`0b70d723f61fcf1cc38c26e4033666bd08936f435a848f624222c77dc86ca7fe`.
The original r4 package's INI was rewritten by OptiScaler during execution, so
its original manifest no longer verifies and must not be rewritten to match.
The fresh `build/mfg-fg-fsrfg-shutdown-20261109-r4b/Package` is verified and
`native/mfg/prepare_ngx_run_copy.py` creates a new package for every bounded
probe, preventing further mutation of the source package. Four-frame and
64-frame r4b `plain` shutdown runs exited 0, completed NGX and Vulkan teardown,
and left the r4b source package hash-verified. The `device` shutdown variant
crashed inside the forwarded original `NVNGXProxy::VULKAN_Shutdown1(VkDevice)`
with `0xC0000005` before FG-provider shutdown; the underlying cause is still
unresolved. The fixture deliberately skips final vendor DLL detach, so a
production cleanup is **not** certified. Do not silently substitute a skip
or double-shutdown workaround. See [native MFG README](../native/mfg/README.md)
for bounded test commands, trace files, and remaining verification steps.

The later pinned r5 GPU-completed ROI readback uses diagnostic DLL SHA-256
`a8e0d5b2bb4f5e13baa5a7694573c78a1187afbc1063974281368150320e6e7f`
from an immutable isolated package. An opt-in NGX moving-box stimulus places
the moving object across the center 64x64 output ROI in frames 11-22. In
isolated PID 6808, all 12 GPU-completion events are paired with copies and
successful FFX callbacks; 12/12 generated-versus-real hashes differ, all 12
generated hashes are unique, and the independently logged source positions
and motion vectors verify projected ROI intersection and edge movement. This
validates GPU-completed **sampled image bytes** and the intended scene geometry,
but the actual generated pixel motion, scanout, FG 2x throughput, latency,
VRAM and production unload remain unverified. See the r5 commands and source
and trace SHA-256 values in [native MFG README](../native/mfg/README.md).
Gate H is **BLOCKED**; no public build/installer was updated.

The later 2026-11-11 matched NVIDIA DLSS-G OFF/ON compositor test resolves the
generated-motion and 2x-compositor-throughput parts for the isolated probe: its
deterministic moving target preserves every OFF endpoint in ON, adds one
intermediate state in every adjacent interval, and places 143/144 measurable
intermediates inside the 0.5 +/- 0.15 midpoint band while doubling changed DWM
states from 150 to 300. Gate H remains BLOCKED because Desktop Duplication is
not physical monitor scanout and Minecraft gameplay integration has not yet
reproduced this presentation proof.

Use RTX 3070 Ti 8 GB, the new runtime, a focused visible window and a fixed Minecraft camera path.

- Start at 2×. Provider creation/evaluation/batches are necessary but **not** proof that interpolated frames reached the monitor. Inspect actual Vulkan presentation events and use an external presentation measurement where possible.
- Compare FG OFF versus 2×: source FPS, real displayed FPS, 1% lows, CPU/GPU times, present intervals, input latency, GPU utilization and dedicated/shared VRAM.
- Confirm distinct `VkImage` identities and GPU-completed image availability within each generated batch before enabling >2×. The old log's `count=5` output reuse must stay guarded; **never** disable duplicate-output rejection as a shortcut.
- Verify resize/swapchain generation changes, window focus, world transitions, render toggling, VRAM pressure, minimize/restore and normal termination. Watch for `VK_ERROR_DEVICE_LOST` and long-session degradation.
- Do not market 3×–6× or DLSS 5 as working without unique displayed frames and genuine provider success. DLSS 5 currently returns `0xBAD00001` on this RTX 3070 Ti route; keep it independent of FG.

## Gate E: preserve RTXDI temporal reuse and repair stationary light pulsing

This is part of the **same 26.3 v0.1.1 + MFG development build**, with the same runtime verification and rollback gates. The detailed source evidence, test matrix, root-cause decision tree and acceptance criteria are in [RTXDI_TEMPORAL_STABILITY.md](RTXDI_TEMPORAL_STABILITY.md).

**Non-negotiable: keep `rtx.di.enableTemporalReuse=true` and spatial reuse on for the shipping fix.** A previous experimental default of temporal reuse OFF was reverted at user request. Do not reintroduce it or disable denoising/sparse rendering/SHaRC as a proxy "fix." Diagnostic temporary A/B comparisons are permitted only with restoration; measured brightness needs a real native repair.

- The source now instruments successful static block light CREATE/UPDATE/REMOVE, light retirement requests and submitted/culled counts. `/rtx lighting stability` captures an in-game baseline; after 20–30 s of stationary pulsing use `/rtx lighting stability compare` to show CPU-side light churn. Counters are only the first diagnostic layer; 0 churn does not certify GPU reservoir correctness.
- Once the exact a00da12a runtime source/shaders are identified, trace the active light-list/index mapping, temporal reservoir pages, reprojection/motion, history validity, weight/PDF normalization and the denoiser/exposure stages to find **the first stage where the fixed-scene lighting begins oscillating**.
- Fix the identified cause with stable light identities/generations and narrow invalidation/remapping where appropriate, or the specific correct reprojection/bias/weight/sparse-page logic. Do not freeze temporal sampling or clamp arbitrary brightness as a visual cover-up.
- Re-run a fixed-world luminance test, original vs v0.1.1, temporal reuse ON, FG OFF then verified 2x. Record luminance variance/frequency, frame time, VRAM, light-counter deltas and relevant native reservoir evidence.
- If the precise runtime source or a Windows GPU session is not available, leave Gate E **BLOCKED**, submit the instrumentation/reproducible test assets and exact commands, and do **not** claim the pulsing defect fixed.

## Required handoff report

Report: changed files/commits; new runtime binary SHA and ABI probe; compile/tests/package outputs; exact addon/OptiScaler/Streamline pins and hashes; before/after MFG counters; source vs displayed frame measurements; frame pacing; VRAM; failures; manual steps for anything that cannot be tested; rollback commands. Mark gates PASS/FAIL/BLOCKED truthfully. **No merge until Gate A is verified and the new adapter independently passes Gate C/D.**
