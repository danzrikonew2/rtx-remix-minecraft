/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.entity;

/** Transform fingerprint counters for opt-in view-model diagnosis; render thread only. */
final class FirstPersonHistoryProbe {
    private static final int WINDOW = 120;
    private long cameraHash, boneHash;
    private int bones, layers;
    private int frames, cameraChanges, boneChanges, layoutChanges, stationaryFrames;
    private boolean initialized;

    record Sample(int cameraChanges, int boneChanges, int layoutChanges, int stationaryFrames) {}

    Sample sample(float[] camera, float[] transforms, int boneCount, int layerCount) {
        long nextCamera = hash(camera, 12);
        long nextBones = hash(transforms, boneCount * 12);
        boolean cameraChanged = initialized && cameraHash != nextCamera;
        boolean bonesChanged = initialized && boneHash != nextBones;
        boolean layoutChanged = initialized && (bones != boneCount || layers != layerCount);
        if (cameraChanged) cameraChanges++;
        if (bonesChanged) boneChanges++;
        if (layoutChanged) layoutChanges++;
        stationaryFrames = initialized && !cameraChanged && !bonesChanged && !layoutChanged
                ? stationaryFrames + 1 : 0;
        cameraHash = nextCamera;
        boneHash = nextBones;
        bones = boneCount;
        layers = layerCount;
        initialized = true;
        if (++frames < WINDOW) return null;
        Sample result = new Sample(cameraChanges, boneChanges, layoutChanges, stationaryFrames);
        frames = cameraChanges = boneChanges = layoutChanges = 0;
        return result;
    }

    private static long hash(float[] values, int length) {
        long hash = 0xcbf29ce484222325L;
        for (int i = 0; i < length; i++) {
            hash = (hash ^ Float.floatToRawIntBits(values[i])) * 0x100000001b3L;
        }
        return hash;
    }
}
