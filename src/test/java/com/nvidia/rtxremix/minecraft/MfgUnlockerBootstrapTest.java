/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft;

import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class MfgUnlockerBootstrapTest {
    @TempDir Path directory;

    @Test
    void ordinaryInstallationDoesNotCreateOrLoadAnAddon() {
        MfgUnlockerBootstrap.load(directory, directory.resolve("nonexistent-runtime"));
        assertFalse(Files.exists(directory.resolve("rtx-remix-addons")));
    }

    @Test
    void streamingHashDetectsModifiedPayload() throws Exception {
        Path payload = directory.resolve("payload.dll");
        Files.writeString(payload, "abc");
        assertEquals("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
                MfgUnlockerBootstrap.sha256(payload));
        Files.writeString(payload, "");
        assertEquals("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                MfgUnlockerBootstrap.sha256(payload));
    }
}
