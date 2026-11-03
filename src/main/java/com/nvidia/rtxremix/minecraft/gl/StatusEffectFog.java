/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.gl;

import com.nvidia.rtxremix.minecraft.ClientViewDistance;
import net.minecraft.client.Camera;
import net.minecraft.client.Minecraft;
import net.minecraft.client.renderer.fog.FogData;
import net.minecraft.client.renderer.fog.environment.BlindnessFogEnvironment;
import net.minecraft.client.renderer.fog.environment.DarknessFogEnvironment;
import net.minecraft.client.renderer.fog.environment.MobEffectFogEnvironment;
import net.minecraft.world.level.material.FogType;
import net.minecraft.world.entity.LivingEntity;

/** Render-thread snapshot of vanilla's temporary blindness/darkness distance bands. */
final class StatusEffectFog {
    private final BlindnessFogEnvironment blindness = new BlindnessFogEnvironment();
    private final DarknessFogEnvironment darkness = new DarknessFogEnvironment();
    private final FogData fog = new FogData();
    private float opacity;

    boolean update(Minecraft client) {
        if (client.level == null) return false;
        Camera camera = client.gameRenderer.mainCamera();
        FogType medium = camera.getFluidInCamera();
        // These media precede the mob-effect environments in vanilla's fog selection.
        if (medium == FogType.LAVA || medium == FogType.POWDER_SNOW) return false;
        MobEffectFogEnvironment effect;
        if (blindness.isApplicable(medium, camera.entity())) {
            effect = blindness;
        } else if (darkness.isApplicable(medium, camera.entity())) {
            effect = darkness;
        } else {
            return false;
        }
        effect.setupFog(fog, camera, client.level, (float) ClientViewDistance.blocks(), client.getDeltaTracker());
        float darkness = effect.getModifiedDarkness((LivingEntity) camera.entity(), 0,
                client.getDeltaTracker().getGameTimeDeltaPartialTick(false));
        opacity = opacityFromDarkness(darkness);
        return opacity > 0;
    }

    /** Complement of vanilla fog color's (1 - darkness)^2 multiplier. */
    static float opacityFromDarkness(float darkness) {
        float strength = Math.clamp(darkness, 0, 1);
        return 1 - (1 - strength) * (1 - strength);
    }

    float start() { return fog.environmentalStart; }
    float end() { return fog.environmentalEnd; }
    float opacity() { return opacity; }
}
