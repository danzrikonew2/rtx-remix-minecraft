# SPDX-License-Identifier: MIT
# Derived from MFG-Unlocker; see LICENSE-MFG.
"""Give OptiScaler's private Vulkan Streamline the existing guarded startup boundary."""

import argparse
import hashlib
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--source", type=Path, required=True)
args = parser.parse_args()
native = args.source / "source/native"
path = native / "patcher.cpp"
backup = args.source / ".remix-original/patcher.cpp"
original = (backup if backup.is_file() else path).read_text(encoding="utf-8")
if (
    hashlib.sha256(original.encode()).hexdigest()
    != "8159caa9d5758895416f652246e6381bf22cf69f6d71ee567e91ffff318e5620"
):
    raise SystemExit("Unrecognized MFG patcher source")
text = original


def replace(old, new):
    global text
    if text.count(old) != 1:
        raise SystemExit(f"Private Vulkan patch context mismatch: {old[:80]}")
    text = text.replace(old, new)


replace(
    "std::atomic<bool> gOptiScalerPrivateAmpereAdmitted{false};",
    """std::atomic<bool> gOptiScalerPrivateAmpereAdmitted{false};
std::atomic<PFun_slSetVulkanInfoAbi*> gOriginalOptiScalerSlSetVulkanInfo{nullptr};
entry_detour::Handle gOptiScalerSlSetVulkanInfoEntryHandle{};
std::atomic<uint64_t> gOptiScalerSlSetVulkanInfoCalls{0};
std::atomic<bool> gOptiScalerSlSetVulkanInfoAtLoad{false};
std::atomic<bool> gOptiScalerSlSetVulkanInfoArmedAtLoad{false};
std::atomic<PFun_slInit*> gOriginalOptiScalerPrivateSlInit{nullptr};
entry_detour::Handle gOptiScalerPrivateSlInitEntryHandle{};
std::atomic<bool> gOptiScalerPrivateSlInitAtLoad{false};
std::atomic<bool> gOptiScalerPrivateSlInitArmedAtLoad{false};""",
)
hook = """
bool TryInstallOptiScalerSlSetVulkanInfoEntryDetour(HMODULE, const std::wstring&);

// slInit has a validated load-time hotpatch. Attach the Vulkan setup gateway
// before forwarding into that private initialization, outside loader notification.
// Providers have not initialized yet, and the load-time architecture evidence
// must still be current. No nonblocking relocation guard is bypassed.
sl::Result HookOptiScalerPrivateSlInit(const sl::Preferences& preferences, uint64_t version)
{
    static thread_local uint32_t depth = 0;
    auto* original = EntryOriginal(gOriginalOptiScalerPrivateSlInit, gOptiScalerPrivateSlInitEntryHandle);
    if (!original) return sl::Result::eErrorNotInitialized;
    if (depth) return original(preferences, version);
    ReentryScope nested(depth);
    const auto entry = entry_detour::ReadSnapshot(gOptiScalerPrivateSlInitEntryHandle);
    if (entry.current && gOptiScalerPrivateSlInitAtLoad.load(std::memory_order_acquire)
        && gOptiScalerPrivateSlInitArmedAtLoad.load(std::memory_order_acquire)
        && ampere_provider_arch::Armed() && ampere_backend::BeforeFirstFeatureCreate()
        && TryInstallOptiScalerSlSetVulkanInfoEntryDetour(entry.owner, LoadedModulePath(entry.owner))) {
        gOptiScalerSlSetVulkanInfoArmedAtLoad.store(true, std::memory_order_release);
        gOptiScalerSlSetVulkanInfoAtLoad.store(true, std::memory_order_release);
        Log(L"OptiScaler private Vulkan gateway established before original slInit; load-time declaration current");
    }
    const sl::Result result = original(preferences, version);
    ObserveOutputPullMaskSlInitResult(entry, result == sl::Result::eOk);
    return result;
}

// Same private-instance policy as D3D12, with the actual Vulkan adapter/device.
// This supplies a startup boundary, never a forced successful admission.
sl::Result HookOptiScalerSlSetVulkanInfo(const VulkanInfoPrefix& info)
{
    static thread_local uint32_t depth = 0;
    auto* original = EntryOriginal(gOriginalOptiScalerSlSetVulkanInfo,
        gOptiScalerSlSetVulkanInfoEntryHandle);
    if (!original || depth) return original ? original(info) : sl::Result::eErrorNotInitialized;
    ReentryScope nested(depth);
    const uint64_t call = gOptiScalerSlSetVulkanInfoCalls.fetch_add(1, std::memory_order_relaxed) + 1;
    void* physical = nullptr;
    void* device = nullptr;
    void* instance = nullptr;
    ReadVulkanInfo(info, physical, device, instance);
    optiscaler_private_streamline::Inputs inputs{};
    inputs.admittedBefore = gOptiScalerPrivateAmpereAdmitted.load(std::memory_order_acquire);
    inputs.gameStreamline = ampere_backend::EarlyInitObserved()
        || gHostInterposer.load(std::memory_order_acquire) != nullptr;
    inputs.hookedAtLoad = gOptiScalerSlSetVulkanInfoAtLoad.load(std::memory_order_acquire);
    inputs.armedAtLoad = gOptiScalerSlSetVulkanInfoArmedAtLoad.load(std::memory_order_acquire);
    if (optiscaler_private_streamline::NeedsDevice(inputs))
        inputs.ampereDevice = physical && device && gpu_backend::ObserveVulkanPhysicalDevice(physical) && UseAmpere();
    const auto decision = optiscaler_private_streamline::Decide(inputs);
    Log(L"OptiScaler private Vulkan RTX 30 startup: call=%llu decision=%hs gatewayBeforeInit=%d declarationBeforeInit=%d device=%d",
        static_cast<unsigned long long>(call), optiscaler_private_streamline::DecisionName(decision),
        inputs.hookedAtLoad, inputs.armedAtLoad, inputs.ampereDevice);
    if (!optiscaler_private_streamline::RunsStartup(decision, inputs.ampereDevice)) return original(info);
    if (decision == optiscaler_private_streamline::Decision::eAdmit) {
        gOptiScalerPrivateAmpereAdmitted.store(true, std::memory_order_release);
        ampere_backend::ObserveEarlyInit();
    }
    ampere_backend::ObserveVulkanDevice(device, true);
    gVulkanAdapterVerified.store(true, std::memory_order_release);
    dlss5::vulkan::ObserveInit(instance, physical, device);
    dlss_sr::PrepareForVulkan();
    temporal_interval_trace::SetEnabled(true);
    gModuleInventoryDirty.store(true, std::memory_order_release);
    const sl::Result result = InvokeAmpereVulkanSetup(original, info);
    const bool ready = ampere_backend::Ready();
    const uint32_t routes = ready ? InstallOptiScalerPrivateWrapperRoutes() : 0;
    Log(L"OptiScaler private Vulkan RTX 30 startup result: call=%llu result=%u ready=%d failure=%u startupMaximum=%u wrapperRoutes=%u",
        static_cast<unsigned long long>(call), static_cast<unsigned>(result), ready,
        ampere_backend::FailureCode(), ampere_backend::StartupMaximumGeneratedFrames(), routes);
    return result;
}

"""
replace(
    "sl::Result HookSlSetVulkanInfo(const VulkanInfoPrefix& info)\n",
    hook + "sl::Result HookSlSetVulkanInfo(const VulkanInfoPrefix& info)\n",
)

# Both public entries have their own handles/originals. Reuse the existing
# Vulkan entry profile, independently owned by the private interposer module.
begin = original.index("void InstallOptiScalerSlSetD3DDeviceAtLoad(")
end = original.index(
    "bool TryInstallSlInitEntryDetour(HMODULE interposer, void* resolvedTarget)", begin
)
cloned = original[begin:end]
cloned = cloned.replace("SlSetD3DDevice", "SlSetVulkanInfo")
cloned = cloned.replace("slSetD3DDevice", "slSetVulkanInfo")
cloned = cloned.replace("PFun_slSetVulkanInfo*", "PFun_slSetVulkanInfoAbi*")
cloned = cloned.replace(
    "entry_detour::Kind::eOptiScalerSlSetVulkanInfo",
    "entry_detour::Kind::eSlSetVulkanInfo",
)
init_at_load = original[
    begin : original.index(
        "// Discovery path for OptiScaler's private interposer", begin
    )
]
init_at_load = init_at_load.replace("SlSetD3DDevice", "PrivateSlInit")
init_at_load = init_at_load.replace("slSetD3DDevice", "slInit")
init_at_load = init_at_load.replace(
    "entry_detour::Kind::eOptiScalerPrivateSlInit", "entry_detour::Kind::eSlInit"
)
cloned += init_at_load
replace(
    "bool TryInstallSlInitEntryDetour(HMODULE interposer, void* resolvedTarget)\n",
    cloned
    + "bool TryInstallSlInitEntryDetour(HMODULE interposer, void* resolvedTarget)\n",
)
replace(
    "const bool optiScaler = TryInstallOptiScalerSlSetD3DDeviceEntryDetour(interposer, path);",
    "const bool d3dPrivate = TryInstallOptiScalerSlSetD3DDeviceEntryDetour(interposer, path);\n        const bool vkPrivate = TryInstallOptiScalerSlSetVulkanInfoEntryDetour(interposer, path);\n        const bool optiScaler = d3dPrivate || vkPrivate;",
)
replace(
    "InstallOptiScalerSlSetD3DDeviceAtLoad(static_cast<HMODULE>(data->loaded.dllBase),\n            data->loaded.fullDllName);",
    "InstallOptiScalerSlSetD3DDeviceAtLoad(static_cast<HMODULE>(data->loaded.dllBase),\n            data->loaded.fullDllName);\n        InstallOptiScalerSlSetVulkanInfoAtLoad(static_cast<HMODULE>(data->loaded.dllBase),\n            data->loaded.fullDllName);\n        InstallOptiScalerPrivateSlInitAtLoad(static_cast<HMODULE>(data->loaded.dllBase),\n            data->loaded.fullDllName);",
)
text = text.replace(
    "gOptiScalerSlSetVulkanInfoArmedAtLoad", "gOptiScalerSlSetVulkanInfoArmedBeforeInit"
)
text = text.replace(
    "gOptiScalerSlSetVulkanInfoAtLoad", "gOptiScalerSlSetVulkanInfoBeforeInit"
)
if path.read_text(encoding="utf-8") not in (original, text):
    raise SystemExit("Preserving edited patcher source; use a fresh MFG copy")
backup.parent.mkdir(exist_ok=True)
if not backup.exists():
    backup.write_text(original, encoding="utf-8", newline="\n")
path.write_text(text, encoding="utf-8", newline="\n")
print(
    "Applied guarded private Vulkan startup parity; existing admission/capacity checks unchanged"
)
