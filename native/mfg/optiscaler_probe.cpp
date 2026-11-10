// SPDX-License-Identifier: Apache-2.0
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <dxgi1_4.h>
#include <wrl/client.h>
#include <cerrno>
#include <cstdio>
#include <cmath>
#include <cwchar>
#include <filesystem>
#include <fstream>
#include <string>
#include "single_module_status.h"
#include "remix_c.h"

static void Check(remixapi_ErrorCode code, const char* operation) {
    if (code != REMIXAPI_ERROR_CODE_SUCCESS) {
        printf("FAIL: %s code=0x%08x\n", operation, static_cast<unsigned>(code));
        ExitProcess(1);
    }
}
// DXGI reports this process's current local video-memory usage on the adapter
// driving the probe window. It is a WDDM allocation estimate, not total GPU
// consumption, physical scanout, or an input-to-photon latency measurement.
static Microsoft::WRL::ComPtr<IDXGIAdapter3> FindDisplayAdapter(HWND window) {
    Microsoft::WRL::ComPtr<IDXGIFactory1> factory;
    if (FAILED(CreateDXGIFactory1(IID_PPV_ARGS(&factory)))) return {};
    const HMONITOR monitor = MonitorFromWindow(window, MONITOR_DEFAULTTONEAREST);
    for (UINT ai = 0; ; ++ai) {
        Microsoft::WRL::ComPtr<IDXGIAdapter1> adapter;
        if (factory->EnumAdapters1(ai, &adapter) == DXGI_ERROR_NOT_FOUND) break;
        for (UINT oi = 0; ; ++oi) {
            Microsoft::WRL::ComPtr<IDXGIOutput> output;
            if (adapter->EnumOutputs(oi, &output) == DXGI_ERROR_NOT_FOUND) break;
            DXGI_OUTPUT_DESC desc{};
            if (SUCCEEDED(output->GetDesc(&desc)) && desc.Monitor == monitor) {
                Microsoft::WRL::ComPtr<IDXGIAdapter3> modern;
                if (SUCCEEDED(adapter.As(&modern))) return modern;
            }
        }
    }
    return {};
}
int wmain(int argc, wchar_t** argv) {
    if (argc < 3 || argc > 7) { puts("Usage: OptiRemixProbe.exe OPTISCALER_DLL REMIX_DLL [visible|hidden] [frame-count] [lighting-conf|request-focus|await-focus=N] [controls]"); return 2; }
    const bool visible = argc > 3 && wcscmp(argv[3], L"visible") == 0;
    if (argc > 3 && !visible && wcscmp(argv[3], L"hidden") != 0) return 2;
    const int frameLimit = argc > 4 ? _wtoi(argv[4]) : 600;
    if (frameLimit < 40 || frameLimit > 3600) return 2;
    const bool controls = argc > 6 && wcscmp(argv[6], L"controls") == 0;
    if (argc > 6 && (!controls || frameLimit < 140)) return 2;
    const bool awaitFocusArg = argc > 5 && wcsncmp(argv[5], L"await-focus=", 12) == 0;
    unsigned awaitFocusSeconds = 0;
    if (awaitFocusArg) {
        wchar_t* end = nullptr;
        errno = 0;
        const unsigned long parsed = wcstoul(argv[5] + 12, &end, 10);
        if (errno || end == argv[5] + 12 || *end || parsed < 5 || parsed > 180) {
            puts("FAIL: await-focus requires a whole number of seconds between 5 and 180");
            return 2;
        }
        awaitFocusSeconds = static_cast<unsigned>(parsed);
    }
    const bool requestFocus = awaitFocusArg || (argc > 5 && wcscmp(argv[5], L"request-focus") == 0);
    if (requestFocus && !visible) { puts("FAIL: foreground focus options require a visible probe window"); return 2; }
    setvbuf(stdout, nullptr, _IONBF, 0);
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
    const auto addon = std::filesystem::absolute(argv[1]);
    const auto runtime = std::filesystem::absolute(argv[2]);
    SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
    AddDllDirectory(runtime.parent_path().c_str());
    if (!LoadLibraryExW(L"vulkan-1.dll",nullptr,LOAD_LIBRARY_SEARCH_SYSTEM32)) return 1;
    const auto opti = LoadLibraryExW(addon.c_str(), nullptr, LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
    if (!opti) { printf("FAIL: OptiScaler load %lu\n", GetLastError()); return 1; }
    const auto mfg = GetModuleHandleW(L"MFGUnlocker.asi");
    const auto query = mfg ? reinterpret_cast<MfgSingleModuleQueryFn>(GetProcAddress(mfg, "MfgUnlockSingleModuleQuery")) : nullptr;
    if (!query) { puts("FAIL: candidate load"); return 1; }
    using ReadyFn = BOOL (WINAPI*)();
    using RemixHostFn = BOOL (WINAPI*)(HMODULE);
    const auto startupReady = reinterpret_cast<ReadyFn>(GetProcAddress(mfg, "MfgUnlockPrivateVulkanStartupReady"));
    const auto deviceReady = reinterpret_cast<ReadyFn>(GetProcAddress(mfg, "MfgUnlockPrivateVulkanDeviceReady"));
    const auto registerHost = reinterpret_cast<RemixHostFn>(GetProcAddress(mfg, "MfgUnlockRegisterRemixVulkanHost"));
    const auto retireHost = reinterpret_cast<RemixHostFn>(GetProcAddress(mfg, "MfgUnlockRetireRemixVulkanHost"));
    if (!startupReady || !deviceReady || !registerHost || !retireHost) {
        puts("FAIL: missing readiness or Remix host lifecycle exports"); return 1;
    }
    MfgSingleModuleStatus status{};
    for (int i=0; i<500; ++i) { status.size=sizeof(status); if (query(&status) && status.backendOwner && startupReady()) break; Sleep(10); }
    if (!status.backendOwner || !startupReady()) { puts("FAIL: early startup prerequisites not ready"); return 1; }
    const auto remix = LoadLibraryExW(runtime.c_str(), nullptr, LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
    if (!remix) { puts("FAIL: renderer registration"); return 1; }
    if (!registerHost(remix)) { puts("FAIL: pinned Remix Vulkan host registration"); return 1; }
    puts("Pinned Remix Vulkan host registered before InitializeLibrary");
    auto initialize = reinterpret_cast<PFN_remixapi_InitializeLibrary>(GetProcAddress(remix, "remixapi_InitializeLibrary"));
    if (!initialize) { puts("FAIL: runtime C API export"); return 1; }
    remixapi_InitializeLibraryInfo init{};
    init.sType=REMIXAPI_STRUCT_TYPE_INITIALIZE_LIBRARY_INFO;
    init.version=REMIXAPI_VERSION_MAKE(REMIXAPI_VERSION_MAJOR, REMIXAPI_VERSION_MINOR, REMIXAPI_VERSION_PATCH);
    remixapi_Interface api{};
    Check(initialize(&init, &api), "InitializeLibrary");
    WNDCLASSW cls{};
    cls.lpfnWndProc=DefWindowProcW; cls.hInstance=GetModuleHandleW(nullptr); cls.lpszClassName=L"MfgRemixSmoke";
    RegisterClassW(&cls);
    HWND window=CreateWindowW(cls.lpszClassName,L"Isolated Remix native test",WS_OVERLAPPEDWINDOW,0,0,800,600,nullptr,nullptr,cls.hInstance,nullptr);
    if (!window) { puts("FAIL: test window"); return 1; }

    remixapi_StartupInfo startup{};
    startup.sType=REMIXAPI_STRUCT_TYPE_STARTUP_INFO;
    startup.hwnd=reinterpret_cast<remixapi_HWND>(window);
    startup.combineGuiInFinalColor=1;
    // Simulate a saved native request, then the Java adapter's pre-startup repair.
    if (controls) Check(api.SetConfigVariable("rtx.dlfg.enable", "true"), "Seed conflicting native FG request");
    Check(api.SetConfigVariable("rtx.dlfg.enable", "false"), "Keep native FG off for the OptiScaler route");
    Check(api.Startup(&startup), "Startup");
    if (!deviceReady()) { puts("FAIL: private Vulkan startup rejected"); api.Shutdown(); return 1; }
    auto readOption = [&api](const char* key) {
        char value[32]{};
        auto query = remixapi_ConfigVariableResolvedInfo_init();
        query.key = key; query.value = value; query.valueSize = sizeof(value);
        Check(api.GetConfigVariableResolved(&query), "Read cache diagnostic option");
        return std::string(value);
    };
    const char* queryKey = "rtx.spatiallyHashedRadianceCache.queryForThinOpaquePrimaryView";
    const char* accumulationKey = "rtx.spatiallyHashedRadianceCache.maxNumFramesToAccumulate";
    const char* staleKey = "rtx.spatiallyHashedRadianceCache.staleFrameNumber";
    const auto queryBefore = readOption(queryKey);
    const auto accumulationBefore = readOption(accumulationKey);
    const auto staleBefore = readOption(staleKey);
    const char* eyeKey = "rtx.autoExposure.enabled";
    const char* speedKey = "rtx.autoExposure.autoExposureSpeed";
    const auto eyeBefore = readOption(eyeKey);
    const auto speedBefore = readOption(speedKey);
    const char* sparseKey = "rtx.sparseRendering.enableSparseRendering";
    const char* sparseQualityKey = "rtx.sparseRendering.quality";
    const auto sparseBefore = readOption(sparseKey);
    const auto sparseQualityBefore = readOption(sparseQualityKey);
    Check(api.SetConfigVariable(sparseKey, "false"), "Disable sparse tracing");
    Check(api.SetConfigVariable(sparseQualityKey, "0.5"), "Set balanced sparse quality");
    Check(api.SetConfigVariable(eyeKey, "true"), "Enable eye adaptation");
    Check(api.SetConfigVariable(speedKey, "2.0"), "Set gentle adaptation speed");
    Check(api.SetConfigVariable(queryKey, "false"), "Disable foliage cache query for diagnostic");
    remixapi_ConfigLayerHandle lightingLayer{};
    if (argc > 5 && !requestFocus) {
        const auto encoded = std::filesystem::absolute(argv[5]).u8string();
        const std::string path(encoded.begin(), encoded.end());
        Check(api.AcquireConfigLayer(path.c_str(), 3101.0f, 0.5f, &lightingLayer), "Acquire lighting settling layer");
        Check(api.SetConfigLayerBlending(lightingLayer, 1.0f, 0.5f), "Enable lighting settling layer");
    }
    if (visible) { ShowWindow(window,SW_SHOW); UpdateWindow(window); }
    if (requestFocus) {
        // Opt-in foreground request for this probe's own window only. Windows
        // may deny it; never inject input or change another window's state.
        SetLastError(0);
        const BOOL focusAccepted = SetForegroundWindow(window);
        printf("Own-window foreground request accepted=%u win32=%lu\n", focusAccepted != 0, GetLastError());
    }
    printf("Probe owns foreground: %u\n", GetForegroundWindow()==window);
    if (awaitFocusSeconds) {
        printf("Awaiting foreground focus for up to %u seconds: click the isolated Remix native test window.\n",
               awaitFocusSeconds);
        const ULONGLONG deadline = GetTickCount64() + static_cast<ULONGLONG>(awaitFocusSeconds) * 1000;
        while (IsWindow(window) && GetForegroundWindow() != window && GetTickCount64() < deadline) {
            MSG pending{};
            while (PeekMessageW(&pending, nullptr, 0, 0, PM_REMOVE)) {
                if (pending.message == WM_QUIT) break;
                TranslateMessage(&pending);
                DispatchMessageW(&pending);
            }
            Sleep(50);
        }
        if (!IsWindow(window) || GetForegroundWindow() != window) {
            puts("FOCUS GATE FAILED: no foreground focus; ending before FG render measurements.");
            // Deliberately terminate this isolated probe without entering the
            // known potentially blocking stock-Remix Shutdown path.
            return 4;
        }
        puts("FOCUS GATE PASSED: foreground acquired; starting GPU frame measurements.");
    }
    remixapi_MaterialInfoOpaqueEXT opaque{};
    opaque.sType=REMIXAPI_STRUCT_TYPE_MATERIAL_INFO_OPAQUE_EXT;
    opaque.albedoConstant={0.8f,0.4f,0.2f}; opaque.opacityConstant=1.0f; opaque.roughnessConstant=0.5f;
    // Match MaterialInfoOpaqueEXT's opaque default (VK_COMPARE_OP_ALWAYS).
    opaque.alphaTestType=7;
    remixapi_MaterialInfo materialInfo{};
    materialInfo.sType=REMIXAPI_STRUCT_TYPE_MATERIAL_INFO; materialInfo.pNext=&opaque; materialInfo.hash=0x4D464750524F4245ull;
    materialInfo.emissiveIntensity=2.0f; materialInfo.emissiveColorConstant={1,0.3f,0.1f};
    materialInfo.spriteSheetRow=1; materialInfo.spriteSheetCol=1;
    remixapi_MaterialHandle material{};
    Check(api.CreateMaterial(&materialInfo,&material),"CreateMaterial");
    remixapi_HardcodedVertex vertices[3]{};
    const float positions[3][3]={{-2,-2,4},{0,2,4},{2,-2,4}};
    for (int i=0;i<3;++i) { for(int j=0;j<3;++j) vertices[i].position[j]=positions[i][j]; vertices[i].normal[2]=-1; vertices[i].color=0xFFFFFFFFu; }
    const uint32_t indices[3]={0,1,2};
    remixapi_MeshInfoSurfaceTriangles surface{};
    surface.vertices_values=vertices; surface.vertices_count=3; surface.indices_values=indices; surface.indices_count=3; surface.material=material;
    remixapi_MeshInfo meshInfo{};
    meshInfo.sType=REMIXAPI_STRUCT_TYPE_MESH_INFO; meshInfo.surfaces_values=&surface; meshInfo.surfaces_count=1;
    remixapi_MeshHandle mesh{};
    Check(api.CreateMesh(&meshInfo,&mesh),"CreateMesh");
    remixapi_InstanceInfo instance{};
    instance.sType=REMIXAPI_STRUCT_TYPE_INSTANCE_INFO; instance.mesh=mesh; instance.doubleSided=1;
    instance.transform.matrix[0][0]=1; instance.transform.matrix[1][1]=1; instance.transform.matrix[2][2]=1;

    unsigned foregroundPresents = 0;
    unsigned presents = 0;
    wchar_t tracePath[32768]{};
    const DWORD traceChars = GetEnvironmentVariableW(L"MFG_PROBE_PRESENT_TRACE_PATH", tracePath,
                                                   static_cast<DWORD>(_countof(tracePath)));
    std::ofstream presentTrace;
    LARGE_INTEGER frequency{};
    Microsoft::WRL::ComPtr<IDXGIAdapter3> displayAdapter;
    if (traceChars >= _countof(tracePath)) { puts("FAIL: source-present trace path exceeds buffer"); return 1; }
    if (traceChars) {
        presentTrace.open(std::filesystem::path(tracePath), std::ios::trunc);
        if (!presentTrace) { puts("FAIL: cannot open source-present timestamp CSV"); return 1; }
        QueryPerformanceFrequency(&frequency);
        printf("Source-present QPC trace enabled, clockHz=%lld\n", static_cast<long long>(frequency.QuadPart));
        displayAdapter = FindDisplayAdapter(window);
        printf("DXGI local memory query adapter found=%u; usage may be unavailable\n", displayAdapter != nullptr);
        presentTrace << "sourceFrame,beforePresentQpc,afterPresentQpc,foreground,qpcHz,gpuLocalUsageBytes,gpuLocalBudgetBytes,instanceX,expectedCropCentroidX\n";
    }
    for (int frame=0; frame<frameLimit && IsWindow(window); ++frame) {
        MSG message{};
        while (PeekMessageW(&message,nullptr,0,0,PM_REMOVE)) { TranslateMessage(&message); DispatchMessageW(&message); }
        if (!IsWindow(window)) break;
        // Only this probe's own window receives synthetic messages. No global input or focus change.
        if (controls && (frame == 20 || frame == 45 || frame == 70 || frame == 95)) {
            const UINT key = frame < 70 ? VK_INSERT : VK_END;
            PostMessageW(window, WM_KEYDOWN, key, 1);
            PostMessageW(window, WM_KEYUP, key, (1ll << 31) | (1ll << 30) | 1);
            printf("Own-window control: frame=%d key=%u\n", frame, key);
        }
        remixapi_CameraInfoParameterizedEXT parameterized{};
        parameterized.sType=REMIXAPI_STRUCT_TYPE_CAMERA_INFO_PARAMETERIZED_EXT;
        parameterized.forward={0,0,1}; parameterized.up={0,1,0}; parameterized.right={1,0,0};
        parameterized.fovYInDegrees=60; parameterized.aspect=800.0f/600.0f; parameterized.nearPlane=0.1f; parameterized.farPlane=128;
        remixapi_CameraInfo camera{};
        camera.sType=REMIXAPI_STRUCT_TYPE_CAMERA_INFO;
        camera.pNext=&parameterized;
        for(int k=0;k<4;++k) camera.view[k][k]=1;
        const float focal=1.7320508f;
        camera.projection[0][0]=focal/parameterized.aspect;
        camera.projection[1][1]=focal;
        camera.projection[2][2]=parameterized.farPlane/(parameterized.farPlane-parameterized.nearPlane);
        camera.projection[2][3]=1;
        camera.projection[3][2]=-parameterized.nearPlane*parameterized.farPlane/(parameterized.farPlane-parameterized.nearPlane);
        camera.type=REMIXAPI_CAMERA_TYPE_WORLD;
        Check(api.SetupCamera(&camera), "SetupCamera");
        const float instanceX=0.5f*std::sin(float(frame)/8.0f);
        instance.transform.matrix[0][3]=instanceX;
        Check(api.DrawInstance(&instance),"DrawInstance");
        auto submit=remixapi_SubmitInfo_init();
        Check(api.Submit(&submit), "Submit");
        auto present=remixapi_PresentInfo_init();
        LARGE_INTEGER beforePresent{};
        LARGE_INTEGER afterPresent{};
        if (presentTrace) QueryPerformanceCounter(&beforePresent);
        Check(api.Present(&present), "Present");
        if (presentTrace) QueryPerformanceCounter(&afterPresent);
        if (frame == 10) {
            if (_stricmp(readOption(sparseKey).c_str(), "false") != 0
                    || std::abs(std::stof(readOption(sparseQualityKey)) - 0.5f) > 0.001f) {
                puts("FAIL: sparse tracing options did not resolve"); return 1;
            }
            puts("Sparse tracing verified off, quality=0.5; testing on");
            Check(api.SetConfigVariable(sparseKey, "true"), "Enable sparse tracing");
            if (_stricmp(readOption(eyeKey).c_str(), "true") != 0
                    || std::abs(std::stof(readOption(speedKey)) - 2.0f) > 0.001f) {
                puts("FAIL: eye adaptation options did not resolve"); return 1;
            }
            puts("Eye adaptation verified: enabled=true speed=2; restoring previous values");
            Check(api.SetConfigVariable(eyeKey, eyeBefore.c_str()), "Restore eye adaptation");
            Check(api.SetConfigVariable(speedKey, speedBefore.c_str()), "Restore adaptation speed");
            if (_stricmp(readOption(queryKey).c_str(), "false") != 0) { puts("FAIL: foliage cache query did not disable"); return 1; }
            if (lightingLayer) {
                if (readOption(accumulationKey) != "8" || readOption(staleKey) != "8") { puts("FAIL: lighting layer did not resolve to 8/8"); return 1; }
                puts("Lighting layer active: accumulation=8 stale=8");
                Check(api.SetConfigLayerBlending(lightingLayer, 0.0f, 0.5f), "Disable lighting settling layer");
            }
            Check(api.SetConfigVariable(queryKey, queryBefore.c_str()), "Restore foliage cache query");
        }
        if (frame == 25) {
            if (_stricmp(readOption(sparseKey).c_str(), "true") != 0) {
                puts("FAIL: sparse tracing did not enable"); return 1;
            }
            puts("Sparse tracing verified on; restoring previous values");
            Check(api.SetConfigVariable(sparseKey, sparseBefore.c_str()), "Restore sparse tracing");
            Check(api.SetConfigVariable(sparseQualityKey, sparseQualityBefore.c_str()), "Restore sparse quality");
        }
        ++presents;
        if (GetForegroundWindow() == window) ++foregroundPresents;
        if (presentTrace) {
            // Triangle centroid is local x=0,z=4. The observer crops the center 256 pixels
            // of the 800-wide client area, so this predicts its ideal crop-space x position
            // for the explicit instance translation above.
            const float expectedCropCentroidX =
                128.0f + instanceX * camera.projection[0][0] * 100.0f;
            presentTrace << presents << ',' << beforePresent.QuadPart << ',' << afterPresent.QuadPart
                         << ',' << (GetForegroundWindow() == window ? 1 : 0) << ','
                         << frequency.QuadPart << ',';
            DXGI_QUERY_VIDEO_MEMORY_INFO videoMemory{};
            if (displayAdapter && SUCCEEDED(displayAdapter->QueryVideoMemoryInfo(
                    0, DXGI_MEMORY_SEGMENT_GROUP_LOCAL, &videoMemory))) {
                presentTrace << videoMemory.CurrentUsage << ',' << videoMemory.Budget;
            } else {
                presentTrace << ',';
            }
            presentTrace << ',' << instanceX << ',' << expectedCropCentroidX << '\n';
            if (presents % 60 == 0) presentTrace.flush();
        }
        if (visible && (frame % 60 == 59)) {
            printf("Focus checkpoint: presents=%u foreground=%u current=%u\n",
                presents, foregroundPresents, GetForegroundWindow()==window);
        }
        Sleep(16);
    }
    printf("Probe presents=%u foreground presents=%u\n", presents, foregroundPresents);
    if (presentTrace) presentTrace.flush();
    if (controls) {
        if (_stricmp(readOption("rtx.dlfg.enable").c_str(), "false") != 0) {
            puts("FAIL: conflicting native FG request was not cleared"); return 1;
        }
        puts("Native FG request cleared; check fresh OptiScaler log for Insert open/close and End off/on");
    }
    if (readOption(queryKey) != queryBefore || readOption(accumulationKey) != accumulationBefore
            || readOption(staleKey) != staleBefore || readOption(eyeKey) != eyeBefore || readOption(speedKey) != speedBefore
            || readOption(sparseKey) != sparseBefore || readOption(sparseQualityKey) != sparseQualityBefore) {
        puts("FAIL: lighting defaults were not restored"); return 1;
    }
    printf("Lighting defaults restored: query=%s accumulation=%s stale=%s\n", queryBefore.c_str(), accumulationBefore.c_str(), staleBefore.c_str());
    if (lightingLayer) Check(api.ReleaseConfigLayer(lightingLayer), "Release lighting settling layer");
    Check(api.DestroyMesh(mesh),"DestroyMesh");
    Check(api.DestroyMaterial(material),"DestroyMaterial");
    status.size=sizeof(status);
    if (!query(&status)) return 1;
    printf("Real Remix: Vulkan hooked=%u presents=%llu menu draws=%llu failures=%u\n",
        status.vulkanHooked,status.vulkanFrames,status.renderedFrames,status.renderFailures);
    puts("Retiring Remix Vulkan swapchain hooks before renderer shutdown");
    if (!retireHost(remix)) { puts("FAIL: Remix Vulkan host retirement"); return 1; }
    puts("Remix Vulkan host retired");
    // This test owns its window. Remove runtime/addon subclass callbacks
    // before disposing the native renderer they reference.
    SetWindowLongPtrW(window, GWLP_WNDPROC, reinterpret_cast<LONG_PTR>(DefWindowProcW));
    puts("Beginning Remix Shutdown");
    Check(api.Shutdown(), "Shutdown");
    puts("Remix Shutdown completed");
    DestroyWindow(window);

    puts("Probe completed. Validate fresh MFG status: created features, evaluations, failures and presentation count. Menu counters alone do not establish FG.");
    return 0;
}

#ifdef MFG_PROBE_JAVA_HOST
extern "C" __declspec(dllexport) int MfgRunJavaHostProbe(wchar_t* addon, wchar_t* runtime, wchar_t* lightingConf) {
    wchar_t name[] = L"JavaHostProbe";
    wchar_t mode[] = L"hidden";
    wchar_t frames[] = L"60";
    wchar_t* args[] = {name, addon, runtime, mode, frames, lightingConf};
    return wmain(6, args);
}
#endif
