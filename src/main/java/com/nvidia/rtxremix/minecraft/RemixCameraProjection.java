/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft;

/** The perspective planes shared by the native camera and primary-depth compositor. */
public final class RemixCameraProjection {
    public static final float NEAR = 0.05f;
    public static final float FAR = 1000.0f;

    private RemixCameraProjection() {}

    /** Converts Remix's standard zero-to-one projected depth to axial blocks. */
    public static double axialDistance(double depth) {
        return NEAR * (double) FAR / (FAR - depth * (FAR - (double) NEAR));
    }

    /** Environmental fog uses spherical distance, including toward screen corners. */
    public static double sphericalDistance(double depth, double u, double v,
                                           double fovYDegrees, double aspect) {
        double tanHalfFov = Math.tan(Math.toRadians(fovYDegrees) * 0.5);
        double x = (2 * u - 1) * aspect * tanHalfFov;
        double y = (2 * v - 1) * tanHalfFov;
        return axialDistance(depth) * Math.sqrt(1 + x * x + y * y);
    }
}
