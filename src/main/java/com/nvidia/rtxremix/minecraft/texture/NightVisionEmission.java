/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.texture;

import com.nvidia.rtxremix.MaterialInfo;
import com.nvidia.rtxremix.TextureFormat;
import com.nvidia.rtxremix.TexturePatch;
import com.nvidia.rtxremix.TextureBatchEntry;
import com.nvidia.rtxremix.TexturePatchInfo;
import com.nvidia.rtxremix.TexturePurpose;
import com.nvidia.rtxremix.RemixAPI;
import com.nvidia.rtxremix.minecraft.asset.RemixMaterial;
import com.nvidia.rtxremix.minecraft.asset.RemixMaterialStore;
import com.nvidia.rtxremix.minecraft.asset.RemixTexture;
import com.nvidia.rtxremix.minecraft.asset.RemixTextureStore;
import com.nvidia.rtxremix.minecraft.util.DirectBufferPool;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.ArrayList;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** Render-thread owner of a temporary, low-radiance block-atlas emission floor. */
public final class NightVisionEmission {
    private static final Logger LOGGER = LoggerFactory.getLogger(NightVisionEmission.class);
    public static final float DEFAULT_STRENGTH = 0.10f;
    public static final float MAX_STRENGTH = 0.20f;
    private static final int FADE_STEPS = 4;
    private final List<Binding> bindings = new ArrayList<>();
    private byte[] albedo, emission, metallic;
    private int width, height;
    private float authoredIntensity, outputIntensity;
    private float configuredStrength = DEFAULT_STRENGTH;
    private float blend;
    private int level;
    private float appliedFloor;
    private boolean bindingsApplied;
    private boolean failed;
    private RemixTexture texture;

    private record Binding(RemixMaterial material, MaterialInfo original) {}

    void configure(byte[] albedo, byte[] emission, byte[] metallic,
                   int width, int height, float authoredIntensity) {
        this.albedo = albedo;
        this.emission = emission;
        this.metallic = metallic;
        this.width = width;
        this.height = height;
        this.authoredIntensity = authoredIntensity;
        outputIntensity = Math.max(1, authoredIntensity);
    }

    void register(RemixMaterial material, MaterialInfo original) {
        if (material == null) return;
        bindings.removeIf(binding -> binding.material.isDeleted());
        bindings.add(new Binding(material, original));
        if (texture != null) {
            bindingsApplied = false;
            try {
                apply(material, original);
            } catch (RuntimeException e) {
                fail(e);
            }
        }
    }

    public float configuredStrength() { return configuredStrength; }
    public float activeStrength() { return appliedFloor; }

    public void setStrength(float value) {
        if (!Float.isFinite(value) || value < 0 || value > MAX_STRENGTH) {
            throw new IllegalArgumentException("Night Vision emission must be between 0 and " + MAX_STRENGTH);
        }
        configuredStrength = value;
    }

    /** Smooth activation and final-second expiry without vanilla's warning flashes. */
    public static float targetStrength(int duration, boolean infinite) {
        return infinite ? 1 : Math.clamp(duration / 20.0f, 0, 1);
    }

    void update(RemixAPI api, float target, float realtimeTicks) {
        if (albedo == null || failed) return;
        try {
            updateNative(api, target, realtimeTicks);
        } catch (RuntimeException e) {
            fail(e);
        }
    }

    private void updateNative(RemixAPI api, float target, float realtimeTicks) {
        float step = Math.clamp(realtimeTicks, 0, 5) / 10;
        blend += Math.clamp(Math.clamp(target, 0, 1) - blend, -step, step);
        int next = configuredStrength == 0 ? 0 : Math.round(blend * FADE_STEPS);
        float floor = configuredStrength * next / FADE_STEPS;
        if (next == level && floor == appliedFloor) {
            if (texture != null && !bindingsApplied) bindAll();
            return;
        }
        if (next == 0) {
            release();
            return;
        }
        boolean created = texture == null;
        ByteBuffer pixels = pixels(0, 0, width, height, floor);
        try {
            if (created) {
                RemixTexture candidate = new RemixTexture(width, height, TextureFormat.RGBA16_SFLOAT,
                        TexturePurpose.COLOR, pixels);
                // The store consumes/releases the creation buffer, including on failure.
                pixels = null;
                RemixTextureStore.get().create(candidate);
                texture = candidate;
                bindingsApplied = false;
            } else {
                TexturePatch patch = patch(0, 0, width, height, pixels);
                TextureBatchEntry entry = new TextureBatchEntry();
                entry.handle = texture.getHandle();
                entry.patches = new TexturePatch[]{patch};
                TexturePatchInfo info = new TexturePatchInfo();
                info.entries = new TextureBatchEntry[]{entry};
                api.updateTextureFromMemory(info);
            }
            bindings.removeIf(binding -> binding.material.isDeleted());
            if (!bindingsApplied) bindAll();
            level = next;
            appliedFloor = floor;
        } finally {
            if (pixels != null) DirectBufferPool.release(pixels);
        }
    }

    private void apply(RemixMaterial material, MaterialInfo original) {
        MaterialInfo info = withEmission(original, texture.getHandle(), outputIntensity);
        RemixMaterialStore.get().update(material, info);
    }

    private void bindAll() {
        for (Binding binding : bindings) {
            if (!binding.material.isDeleted()) apply(binding.material, binding.original);
        }
        bindingsApplied = true;
    }

    private void fail(RuntimeException failure) {
        failed = true;
        try {
            release();
        } catch (RuntimeException restoreFailure) {
            // Keep texture/bindings owned if restoring failed; clear/dispose can retry.
            failure.addSuppressed(restoreFailure);
        }
        LOGGER.error("Night Vision emission unavailable for this atlas session; continuing normal rendering", failure);
    }

    /** Original texture handles/descriptors restore exactly, without inverse brightness math. */
    void release() {
        if (texture != null) {
            for (Binding binding : bindings) {
                if (!binding.material.isDeleted()) RemixMaterialStore.get().update(binding.material, binding.original);
            }
            texture.destroy();
            texture = null;
        }
        level = 0;
        appliedFloor = 0;
        bindingsApplied = false;
    }

    void clear() {
        try {
            release();
            blend = 0;
            failed = false;
        } catch (RuntimeException e) {
            if (!failed) LOGGER.error("Night Vision material restoration failed; retaining resources for cleanup", e);
            failed = true;
        }
    }

    void dispose() {
        release();
        blend = 0;
        failed = false;
        bindings.clear();
        albedo = emission = metallic = null;
    }

    /** Keep CPU source data current even while the effect is inactive. */
    TexturePatch animatedPatch(int x, int y, int w, int h, int padding, ByteBuffer colors, byte[] emissive) {
        for (int row = 0; row < h; row++) {
            int dst = ((y + row) * width + x) * 4;
            int src = row * w * 4;
            for (int i = 0; i < w * 4; i++) albedo[dst + i] = colors.get(src + i);
            System.arraycopy(emissive, src, emission, dst, w * 4);
        }
        SpriteTexels.fillPadding(albedo, width, height, 4, x, y, w, h, padding);
        SpriteTexels.fillPadding(emission, width, height, 4, x, y, w, h, padding);
        SpriteTexels.fillPadding(metallic, width, height, 1, x, y, w, h, padding);
        int left = Math.max(0, x - padding), top = Math.max(0, y - padding);
        int patchWidth = Math.min(width, x + w + padding) - left;
        int patchHeight = Math.min(height, y + h + padding) - top;
        return texture == null ? null : patch(left, top, patchWidth, patchHeight,
                pixels(left, top, patchWidth, patchHeight, activeStrength()));
    }

    void animatedMetallic(int x, int y, int w, int h, ByteBuffer data) {
        for (int row = 0; row < h; row++) {
            for (int col = 0; col < w; col++) metallic[(y + row) * width + x + col] = data.get(row * w + col);
        }
    }

    long textureHandle() { return texture == null ? 0 : texture.getHandle(); }
    boolean isConfigured() { return albedo != null; }

    private ByteBuffer pixels(int x, int y, int w, int h, float floor) {
        ByteBuffer dst = DirectBufferPool.acquire(Math.multiplyExact(Math.multiplyExact(w, h), 8));
        dst.order(ByteOrder.LITTLE_ENDIAN);
        for (int row = 0; row < h; row++) {
            for (int col = 0; col < w; col++) {
                int pixel = (y + row) * width + x + col;
                writePixel(dst, albedo, emission, pixel * 4, metallic[pixel] & 255,
                        authoredIntensity, outputIntensity, floor);
            }
        }
        return dst.flip();
    }

    static void writePixel(ByteBuffer dst, byte[] albedo, byte[] emission, int offset, int metal,
                           float authoredIntensity, float outputIntensity, float floor) {
        boolean boost = (emission[offset + 3] & 255) == 0
                && (albedo[offset + 3] & 255) >= 128 && metal < 128;
        for (int channel = 0; channel < 3; channel++) {
            float authored = (emission[offset + channel] & 255) / 255.0f * authoredIntensity;
            float extra = boost ? (albedo[offset + channel] & 255) / 255.0f * floor : 0;
            dst.putShort(Float.floatToFloat16(Math.max(authored, extra) / outputIntensity));
        }
        dst.putShort(Float.floatToFloat16(boost || emission[offset + 3] != 0 ? 1 : 0));
    }

    private static TexturePatch patch(int x, int y, int w, int h, ByteBuffer data) {
        TexturePatch patch = new TexturePatch();
        patch.dstX = x; patch.dstY = y; patch.width = w; patch.height = h;
        patch.rowPitch = w * 8; patch.format = TextureFormat.RGBA16_SFLOAT; patch.pixelData = data;
        return patch;
    }

    static MaterialInfo withEmission(MaterialInfo source, long texture, float intensity) {
        MaterialInfo info = new MaterialInfo(source.hash);
        info.albedoTexture = source.albedoTexture;
        info.normalTexture = source.normalTexture;
        info.tangentTexture = source.tangentTexture;
        info.emissiveTexture = texture;
        info.emissiveIntensity = intensity;
        info.emissiveColorConstant = source.emissiveColorConstant;
        info.spriteSheetRow = source.spriteSheetRow;
        info.spriteSheetCol = source.spriteSheetCol;
        info.spriteSheetFps = source.spriteSheetFps;
        info.filterMode = source.filterMode;
        info.wrapModeU = source.wrapModeU;
        info.wrapModeV = source.wrapModeV;
        info.opaqueExt = source.opaqueExt;
        info.translucentExt = source.translucentExt;
        return info;
    }
}
