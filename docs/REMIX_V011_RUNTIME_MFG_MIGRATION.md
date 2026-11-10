# RTX Remix v0.1.1 / MFG adapter migration  -  26.3 development branch

Status (2026-11-10): **v0.1.1 x64 bridge/build/tests/archive and runtime ABI probe PASS; exact new runtime hash verified. Isolated NVIDIA MFG OFF/ON packages remain staged and hash-verified; the latest 89 Python tests ran with 86 passed and 3 skipped, and earlier native NGX CTests passed. The comparison now binds source, DWM, provider and observer traces to exact SHA-256 hashes, process PID/birth, and per-run termination evidence; swapped or modified runs are rejected. The latest fresh hidden NVIDIA ON probe rendered 40/40 frames with zero render failures and matching status SHA-256, but timed out in Remix shutdown after 30 seconds; its 95 process-matched status samples show zero FG evaluations/batches. A preceding hidden 70/70 run also timed out after 45 seconds, with zero FG evaluations. The OptiScaler log reports `Dynamic MFG not supported: driver missing required components`. Foreground real-display measurement remains BLOCKED because this process could not acquire focus and Desktop Duplication returned 0x80070005. Earlier isolated r3/r4/r5 OptiScaler diagnostics retain nine exact submodule revisions; an r5 GPU readback showed twelve distinct generated-region hashes, but interpolation quality and physical scanout remain unverified. Plain NGX shutdown and disposable Vulkan teardown completed; device shutdown crashed inside forwarded original NVNGX (0xC0000005), and vendor DLL detach remains untested. Immutable packages and per-run copies preserve evidence. Gate H and actual NVIDIA FG acceptance remain BLOCKED. Gate E RTXDI repair remains BLOCKED pending matching runtime source and controlled reproduction.**
This is a developer-only branch. Do **not** merge or ship it until every required gate passes. The original `feat/minecraft-26.3` branch and known-working MFG development profile are intentionally untouched.

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
