/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.entity;

import com.mojang.blaze3d.vertex.PoseStack;
import net.minecraft.client.model.geom.ModelPart;
import net.minecraft.client.renderer.texture.TextureAtlasSprite;
import org.joml.Quaternionfc;
import org.joml.Vector3f;

/** Vanilla's stacked flame geometry, with billboard rotation retained as a bone pose. */
final class BurningEntityFlame {
    private static final ModelPart.Polygon[] FORWARD_U = quad(false);
    private static final ModelPart.Polygon[] REVERSED_U = quad(true);

    private BurningEntityFlame() {}

    /**
     * Mutates the caller's scratch pose, never the entity renderer's own stack.
     * Sprites must belong to the current block atlas after any resource reload.
     */
    static void emit(PoseStack poses, RemixCapturingConsumer buffer, float width, float height,
                     Quaternionfc rotation, TextureAtlasSprite fire0, TextureAtlasSprite fire1) {
        float scale = width * 1.4f;
        float remaining = height / scale;
        if (!(scale > 0) || !Float.isFinite(scale) || !(remaining > 0) || !Float.isFinite(remaining)) return;
        PoseStack.Pose pose = poses.last();
        pose.scale(scale, scale, scale);
        pose.rotate(rotation);
        pose.translate(0, 0, .3f - (int) remaining * .02f);
        float halfWidth = .5f;
        float bottom = 0;
        float z = 0;
        int layer = 0;
        while (remaining > 0) {
            TextureAtlasSprite sprite = (layer & 1) == 0 ? fire0 : fire1;
            ModelPart.Polygon[] sides = (layer / 2 & 1) == 0 ? FORWARD_U : REVERSED_U;
            // Model-backed parts preserve the off-screen pose cache. Raw captured
            // vertices cannot be replayed after their pooled consumer is recycled.
            poses.pushPose();
            try {
                poses.translate(0, bottom, z);
                poses.scale(halfWidth * 2, 1, 1);
                buffer.acceptCuboid(sides, -1, poses.last().pose(), sprite);
            } finally {
                poses.popPose();
            }
            remaining -= .45f;
            bottom += .45f;
            halfWidth *= .9f;
            z -= .03f;
            layer++;
        }
    }

    private static ModelPart.Polygon[] quad(boolean reverseU) {
        float left = reverseU ? 1 : 0;
        float right = 1 - left;
        // ModelPart vertices use sixteenths of a block; the canonical quad is
        // x=-.5..+.5, y=0..1.4 blocks before each slice's pose scales it.
        return new ModelPart.Polygon[]{new ModelPart.Polygon(new ModelPart.Vertex[]{
                new ModelPart.Vertex(-8, 0, 0, left, 1),
                new ModelPart.Vertex(8, 0, 0, right, 1),
                new ModelPart.Vertex(8, 22.4f, 0, right, 0),
                new ModelPart.Vertex(-8, 22.4f, 0, left, 0)
        }, new Vector3f(0, 1, 0))};
    }
}
