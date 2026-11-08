/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.terrain;

import org.junit.jupiter.api.Test;

import java.lang.reflect.Field;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ChunkManagerLightStabilityDiagnosticTest {

    @Test
    void snapshotIsPassiveAndStartsAtZero() {
        ChunkManager manager = new ChunkManager(null);
        try {
            var first = manager.lightSubmissionSnapshot();
            var second = manager.lightSubmissionSnapshot();
            assertEquals(first, second, "diagnostic read must have no side effects");
            assertEquals(0L, first.frames());
            assertEquals(0L, first.creates());
            assertEquals(0L, first.updates());
            assertEquals(0L, first.removes());
            assertEquals(0L, first.retirementRequests());
            assertEquals(0L, first.pendingOps());
            assertEquals(0, first.drawn());
        } finally {
            manager.destroy();
        }
    }

    @Test
    void worldResetCannotLeakThePreviousWorldsDiagnosticCounters() throws Exception {
        ChunkManager manager = new ChunkManager(null);
        try {
            setLong(manager, "lightFramesObserved", 200L);
            setLong(manager, "lightNativeCreates", 4L);
            setLong(manager, "lightNativeUpdates", 1L);
            setLong(manager, "lightNativeRemoves", 2L);
            setLong(manager, "lightRetiresQueued", 3L);
            setInt(manager, "lastLightsDrawn", 7);

            var before = manager.lightSubmissionSnapshot();
            assertEquals(200L, before.frames());
            assertEquals(4L, before.creates());
            assertEquals(1L, before.updates());
            assertEquals(2L, before.removes());
            assertEquals(3L, before.retirementRequests());
            assertEquals(7, before.drawn());

            manager.clear();
            var after = manager.lightSubmissionSnapshot();
            assertEquals(0L, after.frames());
            assertEquals(0L, after.creates());
            assertEquals(0L, after.updates());
            assertEquals(0L, after.removes());
            assertEquals(0L, after.retirementRequests());
            assertEquals(0, after.drawn());
        } finally {
            manager.destroy();
        }
    }

    private static void setLong(Object target, String fieldName, long value) throws Exception {
        Field field = target.getClass().getDeclaredField(fieldName);
        field.setAccessible(true);
        field.setLong(target, value);
    }

    private static void setInt(Object target, String fieldName, int value) throws Exception {
        Field field = target.getClass().getDeclaredField(fieldName);
        field.setAccessible(true);
        field.setInt(target, value);
    }
}
