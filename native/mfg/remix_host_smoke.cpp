// SPDX-License-Identifier: Apache-2.0
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <cstdio>
#include <filesystem>
#include "single_module_status.h"

int wmain(int argc, wchar_t** argv) {
    if (argc != 3 && argc != 4) return 2;
    const auto addon = std::filesystem::absolute(argv[1]);
    const auto runtime = std::filesystem::absolute(argv[2]);
    SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
    AddDllDirectory(runtime.parent_path().c_str());
    const auto mfg = LoadLibraryExW(addon.c_str(), nullptr, LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
    if (!mfg) { printf("FAIL: addon load error=%lu\n", GetLastError()); return 1; }
    const auto query = reinterpret_cast<MfgSingleModuleQueryFn>(GetProcAddress(mfg, "MfgUnlockSingleModuleQuery"));
    const auto arm = reinterpret_cast<BOOL(WINAPI*)(HMODULE)>(GetProcAddress(mfg, "MfgUnlockRegisterRemixVulkanHost"));
    if (!query || !arm) { puts("FAIL: addon exports"); return 1; }
    MfgSingleModuleStatus status{};
    for (int i=0; i<100; ++i) { status.size=sizeof(status); if (query(&status) && status.backendOwner) break; Sleep(10); }
    if (!status.backendOwner || arm(nullptr) || arm(GetModuleHandleW(L"kernel32.dll")) || arm(mfg)) {
        puts("FAIL: owner or invalid-host rejection"); return 1;
    }
    if (argc == 4) {
        const auto noApi = LoadLibraryExW(argv[3], nullptr,
            LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
        if (!noApi || GetProcAddress(noApi, "remixapi_InitializeLibrary") || arm(noApi)) {
            puts("FAIL: missing Remix API export was accepted"); return 1;
        }
        FreeLibrary(noApi);
    }
    const auto remix = LoadLibraryExW(runtime.c_str(), nullptr, LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
    if (!remix) { printf("FAIL: runtime load error=%lu\n", GetLastError()); return 1; }
    BOOL attached = FALSE;
    for (int i=0; i<20 && !attached; ++i) { attached=arm(remix); if (!attached) Sleep(10); }
    status.size=sizeof(status);
    if (!attached || !query(&status) || !status.vulkanHooked || !arm(remix)) {
        printf("FAIL: host attach=%u vulkanHooked=%u\n", attached, status.vulkanHooked); return 1;
    }
    printf("PASS: pinned Remix runtime registered before InitializeLibrary; Vulkan hooks=%u; invalid hosts rejected; repeat registration accepted\n", status.vulkanHooked);
    return 0;
}
