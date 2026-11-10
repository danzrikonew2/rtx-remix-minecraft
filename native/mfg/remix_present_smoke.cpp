// SPDX-License-Identifier: Apache-2.0
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <cerrno>
#include <cstdio>
#include <cwchar>
#include <filesystem>
#include "single_module_status.h"
#include "remix_c.h"

static void Check(remixapi_ErrorCode code, const char* operation) {
    if (code != REMIXAPI_ERROR_CODE_SUCCESS) {
        printf("FAIL: %s code=0x%08x\n", operation, static_cast<unsigned>(code));
        ExitProcess(1);
    }
}
int wmain(int argc, wchar_t** argv) {
    if (argc < 3) return 2;
    setvbuf(stdout, nullptr, _IONBF, 0);
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
    int frameCount = 40;
    bool requestFg = false;
    bool keepWindowProc = false;
    for (int i = 3; i < argc; ++i) {
        if (wcscmp(argv[i], L"fg-probe") == 0) {
            requestFg = true;
        } else if (wcscmp(argv[i], L"--keep-wndproc") == 0) {
            keepWindowProc = true;
        } else if (wcsncmp(argv[i], L"--frames=", 9) == 0) {
            wchar_t* end = nullptr;
            errno = 0;
            const long parsed = wcstol(argv[i] + 9, &end, 10);
            if (errno || end == argv[i] + 9 || *end || parsed < 0 || parsed > 1200) {
                puts("FAIL: --frames must be an integer between 0 and 1200");
                return 2;
            }
            frameCount = static_cast<int>(parsed);
        } else {
            puts("FAIL: unknown argument (supported: fg-probe, --frames=N, --keep-wndproc)");
            return 2;
        }
    }
    const auto addon = std::filesystem::absolute(argv[1]);
    const auto runtime = std::filesystem::absolute(argv[2]);
    SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
    AddDllDirectory(runtime.parent_path().c_str());
    const bool control = wcscmp(argv[1], L"none") == 0;
    const auto mfg = control ? nullptr : LoadLibraryExW(addon.c_str(), nullptr, LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
    const auto query = mfg ? reinterpret_cast<MfgSingleModuleQueryFn>(GetProcAddress(mfg, "MfgUnlockSingleModuleQuery")) : nullptr;
    const auto arm = mfg ? reinterpret_cast<BOOL(WINAPI*)(HMODULE)>(GetProcAddress(mfg, "MfgUnlockRegisterRemixVulkanHost")) : nullptr;
    const auto retire = mfg ? reinterpret_cast<BOOL(WINAPI*)(HMODULE)>(GetProcAddress(mfg, "MfgUnlockRetireRemixVulkanHost")) : nullptr;
    if (!control && (!query || !arm || !retire)) { puts("FAIL: candidate load"); return 1; }
    MfgSingleModuleStatus status{};
    if (!control) for (int i=0; i<100; ++i) { status.size=sizeof(status); if (query(&status) && status.backendOwner) break; Sleep(10); }
    const auto remix = LoadLibraryExW(runtime.c_str(), nullptr, LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
    if (!remix || (!control && !arm(remix))) { puts("FAIL: renderer registration"); return 1; }
    auto initialize = reinterpret_cast<PFN_remixapi_InitializeLibrary>(GetProcAddress(remix, "remixapi_InitializeLibrary"));
    remixapi_InitializeLibraryInfo init{};
    init.sType=REMIXAPI_STRUCT_TYPE_INITIALIZE_LIBRARY_INFO;
    init.version=REMIXAPI_VERSION_MAKE(REMIXAPI_VERSION_MAJOR, REMIXAPI_VERSION_MINOR, REMIXAPI_VERSION_PATCH);
    remixapi_Interface api{};
    Check(initialize(&init, &api), "InitializeLibrary");
    WNDCLASSW cls{};
    cls.lpfnWndProc=DefWindowProcW; cls.hInstance=GetModuleHandleW(nullptr); cls.lpszClassName=L"MfgRemixSmoke";
    RegisterClassW(&cls);
    HWND window=CreateWindowW(cls.lpszClassName,L"Isolated Remix native test",WS_OVERLAPPEDWINDOW,0,0,800,600,nullptr,nullptr,cls.hInstance,nullptr);
    if (!window) { puts("FAIL: hidden test window"); return 1; }
    remixapi_StartupInfo startup{};
    startup.sType=REMIXAPI_STRUCT_TYPE_STARTUP_INFO;
    startup.hwnd=reinterpret_cast<remixapi_HWND>(window);
    startup.combineGuiInFinalColor=1;
    Check(api.Startup(&startup), "Startup");
    printf("Remix Startup completed; control=%u frames=%d\n", control ? 1u : 0u, frameCount);
    if (requestFg)
        Check(api.SetConfigVariable("rtx.dlfg.enable", "true"), "request FG probe");
    for (int frame=0; frame<frameCount; ++frame) {
        MSG message{};
        while (PeekMessageW(&message,nullptr,0,0,PM_REMOVE)) { TranslateMessage(&message); DispatchMessageW(&message); }
        if (!control && (frame==5 || frame==25)) {
            PostMessageW(window, WM_KEYDOWN, VK_BACK, 0);
            PostMessageW(window, WM_KEYUP, VK_BACK, 1ll << 31);
        }
        if (!control && (frame==10 || frame==30)) {
            status.size=sizeof(status);
            if (!query(&status) || status.overlayVisible != (frame==10 ? 1u : 0u)) {
                puts("FAIL: Backspace menu toggle on actual Remix window"); return 1;
            }
        }
        remixapi_CameraInfoParameterizedEXT parameterized{};
        parameterized.sType=REMIXAPI_STRUCT_TYPE_CAMERA_INFO_PARAMETERIZED_EXT;
        parameterized.forward={0,0,1}; parameterized.up={0,1,0}; parameterized.right={1,0,0};
        parameterized.fovYInDegrees=60; parameterized.aspect=800.0f/600.0f; parameterized.nearPlane=0.1f; parameterized.farPlane=128;
        remixapi_CameraInfo camera{};
        camera.sType=REMIXAPI_STRUCT_TYPE_CAMERA_INFO;
        camera.pNext=&parameterized;
        camera.type=REMIXAPI_CAMERA_TYPE_WORLD;
        Check(api.SetupCamera(&camera), "SetupCamera");
        auto submit=remixapi_SubmitInfo_init();
        Check(api.Submit(&submit), "Submit");
        auto present=remixapi_PresentInfo_init();
        Check(api.Present(&present), "Present");
        Sleep(10);
    }
    printf("Finished %d native Remix presents\n", frameCount);
    status.size=sizeof(status);
    if (!control && !query(&status)) return 1;
    printf("Real Remix: Vulkan hooked=%u presents=%llu menu draws=%llu failures=%u\n",
        status.vulkanHooked,status.vulkanFrames,status.renderedFrames,status.renderFailures);
    if (!control) {
        puts("Retiring candidate menu before runtime shutdown");
        if (!retire(remix)) return 1;
        puts("Candidate menu retired");
    }
    // This test owns its hidden window. Remove runtime/addon subclass callbacks
    // before disposing the native renderer they reference.
    if (!keepWindowProc) SetWindowLongPtrW(window, GWLP_WNDPROC, reinterpret_cast<LONG_PTR>(DefWindowProcW));
    puts("Beginning Remix Shutdown");
    Check(api.Shutdown(), "Shutdown");
    puts("Remix Shutdown completed");
    DestroyWindow(window);
    if (!control && (!status.vulkanHooked || !status.vulkanFrames || status.renderFailures)) return 1;
    puts(control ? "PASS: stock runtime control shut down" : "PASS: pinned Remix Vulkan presentation and shutdown reach the candidate; no generated-frame claim");
    return 0;
}
