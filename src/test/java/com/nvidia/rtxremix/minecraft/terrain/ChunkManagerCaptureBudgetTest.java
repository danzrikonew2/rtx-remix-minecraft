/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.terrain;

import com.nvidia.rtxremix.minecraft.terrain.capture.BlockDataQueue;
import com.nvidia.rtxremix.minecraft.terrain.capture.SectionBlockData;
import net.minecraft.core.SectionPos;
import org.junit.jupiter.api.Test;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.List;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ChunkManagerCaptureBudgetTest {
    @Test
    @SuppressWarnings("unchecked")
    void expiredBudgetMakesProgressReleasesConsumedReferencesAndPreservesDeferredCapture() throws Exception {
        ChunkManager manager = new ChunkManager(null);
        try {
            SectionBlockData data = new SectionBlockData(SectionPos.of(0, 0, 0), null,
                    List.of(), 0, 0, 0, 0, 0, 0, new long[64]);
            var first = new BlockDataQueue.QueuedCapture(data, BlockDataQueue.beginCapture(0, 0));
            var second = new BlockDataQueue.QueuedCapture(data, BlockDataQueue.beginCapture(0, 0));
            BlockDataQueue.clear(); // Both pending captures now belong to a retired generation.
            Field pendingField = ChunkManager.class.getDeclaredField("pending");
            pendingField.setAccessible(true);
            List<BlockDataQueue.QueuedCapture> pending = (List<BlockDataQueue.QueuedCapture>) pendingField.get(manager);
            pending.add(first);
            pending.add(second);
            Method drain = ChunkManager.class.getDeclaredMethod("drainBlockData", long.class);
            drain.setAccessible(true);
            assertEquals(1, drain.invoke(manager, 0L));
            assertNull(pending.get(0));
            assertSame(second, pending.get(1));
            assertEquals(1, drain.invoke(manager, 0L));
            assertTrue(pending.isEmpty());
        } finally {
            manager.destroy();
        }
    }
}
