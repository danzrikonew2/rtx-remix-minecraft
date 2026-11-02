/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.gl;

import com.nvidia.rtxremix.minecraft.RemixCameraProjection;
import org.lwjgl.opengl.GL11;
import org.lwjgl.opengl.GL15;
import org.lwjgl.opengl.GL20;
import org.lwjgl.opengl.GL21;
import org.lwjgl.opengl.GL30;
import org.lwjgl.opengl.GL42;
import org.lwjgl.opengl.GL43;
import org.lwjgl.opengl.GL45;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

/**
 * Black primary-hit distance fog, applied after native tonemapping and before the HUD.
 * No native lighting or saved setting is changed. Render thread / GL 4.5 only.
 */
final class StatusEffectFogPass {
    private static final int[] IMAGE_STATE = {
            GL42.GL_IMAGE_BINDING_NAME, GL42.GL_IMAGE_BINDING_LEVEL,
            GL42.GL_IMAGE_BINDING_LAYERED, GL42.GL_IMAGE_BINDING_LAYER,
            GL42.GL_IMAGE_BINDING_ACCESS, GL42.GL_IMAGE_BINDING_FORMAT
    };
    private final int[] savedImages = new int[3 * IMAGE_STATE.length];
    private int program;
    private int output;
    private int srgbView;
    private int width;
    private int height;
    private int format;

    int apply(int color, int depth, float fovY, float aspect, float start, float end) {
        if (!(end > start)) throw new IllegalArgumentException("Fog end must exceed start");
        int w = GL45.glGetTextureLevelParameteri(color, 0, GL11.GL_TEXTURE_WIDTH);
        int h = GL45.glGetTextureLevelParameteri(color, 0, GL11.GL_TEXTURE_HEIGHT);
        int colorFormat = GL45.glGetTextureLevelParameteri(color, 0, GL11.GL_TEXTURE_INTERNAL_FORMAT);
        if (colorFormat != GL11.GL_RGBA8 && colorFormat != GL21.GL_SRGB8_ALPHA8) {
            throw new IllegalArgumentException("Unsupported fog color format: " + colorFormat);
        }
        if (program == 0) program = createProgram();
        if (output == 0 || w != width || h != height || colorFormat != format) {
            releaseImage();
            output = GL45.glCreateTextures(GL11.GL_TEXTURE_2D);
            GL45.glTextureStorage2D(output, 1, GL11.GL_RGBA8, w, h);
            if (colorFormat == GL21.GL_SRGB8_ALPHA8) {
                srgbView = GL11.glGenTextures();
                GL43.glTextureView(srgbView, GL11.GL_TEXTURE_2D, output, colorFormat, 0, 1, 0, 1);
            }
            width = w;
            height = h;
            format = colorFormat;
        }

        int previousProgram = GL11.glGetInteger(GL20.GL_CURRENT_PROGRAM);
        for (int slot = 0; slot < 3; slot++) {
            for (int field = 0; field < IMAGE_STATE.length; field++) {
                savedImages[slot * IMAGE_STATE.length + field] = GL30.glGetIntegeri(IMAGE_STATE[field], slot);
            }
        }
        try {
            // sRGB textures cannot be read as shader images. Copy their raw bits
            // into the compatible UNORM intermediate and process each pixel in
            // place. Its sRGB view preserves the existing final blit conversion.
            int source = color;
            if (srgbView != 0) {
                GL43.glCopyImageSubData(color, GL11.GL_TEXTURE_2D, 0, 0, 0, 0,
                        output, GL11.GL_TEXTURE_2D, 0, 0, 0, 0, w, h, 1);
                source = output;
            }
            GL42.glBindImageTexture(0, source, 0, false, 0, GL15.GL_READ_ONLY, GL11.GL_RGBA8);
            GL42.glBindImageTexture(1, depth, 0, false, 0, GL15.GL_READ_ONLY, GL30.GL_R32F);
            GL42.glBindImageTexture(2, output, 0, false, 0, GL15.GL_WRITE_ONLY, GL11.GL_RGBA8);
            GL20.glUseProgram(program);
            GL20.glUniform2f(0, RemixCameraProjection.NEAR, RemixCameraProjection.FAR);
            float tanHalf = (float) Math.tan(Math.toRadians(fovY) * 0.5);
            GL20.glUniform2f(1, tanHalf * aspect, tanHalf);
            GL20.glUniform2f(2, start, end);
            GL43.glDispatchCompute((w + 7) / 8, (h + 7) / 8, 1);
            GL42.glMemoryBarrier(GL42.GL_FRAMEBUFFER_BARRIER_BIT
                    | GL42.GL_SHADER_IMAGE_ACCESS_BARRIER_BIT | GL42.GL_TEXTURE_UPDATE_BARRIER_BIT);
        } finally {
            for (int slot = 0; slot < 3; slot++) {
                int base = slot * IMAGE_STATE.length;
                GL42.glBindImageTexture(slot, savedImages[base], savedImages[base + 1],
                        savedImages[base + 2] != 0, savedImages[base + 3],
                        savedImages[base + 4], savedImages[base + 5]);
            }
            GL20.glUseProgram(previousProgram);
        }
        return srgbView != 0 ? srgbView : output;
    }

    /** No full-resolution intermediate remains resident when no effect is active. */
    void releaseImage() {
        if (srgbView != 0) GL11.glDeleteTextures(srgbView);
        srgbView = 0;
        if (output != 0) GL11.glDeleteTextures(output);
        output = 0;
    }

    void close() {
        releaseImage();
        if (program != 0) GL20.glDeleteProgram(program);
        program = 0;
    }

    private static int createProgram() {
        String path = "/assets/rtx-remix-renderer/shaders/status_effect_fog.comp";
        String source;
        try (InputStream stream = StatusEffectFogPass.class.getResourceAsStream(path)) {
            if (stream == null) throw new IllegalStateException("Missing shader " + path);
            source = new String(stream.readAllBytes(), StandardCharsets.UTF_8);
        } catch (IOException e) {
            throw new IllegalStateException("Cannot read shader " + path, e);
        }
        int shader = GL20.glCreateShader(GL43.GL_COMPUTE_SHADER);
        int linked = 0;
        try {
            GL20.glShaderSource(shader, source);
            GL20.glCompileShader(shader);
            if (GL20.glGetShaderi(shader, GL20.GL_COMPILE_STATUS) == GL11.GL_FALSE) {
                throw new IllegalStateException("Status fog shader: " + GL20.glGetShaderInfoLog(shader));
            }
            linked = GL20.glCreateProgram();
            GL20.glAttachShader(linked, shader);
            GL20.glLinkProgram(linked);
            if (GL20.glGetProgrami(linked, GL20.GL_LINK_STATUS) == GL11.GL_FALSE) {
                throw new IllegalStateException("Status fog program: " + GL20.glGetProgramInfoLog(linked));
            }
            return linked;
        } catch (RuntimeException e) {
            if (linked != 0) GL20.glDeleteProgram(linked);
            throw e;
        } finally {
            GL20.glDeleteShader(shader);
        }
    }
}
