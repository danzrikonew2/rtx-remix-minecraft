/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.gl;

import com.nvidia.rtxremix.minecraft.RemixCameraProjection;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.lwjgl.sdl.SDLInit;
import org.lwjgl.sdl.SDLVideo;
import org.lwjgl.opengl.GL;
import org.lwjgl.opengl.GL11;
import org.lwjgl.opengl.GL15;
import org.lwjgl.opengl.GL20;
import org.lwjgl.opengl.GL21;
import org.lwjgl.opengl.GL30;
import org.lwjgl.opengl.GL42;
import org.lwjgl.opengl.GL45;

import static org.junit.jupiter.api.Assertions.*;

/** Opt-in owned hidden GL context; never opens or drives a Minecraft window. */
@EnabledIfEnvironmentVariable(named = "RTXREMIX_GL_TESTS", matches = "1")
class StatusEffectFogPassGlTest {
    @Test
    void fogsSyntheticPrimaryDepthAndRestoresBindings() {
        assertTrue(SDLInit.SDL_Init(SDLInit.SDL_INIT_VIDEO));
        long window = 0;
        long context = 0;
        try {
            SDLVideo.SDL_GL_SetAttribute(SDLVideo.SDL_GL_CONTEXT_MAJOR_VERSION, 4);
            SDLVideo.SDL_GL_SetAttribute(SDLVideo.SDL_GL_CONTEXT_MINOR_VERSION, 5);
            SDLVideo.SDL_GL_SetAttribute(SDLVideo.SDL_GL_CONTEXT_PROFILE_MASK, SDLVideo.SDL_GL_CONTEXT_PROFILE_CORE);
            window = SDLVideo.SDL_CreateWindow("Status fog test", 32, 32,
                    SDLVideo.SDL_WINDOW_OPENGL | SDLVideo.SDL_WINDOW_HIDDEN);
            assertNotEquals(0, window);
            context = SDLVideo.SDL_GL_CreateContext(window);
            assertNotEquals(0, context);
            assertTrue(SDLVideo.SDL_GL_MakeCurrent(window, context));
            GL.createCapabilities();
            for (int format : new int[]{GL11.GL_RGBA8, GL21.GL_SRGB8_ALPHA8}) verifyFormat(format);
        } finally {
            GL.setCapabilities(null);
            if (context != 0) SDLVideo.SDL_GL_DestroyContext(context);
            if (window != 0) SDLVideo.SDL_DestroyWindow(window);
            SDLInit.SDL_Quit();
        }
    }

    private static void verifyFormat(int format) {
        int color = GL45.glCreateTextures(GL11.GL_TEXTURE_2D);
        int depth = GL45.glCreateTextures(GL11.GL_TEXTURE_2D);
        StatusEffectFogPass pass = new StatusEffectFogPass();
        int previousProgram = GL11.glGetInteger(GL20.GL_CURRENT_PROGRAM);
        int sentinelShader = GL20.glCreateShader(org.lwjgl.opengl.GL43.GL_COMPUTE_SHADER);
        GL20.glShaderSource(sentinelShader, "#version 450\nlayout(local_size_x=1) in; void main() {}\n");
        GL20.glCompileShader(sentinelShader);
        int sentinelProgram = GL20.glCreateProgram();
        GL20.glAttachShader(sentinelProgram, sentinelShader);
        GL20.glLinkProgram(sentinelProgram);
        assertEquals(GL11.GL_TRUE, GL20.glGetProgrami(sentinelProgram, GL20.GL_LINK_STATUS));
        GL20.glDeleteShader(sentinelShader);
        GL20.glUseProgram(sentinelProgram);
        try {
            // Non-workgroup-aligned dimensions exercise the shader's bounds guard.
            GL45.glTextureStorage2D(color, 1, format, 3, 1);
            GL45.glTextureStorage2D(depth, 1, GL30.GL_R32F, 3, 1);
            GL45.glTextureSubImage2D(color, 0, 0, 0, 3, 1, GL11.GL_RGBA, GL11.GL_FLOAT,
                    new float[]{1, .5f, .25f, 1, 1, .5f, .25f, 1, 1, .5f, .25f, 1});
            GL45.glTextureSubImage2D(depth, 0, 0, 0, 3, 1, GL11.GL_RED, GL11.GL_FLOAT,
                    new float[]{project(.5), project(3), 1});
            GL42.glBindImageTexture(0, depth, 0, false, 0, GL15.GL_READ_WRITE, GL30.GL_R32F);
            GL42.glBindImageTexture(1, color, 0, false, 0, GL15.GL_READ_ONLY, GL11.GL_RGBA8);
            assertEquals(GL11.GL_NO_ERROR, GL11.glGetError(), "Test texture setup format " + format);
            int output = pass.apply(color, depth, 70, 3, 1.25f, 5);
            assertEquals(GL11.GL_NO_ERROR, GL11.glGetError(), "Fog dispatch format " + format);
            assertEquals(sentinelProgram, GL11.glGetInteger(GL20.GL_CURRENT_PROGRAM));
            assertEquals(depth, GL30.glGetIntegeri(GL42.GL_IMAGE_BINDING_NAME, 0));
            assertEquals(GL15.GL_READ_WRITE, GL30.glGetIntegeri(GL42.GL_IMAGE_BINDING_ACCESS, 0));
            assertEquals(color, GL30.glGetIntegeri(GL42.GL_IMAGE_BINDING_NAME, 1));
            assertEquals(0, GL30.glGetIntegeri(GL42.GL_IMAGE_BINDING_NAME, 2));
            GL42.glMemoryBarrier(GL42.GL_TEXTURE_UPDATE_BARRIER_BIT);
            float[] pixels = new float[12];
            GL45.glGetTextureImage(output, 0, GL11.GL_RGBA, GL11.GL_FLOAT, pixels);
            // Corner ray at axial .5 remains inside the near band. Middle ray at
            // 3 blocks is linearly fogged; a miss (depth 1) is fully black.
            assertEquals(GL11.GL_NO_ERROR, GL11.glGetError(), "Readback format " + format);
            assertEquals(1, pixels[0], .005, "Near pixel format " + format + " " + java.util.Arrays.toString(pixels));
            assertEquals(1 - (3 - 1.25) / (5 - 1.25), pixels[4], .005);
            assertEquals(0, pixels[8], .005);
            assertEquals(1, pixels[11], .005);
            assertEquals(GL11.GL_NO_ERROR, GL11.glGetError(), "OpenGL format/state validation");
            pass.releaseImage();
            assertFalse(GL11.glIsTexture(output));
            int recreated = pass.apply(color, depth, 70, 3, 1.25f, 5);
            assertTrue(GL11.glIsTexture(recreated));
            verifyReducedDepthAndResize(pass, format);
        } finally {
            pass.close();
            GL20.glUseProgram(previousProgram);
            GL20.glDeleteProgram(sentinelProgram);
            GL42.glBindImageTexture(0, 0, 0, false, 0, GL15.GL_READ_ONLY, GL11.GL_RGBA8);
            GL42.glBindImageTexture(1, 0, 0, false, 0, GL15.GL_READ_ONLY, GL11.GL_RGBA8);
            GL11.glDeleteTextures(color);
            GL11.glDeleteTextures(depth);
        }
    }

    private static void verifyReducedDepthAndResize(StatusEffectFogPass pass, int format) {
        int color = GL45.glCreateTextures(GL11.GL_TEXTURE_2D);
        int depth = GL45.glCreateTextures(GL11.GL_TEXTURE_2D);
        try {
            GL45.glTextureStorage2D(color, 1, format, 3, 2);
            GL45.glTextureStorage2D(depth, 1, GL30.GL_R32F, 1, 2);
            GL45.glTextureSubImage2D(color, 0, 0, 0, 3, 2, GL11.GL_RGBA, GL11.GL_FLOAT,
                    new float[]{.25f, .5f, .75f, 1, .25f, .5f, .75f, 1, .25f, .5f, .75f, 1,
                            1, .75f, .5f, 1, 1, .75f, .5f, 1, 1, .75f, .5f, 1});
            GL45.glTextureSubImage2D(depth, 0, 0, 0, 1, 2, GL11.GL_RED, GL11.GL_FLOAT,
                    new float[]{project(.25), 1});
            int output = pass.apply(color, depth, 70, 1.5f, 1.25f, 5);
            GL42.glMemoryBarrier(GL42.GL_TEXTURE_UPDATE_BARRIER_BIT);
            float[] pixels = new float[24];
            GL45.glGetTextureImage(output, 0, GL11.GL_RGBA, GL11.GL_FLOAT, pixels);
            assertEquals(.25, pixels[0], .005, "Source/depth row alignment after resize");
            assertEquals(.75, pixels[2], .005);
            assertEquals(0, pixels[12], .005, "Reduced depth must blacken only its matching far row");
            assertEquals(1, pixels[15], .005);
            assertEquals(GL11.GL_NO_ERROR, GL11.glGetError());
        } finally {
            GL11.glDeleteTextures(color);
            GL11.glDeleteTextures(depth);
        }
    }

    private static float project(double blocks) {
        double n = RemixCameraProjection.NEAR;
        double f = RemixCameraProjection.FAR;
        return (float) (f / (f - n) - n * f / ((f - n) * blocks));
    }
}
