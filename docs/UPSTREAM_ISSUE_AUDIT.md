# Upstream issue review: Minecraft 26.3 branch

Reviewed 2026-11-01 against the open issues in
[NVIDIA's original repository](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues).
The complete REST inventory contained 45 open issues; the connector's first
search response contained only 20, so older reports were fetched separately.
These are community-branch findings, not upstream issue resolutions. No issues
were closed, no comments posted and no upstream pull request opened.

## Changes prepared after Beta 1

| Report | Finding and treatment | Validation limit |
| --- | --- | --- |
| [#69](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/69) skylight snapshot exception | Confirmed stale default minimum in `ServerLightSnapshot`. Each publication now freezes the live sentinel; deleted and absent columns use that value, stored entries retain their values, older views remain unchanged. | Headless regression uses Minecraft's real sky-data constructor across changing minima and layer merges/rebases. |
| [#54](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/54) startup failure hides terrain | Initialization exceptions now disable the capture master flag. SDK presence is no longer falsely reported as missing. Re-enabling an uninitialized renderer is rejected. | Java-side fallback mitigation; does not repair Vulkan initialization or driver failures. |
| [#65](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/65), [#80](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/80) item artifacts | Standalone GLINT blend passes were captured as ordinary surfaces despite unsupported scrolling decal semantics. Exclude those passes while retaining base item geometry. | Conservative mitigation: standalone glint is omitted. This does not establish that every purple item report has the same cause. Visual confirmation pending. |

## Further headless work after the initial batch

- **#20:** added `ShippedProfileUpdater`. Recorded unchanged defaults can
  update; edited files, unknown legacy copies, custom files and retired profiles
  remain intact. Matching legacy defaults can be adopted. Tests cover deleted
  files, malformed metadata and JAR filesystems. Unknown old defaults cannot
  be identified retroactively without a trustworthy prior hash.
- **#82:** removed an unused intermediate GPU block-atlas upload. The final
  AO/padding-adjusted atlas is still uploaded once. At 16384 square the avoided
  upload contains 1 GiB of base-level RGBA8 input. Actual VRAM reduction and
  Yitality compatibility remain unmeasured. Non-SSS specular maps also no longer
  allocate an unused per-sprite RGBA SSS buffer.
- **#29 (partial):** both vanilla beacon beam programs now select emissive
  surface mode. Tests use real game pipelines. This adds no analytic beam
  lights and does not certify brightness or volumetrics.
- **#14/#15:** tests bootstrap Minecraft's real block registry and exercise the
  exact face predicate used by capture. Matching glass faces are culled; leaf
  faces beside top/bottom half-slabs remain visible. Later mesh/native shading
  artifacts are not ruled out by those checks.

## Other open reports reviewed

The progress above supersedes initial assessments below where applicable.

| Report | Finding / remaining limitation |
| --- | --- |
| [#82](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/82) high-resolution pack VRAM exhaustion | A 16384-square atlas and multiple PBR maps can require substantial native allocations. No reproduced Yitality workload or verified VRAM reduction here; do not claim the memory problem fixed or silently lower all packs' quality. |
| [#81](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/81) Litematica/Minihud/Axiom | Arbitrary mod overlay geometry is not automatically a Remix scene surface. Needs a specific integration and compatible 26.3 mod builds. |
| [#76](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/76) held glass tint | Camera-relative scaling versus material absorption distance is plausible. Changing shared world materials would alter placed glass; no unverified global tint change applied. |
| [#73](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/73) purple shadows/PBR | Report alone does not establish a material-decoding defect. Resource-pack and runtime validation still needed. |
| [#72](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/72) modded models | Custom renderer pose/texture/geometry conventions need per-mod capture adapters and reproduction. |
| [#67](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/67) oblique glass shows sky | Native refraction/geometry interaction not reproduced. No blanket refraction setting change. |
| [#64](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/64) resize heap corruption | Native runtime crash; JVM tests cannot validate a native allocator repair. No ABI/header-only changes applied. |
| [#62](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/62) rain puddles | Feature request, not a confirmed regression. No untested world-wide material replacement. |
| [#58](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/58) FRAPI block tint | The 1.21.1 harvest path described in the report differs from this port. The 26.3 baked-quad path resolves tint indices, but custom Fabric `emitQuads` output is not captured yet. Twilight Forest/FRAPI compatibility is not certified. |
| [#52](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/52) sharp POM | Sampling/height interpolation requires runtime-specific support; not solved by declaring a newer resource-pack version. |
| [#50](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/50) Optimus | Needs affected multi-GPU hardware and native presentation/interop investigation. Startup fallback mitigation is separate. |
| [#45](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/45) distribution platforms | Publishing/distribution request, not a renderer bug. No additional accounts or listings created. |
| [#41](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/41) Proton | Windows build tests do not establish Wine/Proton presentation or UI compositing compatibility. |
| [#39](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/39) windowed performance | Requires matched presentation traces. Earlier chunk/GC work is not evidence of fixing windowed presentation stalls. |
| [#37](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/37) portable Prism/export | Installer exposes `-PrismDataDir`; exporting an uninstalled profile remains distinct from exporting an installed instance. No blanket fixed claim. |
| [#83](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/83) hand jitter | Earlier user pass reported a stable hand, but native temporal convergence is not proved repaired. No additional guessed hand transforms applied. |

The leaf-material overlay and MFG integration remain separate experiments.
Neither is counted as a resolved upstream issue. Existing published Beta 1
assets remain unchanged; subsequent commit-stamped packages are test candidates.

## Older reports included in the full inventory

| Report | Finding / remaining limitation |
| --- | --- |
| [#36](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/36) held End Crystal | Special item-renderer geometry needs comparison; no confirmation that glint filtering addresses this item. |
| [#34](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/34) Linux | Platform port request; Windows validation does not establish native Linux support. |
| [#33](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/33) FG device loss | Native GPU crash; MFG installation is not a fix. No FG setting forced on. |
| [#32](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/32) alpha-card mesh conversion | New geometry-generation feature needing dedicated topology/performance validation, not a safe blanket substitution. |
| [#30](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/30) water through glass | Nested refraction/medium handling requires scene/runtime diagnosis. No global water retuning. |
| [#29](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/29) beacon light | Dynamic colored beam-light feature requires lifecycle, segment and radiance handling. No untested infinite-height light added. |
| [#22](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/22) moving shadows | Correct Java transforms do not prove correct native temporal reconstruction. Requires motion-vector and lighting-history inspection. |
| [#21](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/21) ladder light culling | Need a reproducible connectivity/cull counter trace; disabling all light culling would risk performance. |
| [#20](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/20) default profile updates | Extraction intentionally preserves authored profiles. Needs versioned hash-based migration; do not overwrite user edits as a quick fix. |
| [#19](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/19) cloud distance fade | Report requests a native per-instance API exemption. Do not invent a header flag absent from the pinned runtime. |
| [#18](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/18) rotated grass shading | Requires UV/tangent and normal-map comparison; no guessed UV rotations applied. |
| [#17](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/17) overlapping door/stairs | Geometry/precision investigation needed; offsetting every face could introduce gaps. |
| [#16](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/16) redstone shimmer | Coplanar-layer geometry needs dedicated reproduction; glint filtering is unrelated. |
| [#15](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/15) leaves next to slabs | The 26.3 capture uses vanilla face visibility. Requires geometric comparison; the experimental leaf material overlay does not repair missing faces. |
| [#14](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/14) shared glass faces | Requires neighbour-face/coplanarity verification for each glass type; no global removal of transparent interfaces. |
| [#13](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/13) multiplayer zones | Server synchronization feature; cannot be completed as a client-only lighting tweak. |
| [#12](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/12) powered redstone emission | Dynamic state-aware emissive material feature; existing torch lights do not cover dust. Needs visual/intensity acceptance. |
| [#11](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/11) water inside boats | Raster depth masks have no automatic ray-traced equivalent; needs water clipping or native masking support. |
| [#10](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/10) profile-controlled sun | Requires defined precedence with existing sun updates; no conflicting second light driver added. |
| [#9](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/9) flowing water seams | Fluid geometry, normals and refractive interfaces need matched scene capture. |
| [#8](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/8) far-origin precision | Requires coherent camera-relative coordinates across terrain, entities, particles and lights, not a single float cast. |
| [#7](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/7) shallow-water fog | Medium-volume feature; no arbitrary global absorption reduction. |
| [#6](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/6) horse marking fringe | Needs alpha-edge/material comparison. No blanket entity alpha threshold change. |
| [#5](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/5) general vanilla fog state | Existing dimension/time/weather handling is not general support for every mod effect. Needs a coherent vanilla-fog bridge. |
| [#4](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/issues/4) damage/creeper flash | Multiplicative tint differs from vanilla overlay blending. A correct blend implementation needs material/runtime validation; no untested emissive flash added. |
