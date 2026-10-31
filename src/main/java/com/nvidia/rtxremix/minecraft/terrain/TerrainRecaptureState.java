/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.terrain;

import it.unimi.dsi.fastutil.longs.LongOpenHashSet;
import it.unimi.dsi.fastutil.longs.LongSet;
import it.unimi.dsi.fastutil.longs.LongSets;

/** Render-thread handoff from a reload request to vanilla's geometry invalidation. */
public final class TerrainRecaptureState {
    private Object world;
    private LongSet pending = LongSets.emptySet();
    private boolean awaitingInvalidation;

    /** Includes still-building captures when another reload replaces their section slots. */
    public LongSet includePending(Object currentWorld, LongSet built) {
        if (world != currentWorld || pending.isEmpty()) return built;
        LongOpenHashSet union = new LongOpenHashSet(built);
        union.addAll(pending);
        return union;
    }

    /** Keeps only currently eligible positions, never stale inputs from older requests. */
    public void request(Object currentWorld, LongSet eligible) {
        world = currentWorld;
        pending = new LongOpenHashSet(eligible);
        awaitingInvalidation = true;
    }

    /** Called after vanilla has replaced storage and cancelled the old compile queue. */
    public LongSet afterInvalidation(Object currentWorld, boolean captureEnabled) {
        if (world != currentWorld || !captureEnabled) {
            clear();
            return LongSets.emptySet();
        }
        if (!awaitingInvalidation) return LongSets.emptySet();
        awaitingInvalidation = false;
        return pending;
    }

    /** Retains only accepted work so repeated reloads cannot accumulate rejected positions. */
    public void queued(Object currentWorld, LongSet accepted) {
        world = currentWorld;
        pending = new LongOpenHashSet(accepted);
    }

    /** A delayed disconnect must not discard a newer world's request. */
    public void clearFor(Object leavingWorld) {
        if (world == leavingWorld) clear();
    }

    private void clear() {
        world = null;
        pending = LongSets.emptySet();
        awaitingInvalidation = false;
    }
}
