/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.entity;

import it.unimi.dsi.fastutil.objects.Object2LongOpenHashMap;
import net.minecraft.resources.Identifier;

import java.util.Set;
import java.util.function.Consumer;

/** Render-thread usage stamps and bounded retirement of unused dynamic texture sets. */
final class EntityTextureResidency {
    private final Object2LongOpenHashMap<Identifier> lastUsed = new Object2LongOpenHashMap<>();
    private final long graceFrames;
    private final long sweepInterval;
    private final int maxRetirements;
    private boolean swept;
    private long lastSweep;

    EntityTextureResidency() {
        this(600, 60, 4);
    }

    EntityTextureResidency(long graceFrames, long sweepInterval, int maxRetirements) {
        if (graceFrames < 0 || sweepInterval < 1 || maxRetirements < 1) {
            throw new IllegalArgumentException("Invalid entity texture residency bounds");
        }
        this.graceFrames = graceFrames;
        this.sweepInterval = sweepInterval;
        this.maxRetirements = maxRetirements;
        lastUsed.defaultReturnValue(Long.MIN_VALUE);
    }

    /** Marks shared texture use and permits at most one refresh per capture frame. */
    boolean shouldRefresh(Identifier textureId, long frame) {
        return lastUsed.put(textureId, frame) != frame;
    }

    /**
     * Retires only owned dynamic sets, after their complete grace period. The callback
     * destroys their dependent instances and meshes before materials and textures.
     * A failed callback leaves its stamp available for a later sweep to retry.
     */
    void retireCold(long frame, Set<Identifier> ownedDynamicIds, Consumer<Identifier> retire) {
        if (swept && frame - lastSweep < sweepInterval) return;
        swept = true;
        lastSweep = frame;

        int retired = 0;
        var iterator = lastUsed.object2LongEntrySet().fastIterator();
        while (iterator.hasNext()) {
            var entry = iterator.next();
            if (frame - entry.getLongValue() <= graceFrames) continue;

            Identifier textureId = entry.getKey();
            if (ownedDynamicIds.contains(textureId)) {
                if (retired == maxRetirements) continue;
                retire.accept(textureId);
                retired++;
            }
            iterator.remove();
        }
    }

    void clear() {
        lastUsed.clear();
        swept = false;
        lastSweep = 0;
    }

    int size() {
        return lastUsed.size();
    }
}
