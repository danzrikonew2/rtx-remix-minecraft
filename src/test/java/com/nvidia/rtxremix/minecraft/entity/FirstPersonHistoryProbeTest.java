/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.entity;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class FirstPersonHistoryProbeTest {
    @Test
    void stableInputsIgnoreUnusedPooledBoneStorage() {
        FirstPersonHistoryProbe probe = new FirstPersonHistoryProbe();
        float[] camera = new float[12], bones = new float[24];
        FirstPersonHistoryProbe.Sample result = null;
        for (int i = 0; i < 120; i++) {
            bones[23] = i;
            result = probe.sample(camera, bones, 1, 1);
        }
        assertNotNull(result);
        assertEquals(0, result.cameraChanges());
        assertEquals(0, result.boneChanges());
        assertEquals(119, result.stationaryFrames());
    }

    @Test
    void cameraBoneAndLayoutChangesAreReportedSeparately() {
        FirstPersonHistoryProbe probe = new FirstPersonHistoryProbe();
        float[] camera = new float[12], bones = new float[24];
        probe.sample(camera, bones, 1, 1);
        camera[3] = 0.25f;
        probe.sample(camera, bones, 1, 1);
        bones[3] = 0.5f;
        probe.sample(camera, bones, 1, 1);
        FirstPersonHistoryProbe.Sample result = null;
        for (int i = 3; i < 120; i++) result = probe.sample(camera, bones, 1, 2);
        assertNotNull(result);
        assertEquals(1, result.cameraChanges());
        assertEquals(1, result.boneChanges());
        assertEquals(1, result.layoutChanges());
        assertEquals(116, result.stationaryFrames());
    }
}
