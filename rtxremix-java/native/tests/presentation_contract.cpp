/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */

// Exercise the production JNI entry points with a recording C API. No JVM,
// runtime DLL, window or GPU is needed for these marshalling contracts.
#include "../remixbridge.cpp"
#include <cstdlib>

static remixapi_StartupInfo startupInfo;
static remixapi_PresentInfo presentInfo;
static int startupCalls = 0;
static int presentCalls = 0;

static void require(bool condition, const char* message) {
    if (!condition) {
        fprintf(stderr, "FAIL: %s\n", message);
        std::exit(1);
    }
}

static remixapi_ErrorCode REMIXAPI_CALL recordStartup(const remixapi_StartupInfo* info) {
    require(info != nullptr, "Startup must receive a structure");
    startupInfo = *info;
    ++startupCalls;
    return REMIXAPI_ERROR_CODE_INVALID_ARGUMENTS;
}

static remixapi_ErrorCode REMIXAPI_CALL recordPresent(const remixapi_PresentInfo* info) {
    require(info != nullptr, "Present must preserve interop arguments even with a zero HWND");
    presentInfo = *info;
    ++presentCalls;
    return REMIXAPI_ERROR_CODE_INVALID_ARGUMENTS;
}

int main() {
    g_remix = {};
    g_remix.Startup = recordStartup;
    g_remix.Present = recordPresent;
    require(Java_com_nvidia_rtxremix_RemixBridge_startup(
        nullptr, nullptr, 0, false, false, false, false, false, false)
        == REMIXAPI_ERROR_CODE_NOT_INITIALIZED, "Startup rejects an uninitialized bridge");
    require(Java_com_nvidia_rtxremix_RemixBridge_present(
        nullptr, nullptr, 0, 0, 0, 0, 0)
        == REMIXAPI_ERROR_CODE_NOT_INITIALIZED, "Present rejects an uninitialized bridge");
    require(startupCalls == 0 && presentCalls == 0, "Uninitialized calls must not enter the runtime");

    g_inited = true;
    const jlong hwnd = 0x123456789ABC;
    for (int mask = 0; mask < 64; ++mask) {
        const jint result = Java_com_nvidia_rtxremix_RemixBridge_startup(
            nullptr, nullptr, hwnd, (mask & 1) != 0, (mask & 2) != 0,
            (mask & 4) != 0, (mask & 8) != 0, (mask & 16) != 0, (mask & 32) != 0);
        require(result == REMIXAPI_ERROR_CODE_INVALID_ARGUMENTS, "Startup propagates runtime errors");
        require(startupInfo.sType == REMIXAPI_STRUCT_TYPE_STARTUP_INFO && startupInfo.pNext == nullptr,
                "Startup structure header");
        require((uintptr_t)startupInfo.hwnd == (uintptr_t)hwnd, "Startup preserves a 64-bit HWND");
        require(startupInfo.disableSrgbConversionForOutput == ((mask & 1) != 0), "Startup sRGB flag");
        require(startupInfo.forceNoVkSwapchain == ((mask & 2) != 0), "Startup swapchain flag");
        require(startupInfo.editorModeEnabled == ((mask & 4) != 0), "Startup editor flag");
        require(startupInfo.combineGuiInFinalColor == ((mask & 8) != 0), "Startup GUI flag");
        require(startupInfo.interopImage == ((mask & 16) != 0), "Startup interop flag");
        require(startupInfo.useRemixOwnedChildWindow == ((mask & 32) != 0), "Startup child-window ABI tail");
    }

    const jlong timeline = 0x123456789ABCDEF;
    for (jlong window : {jlong(0), hwnd}) {
        for (int mask = 0; mask < 8; ++mask) {
            const jint result = Java_com_nvidia_rtxremix_RemixBridge_present(
                nullptr, nullptr, window, (mask & 1) != 0, (mask & 2) != 0,
                timeline, (mask & 4) != 0);
            require(result == REMIXAPI_ERROR_CODE_INVALID_ARGUMENTS, "Present propagates runtime errors");
            require(presentInfo.sType == REMIXAPI_STRUCT_TYPE_PRESENT_INFO && presentInfo.pNext == nullptr,
                    "Present structure header");
            require((uintptr_t)presentInfo.hwndOverride == (uintptr_t)window, "Present preserves HWND");
            require(presentInfo.skipVulkanSwapchain == ((mask & 1) != 0), "Present swapchain flag");
            require(presentInfo.interopFlipY == ((mask & 2) != 0), "Present image orientation");
            require(presentInfo.clientDoneSemaphore_ValueToWait == (uint64_t)timeline,
                    "Present preserves the 64-bit external timeline value");
            require(presentInfo.disableCpuWaitForExternalSemaphores == ((mask & 4) != 0),
                    "Present preserves external semaphore wait policy");
        }
    }
    require(startupCalls == 64 && presentCalls == 16, "All flag combinations reached the runtime");
    g_remix = {};
    require(Java_com_nvidia_rtxremix_RemixBridge_startup(
        nullptr, nullptr, 0, false, false, false, false, false, false)
        == REMIXAPI_ERROR_CODE_NOT_INITIALIZED, "Startup rejects a missing entry point");
    require(Java_com_nvidia_rtxremix_RemixBridge_present(
        nullptr, nullptr, 0, 0, 0, 0, 0)
        == REMIXAPI_ERROR_CODE_NOT_INITIALIZED, "Present rejects a missing entry point");
    puts("PASS: native startup/present marshalling (80 combinations plus lifecycle guards)");
    return 0;
}
