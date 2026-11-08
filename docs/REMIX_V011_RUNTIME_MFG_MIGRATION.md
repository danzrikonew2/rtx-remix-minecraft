# RTX Remix v0.1.1 / MFG adapter migration — 26.3 development branch

Status: **v0.1.1 ABI staged; read-only RTXDI source-light diagnostics committed; native build, RTXDI root-cause repair, GPU acceptance and MFG adapter re-pin remain NOT RUN.**
This is a developer-only branch. Do **not** merge or ship it until every required gate passes. The original `feat/minecraft-26.3` branch and known-working MFG development profile are intentionally untouched.

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
- Updated renderer initialization for the 0.16.1 ABI. This is a **candidate**, not a compile/GPU acceptance claim.
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

The existing `native/mfg/patch_remix.py` is deliberately **hard-bound** to the old `d3d9.dll` SHA-256 (`44A313F6D2A6FFA3ECCAAB683C472D14F22080BE7C61D07342D8E199A039D1AD`). The new runtime's hash has not been verified in this branch. Thus the new runtime will NOT pass old host registration, by design.

- Validate the exact `a00da12a` binary, exported C API, image identity, and Vulkan interception timing. Audit whether the existing OptiScaler and MFG hook assumptions still hold in the new DLL.
- Make a narrowly scoped, tested **version-specific host-registration profile** for the new runtime with its actual hash; keep the prior `71a581da` profile intact. Reject any unknown hash, architecture or unsupported binary pattern. Do not weaken `MfgUnlockRegisterRemixVulkanHost` / `MfgUnlockPrivateVulkanStartupReady` / device admission merely to start FG.
- Rebuild the local MFG native source via `native/mfg/build.ps1` using its pinned MFG 1.7.0, Streamline, CUDA input manifests, Vulkan headers and OptiScaler fork inputs. Check all upstream source pins, kernel contracts, ABI, notices and output SHA-256. Never ship an unlicensed third-party binary.
- Stage only into an **isolated development** addon directory with `native/mfg/stage_optiscaler.py` using new manifest hashes; never patch system Java or the public beta's existing addon.
- Verify private Java loader/registration and `OptiRemixProbe.exe` with the new runtime first. Fail closed on missing/mismatched files or unexpected hooks.
- Keep Remix's native `rtx.dlfg.enable=false` for the OptiScaler route; independently test FG disabled vs enabled, native feature creation, status heartbeat, foreground evaluation counts and clean shutdown.

## Gate D: actual presentation & resource acceptance

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
