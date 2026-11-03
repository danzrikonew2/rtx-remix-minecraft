/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.entity;

import com.mojang.blaze3d.vertex.PoseStack;
import net.minecraft.client.renderer.texture.TextureAtlasSprite;
import org.joml.Matrix4f;
import org.joml.Quaternionf;
import org.joml.Vector3f;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class BurningEntityFlameTest {
    private final TextureAtlasSprite fire0 = SpriteFixtures.sprite(0, 0, 16, 64);
    private final TextureAtlasSprite fire1 = SpriteFixtures.sprite(16, 32, 16, 64);

    private RemixCapturingConsumer capture(float width, float height, Quaternionf rotation) {
        EntityRenderContext.get().begin(true);
        try {
            RemixCapturingConsumer consumer = new RemixCapturingConsumer(null, true);
            BurningEntityFlame.emit(new PoseStack(), consumer, width, height, rotation, fire0, fire1);
            consumer.finishOpenVertex();
            return consumer;
        } finally {
            EntityRenderContext.get().end();
        }
    }

    @Test
    void stacksAlternatingLiveAtlasSpritesWithVanillaUvOrientation() {
        RemixCapturingConsumer result = capture(.6f, 1.8f, new Quaternionf());
        assertEquals(0, result.getVertexCount(), "Geometry remains model-backed and snapshottable");
        assertEquals(5, result.getPartCount());
        float scale = .6f * 1.4f;
        assertEquals(-.5f * scale, position(result, 0, 0).x, 1e-6);
        assertEquals(.5f * scale, position(result, 0, 1).x, 1e-6);
        assertEquals(1.4f * scale, position(result, 0, 2).y, 1e-6);
        assertEquals(.45f * scale, position(result, 1, 0).y, 1e-6);
        assertEquals(-.45f * scale, position(result, 1, 0).x, 1e-6);
        assertEquals(-.03f * scale, position(result, 1, 0).z - position(result, 0, 0).z, 1e-6);
        RemixCapturingConsumer expanded = new RemixCapturingConsumer(null, false);
        for (int part = 0; part < result.getPartCount(); part++) {
            assertNotNull(result.getPartSides(part), "Off-screen snapshot must retain each flame part");
            expanded.emitCuboidGeometry(result.getPartSides(part), result.getPartTint(part),
                    result.getPartBone(part), result.getPartSprite(part));
        }
        expanded.finishOpenVertex();
        assertEquals(20, expanded.getVertexCount());
        assertEquals(fire0.getU0(), expanded.getTu()[0]);
        assertEquals(fire1.getU0(), expanded.getTu()[4]);
        assertEquals(fire0.getU1(), expanded.getTu()[8]);
        assertEquals(fire1.getU1(), expanded.getTu()[12]);
        assertEquals(fire0.getU0(), expanded.getTu()[16]);
        assertEquals(fire1.getV1(), expanded.getTv()[4]);
        assertEquals(fire1.getV0(), expanded.getTv()[6]);
    }

    @Test
    void cameraRotationChangesBoneButPreservesRigidMeshIdentity() {
        RemixCapturingConsumer first = capture(.6f, 1.8f, new Quaternionf());
        Matrix4f firstBone = new Matrix4f(EntityRenderContext.get().getBoneTransforms().get(0));
        RemixCapturingConsumer turned = capture(.6f, 1.8f, new Quaternionf().rotationY(1));
        var firstKey = new RemixEntitySubmitter.CuboidMeshKey(null, RenderLayerUtils.SurfaceMode.CUTOUT, 0,
                first.getPartSides(0), first.getPartSprite(0));
        var turnedKey = new RemixEntitySubmitter.CuboidMeshKey(null, RenderLayerUtils.SurfaceMode.CUTOUT, 0,
                turned.getPartSides(0), turned.getPartSprite(0));
        assertEquals(firstKey, turnedKey);
        assertFalse(turned.isTransientGeometry());
        assertFalse(firstBone.equals(EntityRenderContext.get().getBoneTransforms().get(0), 1e-6f));
        RemixCapturingConsumer taller = capture(.6f, 2.8f, new Quaternionf());
        assertTrue(taller.getPartCount() > first.getPartCount());
        assertSame(first.getPartSides(0), taller.getPartSides(0), "Different sizes share the canonical quad");
    }

    @Test
    void degenerateBoundsEmitNothingInsteadOfAnUnboundedLoop() {
        assertEquals(0, capture(0, 1, new Quaternionf()).getPartCount());
        assertEquals(0, capture(.6f, 0, new Quaternionf()).getPartCount());
        assertEquals(0, capture(.6f, Float.POSITIVE_INFINITY, new Quaternionf()).getPartCount());
    }

    private static Vector3f position(RemixCapturingConsumer captured, int part, int corner) {
        var vertex = captured.getPartSides(part)[0].vertices()[corner];
        return EntityRenderContext.get().getBoneTransforms().get(captured.getPartBone(part))
                .transformPosition(vertex.worldX(), vertex.worldY(), vertex.worldZ(), new Vector3f());
    }
}
