/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.settings;

import com.nvidia.rtxremix.minecraft.RtxRemixMod;
import com.nvidia.rtxremix.minecraft.texture.BlockTextureManager;

/** Applies a settings reset as one save/rebuild transaction, from either UI or command. */
public final class RtxSettingsReset {
    private RtxSettingsReset() {}

    public static void apply(RtxSettings settings, Runnable save) {
        boolean rebuildLights = settings.hasOverrides(SettingGroup.BLOCK_LIGHTS);
        settings.resetAll();
        BlockTextureManager textures = BlockTextureManager.get();
        boolean rebuildMaterials = textures != null && textures.commitTerrainEmissionMultiplier();
        if (save != null) save.run();
        if (rebuildMaterials) {
            RtxRemixMod.rebuildTerrainForMaterialSettings();
        } else if (rebuildLights) {
            RtxRemixMod.rebuildLoadedTerrain();
        }
    }
}
