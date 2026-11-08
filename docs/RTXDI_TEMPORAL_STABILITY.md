# RTXDI temporal light pulsing — 26.3 source investigation and repair gate

**Status: instrumented; native root cause NOT established; actual visual fix pending RTX 3070 Ti/runtime reproduction.**
Part of [REMIX_V011_RUNTIME_MFG_MIGRATION](REMIX_V011_RUNTIME_MFG_MIGRATION.md). This is an explicit requirement of the combined development build, not a separate release.

## User-observed defect and non-negotiable requirements

- Minecraft Java 26.3 RTX Remix, RTX 3070 Ti 8 GiB. With a stationary camera, torches, wall torches, glow berries, glowstone, sea lanterns and other light sources periodically brighten and dim.
- Prior A/B: switching **RTXDI Temporal Reuse OFF** stopped the visible pulsing. This is evidence the temporal path matters, **not** proof of the exact defective code.
- **Do not disable RTXDI, RTXDI temporal reuse, RTXDI spatial reuse, denoising, sparse rendering, SHaRC or NRC as a shipped fix.** Preserve the performance and image-quality benefits. Diagnostic temporary A/B toggles may be used to localize the fault and must be restored.
- Preserve resource pack texture artwork, authored `_s` emission, per-block analytic intensities/colors and intentional animated ore shimmer. Never lower intensities simply to conceal the defect.
- Do not rework 1.21.1, `main`, existing game profiles or the proven MFG development addon.

## Evidence from source inspection

1. `BlockLightKey` identifies a static light by block position, rule ID, and per-rule light index.
2. `ChunkManager.LightReconcileTask` transfers existing `TerrainLight`/native `RemixLight` ownership across recaptures. Fingerprint-equal entries do not call native UPDATE. Otherwise, native CREATE/UPDATE/REMOVE is budgeted. Thus ordinary recapture is *designed* not to churn unchanged lights; whether a real Minecraft session actually churns is unmeasured.
3. `ChunkManager.draw` submits existing `RemixLight.drawFast` for lights passing reachability/weight culling on each frame. The static light should be consistently submitted while the camera is fixed, but cull status, world reload and active light lists still require evidence.
4. `RemixLight.update` calls CreateLight with the original hash and may replace a native handle. A genuine UPDATE may invalidate runtime tracking; check how the **exact pinned runtime** treats same-hash re-creation.
5. Official dxvk-remix source has `rtx_rtxdi_rayquery.cpp/.h` and the shader `src/dxvk/shaders/rtx/pass/rtxdi/rtxdi_temporal_reuse.comp.slang`. The shader accesses prior screen-space motion, previous best-light candidates, virtual motion, depth/normal confidence, reservoir input/output pages and bias correction. A static view alone does not guarantee that reprojected history, light indexing and sampling weights are valid.
6. The public `dxvk-remix/main` source may not match the binary used by `minecraft-rtx2-a00da12a`. **Do not patch a public source revision and assume the distributed DLL implements it.** Identify the new runtime's corresponding source/commit, shader bundle and build provenance first.
7. The existing foliage SHaRC workaround addresses a distinct daylight/foliage defect. Do not conflate its root cause with RTXDI source pulsing.

## New nonintrusive diagnostic in this branch

`ChunkManager.lightSubmissionSnapshot()` collects cumulative successful native light CREATE/UPDATE/REMOVE requests, retirement requests, completed draw frames and the most recent number of drawn/culled/beyond-reach lights. Counters are updated at existing successful operation sites, without per-frame allocations or logging. The command stores a snapshot only when explicitly invoked:

```text
/rtx lighting stability
# Hold the same viewpoint for ~20–30 seconds while the glow pumps.
/rtx lighting stability compare
```

The output reports **CPU-side light churn** and current resolved RTXDI temporal/spatial/sparse/exposure flags. It does **not** directly observe runtime light list reorder, RTXDI reservoirs, GPU pixel luminance, or displayed FPS. A result of 0 creates/updates/removes plus constant drawn/culled counts while the glow pulses would *rule out many mod-side churn explanations* and justify moving to native RTXDI instrumentation. Do not equate these counters with a completed fix.

### Controlled root-cause isolation matrix

Use an unmodified fixed camera and pinned weather/time for each scene in a disposable world. Test with FG/MFG OFF until the native renderer is stable. Every short diagnostic A/B toggle must be restored after capture. Capture synchronized 30-second video + numeric pixel luminance from a fixed ROI, camera matrices, FPS/frametime and flags; avoid automatic brightness changes masking the signal. Do **not** ship permanently locked exposure.

| Test | Change only this factor | Diagnostic conclusion |
|---|---|---|
| A | one analytic block light, no authored surface emission | isolates explicit light / RTXDI sampling |
| B | one emissive surface, no analytic light | isolates emissive triangle/emissive surface path |
| C | analytic + emissive together | detects combined-source competition or duplicate accounting |
| D | auto exposure ON/OFF temporarily | separates post-exposure pumping from irradiance changes |
| E | temporal reuse ON/OFF temporarily | confirms whether the current runtime reproduces the earlier observation |
| F | sparse rendering ON/OFF temporarily | distinguishes inactive pixel/reservoir-page history faults |
| G | same scene old runtime vs v0.1.1 new runtime | isolates regression/fix, provided both have correct C API + rendering |
| H | unchanged static light vs one legitimately changed dynamic light | verifies history invalidation occurs only when needed |

Prioritize **A–F** without rewriting algorithms. Test GI, reflection, tonemapping and DLSS modes only if the above leaves the source ambiguous.

### Native instrumentation and root-cause decision tree

Instrumentation must be debug-only, sampled/bounded, exact-runtime-compatible, and synchronized with the GPU. Never add per-pixel debug printf to shipping shaders or stall the render loop per frame.

1. Record frame index, active RTXDI local light count, unique stable light hashes/handles, mapping from light identity to current light-list index, `LightPower`/radiance, and add/remove/reorder counts. Compare CPU command results to native lists. **If native light list changes while input is unchanged**, correct identity mapping or churn at the responsible layer.
2. At pre-temporal (initial candidate), after temporal reuse, after spatial reuse and after denoising/post-exposure, record *small bounded sample tiles* with mean/variance/min/max luminance and reservoir diagnostics: light index, light identity or generation where available, age/M, PDF and accumulated weight, history validity, bias-correction result, previous G-buffer similarity/reprojection confidence. Compare the same pixel across successive frames and match exact SDK semantics.
3. If first instability appears at **RTXDI temporal reuse**, distinguish:
   - stored candidate index now references a different light, or refers to a removed source;
   - invalid motion/reprojection due camera jitter, Minecraft game transform or incorrect interop G-buffer;
   - invalid reservoir M/weights/PDF or stale sample with insufficient bias correction;
   - history page/index mismatch on sparse inactive pixels;
   - temporal estimator noise due insufficient candidate sampling in high-contrast emissive scenes (not necessarily a correctness bug).
4. **Repair only the verified failure**:
   - Identity/reorder: carry stable light identity plus epoch/generation, remap to the current index or reject the *specific* stale sample; do not clear all valid history.
   - Reprojection: correct motion/G-buffer and validity thresholds without discarding valid stationary history.
   - Reservoir math: repair PDF/weight normalization, finite checks or relevant bias correction; retain normal temporal reuse.
   - Sparse page: synchronize page ownership/activation and history generation to prevent stale inactive-pixel reuse.
   - High-variance estimator: first test targeted candidate sampling/best-light guidance or temporal confidence clamping with bounded unbiasedness/performance checks; don't make static light brightness artificial or frozen.
5. Preserve stable light hashes, source intensity/radiance, motion, DLSS denoiser, temporal reuse, spatial reuse, and fixed camera output. Use only opt-in debug controls to compare original/new behavior. Avoid hacks that spoof reservoir validity or modify resource-pack emission to conceal pulsation.

### Acceptance

- Confirm numerical reduction in periodic luminance fluctuation in fixed same-scene test **with `rtx.di.enableTemporalReuse=true` and `rtx.di.enableSpatialReuse=true`**.
- Static emitters retain visibility/identity; no invented light changes in stationary world.
- Real switch on/off, block breaking, held torches, resource reload, movement, chunk boundary and camera cuts converge correctly without new ghost trails or light smears.
- Similar or better temporal performance/frametime versus previous temporal-enabled baseline; report any tradeoffs explicitly, especially on 8 GiB RTX 3070 Ti.
- Compare direct light, GI, denoising, HDR/exposure and FG OFF vs development FG 2x. Verify no unbounded VRAM growth, device loss, or startup regression.
- Run JVM tests, focused native shader tests, frame captures and actual Windows gameplay. Report PASS/FAIL/BLOCKED for each test with measured outputs; code inspection alone never passes visual acceptance.

## Upstream reference locations

- https://github.com/NVIDIAGameWorks/dxvk-remix/blob/main/src/dxvk/rtx_render/rtx_rtxdi_rayquery.cpp
- https://github.com/NVIDIAGameWorks/dxvk-remix/blob/main/src/dxvk/rtx_render/rtx_rtxdi_rayquery.h
- https://github.com/NVIDIAGameWorks/dxvk-remix/blob/main/src/dxvk/shaders/rtx/pass/rtxdi/rtxdi_temporal_reuse.comp.slang
- https://github.com/NVIDIAGameWorks/dxvk-remix/blob/main/src/dxvk/shaders/rtx/algorithm/rtxdi/rtxdi_temporal_history.slangh
- https://github.com/danzrikonew2/rtx-remix-minecraft/blob/feat/minecraft-26.3/docs/RESOURCE_PACKS.md
