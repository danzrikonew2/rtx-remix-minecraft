/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RemixCameraProjectionTest {
    @Test
    void projectedDepthIsNotLinearDistance() {
        assertEquals(RemixCameraProjection.NEAR, RemixCameraProjection.axialDistance(0), 1e-8);
        assertEquals(RemixCameraProjection.FAR, RemixCameraProjection.axialDistance(1), 1e-5);
        double n = RemixCameraProjection.NEAR;
        double f = RemixCameraProjection.FAR;
        for (double distance : new double[]{0.1, 1.25, 3, 5, 15, 192}) {
            double projected = f / (f - n) - n * f / ((f - n) * distance);
            assertEquals(distance, RemixCameraProjection.axialDistance(projected), 1e-6);
        }
    }

    @Test
    void environmentalFogUsesLongerSphericalDistanceAtScreenCorners() {
        double n = RemixCameraProjection.NEAR;
        double f = RemixCameraProjection.FAR;
        double projected = f / (f - n) - n * f / ((f - n) * 5);
        assertEquals(5, RemixCameraProjection.sphericalDistance(projected, .5, .5, 90, 2), 1e-6);
        assertEquals(5 * Math.sqrt(6),
                RemixCameraProjection.sphericalDistance(projected, 0, 0, 90, 2), 1e-6);
        assertTrue(RemixCameraProjection.sphericalDistance(projected, 0, 0, 110, 2)
                > RemixCameraProjection.sphericalDistance(projected, 0, 0, 70, 2));
    }
}
