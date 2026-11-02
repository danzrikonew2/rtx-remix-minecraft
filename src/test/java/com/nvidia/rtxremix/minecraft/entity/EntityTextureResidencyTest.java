/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.entity;

import net.minecraft.resources.Identifier;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.fail;

class EntityTextureResidencyTest {
    private static Identifier id(String path) {
        return Identifier.fromNamespaceAndPath("minecraft", path);
    }

    @Test
    void refreshesOncePerFrameIncludingFrameZeroAndAfterClear() {
        EntityTextureResidency residency = new EntityTextureResidency(2, 1, 4);
        Identifier map = id("dynamic/map/1");
        assertTrue(residency.shouldRefresh(map, 0));
        assertFalse(residency.shouldRefresh(map, 0));
        assertTrue(residency.shouldRefresh(map, 1));
        residency.retireCold(50, Set.of(), ignored -> fail("unowned"));
        residency.clear();
        assertEquals(0, residency.size());
        assertTrue(residency.shouldRefresh(map, 0));
        residency.retireCold(3, Set.of(map), ignored -> {});
        assertEquals(0, residency.size(), "clear also resets sweep scheduling");
    }

    @Test
    void currentUseByAnyOwnerProtectsTheSharedTextureAndExactGraceBoundary() {
        EntityTextureResidency residency = new EntityTextureResidency(2, 1, 4);
        Identifier skin = id("skins/shared");
        List<Identifier> retired = new ArrayList<>();
        residency.shouldRefresh(skin, 0);
        residency.retireCold(2, Set.of(skin), retired::add);
        assertTrue(retired.isEmpty(), "the exact grace boundary is protected");
        assertTrue(residency.shouldRefresh(skin, 3));
        assertFalse(residency.shouldRefresh(skin, 3), "another owner shares the refresh");
        residency.retireCold(3, Set.of(skin), retired::add);
        residency.retireCold(5, Set.of(skin), retired::add);
        assertTrue(retired.isEmpty());
        residency.retireCold(6, Set.of(skin), retired::add);
        assertEquals(List.of(skin), retired);
    }

    @Test
    void capsNativeRetirementsAndKeepsOverflowForLaterSweeps() {
        EntityTextureResidency residency = new EntityTextureResidency(2, 3, 2);
        Set<Identifier> owned = new HashSet<>();
        for (int i = 0; i < 5; i++) {
            Identifier map = id("dynamic/map/" + i);
            owned.add(map);
            residency.shouldRefresh(map, 0);
        }
        Set<Identifier> retired = new HashSet<>();
        java.util.function.Consumer<Identifier> retire = texture -> {
            assertTrue(retired.add(texture), "each texture retires once");
            assertTrue(owned.remove(texture), "callback may mutate the ownership set");
        };
        residency.retireCold(3, owned, retire);
        assertEquals(2, retired.size());
        assertEquals(3, residency.size());
        residency.retireCold(4, owned, retire);
        assertEquals(2, retired.size(), "no scan before the next sweep");
        residency.retireCold(6, owned, retire);
        assertEquals(4, retired.size());
        assertEquals(1, residency.size());
        residency.retireCold(9, owned, retire);
        assertEquals(5, retired.size());
        assertEquals(0, residency.size());
    }

    @Test
    void failedNativeRetirementKeepsItsStampForRetry() {
        EntityTextureResidency residency = new EntityTextureResidency(1, 2, 4);
        Identifier map = id("dynamic/map/retry");
        residency.shouldRefresh(map, 0);
        assertThrows(IllegalStateException.class,
                () -> residency.retireCold(2, Set.of(map), ignored -> {
                    throw new IllegalStateException("native retirement failed");
                }));
        assertEquals(1, residency.size());
        List<Identifier> retired = new ArrayList<>();
        residency.retireCold(3, Set.of(map), retired::add);
        assertTrue(retired.isEmpty());
        residency.retireCold(4, Set.of(map), retired::add);
        assertEquals(List.of(map), retired);
        assertEquals(0, residency.size());
    }

    @Test
    void prunesNonownedAndBorrowedStampsWithoutNativeCallbacks() {
        EntityTextureResidency residency = new EntityTextureResidency(1, 1, 1);
        residency.shouldRefresh(id("textures/atlas/blocks.png"), 0);
        residency.shouldRefresh(id("textures/entity/cow.png"), 0);
        residency.retireCold(2, Set.of(), ignored -> fail("no owned dynamic resource"));
        assertEquals(0, residency.size());
    }
}
