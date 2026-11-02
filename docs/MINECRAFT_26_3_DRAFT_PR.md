# Proposed draft PR: entity texture lifetime and 26.3 zone-save preservation

Prepared for review only; no PR has been opened. Coordinate with
[PR #79](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/pull/79) and its
author before proposing a follow-up. Its newer installer/tooling commit
[`600a95f`](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/commit/600a95f6ef63cbdbe566419ff5f1ce25cc1d5f42)
already covers version selection, save-wide storage and diagnostic titles;
those changes should not be presented as a new independent port.

## Proposed description

Dynamic entity textures can outlive the maps and players that used them:
retiring retained instances and cold rigid meshes does not release their
texture/material caches until a full world or material reload. This follow-up
tracks the existing once-per-layer texture-use stamp and retires cold owned
dynamic texture sets after a grace period, under a four-set sweep budget.
Dependent instances and meshes retire before materials and textures. Current
shared use protects a texture, borrowed atlas/static materials stay outside
this policy, and downloaded CPU snapshots remain available for recreation.
Failed native destruction preserves its owner/cache entry so cleanup can retry.

The save-wide zone-storage correction in #79 also needs to preserve worlds
opened with the earlier 26.3 port. Those versions wrote
`dimensions/minecraft/overworld/data/rtx-remix-renderer/zones.dat` rather than
the save-wide `data/rtx-remix-renderer/zones.dat`. When the canonical file is
absent, import the prior 26.3 file before the 1.21.1 legacy file. Keep originals,
honor intentionally empty states, and block fallback overwrite/editing of
unreadable or future-schema data. Existing canonical definitions always win.

This is an unofficial community-maintained experimental follow-up. Original
NVIDIA licensing, attribution and notices are preserved. Alex Melan's #77,
#78, #79 and the follow-up commit above are credited. Coordinate the exact
patch selection with that work. The fork's MFG/provider experiments are a
separate development effort, not a request to include them in this focused PR.
The JNI ABI, copied C API header and official runtime pin remain unchanged.

Executed local validation: 830 Java tests pass, including shared-use, grace,
sweep-budget, cleanup-retry and save-file priority/preservation cases. Required
tooling checks pass with 1,147 tests and 178 subtests; one test is skipped.
Windows x64 JAR/installer verification checks scripts, documentation, licenses
and matching embedded mod contents. JVM tests do not prove native visual
correctness or measure a VRAM/FPS improvement; returning dynamic textures and
real play-session behavior still require manual acceptance.

Separate runtime research also tested native DLSS-NR option acceptance without
MFG/OptiScaler. Renderer smoke completed, but the stock provider reported
FeatureNotSupported and one community-provider experiment reported
FeatureNotFound. Neither establishes working neural rendering on the 3070 Ti.
Ghosting/held-item shimmer remain unresolved. These experiments do not justify
changing the upstream runtime pin or claiming the compatibility port complete.

- [Development branch](https://github.com/danzrikonew2/rtx-remix-minecraft/tree/feat/minecraft-26.3)
- [Current status and build/testing instructions](https://github.com/danzrikonew2/rtx-remix-minecraft/blob/feat/minecraft-26.3/docs/MINECRAFT_26_3_PORT.md)
- [Audit, evidence and remaining visual checks](https://github.com/danzrikonew2/rtx-remix-minecraft/blob/feat/minecraft-26.3/docs/PERFORMANCE_26_3.md#code-and-upstream-research-audit-2026-11-03)

Please initially review this as a Draft PR. No claim of release readiness,
measured performance improvement or resolved temporal artifacts is made.
