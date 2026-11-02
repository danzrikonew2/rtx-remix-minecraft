// SPDX-License-Identifier: Apache-2.0
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <cstdio>
#include <cmath>
#include <filesystem>
#include <string>
#include "single_module_status.h"
#include "remix_c.h"

static void Check(remixapi_ErrorCode code, const char* operation) {
    if (code != REMIXAPI_ERROR_CODE_SUCCESS) {
        printf("FAIL: %s code=0x%08x\n", operation, static_cast<unsigned>(code));
        ExitProcess(1);
    }
}
int wmain(int argc, wchar_t** argv) {
    if (argc < 3 || argc > 6) { puts("Usage: OptiRemixProbe.exe OPTISCALER_DLL REMIX_DLL [visible|hidden] [frame-count] [lighting-conf]"); return 2; }
    const bool visible = argc > 3 && wcscmp(argv[3], L"visible") == 0;
    if (argc > 3 && !visible && wcscmp(argv[3], L"hidden") != 0) return 2;
    const int frameLimit = argc > 4 ? _wtoi(argv[4]) : 600;
    if (frameLimit < 40 || frameLimit > 3600) return 2;
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
    const auto startupReady = reinterpret_cast<ReadyFn>(GetProcAddress(mfg, "MfgUnlockPrivateVulkanStartupReady"));
    const auto deviceReady = reinterpret_cast<ReadyFn>(GetProcAddress(mfg, "MfgUnlockPrivateVulkanDeviceReady"));
    if (!startupReady || !deviceReady) { puts("FAIL: missing startup readiness exports"); return 1; }
    MfgSingleModuleStatus status{};
    for (int i=0; i<500; ++i) { status.size=sizeof(status); if (query(&status) && status.backendOwner && startupReady()) break; Sleep(10); }
    if (!status.backendOwner || !startupReady()) { puts("FAIL: early startup prerequisites not ready"); return 1; }
    const auto remix = LoadLibraryExW(runtime.c_str(), nullptr, LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
    if (!remix) { puts("FAIL: renderer registration"); return 1; }
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
    Check(api.SetConfigVariable(queryKey, "false"), "Disable foliage cache query for diagnostic");
    remixapi_ConfigLayerHandle lightingLayer{};
    if (argc > 5) {
        const auto encoded = std::filesystem::absolute(argv[5]).u8string();
        const std::string path(encoded.begin(), encoded.end());
        Check(api.AcquireConfigLayer(path.c_str(), 3101.0f, 0.5f, &lightingLayer), "Acquire lighting settling layer");
        Check(api.SetConfigLayerBlending(lightingLayer, 1.0f, 0.5f), "Enable lighting settling layer");
    }
    if (visible) { ShowWindow(window,SW_SHOW); UpdateWindow(window); }
    printf("Probe owns foreground: %u\n", GetForegroundWindow()==window);
    remixapi_MaterialInfoOpaqueEXT opaque{};
    opaque.sType=REMIXAPI_STRUCT_TYPE_MATERIAL_INFO_OPAQUE_EXT;
    opaque.albedoConstant={0.8f,0.4f,0.2f}; opaque.opacityConstant=1.0f; opaque.roughnessConstant=0.5f;
    remixapi_MaterialInfo materialInfo{};
    materialInfo.sType=REMIXAPI_STRUCT_TYPE_MATERIAL_INFO; materialInfo.pNext=&opaque; materialInfo.hash=0x4D464750524F4245ull;
    materialInfo.emissiveIntensity=2.0f; materialInfo.emissiveColorConstant={1,0.3f,0.1f};
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
    for (int frame=0; frame<frameLimit && IsWindow(window); ++frame) {
        MSG message{};
        while (PeekMessageW(&message,nullptr,0,0,PM_REMOVE)) { TranslateMessage(&message); DispatchMessageW(&message); }
        if (!IsWindow(window)) break;
        remixapi_CameraInfoParameterizedEXT parameterized{};
        parameterized.sType=REMIXAPI_STRUCT_TYPE_CAMERA_INFO_PARAMETERIZED_EXT;
        parameterized.forward={0,0,1}; parameterized.up={0,1,0}; parameterized.right={1,0,0};
        parameterized.fovYInDegrees=60; parameterized.aspect=800.0f/600.0f; parameterized.nearPlane=0.1f; parameterized.farPlane=128;
        remixapi_CameraInfo camera{};
        camera.sType=REMIXAPI_STRUCT_TYPE_CAMERA_INFO;
        parameterized.position.x=0.5f*std::sin(float(frame)/8.0f);
        camera.pNext=&parameterized;
        for(int k=0;k<4;++k) camera.view[k][k]=1;
        camera.view[3][0]=-parameterized.position.x;
        const float focal=1.7320508f;
        camera.projection[0][0]=focal/parameterized.aspect;
        camera.projection[1][1]=focal;
        camera.projection[2][2]=parameterized.farPlane/(parameterized.farPlane-parameterized.nearPlane);
        camera.projection[2][3]=1;
        camera.projection[3][2]=-parameterized.nearPlane*parameterized.farPlane/(parameterized.farPlane-parameterized.nearPlane);
        camera.type=REMIXAPI_CAMERA_TYPE_WORLD;
        Check(api.SetupCamera(&camera), "SetupCamera");
        Check(api.DrawInstance(&instance),"DrawInstance");
        auto submit=remixapi_SubmitInfo_init();
        Check(api.Submit(&submit), "Submit");
        auto present=remixapi_PresentInfo_init();
        Check(api.Present(&present), "Present");
        if (frame == 10) {
            if (_stricmp(readOption(queryKey).c_str(), "false") != 0) { puts("FAIL: foliage cache query did not disable"); return 1; }
            if (lightingLayer) {
                if (readOption(accumulationKey) != "8" || readOption(staleKey) != "8") { puts("FAIL: lighting layer did not resolve to 8/8"); return 1; }
                puts("Lighting layer active: accumulation=8 stale=8");
                Check(api.SetConfigLayerBlending(lightingLayer, 0.0f, 0.5f), "Disable lighting settling layer");
            }
            Check(api.SetConfigVariable(queryKey, queryBefore.c_str()), "Restore foliage cache query");
        }
        ++presents;
        if (GetForegroundWindow() == window) ++foregroundPresents;
        Sleep(16);
    }
    printf("Probe presents=%u foreground presents=%u\n", presents, foregroundPresents);
    if (readOption(queryKey) != queryBefore || readOption(accumulationKey) != accumulationBefore || readOption(staleKey) != staleBefore) {
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
    // This test owns its window. Remove runtime/addon subclass callbacks
    // before disposing the native renderer they reference.
    SetWindowLongPtrW(window, GWLP_WNDPROC, reinterpret_cast<LONG_PTR>(DefWindowProcW));
    Check(api.Shutdown(), "Shutdown");
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
