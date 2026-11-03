# Minecraft 26.3 status effects

This is an unofficial community-port audit. Gameplay effects remain Minecraft's
responsibility; the statuses below concern their appearance with RTX enabled.
Source tracing and synthetic GPU tests are not an in-game visual acceptance.

## Current coverage

| Effect or visual | RTX path and remaining limits |
|---|---|
| Blindness | Candidate restores black primary-hit distance fog. It calls vanilla's `BlindnessFogEnvironment` for the 1.25–5 block full-strength band and final-second distance recovery. Black-overlay strength also fades with vanilla's fog darkening curve. HUD is drawn afterward. Visual acceptance is pending. |
| Darkness | Candidate restores the distance band and black-overlay transition from vanilla's `DarknessFogEnvironment` and effect blend. This does **not** reproduce the lightmap's pulsing darkening or gamma suppression. Vanilla's Darkness Effect accessibility slider controls that separate pulse, not its distance band. |
| Glowing | Candidate preserves vanilla submission for glowing entities. Vanilla prepares its outline target before Remix replaces the main image, then blends the outline afterward. This adds model/render work for glowing entities. Through-wall visibility, removal, team colors, and invisible glowing entities need visual acceptance. |
| Night vision | Blocked by the pinned renderer interface. Minecraft supplies effect strength, but camera-only diffuse illumination needs native albedo/lighting access and a compositing hook that the API does not expose. See the [renderer audit](#night-vision-renderer-audit-2026-11-03). No brightness replacement is enabled. |
| Conduit power | Gameplay remains vanilla. Its underwater vision/lightmap boost has the same incomplete path as night vision; native underwater lighting is a separate mechanism. |
| Speed, slowness and movement effects | Native camera reads vanilla's extracted position and FOV. Movement and FOV changes therefore retain a source path; a visual comparison is still needed. This is not certification of every effect. |
| Invisibility | Capture uses vanilla entity render states and selected layers. Armor/held items, spectator visibility and invisibility combined with glowing require visual checks; this audit has not certified all combinations. |
| Nausea and portal distortion | Incomplete. Vanilla modifies its world projection after camera extraction. The native parameterized camera does not receive that projection deformation. |
| Hurt/world camera bob | First-person capture receives vanilla's hand matrices; native world camera uses position/orientation/FOV. World projection bob/hurt transformations are not fully reproduced. This gap does not establish the cause of stationary temporal shimmer. |
| Fire, suffocation and water screen overlays | Vanilla's first-person screen-effect submission runs after the Remix composite. The follow-up candidate also captures world-entity flames from current block-atlas sprites; animation, edges, reflections and extinguishing require visual acceptance. |
| Poison, wither, regeneration, resistance, strength and other gameplay/HUD effects | Gameplay and HUD remain vanilla. Damage overlays are captured as entity overlay coordinates; their final appearance and all effect combinations remain unverified. |

## How the distance candidate works

`StatusEffectFog` reads the **camera's entity**, so it also follows a spectated
living entity. It selects blindness before darkness, matching vanilla, and
keeps vanilla's lava/powder-snow environment precedence. It reads the current
duration/blend each frame. No temporary value is written to a saved config,
native User Settings, a resource pack, or the lighting cache.

`StatusEffectFogPass` operates after native tonemapping, before Minecraft's
screen overlays and HUD. Native interop depth is single-channel **projected**
depth, not distance in blocks. Shared native-camera planes reconstruct axial
depth; FOV/aspect convert it to spherical distance for a linear black fog band.
Color and depth keep the same row orientation, and the existing final blit
performs the row flip. Lower-resolution depth is sampled in normalized image
coordinates. A miss is beyond the effect's visibility range.

The pass preserves GL program/image bindings. Its full-resolution intermediate
is allocated only for an active effect and is released on removal, RTX off,
missing output/depth, disconnect or shutdown. Framebuffer attachments are
detached after the blit so they do not retain deleted storage. sRGB input uses
a raw compatible copy and output view; it is not read as an unsupported shader
image. Unsupported input or a shader exception is logged without intentionally
blanking a valid native frame.

This is a **primary-surface, post-tonemap** effect. It cannot apply separate fog
distances to every transparent/reflected surface. It does not reproduce
vanilla's exact fog colors, lightmap pulse, or lighting/gamma response. Its
black-overlay weight follows the complement of vanilla's `(1 - darkness)^2`
fog-color multiplier. This lets darkness's blend and blindness's final-second
recovery fade the effect rather than leaving a fully black sky until removal.
It adds one full-screen dispatch while active (and a copy for sRGB input),
with no dispatch or intermediate image when inactive. Cost is unmeasured.

World-entity fire uses the vanilla stacked flame shape, alternating `FIRE_0`
and `FIRE_1` from the current block atlas. It keeps vanilla's cutout layer and
borrows the existing LabPBR atlas material, including the shipped fire emission.
Resource-pack emission remains author-controlled. Each slice is an immutable
model-backed quad with size/rotation in its bone transform. This shares mesh
geometry across sizes/camera angles and preserves the off-screen pose cache;
raw vertex capture would make those mobs ineligible for that cache. It adds
flame parts and draws only where vanilla requests flames. No new analytic
light or global brightness override is introduced. Game cost is unmeasured.

## Night Vision renderer audit (2026-11-03)

**Camera-only diffuse illumination is not implemented.** The audit covers the
Minecraft 26.3 client, the copied C API **0.16.0**, Java/JNI forwarding, and the
`minecraft-rtx2-71a581da` SDK pinned for both architectures in
[`packman/remix-sdk.packman.xml`](../packman/remix-sdk.packman.xml).
The limitation is missing renderer access, rather than effect detection.

| Required input or hook | Verified availability |
|---|---|
| Night Vision strength | `GameRenderer.gameRenderState().lightmapRenderState.nightVisionEffectIntensity` already contains Minecraft's extracted strength. |
| Per-pixel diffuse albedo and physical illumination | Internal native resources exist, but the pinned API does not export these images. Material texture handles are inputs to shading, not per-pixel surface readback. |
| Camera-only contribution before tonemapping | No supported shader-injection or HDR-composite callback is present in the pinned interface. |
| Existing GL composite | `GlInterop` imports final color and primary depth. `TextureOverlay` runs after native tonemapping; it has neither diffuse texture colors in darkness nor the required HDR illumination. |
| Material updates | `UpdateMaterial` changes the shared physical material. Emission or albedo changes do not provide a view-only vision term and cannot satisfy the GI/reflection requirements. |

The complete output enum in
[`remix_c.h`](../rtxremix-java/native/include/remix_c.h) contains final color,
depth, normals, object picking and GUI. Its `remixapi_dxvk_InteropInfo` exposes
only color/depth image memory. Neither the
[`Java facade`](../rtxremix-java/src/com/nvidia/rtxremix/RemixAPI.java) nor the
[`JNI bridge`](../rtxremix-java/native/remixbridge.cpp) supplies another
compositing hook. Raising exposure cannot recover a diffuse texture from zero
radiance. A light or emissive-material substitute would change scene lighting.

For comparison, official public dxvk-remix source at
[`bd5f3c8`](https://github.com/NVIDIAGameWorks/dxvk-remix/tree/bd5f3c8001bdfbafcef44ec58b4cb7015d80d21d)
binds albedo, diffuse radiance and shading normals inside
[`CompositePass`](https://github.com/NVIDIAGameWorks/dxvk-remix/blob/bd5f3c8001bdfbafcef44ec58b4cb7015d80d21d/src/dxvk/rtx_render/rtx_composite.cpp#L302).
Its public output API also has raw position/UV/coverage outputs, but no albedo
or HDR-lighting composite callback. That source is not the pinned Minecraft
runtime and is not evidence of binary compatibility; its additional enum
values must not be passed to the pinned SDK. The matching runtime source is
not included in this checkout; see the [runtime contribution contract](../CONTRIBUTING.md#which-repository).

Minecraft's `LightmapRenderStateExtractor` reads the local player's Night Vision
first, then underwater conduit vision if Night Vision is absent. Infinite
duration or more than 200 ticks gives strength 1. Near expiration it uses
`0.7 + 0.3 * sin((duration - partialTick) * PI * 0.2)`, intentionally flickering.
The current camera's environment probe supplies the vision tint. The 26.3
lightmap shader takes `max(ambient, nightVisionColor * strength)` before adding
sky/block lighting; Remix does not consume that lightmap. This existing scalar
is suitable for a future native integration, but does not itself reveal dark
surface textures. Smoothing activation/expiration would be an explicit visual
choice rather than an exact copy of vanilla's final-seconds behavior.

The proposed `RTX + diffuseAlbedo * 0.20 * darknessFactor * strength` is a
reasonable native-renderer starting point, not a validated shader. A renderer
implementation would use linear, exposure-independent lighting to estimate
darkness, exclude misses/sky and inappropriate transparent/emissive surfaces,
and use the actual diffuse lobe rather than treating metallic base color as
diffuse. A diffuse floor necessarily reduces shadow contrast; normal-map
detail and the 0.20 strength need visual tuning. The contribution must remain
outside transport/cache updates and be composed before tonemapping with the
correct RR/upscaling ordering. Sparse sampling and generated frames need
matching handling so that the term does not flicker or appear only in base
frames. None of those compatibility properties has been tested or claimed.

A matching native runtime extension and published SDK are required before
changing the header, JNI, Java facade and caller together. No renderer code,
settings, installed candidate, or release asset changes for this audit. The
documentation checks do not constitute a new build or visual acceptance.
Dark caves, torch-lit areas, daylight, night, underwater and PBR-pack checks,
including exposure, flicker, normal detail and frame-time comparisons, remain
pending an implementation. There is no new Night Vision candidate to install.

## One combined manual check

Use the isolated development instance and a disposable single-player test
world with cheats. Keep both FG routes off during the initial comparison.
Test effects separately, then their combinations if the basic checks pass.

1. **Blindness:** `/effect give @s minecraft:blindness 20 0 true`. Check a
   nearby lit block, terrain a few blocks away, sky, and held item. Expect a
   short visibility range and recovery near expiration. Repeat once with F8
   off for the vanilla reference. Remove only this effect with
   `/effect clear @s minecraft:blindness`.
2. **Darkness:** `/effect give @s minecraft:darkness 20 0 true`. Check the
   range contracts and recovers without changing saved exposure. The separate
   vanilla pulse remains a known gap. Remove with
   `/effect clear @s minecraft:darkness`. Try an RTX off/on transition and
   leaving/reopening the world; the distance effect must not stick afterward.
3. **Glowing:** apply glowing to a nearby mob, e.g.
   `/effect give @e[type=minecraft:pig,distance=..16,limit=1,sort=nearest] minecraft:glowing 30 0 true`.
   Look directly at it and from behind a wall. Check its model remains normal
   and the outline disappears after expiration. If no pig is nearby, summon
   one in the disposable world first. Optionally compare invisibility with
   glowing; report an unexpectedly solid model separately.
4. **Burning mobs:** in the disposable daylight world, summon a zombie with
   `/summon minecraft:zombie ~3 ~ ~` or watch an existing burning mob. Compare
   RTX on/off, rotate the camera, and check animation, outline of the flame,
   and any reflections. Put the mob in water and verify the flame disappears.
   Do not change packs mid-comparison unless testing a resource reload itself.
5. **Known gaps/reference checks:** compare night vision, conduit underwater,
   nausea, speed/slowness FOV and invisibility with RTX on/off. Night vision
   and nausea are not expected to match yet. Report other failures rather
   than treating the source audit as a pass.

Finish the existing [combined acceptance list](MINECRAFT_26_3_PORT.md#combined-candidate-acceptance),
quit Minecraft and Prism, and send all results together. Include effect,
RTX/FG state, first/third person, water/land, expiration/removal behavior and
any error or crash. Local logs can reveal shader/depth failures but cannot
prove that an outline or visibility range looks correct.

## Automated verification

Regular Java tests cover the projected-depth convention and spherical
reconstruction. For an available Windows OpenGL 4.5 device, run the opt-in
synthetic test with Minecraft and Prism stopped:

```powershell
$env:RTXREMIX_GL_TESTS = '1'
.\gradlew.bat test --tests '*StatusEffectFogPassGlTest' -Parch=win64
Remove-Item Env:RTXREMIX_GL_TESTS
```

The test owns a hidden SDL/OpenGL window. It checks shader execution with
RGBA8 and sRGB, near/middle/miss depths, differing depth/color resolution,
zero/partial/full fog weight, row alignment, resize/recreation, intermediate deletion, and GL binding
restoration. It does not launch or automate Minecraft. Glowing integration
and real native output remain manual checks. `BurningEntityFlameTest` checks
effective slice positions, alternating current sprite UVs, pooled mesh-key
stability across camera rotation and sizes, snapshot eligibility and degenerate
bounds without creating a GPU context.
