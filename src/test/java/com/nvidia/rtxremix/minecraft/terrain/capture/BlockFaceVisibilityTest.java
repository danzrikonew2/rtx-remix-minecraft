/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.terrain.capture;

import net.minecraft.SharedConstants;
import net.minecraft.core.Direction;
import net.minecraft.server.Bootstrap;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.SlabBlock;
import net.minecraft.world.level.block.state.properties.SlabType;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

/** Headless checks of the exact vanilla face predicate used by terrain capture. */
class BlockFaceVisibilityTest {
    @BeforeAll static void bootstrap() {
        SharedConstants.tryDetectVersion();
        Bootstrap.bootStrap();
    }

    @Test void halfSlabsDoNotCullTheWholeNeighbouringLeafFace() {
        for (SlabType half : new SlabType[]{SlabType.BOTTOM, SlabType.TOP}) {
            var slab = Blocks.STONE_SLAB.defaultBlockState().setValue(SlabBlock.TYPE, half);
            for (Direction side : Direction.Plane.HORIZONTAL) {
                assertTrue(Block.shouldRenderFace(Blocks.OAK_LEAVES.defaultBlockState(), slab, side),
                        half + " " + side);
            }
        }
    }

    @Test void matchingGlassBlocksCullTheirSharedFace() {
        for (Direction side : Direction.values()) {
            assertFalse(Block.shouldRenderFace(Blocks.GLASS.defaultBlockState(), Blocks.GLASS.defaultBlockState(), side));
            assertFalse(Block.shouldRenderFace(Blocks.STAINED_GLASS.red().defaultBlockState(),
                    Blocks.STAINED_GLASS.red().defaultBlockState(), side));
        }
    }
}
