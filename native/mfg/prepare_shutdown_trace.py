# SPDX-License-Identifier: Apache-2.0
"""Stage a new, source-only NGX Vulkan shutdown diagnostic over the verified r3 trace.

The r3 build and its packaged DLL remain immutable. An operator copies the
complete r3 checkout into a separate r4 build directory, installs the staged
files there, and builds a NEW DLL. Logging only; shutdown behavior is unchanged.
"""

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from prepare_fsrfg_diagnostic_package import git, verify_source
from prepare_fsrfg_trace import replace_once


ROOT = Path(__file__).resolve().parents[2]
R3_CLONE = ROOT / "build" / "optiscaler-fsrfg-trace-build-20261109"
R4_OVERLAY = ROOT / "build" / "optiscaler-fsrfg-shutdown-source-20261109-r4"
R4_CLONE = ROOT / "build" / "optiscaler-fsrfg-shutdown-build-20261109-r4"
INPUT = "OptiScaler/inputs/NVNGX_DLSS_Vk.cpp"
PROVIDER = "OptiScaler/framegen/nvngx/Nvngx_FG.cpp"
TRACED = (INPUT, PROVIDER)


def add_helper(source: str) -> str:
    return replace_once(source, '#include "pch.h"\n', '''#include "pch.h"
#include <cstdio>

namespace {
// The stderr line is synchronously flushed so a bounded killed probe still
// records its last reached stage even when the main log buffers messages.
void ShutdownProbeTrace(const char* stage)
{
    std::fprintf(stderr, "FGSHUT stage=%s pid=%lu tid=%lu\\n", stage,
                 static_cast<unsigned long>(GetCurrentProcessId()),
                 static_cast<unsigned long>(GetCurrentThreadId()));
    std::fflush(stderr);
    LOG_INFO("FGSHUT stage={} pid={} tid={}", stage, GetCurrentProcessId(), GetCurrentThreadId());
}
} // namespace
''')


def trace_input(source: str) -> str:
    source = add_helper(source)
    source = replace_once(source, '''NVSDK_NGX_API NVSDK_NGX_Result NVSDK_NGX_VULKAN_Shutdown(void)
{
    shutdown = true;''', '''NVSDK_NGX_API NVSDK_NGX_Result NVSDK_NGX_VULKAN_Shutdown(void)
{
    ShutdownProbeTrace("shutdown_enter");
    shutdown = true;''')
    source = replace_once(source, '''        auto result = NVNGXProxy::VULKAN_Shutdown()();
        NVNGXProxy::SetVulkanInited(false);''', '''        ShutdownProbeTrace("shutdown_original_ngx_begin");
        auto result = NVNGXProxy::VULKAN_Shutdown()();
        ShutdownProbeTrace("shutdown_original_ngx_end");
        NVNGXProxy::SetVulkanInited(false);''')
    source = replace_once(source, '''    Nvngx_FG::VULKAN_Shutdown();

    shutdown = false;''', '''    ShutdownProbeTrace("shutdown_fg_begin");
    const auto fgShutdownResult = Nvngx_FG::VULKAN_Shutdown();
    ShutdownProbeTrace("shutdown_fg_end");
    (void) fgShutdownResult;

    shutdown = false;''')
    source = replace_once(source, '''    State::Instance().nvngxVkInited = false;

    return NVSDK_NGX_Result_Success;''', '''    State::Instance().nvngxVkInited = false;

    ShutdownProbeTrace("shutdown_exit");
    return NVSDK_NGX_Result_Success;''')
    source = replace_once(source, '''NVSDK_NGX_API NVSDK_NGX_Result NVSDK_NGX_VULKAN_Shutdown1(VkDevice InDevice)
{
    shutdown = true;''', '''NVSDK_NGX_API NVSDK_NGX_Result NVSDK_NGX_VULKAN_Shutdown1(VkDevice InDevice)
{
    ShutdownProbeTrace("shutdown1_enter");
    shutdown = true;''')
    source = replace_once(source, '''        auto result = NVNGXProxy::VULKAN_Shutdown1()(InDevice);
        NVNGXProxy::SetVulkanInited(false);''', '''        ShutdownProbeTrace("shutdown1_original_ngx_begin");
        auto result = NVNGXProxy::VULKAN_Shutdown1()(InDevice);
        ShutdownProbeTrace("shutdown1_original_ngx_end");
        NVNGXProxy::SetVulkanInited(false);''')
    source = replace_once(source, '''    Nvngx_FG::VULKAN_Shutdown1(InDevice);

    shutdown = false;''', '''    ShutdownProbeTrace("shutdown1_fg_begin");
    const auto fgShutdownResult = Nvngx_FG::VULKAN_Shutdown1(InDevice);
    ShutdownProbeTrace("shutdown1_fg_end");
    (void) fgShutdownResult;

    shutdown = false;''')
    source = replace_once(source, '''    return NVSDK_NGX_VULKAN_Shutdown();
}''', '''    ShutdownProbeTrace("shutdown1_delegate_plain_begin");
    const auto result = NVSDK_NGX_VULKAN_Shutdown();
    ShutdownProbeTrace("shutdown1_delegate_plain_end");
    return result;
}''')
    return source


def trace_provider(source: str) -> str:
    source = add_helper(source)
    source = replace_once(source, '''NVSDK_NGX_Result Nvngx_FG::VULKAN_Shutdown()
{
    auto* provider = getProvider();

    if (!provider)
        return NVSDK_NGX_Result_Fail;

    return provider->VULKAN_Shutdown();
}''', '''NVSDK_NGX_Result Nvngx_FG::VULKAN_Shutdown()
{
    ShutdownProbeTrace("provider_shutdown_enter");
    auto* provider = getProvider();
    ShutdownProbeTrace("provider_shutdown_resolved");

    if (!provider)
        return NVSDK_NGX_Result_Fail;

    ShutdownProbeTrace("provider_shutdown_call_begin");
    const auto result = provider->VULKAN_Shutdown();
    ShutdownProbeTrace("provider_shutdown_call_end");
    return result;
}''')
    source = replace_once(source, '''NVSDK_NGX_Result Nvngx_FG::VULKAN_Shutdown1(VkDevice InDevice)
{
    auto* provider = getProvider();

    if (!provider)
        return NVSDK_NGX_Result_Fail;

    return provider->VULKAN_Shutdown1(InDevice);
}''', '''NVSDK_NGX_Result Nvngx_FG::VULKAN_Shutdown1(VkDevice InDevice)
{
    ShutdownProbeTrace("provider_shutdown1_enter");
    auto* provider = getProvider();
    ShutdownProbeTrace("provider_shutdown1_resolved");

    if (!provider)
        return NVSDK_NGX_Result_Fail;

    ShutdownProbeTrace("provider_shutdown1_call_begin");
    const auto result = provider->VULKAN_Shutdown1(InDevice);
    ShutdownProbeTrace("provider_shutdown1_call_end");
    return result;
}''')
    return source


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stage(source: Path, destination: Path, verify_r3: bool = True) -> dict:
    source, destination = source.resolve(), destination.resolve()
    if verify_r3:
        verify_source(ROOT)  # verifies pinned baseline, exact r3 trace + nine submodule revisions
        if source != R3_CLONE.resolve():
            raise ValueError("Refusing unverified diagnostic source checkout")
    if destination.exists():
        raise FileExistsError(f"Refusing overwrite of shutdown trace overlay: {destination}")
    staged = {}
    for relative, transform in ((INPUT, trace_input), (PROVIDER, trace_provider)):
        original = (source / relative).read_bytes()
        patched = transform(original.decode("utf-8-sig").replace("\r\n", "\n")).encode("utf-8")
        staged[relative] = (patched, {"r3_source_sha256": sha(original), "r4_source_sha256": sha(patched)})
    manifest = {
        "schema": 1,
        "status": "SOURCE_ONLY_UNBUILT",
        "parent_checkout": str(source),
        "parent_commit": "aeb1f29783106b96c89ba71ce9b6db80eacdae46",
        "preserves_r3_fsrfg_instrumentation": True,
        "files": {name: metadata for name, (_, metadata) in staged.items()},
        "limitations": ["GPU completion unverified", "physical scanout unverified", "clean shutdown unverified"],
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=".shutdown-trace-staging-", dir=destination.parent))
    try:
        for name, (payload, _) in staged.items():
            path = temp / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        (temp / "shutdown-source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        temp.rename(destination)
    finally:
        if temp.exists():
            shutil.rmtree(temp)
    return manifest


def install(destination: Path) -> dict:
    """Install only staged, pre-verified r4 sources into a separate r3 clone copy."""
    destination = destination.resolve()
    if destination != R4_CLONE.resolve():
        raise ValueError("Shutdown trace installation restricted to the dedicated r4 checkout")
    verify_source(ROOT)
    manifest = json.loads((R4_OVERLAY / "shutdown-source-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "SOURCE_ONLY_UNBUILT" or set(manifest["files"]) != set(TRACED):
        raise ValueError("Unexpected shutdown trace source manifest")
    if git(destination, "rev-parse", "HEAD") != manifest["parent_commit"]:
        raise ValueError("Diagnostic checkout is not pinned to the exact expected commit")
    if git(destination, "submodule", "status") != git(R3_CLONE, "submodule", "status"):
        raise ValueError("Diagnostic checkout dependencies differ from verified r3")
    changes = set(git(destination, "diff", "--name-only").splitlines())
    if changes != {"OptiScaler/framegen/ffx/FSRFG_Vk.cpp", "OptiScaler/hooks/Vulkan_Hooks.cpp"}:
        raise ValueError(f"Diagnostic checkout contains unexpected changes: {changes}")
    for name in ("OptiScaler/framegen/ffx/FSRFG_Vk.cpp", "OptiScaler/hooks/Vulkan_Hooks.cpp"):
        if (R3_CLONE / name).read_bytes() != (destination / name).read_bytes():
            raise ValueError(f"Copied r3 FSRFG trace differs: {name}")
    sources = {}
    for name in TRACED:
        entry = manifest["files"][name]
        current = (destination / name).read_bytes()
        overlay = (R4_OVERLAY / name).read_bytes()
        if sha(current) != entry["r3_source_sha256"]:
            raise ValueError(f"Expected exact uninstrumented source in r4 checkout: {name}")
        if sha(overlay) != entry["r4_source_sha256"]:
            raise ValueError(f"Trace overlay SHA-256 mismatch: {name}")
        sources[name] = overlay
    for name, payload in sources.items():
        (destination / name).write_bytes(payload)
        if sha((destination / name).read_bytes()) != manifest["files"][name]["r4_source_sha256"]:
            raise ValueError(f"Failed to verify installed source: {name}")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=R4_OVERLAY)
    parser.add_argument("--install-to", type=Path, help="Install verified overlay into dedicated r4 checkout")
    args = parser.parse_args()
    if args.install_to:
        print(json.dumps(install(args.install_to), indent=2))
        return 0
    if not args.output.resolve().is_relative_to((ROOT / "build").resolve()):
        parser.error("Diagnostic source must be staged inside the ignored repository build tree")
    print(json.dumps(stage(R3_CLONE, args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
