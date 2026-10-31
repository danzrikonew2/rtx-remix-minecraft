# Proposed draft PR: isolate and validate community 26.3 development

This description is prepared for review only. No PR has been opened. Coordinate
with [existing PR #79](https://github.com/NVIDIAGameWorks/rtx-remix-minecraft/pull/79)
first; its renderer port should be credited and reviewed in its existing venue.
Prefer a focused follow-up after #79 lands, or offer these changes to its author.

## Proposed description

The existing experimental Minecraft 26.3 port compiles the renderer, but its
launcher and installer still select 1.21.1 and Java 21. This follow-up selects
26.3, Fabric Loader 0.20.1, Fabric API 0.165.0+26.3, and Java 25 consistently,
and gives development and installation profiles separate game directories.
Working 1.21.1 instances, worlds, runtime files, and configurations are preserved.

This is a community-maintained experimental compatibility effort, not an
official NVIDIA release. The source branch incorporates Alex Melan's #77, #78,
and #79 with original attribution and sign-offs. Its renderer migration covers
SectionCompiler terrain capture, extract/submit entity rendering, renderpearl
OpenGL presentation, SDL3 input, and GPU-side sprite animation. This follow-up
adds Windows path handling, profile isolation, tooling consistency, restores an
access-widener SPDX header lost during migration, and narrows Minecraft metadata
to the exact tested version. The JNI ABI and runtime pin are unchanged.

Executed local validation: the 1.21.1 baseline passed 800 JVM tests after the
Windows path fix; the integrated 26.3 port passed Java/native compilation, 767
JVM tests, Windows x64 package inventory checks, and the native compatibility
probe (return code 0). The locked tooling suite passes 1,135 tests and 178
subtests with one skip. Local startup logs confirm runtime initialization;
the user confirmed basic terrain/hands/demo-scene rendering, world reopening,
and RTX toggling, and supplied an initialized `/rtx status` screenshot. Detailed
runtime acceptance and stability testing remain incomplete. See the status document for
the latest validation results rather than interpreting compile success as
runtime proof.

Known gaps include missing burning-entity flame, leash and moving-piston block
submits, custom Fabric submit phases, and unverified weather parity. Stability,
8 GB VRAM behavior, full transparency/material coverage, and installer execution
remain under test. Weak stained-glass tint is a user-reported deferred visual
issue. ARM64 is untested here. No request is made to treat the port
as release-ready.

- [Development branch](https://github.com/danzrikonew2/rtx-remix-minecraft/tree/feat/minecraft-26.3)
- [Current status, build instructions and known issues](https://github.com/danzrikonew2/rtx-remix-minecraft/blob/feat/minecraft-26.3/docs/MINECRAFT_26_3_PORT.md)

Please review the launcher isolation, version consistency, and package checks
as a focused follow-up to #79. Runtime reports and missing submit implementations
are welcome through the community fork while the port remains experimental.
