/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.terrain;

import it.unimi.dsi.fastutil.longs.LongOpenHashSet;
import it.unimi.dsi.fastutil.longs.LongSet;
import it.unimi.dsi.fastutil.longs.LongSets;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class TerrainRecaptureStateTest {
    private static LongSet sections(long... positions) {
        return new LongOpenHashSet(positions);
    }

    @Test
    void reloadKeepsSnapshotUntilOldStorageAndQueueHaveBeenInvalidated() {
        TerrainRecaptureState state = new TerrainRecaptureState();
        Object world = new Object();
        LongSet snapshot = sections(11, 22);
        state.request(world, snapshot);
        snapshot.clear(); // Vanilla can now forget every old built slot.
        assertEquals(sections(11, 22), state.includePending(world, LongSets.emptySet()));
        assertEquals(sections(11, 22), state.afterInvalidation(world, true));
        assertTrue(state.afterInvalidation(world, true).isEmpty(), "Do not compile the same request twice");
    }

    @Test
    void repeatedReloadIncludesInFlightWorkButDropsRejectedPositions() {
        TerrainRecaptureState state = new TerrainRecaptureState();
        Object world = new Object();
        state.request(world, sections(11, 22));
        state.afterInvalidation(world, true);
        state.queued(world, sections(11));
        assertEquals(sections(11, 33), state.includePending(world, sections(33)));
        state.request(world, sections(33)); // 11 is no longer resident/lit.
        assertEquals(sections(33), state.afterInvalidation(world, true));
        assertEquals(sections(33), state.includePending(world, LongSets.emptySet()));
    }

    @Test
    void worldSwitchAndDisabledCaptureDiscardOldRequests() {
        TerrainRecaptureState state = new TerrainRecaptureState();
        Object first = new Object();
        Object second = new Object();
        state.request(first, sections(11));
        assertEquals(sections(22), state.includePending(second, sections(22)));
        assertTrue(state.afterInvalidation(second, true).isEmpty());
        state.request(second, sections(22));
        assertTrue(state.afterInvalidation(second, false).isEmpty());
        assertTrue(state.afterInvalidation(second, true).isEmpty());
    }

    @Test
    void delayedDisconnectCannotEraseNewWorldWork() {
        TerrainRecaptureState state = new TerrainRecaptureState();
        Object first = new Object();
        Object second = new Object();
        state.request(second, sections(22));
        state.clearFor(first);
        assertEquals(sections(22), state.afterInvalidation(second, true));
        state.clearFor(second);
        assertTrue(state.includePending(second, LongSets.emptySet()).isEmpty());
    }
}
