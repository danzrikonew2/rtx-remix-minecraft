# Rendering Diagnostics

## Bright foliage after time changes

The transition layer `mc.lighting.settling` briefly reduces SHaRC history after
an abrupt Overworld clock change or moving weather. It retains warm cache
entries and restores the authored history settings afterwards. It is a
mitigation under visual testing, not proof that cached lighting causes every
bright foliage patch.

For a reversible comparison in the same view:

```text
/rtx lighting cache
/rtx lighting cache off
/time set day
/time set midnight
/rtx lighting cache on
```

Repeat the time changes with queries on. `off` bypasses primary thin-opaque
foliage queries, not the whole renderer. `on` restores those queries. Status
reports resolved values; a write may take a native frame or more to resolve.
Each command writes its result to `logs/latest.log`. Restore `on` after the
comparison. Report whether the bright patches differ with cache queries off,
and whether they fade while the camera stays still.

Read the [architecture and invariants](../AGENTS.md#architecture) first. This
guide explains failure signatures and the ownership boundaries behind them;
[Benchmarking](../tools/docs/BENCHMARKING.md) owns measured counters and
[Profiling](../tools/docs/PROFILING.md) owns capture analysis.

## World Transitions

Fabric's `ClientPlayConnectionEvents.JOIN` and `DISCONNECT` are not paired.
`DISCONNECT` fires when the connection closes. A server reconfiguration
(`EnterReconfigurationS2CPacket`) switches the play handler to a configuration
handler without closing that connection, clears `client.world`, and fires
`JOIN` again when play resumes. Modded servers and proxies switching backends
can do this; the integrated server does not reconfigure.

The `RtxRemixMod` disconnect cleanup therefore does not run on that path:
renderer world clear, benchmark and camera session reset, and world conf-layer
release cannot be assumed to have happened. The null-world frame path hides
retained terrain and discards the prepared particle payload. Join handlers
must release the previous session before acquiring the next one, as the zone
registry clear and `ConfLayerDriver.onWorldJoin` do.

Schedule transition work through the client executor and re-check the session
when it runs. A flag drained from `WorldRenderEvents` or the submit hook will
not drain while the world is null. It can instead clear native resources in
the first frame of the next world, during their reinitialization.

## Terrain Recapture

`RtxRemixMod.rebuildLoadedTerrain()` owns the full recapture sequence:

1. Clear the Remix terrain through `ChunkManager.clear()`.
2. Snapshot `builtSections(client)` before requesting a vanilla terrain reload
   through `LevelExtractor.allChanged()`.
3. Call `recaptureTerrainForRemix(client, built)` to retain the currently
   resident, non-empty, lit subset, scoped to this world.
4. At the return of `LevelRenderer.invalidateCompiledGeometry`, queue that set
   against the replacement section storage, rechecking residency and lighting.

In 26.3, `allChanged()` defers geometry invalidation until extraction. That
invalidation releases old buffers and cancels the old compile queue. Queueing
recapture immediately after `allChanged()` therefore loses work on the next
extraction, producing holes after toggles or reloads. `TerrainRecaptureState`
holds positions across this boundary and retains only accepted work for a
subsequent reload; disconnect cleanup is scheduled on the client thread and
cannot erase another world's request.

The RTX toggle and material/texture reload paths preserve the same contract.
A clear alone leaves an empty path-traced world until vanilla happens to
rebuild. A reload alone schedules only what its current occlusion graph
reaches and can omit terrain the prior scene held. The explicit queue restores
the previously built set, including accepted work still pending from an earlier
recapture in the same world. It does not capture every loaded section, which
would add terrain the scene never held and increase memory use. `/rtx reload`
uses this sequence too.

A settings transaction triggers one recapture, not one per slider step. When
it is expensive, investigate page sizing, native work and runtime capacity,
rather than silently omitting one of the steps. Queue waiting and the two
retirement gates are documented in [Tuning](TUNING.md#terrain-capture).

## Dark Daytime And Weather

`/time set day` and `/time set noon` do not clear rain or thunder. The renderer
attenuates direct sunlight during storms, so a bright-looking sky can coexist
with weak sunlight on terrain. In a disposable creative test world, compare:

```text
/weather clear 600
/time set noon
/rtx sky status
```

Allow about five seconds for the vanilla weather gradients to settle. The new
`/rtx sky status` command reports the raw rain/thunder gradients, camera-probed
sun angle in degrees, intensity controls and last submitted direct sun RGB.
The submitted values describe the last renderer update; with RTX disabled they
can be stale. At clear noon in the Overworld, expect weather gradients near
zero, positive sun height and nonzero direct sunlight with default settings.
Compare the same view using `/rtx off` and `/rtx on`; include both screenshots
and the diagnostic output if clear noon is still excessively dark. Do not
increase sun intensity merely to compensate for an active thunderstorm.

## Block Lights And Resource Reload

`BlockLightRuleManager` loads built-in rules from `BlockLightDefaults` and
resource-pack rules under `rtx_remix/block_lights/`. One `BlockLightKey`
(position, rule id, light index) owns one `RemixLight`; a rule can emit multiple
lights per block, and lights are not clustered. `TerrainState` owns the
section light set and connectivity flood; `ChunkManager.draw` applies the
culls and counts their outcomes. The [resource-pack guide](RESOURCE_PACKS.md)
describes authoring rules.

Keep `BlockLightDefaults` and `BlockLightIntensityControls` in lockstep.
`validateBuiltInRules` requires the built-in rule ids and slider control ids to
match when the catalog is built during resource reload. A mismatch throws from
the reload. Minecraft can then clear the selected packs and return to the
title screen, leaving a quick-play launch waiting for a world it will never
join. Read `logs/latest.log`, not just the launcher's final timeout.
`BlockLightIntensityControlsTest` checks distinct control mappings but cannot
build the registry-bootstrapped catalog.

## Entity Geometry And Motion

Capture uses vanilla's `EntityRenderDispatcher` only on the render thread.
The dispatcher owns one renderer and mutable model per entity type, so a
parallel gather would race on model part angles.

Minecraft's model parts are rigid: their pivot belongs in the instance
transform, not a skinning stream. Skinning would add CPU mesh work in the
runtime without deforming any vertices. GPU-instanced `RemixAPI.drawInstanced`
is not interchangeable with retained parts either: the runtime can derive
previous and current transforms from the same per-instance array beneath an
identity parent, yielding zero motion and denoiser trails. Verify the matching
runtime's transform-history behavior before changing the submission model.
`Ent.Draws` near `Ent.Bones` is expected for one instance per rigid part;
`Ent.MeshCreates`, not that ratio, exposes pooled-mesh misses.

Flat item cards use rectangles of opaque texels instead of two full faces.
The runtime resumes a ray after a transparent texel from an origin displaced
by a few floating-point units along the normal. A surface within that offset,
such as a held flame crossing the card, can be skipped and show a hairline of
background. The offset grows with world-position magnitude, and the view-model
rig is scaled by `RemixFirstPersonPass.VIEW_MODEL_SCALE`. Compare near the
origin and thousands of blocks away before attributing a distance-dependent
artifact to capture. Sprites exceeding
`RemixCapturingConsumer.MAX_CARD_FACE_RECTS` retain full faces and their alpha
relaunch behavior.

## Material Updates And Surface Capacity

`RemixMaterialStore.update` uses the runtime's `UpdateMaterial` to mutate a
live material without changing its handle. Terrain pages and pooled meshes
that baked the handle then use the new parameters without rebuilding. Sun,
moon and star opacity, cloud tint, and the active beacon lens use this path.
Destroying and recreating the material instead orphans the baked handles and
requires recapture.

Success from the API alone is not proof of a visible update. The runtime can
reject a type or sprite-sheet-layout change with a warning, and updates rely
on the GPU-resident scene path. Verify the effect in game before removing a
recapture path. These semantics belong to the runtime revision pinned by
`packman/remix-sdk.packman.xml`; this repository's unit tests do not execute
that implementation.

Mod-built material parameters are not automatically exposed as `rtx.*` options.
`SetConfigVariable` accepts registered options and valid keys in registered
dynamic namespaces, not arbitrary material fields, and the Remix C API has no
config read-back operation. A tunable mod-built material parameter therefore
needs a mod-owned setting that the mod parses unless the runtime explicitly
exposes it.

Per-frame `drawInstance` submissions, including sky, clouds, the block outline
and particles, can return success while the runtime drops them for lack of a
free surface slot. `Cloud.Draws` counts calls made, not surfaces accepted, and
`latest.log` need not contain an error. Sky and cloud draws arrive late, so
intermittently missing clouds under load are a reason to inspect the runtime
log, not proof that the cloud generator failed.

Look in `rtx-remix/logs/remix-dxvk.log` under the game directory for
`GPU-resident scene exceeded its fixed surface capacity`. The runtime emits
that warning only once per process. Retained terrain/entity adds instead fail
through `sceneInstanceAdd`. Bursts can exhaust capacity while frees are still
pending and replacements arrive, even if steady-state use is low. The native
runtime owns the capacity and warning behavior; inspect that build rather than
hardcoding its pool size here.

## Separating Capture From Shading

Use a [Remix debug view](GETTING_STARTED.md#viewing-a-remix-debug-view) to isolate
texture coordinates, normals, emission, or mesh identity. A defect already
visible in those inputs points toward capture or its native interpretation;
a clean input with a defect only in the final image points toward shading or
denoising. Include player coordinates in the report and compare the same pose,
settings and resource pack. The [contribution guide](../CONTRIBUTING.md#visual-comparisons)
explains repeatable captures.
