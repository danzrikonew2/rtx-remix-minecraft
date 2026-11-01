# SPDX-License-Identifier: MIT
# Derived from MFG-Unlocker; see LICENSE-MFG.
import argparse
import hashlib
from pathlib import Path

parser = argparse.ArgumentParser(
    description="Apply the runtime-bound Remix Vulkan menu registration to MFG"
)
parser.add_argument("--source", type=Path, required=True)
args = parser.parse_args()
native = args.source / "source/native"
backup = args.source / ".remix-original"

PINS = {
    "overlay_application_imports.cpp": "6b6f1053084590824beae5fc0540e8fa03eeb51aeebabecd759c809edaa59377",
    "overlay_vulkan.cpp": "5d123ad2071078184c112a313d478d5a7bfcd56e0604af2a7612926d5ac7e0e3",
}
for name, expected in PINS.items():
    original = backup / name if (backup / name).is_file() else native / name
    if (
        hashlib.sha256(original.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        != expected
    ):
        raise SystemExit(f"Unrecognized MFG source input: {name}")

s = (backup / "overlay_application_imports.cpp").read_text()


def replace(old, new):
    global s
    if s.count(old) != 1:
        raise ValueError(f"Source patch context mismatch: {old[:100]}")
    s = s.replace(old, new)


replace(
    '#include "overlay_platform.h"',
    '#include "overlay_platform.h"\n#include "sha256_util.h"\nnamespace single_overlay::vulkan { void RetireRemixSwapchains(); }',
)
replace(
    "std::atomic_flag publishing = ATOMIC_FLAG_INIT;",
    "std::atomic_flag publishing = ATOMIC_FLAG_INIT;\nstd::atomic<HMODULE> remixHost{nullptr};",
)
replace(
    "if (FactoryName(name)) result=single_overlay::ResolveProc(module,name,result);",
    "if (FactoryName(name) || (name[0] == 'v' && name[1] == 'k'))\n            result=single_overlay::ResolveProc(module,name,result);",
)
replace(
    "        if (FactoryName(name)) {",
    """        if (name[0] == 'v' && name[1] == 'k') {
            HMODULE owner = nullptr;
            if (!value || !GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS,
                    reinterpret_cast<LPCWSTR>(value), &owner)) return true;
            const auto replacement = single_overlay::ResolveProc(owner, name, reinterpret_cast<FARPROC>(value));
            FreeLibrary(owner);
            if (replacement != reinterpret_cast<FARPROC>(value)) {
                graphics = true;
                return batch.Add(module, slot, value, reinterpret_cast<void*>(replacement));
            }
        }
        if (FactoryName(name)) {""",
)
replace(
    "if (!paths || !LocalApplicationDll(module,*paths)) return;",
    """if (!paths) return;
    if (!LocalApplicationDll(module,*paths)) {
        if (remixHost.load(std::memory_order_acquire) != module) return;
        const DWORD n = GetModuleFileNameW(module, paths->module, _countof(paths->module));
        if (!n || n >= _countof(paths->module)) return;
    }""",
)
s += """
// Explicit registration from the JNI bridge, after LoadLibrary and before
// remixapi_InitializeLibrary creates Vulkan objects. This is deliberately not
// a process-wide loader hook or permission to initialize Frame Generation.
extern "C" __declspec(dllexport) BOOL WINAPI MfgUnlockRegisterRemixVulkanHost(HMODULE module) noexcept
{
    using namespace single_overlay::application_imports;
    if (!module || !single_module::OwnsBackend()
        || !GetProcAddress(module, "remixapi_InitializeLibrary")) return FALSE;
    Reference retained(module);
    std::unique_ptr<ModulePaths> paths(new(std::nothrow) ModulePaths);
    if (!retained.module || !paths) return FALSE;
    const DWORD length = GetModuleFileNameW(module, paths->module, _countof(paths->module));
    if (!length || length >= _countof(paths->module)) return FALSE;
    const wchar_t* leaf = wcsrchr(paths->module, L'\\\\');
    if (!leaf || _wcsicmp(leaf + 1, L"d3d9.dll")) return FALSE;
    // Exact runtime shipped by this port. Unknown runtimes retain stock paths.
    HANDLE file = CreateFileW(paths->module, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_DELETE,
        nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) return FALSE;
    LARGE_INTEGER size{};
    const bool bounded = GetFileSizeEx(file, &size) && size.QuadPart > 0 && size.QuadPart <= (512ll << 20);
    HANDLE mapping = bounded ? CreateFileMappingW(file, nullptr, PAGE_READONLY, 0, 0, nullptr) : nullptr;
    const auto* bytes = mapping ? static_cast<const uint8_t*>(MapViewOfFile(mapping, FILE_MAP_READ, 0, 0, 0)) : nullptr;
    const bool identity = bytes && sha256_util::EqualsUpperHex(bytes, static_cast<size_t>(size.QuadPart),
        "44A313F6D2A6FFA3ECCAAB683C472D14F22080BE7C61D07342D8E199A039D1AD", 512ull << 20);
    if (bytes) UnmapViewOfFile(bytes);
    if (mapping) CloseHandle(mapping);
    CloseHandle(file);
    if (!identity) return FALSE;
    HMODULE pinned = nullptr;
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_PIN,
            reinterpret_cast<LPCWSTR>(module), &pinned) || pinned != module) return FALSE;
    HMODULE expected = nullptr;
    if (!remixHost.compare_exchange_strong(expected, module, std::memory_order_acq_rel)
        && expected != module) return FALSE;
    ArmModule(module);
    if (publishing.test_and_set(std::memory_order_acquire)) return FALSE;
    struct Unlock { ~Unlock(){publishing.clear(std::memory_order_release);} } unlock;
    for (const auto& binding : bindings)
        if (binding.importer.load(std::memory_order_acquire) == module && binding.complete) {
            single_module::Log(L"Remix Vulkan renderer imports registered before initialization; FG admission unchanged");
            return TRUE;
        }
    return FALSE;
}

extern "C" __declspec(dllexport) BOOL WINAPI MfgUnlockRetireRemixVulkanHost(HMODULE module)
{
    if (!module || module != single_overlay::application_imports::remixHost.load(std::memory_order_acquire)) return FALSE;
    single_overlay::vulkan::RetireRemixSwapchains();
    return TRUE;
}
"""
p = native / "overlay_application_imports.cpp"
current = p.read_text(encoding="utf-8")
original = (backup / p.name).read_text(encoding="utf-8")
if current not in (original, s):
    raise SystemExit("Preserving edited renderer source; use a fresh MFG copy")
p.write_text(s, encoding="utf-8", newline="\n")
vulkan = native / "overlay_vulkan.cpp"
vulkan_backup = backup / vulkan.name
if not vulkan_backup.exists():
    vulkan_backup.write_bytes(vulkan.read_bytes())
original = vulkan_backup.read_text(encoding="utf-8")
addition = """
namespace single_overlay::vulkan {
// Retire UI on the caller's window/render thread before Remix joins its native
// presentation worker. No native renderer objects or NGX features are released here.
void RetireRemixSwapchains() {
    std::vector<std::pair<VkDevice, VkSwapchainKHR>> chains;
    {
        std::lock_guard lock(gRegistryMutex);
        for (const auto& [chain, state] : gSwapchains)
            chains.emplace_back(state->device->handle, chain);
    }
    for (const auto& [device, chain] : chains) ForgetSwapchain(device, chain);
}
}
"""
if vulkan.read_text(encoding="utf-8") not in (original, original + addition):
    raise SystemExit("Preserving edited Vulkan source; use a fresh MFG copy")
vulkan.write_text(original + addition, encoding="utf-8", newline="\n")
print("Applied explicit, runtime-hash-bound Remix Vulkan import registration")
