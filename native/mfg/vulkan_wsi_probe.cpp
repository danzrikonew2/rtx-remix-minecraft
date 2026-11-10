// SPDX-License-Identifier: Apache-2.0
// Isolated Vulkan WSI baseline. A successful source-present is NOT FG proof.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <tlhelp32.h>
#include <vulkan/vulkan.h>
#include <nvsdk_ngx_vk.h>

#include <algorithm>
#include <chrono>
#include <cstring>
#include <cstdint>
#include <filesystem>
#include <functional>
#include <iomanip>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace {
using Clock = std::chrono::steady_clock;

// Diagnostic-only observer: never intercepts, handles, or modifies exceptions.
// Snapshot module bases outside the handler so the handler itself only uses
// simple Win32 operations while the vendor's shutdown stack may be damaged.
bool g_traceShutdownAvEnabled = false;
volatile LONG g_traceShutdownActive = 0;
volatile LONG g_shutdownFaultCount = 0;

void AppendFaultText(char*& cursor, const char* value) {
    while (*value) *cursor++ = *value++;
}

void AppendFaultHex(char*& cursor, std::uintptr_t value) {
    *cursor++ = '0';
    *cursor++ = 'x';
    for (int shift = static_cast<int>(sizeof(value) * 8) - 4; shift >= 0; shift -= 4) {
        const unsigned nibble = static_cast<unsigned>((value >> shift) & 0xF);
        *cursor++ = "0123456789ABCDEF"[nibble];
    }
}

LONG CALLBACK ShutdownAccessViolationObserver(EXCEPTION_POINTERS* exception) {
    if (!exception || !exception->ExceptionRecord ||
        exception->ExceptionRecord->ExceptionCode != EXCEPTION_ACCESS_VIOLATION ||
        InterlockedCompareExchange(&g_traceShutdownActive, 0, 0) != 1)
        return EXCEPTION_CONTINUE_SEARCH;
    const LONG occurrence = InterlockedIncrement(&g_shutdownFaultCount);
    if (occurrence > 4) return EXCEPTION_CONTINUE_SEARCH;

    const EXCEPTION_RECORD* record = exception->ExceptionRecord;
    MEMORY_BASIC_INFORMATION memory{};
    const bool mapped = VirtualQuery(record->ExceptionAddress, &memory, sizeof(memory)) != 0;
    char line[512]{};
    char* out = line;
    AppendFaultText(out, "shutdown_av_first_chance=1 occurrence=");
    AppendFaultHex(out, static_cast<std::uintptr_t>(occurrence));
    AppendFaultText(out, " tid=");
    AppendFaultHex(out, static_cast<std::uintptr_t>(GetCurrentThreadId()));
    AppendFaultText(out, " instruction=");
    AppendFaultHex(out, reinterpret_cast<std::uintptr_t>(record->ExceptionAddress));
    AppendFaultText(out, " module_base=");
    AppendFaultHex(out, mapped ? reinterpret_cast<std::uintptr_t>(memory.AllocationBase) : 0);
    AppendFaultText(out, " module_type=");
    AppendFaultHex(out, mapped ? static_cast<std::uintptr_t>(memory.Type) : 0);
    AppendFaultText(out, " access_kind=");
    AppendFaultHex(out, record->NumberParameters >= 1 ? record->ExceptionInformation[0] : 0);
    AppendFaultText(out, " access_address=");
    AppendFaultHex(out, record->NumberParameters >= 2 ? record->ExceptionInformation[1] : 0);
    AppendFaultText(out, " observer_does_not_handle=1\r\n");
    DWORD written = 0;
    WriteFile(GetStdHandle(STD_ERROR_HANDLE), line,
              static_cast<DWORD>(out - line), &written, nullptr);
    return EXCEPTION_CONTINUE_SEARCH;
}

void BeginNgxShutdownAvTrace() {
    if (!g_traceShutdownAvEnabled) return;
    HANDLE modules = INVALID_HANDLE_VALUE;
    for (int attempt = 0; attempt < 3; ++attempt) {
        modules = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32,
                                          GetCurrentProcessId());
        if (modules != INVALID_HANDLE_VALUE || GetLastError() != ERROR_BAD_LENGTH) break;
    }
    if (modules == INVALID_HANDLE_VALUE) {
        std::cout << "shutdown_module_snapshot_error=" << GetLastError() << '\n';
    } else {
        MODULEENTRY32W entry{};
        entry.dwSize = sizeof(entry);
        if (Module32FirstW(modules, &entry)) {
            do {
                char name[1024]{};
                char path[2048]{};
                WideCharToMultiByte(CP_UTF8, 0, entry.szModule, -1,
                                    name, static_cast<int>(sizeof(name)), nullptr, nullptr);
                WideCharToMultiByte(CP_UTF8, 0, entry.szExePath, -1,
                                    path, static_cast<int>(sizeof(path)), nullptr, nullptr);
                std::cout << "shutdown_module base=0x" << std::hex
                          << reinterpret_cast<std::uintptr_t>(entry.modBaseAddr)
                          << std::dec << " size=" << entry.modBaseSize
                          << " name=" << name << " path=" << path << '\n';
            } while (Module32NextW(modules, &entry));
        } else {
            std::cout << "shutdown_module_first_error=" << GetLastError() << '\n';
        }
        CloseHandle(modules);
    }
    InterlockedExchange(&g_shutdownFaultCount, 0);
    InterlockedExchange(&g_traceShutdownActive, 1);
    std::cout << "stage=shutdown_av_observer_armed first_chance_only=1\n";
}

void EndNgxShutdownAvTrace() {
    if (!g_traceShutdownAvEnabled) return;
    InterlockedExchange(&g_traceShutdownActive, 0);
    std::cout << "stage=shutdown_av_observer_disarmed\n";
}

void Check(VkResult result, const char* stage) {
    if (result != VK_SUCCESS)
        throw std::runtime_error(std::string(stage) + " VkResult=" + std::to_string(result));
}

LRESULT CALLBACK WindowProc(HWND hwnd, UINT message, WPARAM wparam, LPARAM lparam) {
    if (message == WM_CLOSE) { DestroyWindow(hwnd); return 0; }
    return DefWindowProcW(hwnd, message, wparam, lparam);
}

bool HasExtension(VkPhysicalDevice gpu, const char* name) {
    uint32_t count = 0;
    Check(vkEnumerateDeviceExtensionProperties(gpu, nullptr, &count, nullptr), "enumerate_device_extensions_count");
    std::vector<VkExtensionProperties> values(count);
    Check(vkEnumerateDeviceExtensionProperties(gpu, nullptr, &count, values.data()), "enumerate_device_extensions");
    for (const auto& ext : values) if (std::string(ext.extensionName) == name) return true;
    return false;
}

struct Wsi {
    bool verifySync2 = false;
    PFN_vkCmdPipelineBarrier2KHR cmdPipelineBarrier2 = nullptr;
    HINSTANCE application = GetModuleHandleW(nullptr);
    HWND window = nullptr;
    VkInstance instance = VK_NULL_HANDLE;
    VkPhysicalDevice gpu = VK_NULL_HANDLE;
    VkSurfaceKHR surface = VK_NULL_HANDLE;
    VkDevice device = VK_NULL_HANDLE;
    VkQueue queue = VK_NULL_HANDLE;
    uint32_t queueFamily = UINT32_MAX;
    VkSwapchainKHR swapchain = VK_NULL_HANDLE;
    VkCommandPool pool = VK_NULL_HANDLE;
    VkCommandBuffer command = VK_NULL_HANDLE;
    VkSemaphore available = VK_NULL_HANDLE;
    std::vector<VkSemaphore> completed;
    VkFence fence = VK_NULL_HANDLE;
    std::vector<VkImage> images;
    std::vector<VkImageLayout> layouts;
    VkExtent2D extent{};
    VkFormat format = VK_FORMAT_UNDEFINED;

    ~Wsi() {
        std::cout << "stage=teardown_begin\n";
        if (device) {
            // The external timeout supervisor handles hangs in driver/provider teardown.
            std::cout << "stage=teardown_wait_idle_begin\n";
            vkDeviceWaitIdle(device);
            std::cout << "stage=teardown_wait_idle_end\n";
            if (fence) vkDestroyFence(device, fence, nullptr);
            if (available) vkDestroySemaphore(device, available, nullptr);
            for (auto sem : completed) if (sem) vkDestroySemaphore(device, sem, nullptr);
            if (pool) vkDestroyCommandPool(device, pool, nullptr);
            if (swapchain) {
                std::cout << "stage=teardown_swapchain_begin\n";
                vkDestroySwapchainKHR(device, swapchain, nullptr);
                std::cout << "stage=teardown_swapchain_end\n";
            }
            std::cout << "stage=teardown_device_begin\n";
            vkDestroyDevice(device, nullptr);
            std::cout << "stage=teardown_device_end\n";
        }
        if (surface) vkDestroySurfaceKHR(instance, surface, nullptr);
        if (instance) vkDestroyInstance(instance, nullptr);
        std::cout << "stage=teardown_instance_end\n";
        if (window && IsWindow(window)) DestroyWindow(window);
        UnregisterClassW(L"MfgVulkanWsiProbe", application);
    }

    void CreateProbeWindow() {
        WNDCLASSW cls{};
        cls.lpfnWndProc = WindowProc;
        cls.hInstance = application;
        cls.lpszClassName = L"MfgVulkanWsiProbe";
        if (!RegisterClassW(&cls)) throw std::runtime_error("register_window_class");
        window = CreateWindowExW(WS_EX_NOACTIVATE, cls.lpszClassName,
            L"MFG Vulkan WSI source frames (FG unverified)",
            WS_OVERLAPPEDWINDOW, CW_USEDEFAULT, CW_USEDEFAULT, 720, 440,
            nullptr, nullptr, application, nullptr);
        if (!window) throw std::runtime_error("create_window");
        ShowWindow(window, SW_SHOWNOACTIVATE); // Never steal foreground focus.
        UpdateWindow(window);
        std::cout << "stage=win32_window_created hwnd=" << window << '\n';
    }

    void InitVulkan() {
        const char* instanceExtensions[] = { VK_KHR_SURFACE_EXTENSION_NAME, VK_KHR_WIN32_SURFACE_EXTENSION_NAME };
        VkApplicationInfo app{VK_STRUCTURE_TYPE_APPLICATION_INFO};
        app.pApplicationName = "MfgVulkanWsiProbe";
        app.apiVersion = VK_API_VERSION_1_2;
        VkInstanceCreateInfo createInstance{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
        createInstance.pApplicationInfo = &app;
        createInstance.enabledExtensionCount = 2;
        createInstance.ppEnabledExtensionNames = instanceExtensions;
        Check(vkCreateInstance(&createInstance, nullptr, &instance), "vkCreateInstance");
        std::cout << "stage=vulkan_instance_created\n";

        VkWin32SurfaceCreateInfoKHR surfaceCreate{VK_STRUCTURE_TYPE_WIN32_SURFACE_CREATE_INFO_KHR};
        surfaceCreate.hinstance = application;
        surfaceCreate.hwnd = window;
        Check(vkCreateWin32SurfaceKHR(instance, &surfaceCreate, nullptr, &surface), "vkCreateWin32SurfaceKHR");

        uint32_t count = 0;
        Check(vkEnumeratePhysicalDevices(instance, &count, nullptr), "enumerate_gpus_count");
        if (!count) throw std::runtime_error("no_vulkan_physical_devices");
        std::vector<VkPhysicalDevice> gpus(count);
        Check(vkEnumeratePhysicalDevices(instance, &count, gpus.data()), "enumerate_gpus");
        for (auto candidate : gpus) {
            VkPhysicalDeviceProperties properties{};
            vkGetPhysicalDeviceProperties(candidate, &properties);
            std::cout << "gpu_candidate=" << properties.deviceName << " vendor=0x" << std::hex
                      << properties.vendorID << " device=0x" << properties.deviceID << std::dec << '\n';
            if (properties.vendorID == 0x10de && properties.deviceID == 0x2482) {
                gpu = candidate;
                break;
            }
        }
        if (!gpu) throw std::runtime_error("RTX_3070_Ti_not_found_abort_automatic_fallback");
        if (!HasExtension(gpu, VK_KHR_SWAPCHAIN_EXTENSION_NAME))
            throw std::runtime_error("no_VK_KHR_swapchain");

        uint32_t familiesCount = 0;
        vkGetPhysicalDeviceQueueFamilyProperties(gpu, &familiesCount, nullptr);
        std::vector<VkQueueFamilyProperties> families(familiesCount);
        vkGetPhysicalDeviceQueueFamilyProperties(gpu, &familiesCount, families.data());
        for (uint32_t i = 0; i < familiesCount; ++i) {
            VkBool32 present = VK_FALSE;
            Check(vkGetPhysicalDeviceSurfaceSupportKHR(gpu, i, surface, &present), "query_present_support");
            std::cout << "queue_family=" << i << " count=" << families[i].queueCount
                      << " flags=" << families[i].queueFlags << " present=" << present << '\n';
            if (queueFamily == UINT32_MAX && (families[i].queueFlags & VK_QUEUE_GRAPHICS_BIT) && present)
                queueFamily = i;
        }
        if (queueFamily == UINT32_MAX) throw std::runtime_error("no_graphics_present_queue");

        const bool sync2Extension = HasExtension(gpu, VK_KHR_SYNCHRONIZATION_2_EXTENSION_NAME);
        VkPhysicalDeviceSynchronization2FeaturesKHR supportedSync2{
            VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SYNCHRONIZATION_2_FEATURES_KHR};
        VkPhysicalDeviceVulkan12Features supported12{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_2_FEATURES};
        supported12.pNext = &supportedSync2;
        VkPhysicalDeviceFeatures2 supported{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2};
        supported.pNext = &supported12;
        vkGetPhysicalDeviceFeatures2(gpu, &supported);
        std::cout << "timelineSemaphore=" << supported12.timelineSemaphore
                  << " descriptorIndexing=" << supported12.descriptorIndexing
                  << " pushDescriptor=" << HasExtension(gpu, VK_KHR_PUSH_DESCRIPTOR_EXTENSION_NAME) << '\n';
        std::cout << "sync2_extension_supported=" << sync2Extension
                  << " sync2_feature_supported=" << supportedSync2.synchronization2
                  << " sync2_explicitly_requested=" << verifySync2
                  << " instance_api=1.2\n";
        if (verifySync2 && (!sync2Extension || supportedSync2.synchronization2 != VK_TRUE))
            throw std::runtime_error("synchronization2_unsupported_on_selected_gpu");

        VkPhysicalDeviceVulkan12Features enable12{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_2_FEATURES};
        enable12.timelineSemaphore = supported12.timelineSemaphore;
        enable12.descriptorIndexing = supported12.descriptorIndexing;
        VkPhysicalDeviceSynchronization2FeaturesKHR enableSync2{
            VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_SYNCHRONIZATION_2_FEATURES_KHR};
        if (verifySync2) {
            enableSync2.synchronization2 = VK_TRUE;
            enable12.pNext = &enableSync2;
        }
        float priority = 1.0f;
        VkDeviceQueueCreateInfo queueCreate{VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO};
        queueCreate.queueFamilyIndex = queueFamily;
        queueCreate.queueCount = 1; // Reserve the remaining queues for the FG provider.
        queueCreate.pQueuePriorities = &priority;
        std::vector<const char*> extensions{VK_KHR_SWAPCHAIN_EXTENSION_NAME};
        if (HasExtension(gpu, VK_KHR_PUSH_DESCRIPTOR_EXTENSION_NAME))
            extensions.push_back(VK_KHR_PUSH_DESCRIPTOR_EXTENSION_NAME);
        if (verifySync2)
            extensions.push_back(VK_KHR_SYNCHRONIZATION_2_EXTENSION_NAME);
        VkDeviceCreateInfo deviceCreate{VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO};
        deviceCreate.pNext = &enable12;
        deviceCreate.queueCreateInfoCount = 1;
        deviceCreate.pQueueCreateInfos = &queueCreate;
        deviceCreate.enabledExtensionCount = static_cast<uint32_t>(extensions.size());
        deviceCreate.ppEnabledExtensionNames = extensions.data();
        Check(vkCreateDevice(gpu, &deviceCreate, nullptr, &device), "vkCreateDevice");
        if (verifySync2) {
            cmdPipelineBarrier2 = reinterpret_cast<PFN_vkCmdPipelineBarrier2KHR>(
                vkGetDeviceProcAddr(device, "vkCmdPipelineBarrier2KHR"));
            if (!cmdPipelineBarrier2)
                throw std::runtime_error("vkCmdPipelineBarrier2KHR_unavailable_after_enable");
            std::cout << "stage=sync2_device_feature_enabled command_resolved=1\n";
        }
        vkGetDeviceQueue(device, queueFamily, 0, &queue);
        if (!queue) throw std::runtime_error("vkGetDeviceQueue_null");
        std::cout << "stage=vulkan_device_created\n";

        VkSurfaceCapabilitiesKHR capabilities{};
        std::cout << "stage=surface_capabilities_begin\n";
        Check(vkGetPhysicalDeviceSurfaceCapabilitiesKHR(gpu, surface, &capabilities), "surface_capabilities");
        std::cout << "stage=surface_capabilities_end\n";
        if (!(capabilities.supportedUsageFlags & VK_IMAGE_USAGE_TRANSFER_DST_BIT))
            throw std::runtime_error("surface_does_not_support_transfer_dst");
        uint32_t formatCount = 0;
        Check(vkGetPhysicalDeviceSurfaceFormatsKHR(gpu, surface, &formatCount, nullptr), "surface_formats_count");
        std::vector<VkSurfaceFormatKHR> formats(formatCount);
        if (!formatCount) throw std::runtime_error("surface_has_no_formats");
        Check(vkGetPhysicalDeviceSurfaceFormatsKHR(gpu, surface, &formatCount, formats.data()), "surface_formats");
        auto chosen = formats.front();
        for (const auto& candidate : formats)
            if (candidate.format == VK_FORMAT_B8G8R8A8_UNORM && candidate.colorSpace == VK_COLOR_SPACE_SRGB_NONLINEAR_KHR)
                chosen = candidate;
        format = chosen.format;
        extent = capabilities.currentExtent;
        if (extent.width == UINT32_MAX) {
            extent.width = std::clamp(640u, capabilities.minImageExtent.width, capabilities.maxImageExtent.width);
            extent.height = std::clamp(360u, capabilities.minImageExtent.height, capabilities.maxImageExtent.height);
        }
        uint32_t imageCount = std::max(2u, capabilities.minImageCount + 1);
        if (capabilities.maxImageCount) imageCount = std::min(imageCount, capabilities.maxImageCount);
        VkSwapchainCreateInfoKHR swapCreate{VK_STRUCTURE_TYPE_SWAPCHAIN_CREATE_INFO_KHR};
        swapCreate.surface = surface;
        swapCreate.minImageCount = imageCount;
        swapCreate.imageFormat = format;
        swapCreate.imageColorSpace = chosen.colorSpace;
        swapCreate.imageExtent = extent;
        swapCreate.imageArrayLayers = 1;
        swapCreate.imageUsage = VK_IMAGE_USAGE_TRANSFER_DST_BIT | (capabilities.supportedUsageFlags & VK_IMAGE_USAGE_TRANSFER_SRC_BIT);
        swapCreate.imageSharingMode = VK_SHARING_MODE_EXCLUSIVE;
        swapCreate.preTransform = capabilities.currentTransform;
        swapCreate.compositeAlpha = (capabilities.supportedCompositeAlpha & VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR)
            ? VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR : VK_COMPOSITE_ALPHA_INHERIT_BIT_KHR;
        swapCreate.presentMode = VK_PRESENT_MODE_FIFO_KHR;
        swapCreate.clipped = VK_TRUE;
        std::cout << "stage=swapchain_create_begin\n";
        Check(vkCreateSwapchainKHR(device, &swapCreate, nullptr, &swapchain), "vkCreateSwapchainKHR");
        std::cout << "stage=swapchain_create_end\n";
        Check(vkGetSwapchainImagesKHR(device, swapchain, &imageCount, nullptr), "swap_images_count");
        images.resize(imageCount);
        Check(vkGetSwapchainImagesKHR(device, swapchain, &imageCount, images.data()), "swap_images");
        layouts.resize(imageCount, VK_IMAGE_LAYOUT_UNDEFINED);
        completed.resize(imageCount);
        std::cout << "stage=vulkan_swapchain_created width=" << extent.width << " height=" << extent.height
                  << " images=" << imageCount << " format=" << format << '\n';

        VkCommandPoolCreateInfo poolCreate{VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO};
        poolCreate.queueFamilyIndex = queueFamily;
        poolCreate.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;
        Check(vkCreateCommandPool(device, &poolCreate, nullptr, &pool), "create_command_pool");
        VkCommandBufferAllocateInfo allocation{VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO};
        allocation.commandPool = pool;
        allocation.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
        allocation.commandBufferCount = 1;
        Check(vkAllocateCommandBuffers(device, &allocation, &command), "allocate_command_buffer");
        VkSemaphoreCreateInfo semaphoreInfo{VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO};
        Check(vkCreateSemaphore(device, &semaphoreInfo, nullptr, &available), "create_available_semaphore");
        for (auto& sem : completed)
            Check(vkCreateSemaphore(device, &semaphoreInfo, nullptr, &sem), "create_completed_semaphore");
        VkFenceCreateInfo fenceInfo{VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};
        fenceInfo.flags = VK_FENCE_CREATE_SIGNALED_BIT;
        Check(vkCreateFence(device, &fenceInfo, nullptr, &fence), "create_fence");
        std::cout << "stage=wsi_ready\n";
    }

    void PresentFrame(uint32_t seq, const std::function<void(VkCommandBuffer, VkImage)>& render = {}) {
        Check(vkWaitForFences(device, 1, &fence, VK_TRUE, 2'000'000'000ull), "wait_render_fence");
        uint32_t index = 0;
        Check(vkAcquireNextImageKHR(device, swapchain, 2'000'000'000ull, available,
                                    VK_NULL_HANDLE, &index), "acquire_next_image");
        Check(vkResetFences(device, 1, &fence), "reset_fence");
        Check(vkResetCommandBuffer(command, 0), "reset_command_buffer");
        VkCommandBufferBeginInfo begin{VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};
        Check(vkBeginCommandBuffer(command, &begin), "begin_commands");
        VkImageMemoryBarrier toTransfer{VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER};
        toTransfer.oldLayout = layouts[index];
        toTransfer.newLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
        toTransfer.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        toTransfer.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        toTransfer.image = images[index];
        toTransfer.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
        toTransfer.dstAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
        if (verifySync2) {
            VkImageMemoryBarrier2KHR imageBarrier{VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER_2_KHR};
            imageBarrier.srcStageMask = VK_PIPELINE_STAGE_2_TOP_OF_PIPE_BIT_KHR;
            imageBarrier.dstStageMask = VK_PIPELINE_STAGE_2_TRANSFER_BIT_KHR;
            imageBarrier.dstAccessMask = VK_ACCESS_2_TRANSFER_WRITE_BIT_KHR;
            imageBarrier.oldLayout = toTransfer.oldLayout;
            imageBarrier.newLayout = toTransfer.newLayout;
            imageBarrier.srcQueueFamilyIndex = toTransfer.srcQueueFamilyIndex;
            imageBarrier.dstQueueFamilyIndex = toTransfer.dstQueueFamilyIndex;
            imageBarrier.image = toTransfer.image;
            imageBarrier.subresourceRange = toTransfer.subresourceRange;
            VkDependencyInfoKHR dependency{VK_STRUCTURE_TYPE_DEPENDENCY_INFO_KHR};
            dependency.imageMemoryBarrierCount = 1;
            dependency.pImageMemoryBarriers = &imageBarrier;
            cmdPipelineBarrier2(command, &dependency);
        } else {
            vkCmdPipelineBarrier(command, VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT,
                                 0, 0, nullptr, 0, nullptr, 1, &toTransfer);
        }
        VkImageSubresourceRange subresource{VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
        if (render) {
            render(command, images[index]);
        } else {
            // Source-only baseline. This color variation is never counted as FG.
            const float red = static_cast<float>((seq * 17u) % 251u) / 250.0f;
            const float green = static_cast<float>((seq * 43u) % 251u) / 250.0f;
            const float blue = static_cast<float>((seq * 79u) % 251u) / 250.0f;
            VkClearColorValue color{{red, green, blue, 1.0f}};
            vkCmdClearColorImage(command, images[index], VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
                                 &color, 1, &subresource);
        }
        VkImageMemoryBarrier toPresent{VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER};
        toPresent.oldLayout = VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL;
        toPresent.newLayout = VK_IMAGE_LAYOUT_PRESENT_SRC_KHR;
        toPresent.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        toPresent.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        toPresent.image = images[index];
        toPresent.subresourceRange = subresource;
        toPresent.srcAccessMask = VK_ACCESS_TRANSFER_WRITE_BIT;
        if (verifySync2) {
            VkImageMemoryBarrier2KHR imageBarrier{VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER_2_KHR};
            imageBarrier.srcStageMask = VK_PIPELINE_STAGE_2_TRANSFER_BIT_KHR;
            imageBarrier.srcAccessMask = VK_ACCESS_2_TRANSFER_WRITE_BIT_KHR;
            imageBarrier.dstStageMask = VK_PIPELINE_STAGE_2_BOTTOM_OF_PIPE_BIT_KHR;
            imageBarrier.oldLayout = toPresent.oldLayout;
            imageBarrier.newLayout = toPresent.newLayout;
            imageBarrier.srcQueueFamilyIndex = toPresent.srcQueueFamilyIndex;
            imageBarrier.dstQueueFamilyIndex = toPresent.dstQueueFamilyIndex;
            imageBarrier.image = toPresent.image;
            imageBarrier.subresourceRange = toPresent.subresourceRange;
            VkDependencyInfoKHR dependency{VK_STRUCTURE_TYPE_DEPENDENCY_INFO_KHR};
            dependency.imageMemoryBarrierCount = 1;
            dependency.pImageMemoryBarriers = &imageBarrier;
            cmdPipelineBarrier2(command, &dependency);
        } else {
            vkCmdPipelineBarrier(command, VK_PIPELINE_STAGE_TRANSFER_BIT, VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT,
                                 0, 0, nullptr, 0, nullptr, 1, &toPresent);
        }
        Check(vkEndCommandBuffer(command), "end_commands");
        VkPipelineStageFlags waitStage = VK_PIPELINE_STAGE_TRANSFER_BIT;
        VkSubmitInfo submit{VK_STRUCTURE_TYPE_SUBMIT_INFO};
        submit.waitSemaphoreCount = 1;
        submit.pWaitSemaphores = &available;
        submit.pWaitDstStageMask = &waitStage;
        submit.commandBufferCount = 1;
        submit.pCommandBuffers = &command;
        submit.signalSemaphoreCount = 1;
        submit.pSignalSemaphores = &completed[index];
        Check(vkQueueSubmit(queue, 1, &submit, fence), "vkQueueSubmit");
        VkPresentInfoKHR present{VK_STRUCTURE_TYPE_PRESENT_INFO_KHR};
        present.waitSemaphoreCount = 1;
        present.pWaitSemaphores = &completed[index];
        present.swapchainCount = 1;
        present.pSwapchains = &swapchain;
        present.pImageIndices = &index;
        Check(vkQueuePresentKHR(queue, &present), "vkQueuePresentKHR");
        layouts[index] = VK_IMAGE_LAYOUT_PRESENT_SRC_KHR;
    }
};

#include "ngx_vulkan_fixture.h"

} // namespace

int wmain(int argc, wchar_t** argv) {
    bool skipVendorDetach = false;
    try {
        std::filesystem::path optiscaler;
        int frames = 120;
        int interval = 16;
        bool ngxEvaluate = false;
        bool ngxInitOnly = false;
        bool verifySync2 = false;
        bool traceShutdownAv = false;
        NgxFixture::ShutdownMode ngxShutdownMode = NgxFixture::ShutdownMode::Device;
        for (int i = 1; i < argc; ++i) {
            const std::wstring key = argv[i];
            if (key == L"--optiscaler" && i + 1 < argc) optiscaler = argv[++i];
            else if (key == L"--frames" && i + 1 < argc) frames = std::stoi(argv[++i]);
            else if (key == L"--interval-ms" && i + 1 < argc) interval = std::stoi(argv[++i]);
            else if (key == L"--ngx-evaluate") ngxEvaluate = true;
            else if (key == L"--ngx-init-only") ngxInitOnly = true;
            else if (key == L"--verify-sync2") verifySync2 = true;
            else if (key == L"--ngx-shutdown-mode" && i + 1 < argc) {
                const std::wstring mode = argv[++i];
                if (mode == L"device") ngxShutdownMode = NgxFixture::ShutdownMode::Device;
                else if (mode == L"plain") ngxShutdownMode = NgxFixture::ShutdownMode::Plain;
                else if (mode == L"skip") ngxShutdownMode = NgxFixture::ShutdownMode::Skip;
                else throw std::runtime_error("invalid_ngx_shutdown_mode");
            }
            else if (key == L"--skip-vendor-detach") skipVendorDetach = true;
            else if (key == L"--trace-ngx-shutdown-av") traceShutdownAv = true;
            else throw std::runtime_error("usage: MfgVulkanWsiProbe [--optiscaler ABSOLUTE_DLL_PATH] [--ngx-evaluate|--ngx-init-only] [--verify-sync2] [--ngx-shutdown-mode device|plain|skip] [--skip-vendor-detach] [--trace-ngx-shutdown-av] [--frames 1..1000] [--interval-ms 0..100]");
        }
        if (frames < 1 || frames > 1000 || interval < 0 || interval > 100)
            throw std::runtime_error("invalid_frames_or_interval");
        if (ngxEvaluate && optiscaler.empty())
            throw std::runtime_error("ngx_evaluate_requires_optiscaler");
        if (ngxInitOnly && (ngxEvaluate || optiscaler.empty() || !skipVendorDetach ||
                            ngxShutdownMode == NgxFixture::ShutdownMode::Skip))
            throw std::runtime_error("ngx_init_only_requires_optiscaler_skip_vendor_detach_and_non_skipped_shutdown_without_evaluate");
        if (skipVendorDetach && optiscaler.empty())
            throw std::runtime_error("skip_vendor_detach_requires_optiscaler");
        if (ngxShutdownMode != NgxFixture::ShutdownMode::Device &&
            (!(ngxEvaluate || ngxInitOnly) || !skipVendorDetach))
            throw std::runtime_error("diagnostic_ngx_shutdown_mode_requires_ngx_stimulus_and_skip_vendor_detach");
        if (traceShutdownAv && (!(ngxEvaluate || ngxInitOnly) || !skipVendorDetach ||
                                ngxShutdownMode != NgxFixture::ShutdownMode::Device))
            throw std::runtime_error("shutdown_av_trace_requires_device_mode_ngx_stimulus_and_skip_vendor_detach");
        std::cout.setf(std::ios::unitbuf);
        if (traceShutdownAv) {
            if (!AddVectoredExceptionHandler(1, ShutdownAccessViolationObserver))
                throw std::runtime_error("shutdown_av_handler_registration_failed");
            g_traceShutdownAvEnabled = true;
            std::cout << "stage=shutdown_av_observer_registered mode=diagnostic_only\n";
        }
        std::cout << "probe=real_win32_vulkan_wsi source_present_only=" << !ngxEvaluate
                  << " ngx_evaluate=" << ngxEvaluate << " ngx_init_only=" << ngxInitOnly
                  << " verify_sync2=" << verifySync2 << " fg_proven=0\n";
        HMODULE opti = nullptr;
        if (!optiscaler.empty()) {
            if (!optiscaler.is_absolute() || !std::filesystem::is_regular_file(optiscaler))
                throw std::runtime_error("optiscaler_requires_existing_absolute_path");
            if (!GetModuleHandleW(L"vulkan-1.dll") && !LoadLibraryW(L"vulkan-1.dll"))
                throw std::runtime_error("vulkan_loader_missing");
            opti = LoadLibraryW(optiscaler.c_str());
            if (!opti) throw std::runtime_error("LoadLibraryW_OptiScaler_failed=" + std::to_string(GetLastError()));
            for (const char* entry : {"NVSDK_NGX_VULKAN_Init_Ext2", "NVSDK_NGX_VULKAN_CreateFeature1",
                                      "NVSDK_NGX_VULKAN_EvaluateFeature"})
                if (!GetProcAddress(opti, entry)) throw std::runtime_error(std::string("missing_NGX_export_") + entry);
            std::cout << "stage=optiscaler_loaded ngx_exports_present=1\n";
        }
        {
            Wsi wsi;
            wsi.verifySync2 = verifySync2;
            wsi.CreateProbeWindow();
            wsi.InitVulkan();
            std::unique_ptr<NgxFixture> ngx;
            if (ngxEvaluate || ngxInitOnly) {
                ngx = std::make_unique<NgxFixture>(wsi, opti, ngxShutdownMode);
                ngx->Initialize(ngxInitOnly);
            }
            const auto started = Clock::now();
            std::cout << "csv=seq,elapsed_ms,source_present_result\n";
            for (int seq = 0; seq < frames; ++seq) {
                MSG message{};
                while (PeekMessageW(&message, nullptr, 0, 0, PM_REMOVE)) {
                    if (message.message == WM_QUIT) throw std::runtime_error("window_closed");
                    TranslateMessage(&message);
                    DispatchMessageW(&message);
                }
                if (!IsWindow(wsi.window)) throw std::runtime_error("window_closed");
                if (ngx && !ngxInitOnly)
                    wsi.PresentFrame(static_cast<uint32_t>(seq),
                        [&](VkCommandBuffer cmd, VkImage image) { ngx->Render(static_cast<uint32_t>(seq), cmd, image); });
                else
                    wsi.PresentFrame(static_cast<uint32_t>(seq));
                auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now() - started).count();
                std::cout << "frame=" << seq << ',' << elapsed << ",VK_SUCCESS\n";
                if (interval) std::this_thread::sleep_for(std::chrono::milliseconds(interval));
            }
            if (ngxEvaluate && ngx) {
                std::cout << "ngx_evaluations_completed=" << ngx->evaluated << '\n';
                if (ngx->evaluated != static_cast<uint32_t>(frames))
                    throw std::runtime_error("ngx_evaluation_count_mismatch");
            }
        }
        // Intentionally retain loaded OptiScaler until process exit to avoid
        // tearing down detoured Vulkan function pointers during static cleanup.
        const bool skippedShutdown = ngxShutdownMode == NgxFixture::ShutdownMode::Skip;
        std::cout << "result=" << (ngxInitOnly ? "NGX_INIT_ONLY_SOURCE_PRESENT_PASS" :
                  ngxEvaluate ? (skippedShutdown ? "NGX_EVALUATE_PRESENT_SHUTDOWN_SKIPPED" : "NGX_EVALUATE_PRESENT_PASS") : "SOURCE_PRESENT_PASS")
                  << " fg_proven=0 generated_frames_verified=0 sync2_exercised=" << verifySync2
                  << " clean_shutdown_proven=" << !skippedShutdown << '\n';
        if (skipVendorDetach) {
            // The vendor's DLL_PROCESS_DETACH may deadlock after the last
            // vkDestroyInstance, even when all source frames were presented.
            // Only use this opt-in escape hatch AFTER both RAII destructors
            // have completely destroyed NGX and Vulkan objects. This is a
            // disposable dedicated probe process; never use in Minecraft.
            std::cout << "stage=isolated_post_teardown_terminate skip_vendor_detach=1\n";
            std::cout.flush();
            std::cerr.flush();
            if (!TerminateProcess(GetCurrentProcess(), 0))
                throw std::runtime_error("post_teardown_terminate_failed=" + std::to_string(GetLastError()));
        }
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "result=FAIL stage=" << e.what() << " fg_proven=0\n";
        if (skipVendorDetach) {
            // Skip third-party DLL detach only after stack unwinding has
            // destroyed all locally owned Vulkan/NGX objects. Preserve the
            // failure exit code for the external bounded-run supervisor.
            std::cerr << "stage=isolated_failure_post_teardown_terminate skip_vendor_detach=1\n";
            std::cout.flush();
            std::cerr.flush();
            if (!TerminateProcess(GetCurrentProcess(), 1))
                std::cerr << "stage=post_teardown_terminate_failed win32=" << GetLastError() << '\n';
        }
        return 1;
    }
}
