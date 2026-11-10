// SPDX-License-Identifier: Apache-2.0
// Included after Wsi in vulkan_wsi_probe.cpp. Opt-in NGX upscaling stimulus:
// source images, depth and pixel-space motion vectors. This is NOT an FG verifier.
#pragma once

template <typename Function>
Function NgxProc(HMODULE module, const char* name) {
    const auto raw = GetProcAddress(module, name);
    if (!raw) throw std::runtime_error(std::string("ngx_export_missing_") + name);
    return reinterpret_cast<Function>(raw);
}

struct NgxImage {
    VkImage image = VK_NULL_HANDLE;
    VkDeviceMemory memory = VK_NULL_HANDLE;
    VkImageView view = VK_NULL_HANDLE;
    VkFormat format = VK_FORMAT_UNDEFINED;
    VkImageAspectFlags aspect = 0;
    VkImageLayout layout = VK_IMAGE_LAYOUT_UNDEFINED;
    VkExtent2D size{};
};

struct NgxFixture {
    enum class ShutdownMode { Device, Plain, Skip };
    using Init = decltype(&NVSDK_NGX_VULKAN_Init_Ext2);
    using Allocate = decltype(&NVSDK_NGX_VULKAN_AllocateParameters);
    using Create = decltype(&NVSDK_NGX_VULKAN_CreateFeature1);
    // The pinned OptiScaler Vulkan provider exports the C++ SDK entry point.
    // The SDK also declares _C, but that symbol is not present in this DLL.
    using Evaluate = decltype(&NVSDK_NGX_VULKAN_EvaluateFeature);
    using Release = decltype(&NVSDK_NGX_VULKAN_ReleaseFeature);
    using Destroy = decltype(&NVSDK_NGX_VULKAN_DestroyParameters);
    using Shutdown = decltype(&NVSDK_NGX_VULKAN_Shutdown1);
    // The SDK only declares this deprecated export when
    // NGX_ENABLE_DEPRECATED_SHUTDOWN is defined; the pinned DLL exports it.
    using ShutdownPlain = NVSDK_NGX_Result (NVSDK_CONV *)(void);

    Wsi& wsi;
    HMODULE module;
    Init init;
    Allocate allocate;
    Create create;
    Evaluate evaluate;
    Release release;
    Destroy destroy;
    Shutdown shutdown;
    ShutdownPlain shutdownPlain;
    ShutdownMode shutdownMode;
    VkExtent2D renderSize{};
    NgxImage color, depth, motion, output;
    VkBuffer staging = VK_NULL_HANDLE;
    VkDeviceMemory stagingMemory = VK_NULL_HANDLE;
    void* stagingMap = nullptr;
    VkDeviceSize colorOffset = 0, depthOffset = 0, motionOffset = 0;
    VkDeviceSize colorBytes = 0, depthBytes = 0, motionBytes = 0;
    // NGX providers may defer consumption of parameter resource pointers.
    // These descriptions must remain alive for the entire feature lifetime.
    NVSDK_NGX_Resource_VK colorResource{}, depthResource{}, motionResource{}, outputResource{};
    NVSDK_NGX_Parameter* parameters = nullptr;
    NVSDK_NGX_Handle* handle = nullptr;
    bool initialized = false;
    uint32_t evaluated = 0;

    NgxFixture(Wsi& owner, HMODULE dll, ShutdownMode mode)
        : wsi(owner), module(dll),
          init(NgxProc<Init>(dll, "NVSDK_NGX_VULKAN_Init_Ext2")),
          allocate(NgxProc<Allocate>(dll, "NVSDK_NGX_VULKAN_AllocateParameters")),
          create(NgxProc<Create>(dll, "NVSDK_NGX_VULKAN_CreateFeature1")),
          evaluate(NgxProc<Evaluate>(dll, "NVSDK_NGX_VULKAN_EvaluateFeature")),
          release(NgxProc<Release>(dll, "NVSDK_NGX_VULKAN_ReleaseFeature")),
          destroy(NgxProc<Destroy>(dll, "NVSDK_NGX_VULKAN_DestroyParameters")),
          shutdown(NgxProc<Shutdown>(dll, "NVSDK_NGX_VULKAN_Shutdown1")),
          shutdownPlain(NgxProc<ShutdownPlain>(dll, "NVSDK_NGX_VULKAN_Shutdown")),
          shutdownMode(mode) {
        if (wsi.format != VK_FORMAT_B8G8R8A8_UNORM)
            throw std::runtime_error("ngx_fixture_requires_bgra8_unorm_swapchain");
        renderSize = {std::max(64u, (wsi.extent.width * 2u / 3u) & ~1u),
                      std::max(64u, (wsi.extent.height * 2u / 3u) & ~1u)};
        // All resources are owned by the fixture; exception-safe destruction is
        // performed in the factory after partial construction failures.
    }

    ~NgxFixture() {
        std::cout << "stage=ngx_cleanup_begin\n";
        if (wsi.device) {
            VkResult idle = vkDeviceWaitIdle(wsi.device);
            std::cout << "stage=ngx_cleanup_idle result=" << idle << '\n';
        }
        if (handle) {
            std::cout << "stage=ngx_release_begin\n";
            auto result = release(handle);
            std::cout << "stage=ngx_release_end result=" << static_cast<unsigned>(result) << '\n';
        }
        if (parameters) {
            auto result = destroy(parameters);
            std::cout << "stage=ngx_params_destroy result=" << static_cast<unsigned>(result) << '\n';
        }
        if (initialized) {
            if (shutdownMode == ShutdownMode::Skip) {
                // Isolated failure localization ONLY. Vulkan destruction will
                // still be attempted by Wsi; this is not a clean NGX shutdown.
                std::cout << "stage=ngx_shutdown_skipped clean_shutdown_proven=0\n";
            } else {
                std::cout << "stage=ngx_shutdown_begin mode="
                          << (shutdownMode == ShutdownMode::Plain ? "plain" : "device") << '\n';
                if (shutdownMode == ShutdownMode::Device) BeginNgxShutdownAvTrace();
                auto result = shutdownMode == ShutdownMode::Plain ? shutdownPlain() : shutdown(wsi.device);
                if (shutdownMode == ShutdownMode::Device) EndNgxShutdownAvTrace();
                std::cout << "stage=ngx_shutdown_end result=" << static_cast<unsigned>(result) << '\n';
            }
        }
        if (stagingMap) vkUnmapMemory(wsi.device, stagingMemory);
        if (staging) vkDestroyBuffer(wsi.device, staging, nullptr);
        if (stagingMemory) vkFreeMemory(wsi.device, stagingMemory, nullptr);
        for (NgxImage* resource : {&output, &motion, &depth, &color}) {
            if (resource->view) vkDestroyImageView(wsi.device, resource->view, nullptr);
            if (resource->image) vkDestroyImage(wsi.device, resource->image, nullptr);
            if (resource->memory) vkFreeMemory(wsi.device, resource->memory, nullptr);
        }
        std::cout << "stage=ngx_cleanup_end\n";
    }

    uint32_t MemoryType(uint32_t bits, VkMemoryPropertyFlags flags) const {
        VkPhysicalDeviceMemoryProperties properties{};
        vkGetPhysicalDeviceMemoryProperties(wsi.gpu, &properties);
        for (uint32_t i = 0; i < properties.memoryTypeCount; ++i)
            if ((bits & (1u << i)) &&
                (properties.memoryTypes[i].propertyFlags & flags) == flags) return i;
        throw std::runtime_error("ngx_required_memory_type_unavailable");
    }

    void CreateImage(NgxImage& target, VkFormat fmt, VkImageAspectFlags aspect,
                     VkExtent2D size, VkImageUsageFlags usage) {
        // Check the exact requested usage/tiling; never silently substitute an
        // unsupported storage, depth, or sampled image format.
        VkImageFormatProperties support{};
        Check(vkGetPhysicalDeviceImageFormatProperties(wsi.gpu, fmt, VK_IMAGE_TYPE_2D,
            VK_IMAGE_TILING_OPTIMAL, usage, 0, &support), "ngx_image_format_unsupported");
        target.format = fmt;
        target.aspect = aspect;
        target.size = size;
        VkImageCreateInfo info{VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO};
        info.imageType = VK_IMAGE_TYPE_2D;
        info.format = fmt;
        info.extent = {size.width, size.height, 1};
        info.mipLevels = 1;
        info.arrayLayers = 1;
        info.samples = VK_SAMPLE_COUNT_1_BIT;
        info.tiling = VK_IMAGE_TILING_OPTIMAL;
        info.usage = usage;
        info.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
        info.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
        Check(vkCreateImage(wsi.device, &info, nullptr, &target.image), "ngx_create_image");
        VkMemoryRequirements requirements{};
        vkGetImageMemoryRequirements(wsi.device, target.image, &requirements);
        VkMemoryAllocateInfo allocation{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};
        allocation.allocationSize = requirements.size;
        allocation.memoryTypeIndex = MemoryType(requirements.memoryTypeBits, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT);
        Check(vkAllocateMemory(wsi.device, &allocation, nullptr, &target.memory), "ngx_allocate_image_memory");
        Check(vkBindImageMemory(wsi.device, target.image, target.memory, 0), "ngx_bind_image_memory");
        VkImageViewCreateInfo view{VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO};
        view.image = target.image;
        view.viewType = VK_IMAGE_VIEW_TYPE_2D;
        view.format = fmt;
        view.subresourceRange = {aspect, 0, 1, 0, 1};
        Check(vkCreateImageView(wsi.device, &view, nullptr, &target.view), "ngx_create_image_view");
    }

    void CreateStaging() {
        const VkDeviceSize pixelCount = static_cast<VkDeviceSize>(renderSize.width) * renderSize.height;
        colorBytes = pixelCount * 4;
        depthBytes = pixelCount * sizeof(float);
        motionBytes = pixelCount * sizeof(float) * 2;
        colorOffset = 0;
        depthOffset = colorBytes;
        motionOffset = depthOffset + depthBytes;
        VkBufferCreateInfo info{VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO};
        info.size = motionOffset + motionBytes;
        info.usage = VK_BUFFER_USAGE_TRANSFER_SRC_BIT;
        info.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
        Check(vkCreateBuffer(wsi.device, &info, nullptr, &staging), "ngx_create_staging_buffer");
        VkMemoryRequirements requirements{};
        vkGetBufferMemoryRequirements(wsi.device, staging, &requirements);
        VkMemoryAllocateInfo allocation{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};
        allocation.allocationSize = requirements.size;
        allocation.memoryTypeIndex = MemoryType(requirements.memoryTypeBits,
            VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
        Check(vkAllocateMemory(wsi.device, &allocation, nullptr, &stagingMemory), "ngx_allocate_staging");
        Check(vkBindBufferMemory(wsi.device, staging, stagingMemory, 0), "ngx_bind_staging");
        Check(vkMapMemory(wsi.device, stagingMemory, 0, info.size, 0, &stagingMap), "ngx_map_staging");
        std::cout << "stage=ngx_resources_ready render=" << renderSize.width << 'x' << renderSize.height
                  << " display=" << wsi.extent.width << 'x' << wsi.extent.height
                  << " staging_bytes=" << info.size << '\n';
    }

    static void DescribeResource(NVSDK_NGX_Resource_VK& dst, const NgxImage& src, bool write) {
        dst.Type = NVSDK_NGX_RESOURCE_VK_TYPE_VK_IMAGEVIEW;
        dst.Resource.ImageViewInfo.ImageView = src.view;
        dst.Resource.ImageViewInfo.Image = src.image;
        dst.Resource.ImageViewInfo.SubresourceRange = {src.aspect, 0, 1, 0, 1};
        dst.Resource.ImageViewInfo.Format = src.format;
        dst.Resource.ImageViewInfo.Width = src.size.width;
        dst.Resource.ImageViewInfo.Height = src.size.height;
        dst.ReadWrite = write;
    }

    // Control condition: exercise NGX initialization plus either shutdown
    // export without creating a feature or any NGX GPU images.
    void Initialize(bool initOnly = false) {
        if (!initOnly) {
            CreateImage(color, VK_FORMAT_B8G8R8A8_UNORM, VK_IMAGE_ASPECT_COLOR_BIT, renderSize,
                        VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_SAMPLED_BIT);
            CreateImage(depth, VK_FORMAT_D32_SFLOAT, VK_IMAGE_ASPECT_DEPTH_BIT, renderSize,
                        VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_SAMPLED_BIT | VK_IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT);
            CreateImage(motion, VK_FORMAT_R32G32_SFLOAT, VK_IMAGE_ASPECT_COLOR_BIT, renderSize,
                        VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_SAMPLED_BIT);
            CreateImage(output, VK_FORMAT_B8G8R8A8_UNORM, VK_IMAGE_ASPECT_COLOR_BIT, wsi.extent,
                        VK_IMAGE_USAGE_STORAGE_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT | VK_IMAGE_USAGE_SAMPLED_BIT);
            CreateStaging();
            DescribeResource(colorResource, color, false);
            DescribeResource(depthResource, depth, false);
            DescribeResource(motionResource, motion, false);
            DescribeResource(outputResource, output, true);
        }
        const std::wstring path = std::filesystem::current_path().wstring();
        std::cout << "stage=ngx_init_begin\n";
        auto result = init(0x1337, path.c_str(), wsi.instance, wsi.gpu, wsi.device,
                           vkGetInstanceProcAddr, vkGetDeviceProcAddr, NVSDK_NGX_Version_API, nullptr);
        std::cout << "stage=ngx_init_end result=" << static_cast<unsigned>(result) << '\n';
        if (result != NVSDK_NGX_Result_Success) throw std::runtime_error("ngx_init_failed");
        initialized = true;
        if (initOnly) {
            std::cout << "stage=ngx_init_only_ready feature_created=0 evaluations=0\n";
            return;
        }
        result = allocate(&parameters);
        if (result != NVSDK_NGX_Result_Success || !parameters)
            throw std::runtime_error("ngx_allocate_parameters_failed");
        parameters->Set(NVSDK_NGX_Parameter_Width, renderSize.width);
        parameters->Set(NVSDK_NGX_Parameter_Height, renderSize.height);
        parameters->Set(NVSDK_NGX_Parameter_OutWidth, wsi.extent.width);
        parameters->Set(NVSDK_NGX_Parameter_OutHeight, wsi.extent.height);
        parameters->Set(NVSDK_NGX_Parameter_PerfQualityValue, static_cast<int>(NVSDK_NGX_PerfQuality_Value_Balanced));
        parameters->Set(NVSDK_NGX_Parameter_DLSS_Feature_Create_Flags,
            static_cast<int>(NVSDK_NGX_DLSS_Feature_Flags_MVLowRes | NVSDK_NGX_DLSS_Feature_Flags_AutoExposure));
        Check(vkWaitForFences(wsi.device, 1, &wsi.fence, VK_TRUE, 2'000'000'000ull), "ngx_create_wait_fence");
        Check(vkResetCommandBuffer(wsi.command, 0), "ngx_create_reset_command");
        VkCommandBufferBeginInfo begin{VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};
        Check(vkBeginCommandBuffer(wsi.command, &begin), "ngx_create_begin_command");
        std::cout << "stage=ngx_create_feature_begin\n";
        result = create(wsi.device, wsi.command, NVSDK_NGX_Feature_SuperSampling, parameters, &handle);
        std::cout << "stage=ngx_create_feature_end result=" << static_cast<unsigned>(result) << '\n';
        if (result != NVSDK_NGX_Result_Success || !handle)
            throw std::runtime_error("ngx_create_feature_failed");
        Check(vkEndCommandBuffer(wsi.command), "ngx_create_end_command");
        Check(vkResetFences(wsi.device, 1, &wsi.fence), "ngx_create_reset_fence");
        VkSubmitInfo submit{VK_STRUCTURE_TYPE_SUBMIT_INFO};
        submit.commandBufferCount = 1;
        submit.pCommandBuffers = &wsi.command;
        Check(vkQueueSubmit(wsi.queue, 1, &submit, wsi.fence), "ngx_create_submit");
        Check(vkWaitForFences(wsi.device, 1, &wsi.fence, VK_TRUE, 15'000'000'000ull), "ngx_create_complete");
        std::cout << "stage=ngx_feature_ready handle=" << handle->Id << '\n';
    }

    void Transition(VkCommandBuffer cmd, NgxImage& image, VkImageLayout next,
                    VkAccessFlags nextAccess, VkPipelineStageFlags nextStage) {
        VkImageMemoryBarrier barrier{VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER};
        barrier.oldLayout = image.layout;
        barrier.newLayout = next;
        barrier.srcAccessMask = image.layout == VK_IMAGE_LAYOUT_UNDEFINED ? 0 :
            (VK_ACCESS_TRANSFER_WRITE_BIT | VK_ACCESS_TRANSFER_READ_BIT |
             VK_ACCESS_SHADER_READ_BIT | VK_ACCESS_SHADER_WRITE_BIT);
        barrier.dstAccessMask = nextAccess;
        barrier.srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        barrier.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
        barrier.image = image.image;
        barrier.subresourceRange = {image.aspect, 0, 1, 0, 1};
        vkCmdPipelineBarrier(cmd, image.layout == VK_IMAGE_LAYOUT_UNDEFINED ?
            VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT : VK_PIPELINE_STAGE_ALL_COMMANDS_BIT,
            nextStage, 0, 0, nullptr, 0, nullptr, 1, &barrier);
        image.layout = next;
    }

    void Upload(VkCommandBuffer cmd, NgxImage& image, VkDeviceSize offset) {
        Transition(cmd, image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL,
                   VK_ACCESS_TRANSFER_WRITE_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT);
        VkBufferImageCopy region{};
        region.bufferOffset = offset;
        region.imageSubresource = {image.aspect, 0, 0, 1};
        region.imageExtent = {image.size.width, image.size.height, 1};
        vkCmdCopyBufferToImage(cmd, staging, image.image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &region);
        Transition(cmd, image, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL,
                   VK_ACCESS_SHADER_READ_BIT, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT);
    }

    static int Oscillate(uint32_t frame, uint32_t period, int speed) {
        const uint32_t phase = frame % period;
        return static_cast<int>(phase < period / 2 ? phase : period - phase) * speed;
    }

    void FillMovingScene(uint32_t frame) {
        // One pixel of motion vector = one input-resolution pixel. MVs point
        // from the current object location back toward its previous position.
        // The r5 GPU readback samples the center 64x64 of the output image.
        // During an explicit GPU-content probe place the moving box across
        // that center so its left edge and stripes traverse the sampled ROI.
        // Ordinary NGX diagnostics retain their original stimulus.
        char gpuContent[8] {};
        const bool roiAligned = GetEnvironmentVariableA("RTX_REMIX_FG_GPUCONTENT", gpuContent,
                                                       sizeof(gpuContent)) == 1 && gpuContent[0] == '1';
        const int baseX = roiAligned ? static_cast<int>(renderSize.width / 2) - 60 : 26;
        const int baseY = roiAligned ? static_cast<int>(renderSize.height / 2) - 51 : 24;
        const int posX = baseX + Oscillate(frame, 130, 2);
        const int posY = baseY + Oscillate(frame, 110, 1);
        const float mvX = frame ? static_cast<float>(Oscillate(frame - 1, 130, 2) -
                                                     Oscillate(frame, 130, 2)) : 0.0f;
        const float mvY = frame ? static_cast<float>(Oscillate(frame - 1, 110, 1) -
                                                     Oscillate(frame, 110, 1)) : 0.0f;
        auto* base = static_cast<uint8_t*>(stagingMap);
        for (uint32_t y = 0; y < renderSize.height; ++y) {
            for (uint32_t x = 0; x < renderSize.width; ++x) {
                const size_t i = static_cast<size_t>(y) * renderSize.width + x;
                const int dx = static_cast<int>(x) - posX;
                const int dy = static_cast<int>(y) - posY;
                const bool inside = dx >= 0 && dx < 90 && dy >= 0 && dy < 70;
                const bool edge = inside && (dx < 5 || dx >= 85 || dy < 5 || dy >= 65);
                const uint8_t checker = ((x / 24 + y / 24) & 1) ? 32 : 0;
                auto* pixel = base + colorOffset + i * 4;
                pixel[0] = inside ? (edge ? 18 : 26) : static_cast<uint8_t>(48 + checker);
                pixel[1] = inside ? (edge ? 18 : ((dx / 8) & 1 ? 220 : 178)) : static_cast<uint8_t>(68 + checker);
                pixel[2] = inside ? (edge ? 18 : 235) : static_cast<uint8_t>(87 + checker);
                pixel[3] = 255;
                const float depthValue = inside ? 0.25f : 0.86f;
                std::memcpy(base + depthOffset + i * sizeof(float), &depthValue, sizeof(float));
                const float xy[2] = {inside ? mvX : 0.0f, inside ? mvY : 0.0f};
                std::memcpy(base + motionOffset + i * sizeof(xy), xy, sizeof(xy));
            }
        }
        std::cout << "source_scene=" << frame << " box_x=" << posX << " box_y=" << posY
                  << " mv_x=" << mvX << " mv_y=" << mvY
                  << " gpu_roi_center_aligned=" << (roiAligned ? 1 : 0) << '\n';
    }

    void Render(uint32_t frame, VkCommandBuffer cmd, VkImage swapImage) {
        FillMovingScene(frame);
        Upload(cmd, color, colorOffset);
        Upload(cmd, depth, depthOffset);
        Upload(cmd, motion, motionOffset);
        Transition(cmd, output, VK_IMAGE_LAYOUT_GENERAL,
                   VK_ACCESS_SHADER_WRITE_BIT, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT);

        parameters->Set(NVSDK_NGX_Parameter_Color, static_cast<void*>(&colorResource));
        parameters->Set(NVSDK_NGX_Parameter_Depth, static_cast<void*>(&depthResource));
        parameters->Set(NVSDK_NGX_Parameter_MotionVectors, static_cast<void*>(&motionResource));
        parameters->Set(NVSDK_NGX_Parameter_Output, static_cast<void*>(&outputResource));
        parameters->Set(NVSDK_NGX_Parameter_Reset, frame == 0 ? 1 : 0);
        parameters->Set(NVSDK_NGX_Parameter_Jitter_Offset_X, 0.0f);
        parameters->Set(NVSDK_NGX_Parameter_Jitter_Offset_Y, 0.0f);
        parameters->Set(NVSDK_NGX_Parameter_MV_Scale_X, 1.0f);
        parameters->Set(NVSDK_NGX_Parameter_MV_Scale_Y, 1.0f);
        parameters->Set(NVSDK_NGX_Parameter_DLSS_Render_Subrect_Dimensions_Width, renderSize.width);
        parameters->Set(NVSDK_NGX_Parameter_DLSS_Render_Subrect_Dimensions_Height, renderSize.height);
        parameters->Set(NVSDK_NGX_Parameter_DLSS_Pre_Exposure, 1.0f);
        parameters->Set(NVSDK_NGX_Parameter_DLSS_Exposure_Scale, 1.0f);
        parameters->Set(NVSDK_NGX_Parameter_FrameTimeDeltaInMsec, 16.667f);
        const auto result = evaluate(cmd, handle, parameters, nullptr);
        std::cout << "ngx_evaluate=" << frame << " result=" << static_cast<unsigned>(result) << '\n';
        if (result != NVSDK_NGX_Result_Success) throw std::runtime_error("ngx_evaluate_failed");
        ++evaluated;

        Transition(cmd, output, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
                   VK_ACCESS_TRANSFER_READ_BIT, VK_PIPELINE_STAGE_TRANSFER_BIT);
        VkImageCopy copy{};
        copy.srcSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};
        copy.dstSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};
        copy.extent = {wsi.extent.width, wsi.extent.height, 1};
        vkCmdCopyImage(cmd, output.image, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
                       swapImage, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 1, &copy);
        Transition(cmd, output, VK_IMAGE_LAYOUT_GENERAL,
                   VK_ACCESS_SHADER_WRITE_BIT, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT);
    }
};
