/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.texture;

import com.nvidia.rtxremix.MaterialInfo;
import com.nvidia.rtxremix.MaterialInfoOpaqueEXT;
import org.junit.jupiter.api.Test;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;

import static org.junit.jupiter.api.Assertions.*;

class NightVisionEmissionTest {
    private static byte[] rgba(int r, int g, int b, int a) {
        return new byte[]{(byte) r, (byte) g, (byte) b, (byte) a};
    }

    private static float[] radiance(byte[] color, byte[] emission, int metal, float authored) {
        ByteBuffer data = ByteBuffer.allocate(8).order(ByteOrder.LITTLE_ENDIAN);
        float scale = Math.max(1, authored);
        NightVisionEmission.writePixel(data, color, emission, 0, metal, authored, scale, 0.10f);
        data.flip();
        return new float[]{Float.float16ToFloat(data.getShort()) * scale,
                Float.float16ToFloat(data.getShort()) * scale,
                Float.float16ToFloat(data.getShort()) * scale,
                Float.float16ToFloat(data.getShort())};
    }

    @Test
    void ordinaryDiffuseColorsHaveAWeakBoundedFloorWithoutEightBitQuantization() {
        float[] result = radiance(rgba(255, 128, 16, 255), rgba(0, 0, 0, 0), 0, 100);
        assertEquals(0.10f, result[0], 0.0001f);
        assertEquals(0.10f * 128 / 255, result[1], 0.0001f);
        assertEquals(0.10f * 16 / 255, result[2], 0.0001f);
        assertTrue(result[0] < 100.0f / 255);
        assertEquals(1, result[3]);
    }

    @Test
    void authoredGlowIsPreservedWithinHalfFloatPrecisionAndNeverAddedTo() {
        byte[] authored = rgba(1, 84, 255, 255);
        float[] result = radiance(rgba(255, 255, 255, 255), authored, 0, 100);
        for (int i = 0; i < 3; i++) {
            float expected = (authored[i] & 255) * 100.0f / 255;
            assertEquals(expected, result[i], expected * 0.0005f);
        }
        assertArrayEquals(rgba(1, 84, 255, 255), authored);
    }

    @Test
    void authoredEmissionMaskProtectsEvenTexelsThatQuantizeToBlack() {
        assertArrayEquals(new float[]{0, 0, 0, 1}, radiance(
                rgba(255, 255, 255, 255), rgba(0, 0, 0, 255), 0, 100));
    }

    @Test
    void transparentTexelsAndMetalsReceiveNoArtificialEmission() {
        assertArrayEquals(new float[]{0, 0, 0, 0}, radiance(
                rgba(255, 255, 255, 0), rgba(0, 0, 0, 0), 0, 100));
        assertArrayEquals(new float[]{0, 0, 0, 0}, radiance(
                rgba(255, 255, 255, 255), rgba(0, 0, 0, 0), 255, 100));
    }

    @Test
    void zeroTerrainEmissionStillAllowsTheIndependentSmallVisionFloor() {
        assertEquals(0.10f, radiance(rgba(255, 255, 255, 255), rgba(0, 0, 0, 0), 0, 0)[0], 0.0001f);
        assertEquals(0, radiance(rgba(255, 255, 255, 255), rgba(255, 255, 255, 255), 0, 0)[0]);
    }

    @Test
    void materialOverrideRetainsPbrUvAndAnimationAndDoesNotMutateOriginal() {
        MaterialInfo original = MaterialInfo.builder().hash(9).albedoTexture(2).normalTexture(3)
                .tangentTexture(4).emissiveTexture(5).emissiveIntensity(100)
                .spriteSheetRow(2).spriteSheetCol(4).spriteSheetFps(12)
                .filterMode(0).wrapMode(2, 0).opaqueExt(MaterialInfoOpaqueEXT.builder()
                        .roughnessTexture(11).metallicTexture(12).heightTexture(13).build()).build();
        MaterialInfo override = NightVisionEmission.withEmission(original, 99, 100);
        assertEquals(9, override.hash);
        assertEquals(2, override.albedoTexture);
        assertEquals(3, override.normalTexture);
        assertEquals(4, override.tangentTexture);
        assertEquals(99, override.emissiveTexture);
        assertSame(original.opaqueExt, override.opaqueExt);
        assertSame(original.emissiveColorConstant, override.emissiveColorConstant);
        assertEquals(2, override.spriteSheetRow);
        assertEquals(4, override.spriteSheetCol);
        assertEquals(12, override.spriteSheetFps);
        assertEquals(0, override.filterMode);
        assertEquals(2, override.wrapModeU);
        assertEquals(0, override.wrapModeV);
        assertEquals(5, original.emissiveTexture);
        assertEquals(100, original.emissiveIntensity);
    }

    @Test
    void animatedSourcesStayCurrentWhileEffectIsOffAndTouchOnlyThePatch() {
        NightVisionEmission vision = new NightVisionEmission();
        byte[] colors = new byte[16], emission = new byte[16], metal = new byte[4];
        vision.configure(colors, emission, metal, 2, 2, 100);
        assertNull(vision.animatedPatch(1, 1, 1, 1, 0,
                ByteBuffer.wrap(rgba(21, 22, 23, 255)), rgba(1, 2, 3, 255)));
        vision.animatedMetallic(1, 1, 1, 1, ByteBuffer.wrap(new byte[]{(byte) 255}));
        assertArrayEquals(rgba(21, 22, 23, 255), java.util.Arrays.copyOfRange(colors, 12, 16));
        assertArrayEquals(rgba(1, 2, 3, 255), java.util.Arrays.copyOfRange(emission, 12, 16));
        assertEquals(255, metal[3] & 255);
        for (int i = 0; i < 12; i++) assertEquals(0, colors[i]);
    }

    @Test
    void animatedPaddingFollowsTheLatestTexelsRatherThanTheInitialAtlas() {
        NightVisionEmission vision = new NightVisionEmission();
        byte[] colors = new byte[36], emission = new byte[36], metal = new byte[9];
        vision.configure(colors, emission, metal, 3, 3, 100);
        vision.animatedMetallic(1, 1, 1, 1, ByteBuffer.wrap(new byte[]{90}));
        vision.animatedPatch(1, 1, 1, 1, 1, ByteBuffer.wrap(rgba(10, 20, 30, 255)), rgba(4, 5, 6, 255));
        for (int i = 0; i < 9; i++) {
            assertArrayEquals(rgba(10, 20, 30, 255), java.util.Arrays.copyOfRange(colors, i * 4, i * 4 + 4));
            assertArrayEquals(rgba(4, 5, 6, 255), java.util.Arrays.copyOfRange(emission, i * 4, i * 4 + 4));
            assertEquals(90, metal[i]);
        }
    }

    @Test
    void finalSecondFadesWithoutTheVanillaWarningPulseAndStrengthIsRestricted() {
        assertEquals(1, NightVisionEmission.targetStrength(-1, true));
        assertEquals(1, NightVisionEmission.targetStrength(200, false));
        assertEquals(0.5f, NightVisionEmission.targetStrength(10, false));
        assertEquals(0, NightVisionEmission.targetStrength(0, false));
        NightVisionEmission vision = new NightVisionEmission();
        assertEquals(0.10f, vision.configuredStrength());
        vision.setStrength(0);
        assertEquals(0, vision.configuredStrength());
        assertThrows(IllegalArgumentException.class, () -> vision.setStrength(Float.NaN));
        assertThrows(IllegalArgumentException.class, () -> vision.setStrength(-1));
        assertThrows(IllegalArgumentException.class, () -> vision.setStrength(0.21f));
    }
}
