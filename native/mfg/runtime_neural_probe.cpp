/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <cmath>
#include <cstdio>
#include <filesystem>
#include <stdexcept>
#include <string>
#include "remix_c.h"

static constexpr const char* NeuralKey = "rtx.dlssNeuralRendering.enable";

static void ReportLoadedProvider() {
    const HMODULE provider = GetModuleHandleW(L"nvngx_dlssnr.dll");
    wchar_t path[32768]{};
    if (provider && GetModuleFileNameW(provider, path, static_cast<DWORD>(std::size(path))))
        std::printf("Loaded neural provider: %ls\n", path);
    else
        std::puts("Neural provider is not loaded at this check.");
}

static bool Report(remixapi_ErrorCode code, const char* operation) {
    if (code == REMIXAPI_ERROR_CODE_SUCCESS) return true;
    std::printf("FAIL: %s C API code=0x%08x (%u)\n", operation,
        static_cast<unsigned>(code), static_cast<unsigned>(code));
    return false;
}

static void Check(remixapi_ErrorCode code, const char* operation) {
    if (!Report(code, operation)) throw std::runtime_error(operation);
}

static remixapi_ErrorCode ReadOption(remixapi_Interface& api, std::string& value) {
    char buffer[256]{};
    auto query = remixapi_ConfigVariableResolvedInfo_init();
    query.key = NeuralKey;
    query.value = buffer;
    query.valueSize = sizeof(buffer);
    auto code = api.GetConfigVariableResolved(&query);
    if (code == REMIXAPI_ERROR_CODE_SUCCESS) value = buffer;
    return code;
}

int wmain(int argc, wchar_t** argv) {
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    if (argc != 2 || !std::filesystem::path(argv[1]).is_absolute()) {
        std::puts("Usage: RemixNeuralProbe.exe ABSOLUTE_PINNED_REMIX_DLL");
        return 2;
    }
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
    const std::filesystem::path runtime(argv[1]);
    std::puts("Run only from a disposable caller-owned working directory; runtime logs/config belong there.");
    std::puts("Option acceptance is NOT feature creation, provider capability, or evaluation success. Inspect fresh runtime logs for that outcome.");
    std::printf("Pinned runtime input: %ls\n", runtime.c_str());

    HMODULE library = nullptr;
    DLL_DIRECTORY_COOKIE runtimeDirectory = nullptr;
    HWND window = nullptr;
    remixapi_Interface api{};
    remixapi_MaterialHandle material{};
    remixapi_MeshHandle mesh{};
    bool started = false;
    bool needsRestore = false;
    bool optionAvailable = false;
    std::string original;
    int result = 0;
    try {
        if (!std::filesystem::is_regular_file(runtime)) throw std::runtime_error("runtime path is not a file");
        if (!SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_DEFAULT_DIRS)) throw std::runtime_error("DLL search policy");
        runtimeDirectory = AddDllDirectory(runtime.parent_path().c_str());
        if (!runtimeDirectory) throw std::runtime_error("runtime dependency directory");
        library = LoadLibraryExW(runtime.c_str(), nullptr,
            LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
        if (!library) {
            std::printf("Runtime load Win32 error=%lu\n", GetLastError());
            throw std::runtime_error("runtime load");
        }
        const auto initialize = reinterpret_cast<PFN_remixapi_InitializeLibrary>(
            GetProcAddress(library, "remixapi_InitializeLibrary"));
        if (!initialize) throw std::runtime_error("missing remixapi_InitializeLibrary export");
        remixapi_InitializeLibraryInfo init{};
        init.sType = REMIXAPI_STRUCT_TYPE_INITIALIZE_LIBRARY_INFO;
        init.version = REMIXAPI_VERSION_MAKE(REMIXAPI_VERSION_MAJOR, REMIXAPI_VERSION_MINOR, REMIXAPI_VERSION_PATCH);
        Check(initialize(&init, &api), "InitializeLibrary");

        WNDCLASSW cls{};
        cls.lpfnWndProc = DefWindowProcW;
        cls.hInstance = GetModuleHandleW(nullptr);
        cls.lpszClassName = L"RemixNativeNeuralProbe";
        if (!RegisterClassW(&cls)) throw std::runtime_error("register probe window class");
        RECT bounds{0, 0, 800, 600};
        if (!AdjustWindowRect(&bounds, WS_OVERLAPPEDWINDOW, FALSE)) throw std::runtime_error("window bounds");
        window = CreateWindowW(cls.lpszClassName, L"Isolated native neural runtime probe",
            WS_OVERLAPPEDWINDOW, 0, 0, bounds.right - bounds.left, bounds.bottom - bounds.top,
            nullptr, nullptr, cls.hInstance, nullptr);
        if (!window) throw std::runtime_error("create hidden probe window");

        Check(api.SetConfigVariable("rtx.dlfg.enable", "false"), "Disable native FG before Startup");
        remixapi_StartupInfo startup{};
        startup.sType = REMIXAPI_STRUCT_TYPE_STARTUP_INFO;
        startup.hwnd = reinterpret_cast<remixapi_HWND>(window);
        startup.combineGuiInFinalColor = 1;
        Check(api.Startup(&startup), "Startup");
        started = true;
        ReportLoadedProvider();

        const auto queryCode = ReadOption(api, original);
        optionAvailable = queryCode == REMIXAPI_ERROR_CODE_SUCCESS;
        if (!optionAvailable) {
            std::printf("Option unavailable: %s C API code=0x%08x (%u); continuing basic renderer smoke.\n",
                NeuralKey, static_cast<unsigned>(queryCode), static_cast<unsigned>(queryCode));
        } else {
            std::printf("Option available: %s original=%s\n", NeuralKey, original.c_str());
            // Restore even if a later native call or resolved-value check fails.
            needsRestore = true;
            Check(api.SetConfigVariable(NeuralKey, "true"), "Request native neural rendering");
        }

        remixapi_MaterialInfoOpaqueEXT opaque{};
        opaque.sType = REMIXAPI_STRUCT_TYPE_MATERIAL_INFO_OPAQUE_EXT;
        opaque.albedoConstant = {0.8f, 0.4f, 0.2f};
        opaque.opacityConstant = 1.0f;
        opaque.roughnessConstant = 0.5f;
        remixapi_MaterialInfo materialInfo{};
        materialInfo.sType = REMIXAPI_STRUCT_TYPE_MATERIAL_INFO;
        materialInfo.pNext = &opaque;
        materialInfo.hash = 0x4E45555250524F42ull;
        materialInfo.emissiveIntensity = 2.0f;
        materialInfo.emissiveColorConstant = {1, 0.3f, 0.1f};
        Check(api.CreateMaterial(&materialInfo, &material), "CreateMaterial");
        remixapi_HardcodedVertex vertices[3]{};
        const float positions[3][3] = {{-2, -2, 4}, {0, 2, 4}, {2, -2, 4}};
        for (int i = 0; i < 3; ++i) {
            for (int j = 0; j < 3; ++j) vertices[i].position[j] = positions[i][j];
            vertices[i].normal[2] = -1;
            vertices[i].color = 0xFFFFFFFFu;
        }
        const uint32_t indices[3] = {0, 1, 2};
        remixapi_MeshInfoSurfaceTriangles surface{};
        surface.vertices_values = vertices; surface.vertices_count = 3;
        surface.indices_values = indices; surface.indices_count = 3; surface.material = material;
        remixapi_MeshInfo meshInfo{};
        meshInfo.sType = REMIXAPI_STRUCT_TYPE_MESH_INFO;
        meshInfo.hash = 0x4E4555524D455348ull;
        meshInfo.surfaces_values = &surface; meshInfo.surfaces_count = 1;
        Check(api.CreateMesh(&meshInfo, &mesh), "CreateMesh");
        remixapi_InstanceInfo instance{};
        instance.sType = REMIXAPI_STRUCT_TYPE_INSTANCE_INFO;
        instance.mesh = mesh; instance.doubleSided = 1;
        for (int i = 0; i < 3; ++i) instance.transform.matrix[i][i] = 1;

        for (int presents = 1; presents <= 60; ++presents) {
            MSG message{};
            while (PeekMessageW(&message, nullptr, 0, 0, PM_REMOVE)) {
                TranslateMessage(&message); DispatchMessageW(&message);
            }
            if (!IsWindow(window)) throw std::runtime_error("probe window closed before 60 presents");
            remixapi_CameraInfoParameterizedEXT parameterized{};
            parameterized.sType = REMIXAPI_STRUCT_TYPE_CAMERA_INFO_PARAMETERIZED_EXT;
            parameterized.forward = {0, 0, 1}; parameterized.up = {0, 1, 0}; parameterized.right = {1, 0, 0};
            parameterized.position.x = 0.5f * std::sin(float(presents) / 8.0f);
            parameterized.fovYInDegrees = 60; parameterized.aspect = 800.0f / 600.0f;
            parameterized.nearPlane = 0.1f; parameterized.farPlane = 128;
            remixapi_CameraInfo camera{};
            camera.sType = REMIXAPI_STRUCT_TYPE_CAMERA_INFO;
            camera.type = REMIXAPI_CAMERA_TYPE_WORLD; camera.pNext = &parameterized;
            for (int i = 0; i < 4; ++i) camera.view[i][i] = 1;
            camera.view[3][0] = -parameterized.position.x;
            const float focal = 1.7320508f;
            camera.projection[0][0] = focal / parameterized.aspect;
            camera.projection[1][1] = focal;
            camera.projection[2][2] = parameterized.farPlane / (parameterized.farPlane - parameterized.nearPlane);
            camera.projection[2][3] = 1;
            camera.projection[3][2] = -parameterized.nearPlane * parameterized.farPlane / (parameterized.farPlane - parameterized.nearPlane);
            Check(api.SetupCamera(&camera), "SetupCamera");
            Check(api.DrawInstance(&instance), "DrawInstance");
            auto submit = remixapi_SubmitInfo_init();
            Check(api.Submit(&submit), "Submit");
            auto present = remixapi_PresentInfo_init();
            Check(api.Present(&present), "Present");
            if (optionAvailable && presents == 10) {
                ReportLoadedProvider();
                std::string resolved;
                Check(ReadOption(api, resolved), "Read neural option after 10 presents");
                std::printf("After 10 presents: %s=%s\n", NeuralKey, resolved.c_str());
                if (_stricmp(resolved.c_str(), "true") != 0) throw std::runtime_error("neural enable request did not resolve true");
            }
            if (optionAvailable && presents == 30) {
                Check(api.SetConfigVariable(NeuralKey, original.c_str()), "Restore neural option after 30 presents");
                std::printf("After 30 presents: requested original=%s\n", original.c_str());
            }
            Sleep(16);
        }
        if (optionAvailable) {
            std::string resolved;
            Check(ReadOption(api, resolved), "Verify restored neural option after 60 presents");
            std::printf("After 60 presents: %s=%s\n", NeuralKey, resolved.c_str());
            if (_stricmp(resolved.c_str(), original.c_str()) != 0) throw std::runtime_error("original neural option did not resolve");
            needsRestore = false;
        }
        std::puts("Completed 60 Submit/Present frames. This establishes renderer smoke and option acceptance only; fresh runtime logs must establish feature/provider/evaluation success.");
    } catch (const std::exception& error) {
        std::printf("FAIL: %s\n", error.what());
        result = 1;
    }

    if (started) {
        if (needsRestore && !Report(api.SetConfigVariable(NeuralKey, original.c_str()), "Restore neural option during cleanup")) result = 1;
        if (mesh && !Report(api.DestroyMesh(mesh), "DestroyMesh")) result = 1;
        if (material && !Report(api.DestroyMaterial(material), "DestroyMaterial")) result = 1;
        // The runtime subclasses this owned window. Detach it before shutdown.
        if (IsWindow(window)) SetWindowLongPtrW(window, GWLP_WNDPROC, reinterpret_cast<LONG_PTR>(DefWindowProcW));
        if (!Report(api.Shutdown(), "Shutdown")) result = 1;
    }
    if (IsWindow(window)) DestroyWindow(window);
    if (library) FreeLibrary(library);
    if (runtimeDirectory) RemoveDllDirectory(runtimeDirectory);
    return result;
}
