/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class MfgOptiScalerPayloadTest {
    @TempDir Path directory;

    @Test
    void aManifestMustBeExplicitlyPinned() throws Exception {
        Files.writeString(directory.resolve("payload.sha256"), "");
        assertEquals("OptiScaler development manifest checksum mismatch", assertThrows(IOException.class,
                () -> MfgOptiScalerPayload.validate(directory, "", "")).getMessage());
    }

    @Test
    void aPinnedManifestCannotReadOutsideItsPayload() throws Exception {
        Path payload = Files.createDirectory(directory.resolve("payload"));
        Path outside = Files.writeString(directory.resolve("outside.dll"), "outside");
        Path manifest = Files.writeString(payload.resolve("payload.sha256"),
                MfgUnlockerBootstrap.sha256(outside) + "  ../outside.dll\n");
        assertEquals("Adapter manifest entry is invalid or modified", assertThrows(IOException.class,
                () -> MfgOptiScalerPayload.validate(payload, MfgUnlockerBootstrap.sha256(manifest), "")).getMessage());
    }

    @Test
    void modifyingANativeDependencyInvalidatesThePayload() throws Exception {
        Path dependency = Files.writeString(directory.resolve("dependency.dll"), "original");
        Path manifest = Files.writeString(directory.resolve("payload.sha256"),
                MfgUnlockerBootstrap.sha256(dependency) + "  dependency.dll\n");
        String pin = MfgUnlockerBootstrap.sha256(manifest);
        Files.writeString(dependency, "modified");
        assertEquals("Adapter manifest entry is invalid or modified", assertThrows(IOException.class,
                () -> MfgOptiScalerPayload.validate(directory, pin, "")).getMessage());
    }

    @Test
    void addingAnUnlistedNativeDependencyIsRejected() throws Exception {
        Path manifest = Files.writeString(directory.resolve("payload.sha256"), "");
        String pin = MfgUnlockerBootstrap.sha256(manifest);
        Files.writeString(directory.resolve("unlisted.asi"), "extra");
        assertEquals("Unlisted native adapter library", assertThrows(IOException.class,
                () -> MfgOptiScalerPayload.validate(directory, pin, "")).getMessage());
    }
}
