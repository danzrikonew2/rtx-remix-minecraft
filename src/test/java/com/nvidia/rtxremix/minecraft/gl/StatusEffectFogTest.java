/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.gl;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class StatusEffectFogTest {
    @Test
    void blackOverlayWeightFollowsVanillaFogDarkeningCurve() {
        assertEquals(0, StatusEffectFog.opacityFromDarkness(0));
        assertEquals(.75f, StatusEffectFog.opacityFromDarkness(.5f));
        assertEquals(1, StatusEffectFog.opacityFromDarkness(1));
        float last = 0;
        for (int tick = 0; tick <= 20; tick++) {
            float opacity = StatusEffectFog.opacityFromDarkness(tick / 20f);
            assertTrue(opacity >= last && opacity <= 1);
            last = opacity;
        }
    }
}
