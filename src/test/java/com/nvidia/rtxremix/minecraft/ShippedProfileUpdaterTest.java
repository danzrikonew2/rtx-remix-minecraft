/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft;

import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;

class ShippedProfileUpdaterTest {
    @TempDir Path root;

    private void sync() throws Exception {
        ShippedProfileUpdater.sync(root.resolve("source"), root.resolve("live"), root.resolve("hashes.properties"));
    }

    private void shipped(String value) throws Exception {
        Files.createDirectories(root.resolve("source"));
        Files.writeString(root.resolve("source/day.conf"), value);
    }

    @Test void updatesUntouchedDefaultButPreservesEditsAcrossUpgrades() throws Exception {
        shipped("v1"); sync();
        shipped("v2"); sync();
        assertEquals("v2", Files.readString(root.resolve("live/day.conf")));
        Files.writeString(root.resolve("live/day.conf"), "custom");
        shipped("v3"); sync(); sync();
        assertEquals("custom", Files.readString(root.resolve("live/day.conf")));
        Files.writeString(root.resolve("live/day.conf"), "v2");
        sync();
        assertEquals("v3", Files.readString(root.resolve("live/day.conf")));
    }

    @Test void adoptsMatchingLegacyDefaultButNeverUnknownLegacyEdits() throws Exception {
        shipped("v1");
        Files.createDirectories(root.resolve("live"));
        Files.writeString(root.resolve("live/day.conf"), "unknown old or edited default");
        sync(); shipped("v2"); sync();
        assertEquals("unknown old or edited default", Files.readString(root.resolve("live/day.conf")));
        Files.writeString(root.resolve("live/day.conf"), "v2"); sync();
        shipped("v3"); sync();
        assertEquals("v3", Files.readString(root.resolve("live/day.conf")));
    }

    @Test void restoresDeletedDefaultWithoutDeletingRetiredOrUserFiles() throws Exception {
        shipped("v1"); sync();
        Files.delete(root.resolve("live/day.conf"));
        sync(); assertEquals("v1", Files.readString(root.resolve("live/day.conf")));
        Files.writeString(root.resolve("live/custom.conf"), "mine");
        Files.delete(root.resolve("source/day.conf")); sync();
        assertEquals("v1", Files.readString(root.resolve("live/day.conf")));
        assertEquals("mine", Files.readString(root.resolve("live/custom.conf")));
    }

    @Test void malformedManifestDoesNotAdoptOrReplaceAnExistingEdit() throws Exception {
        shipped("new"); Files.createDirectories(root.resolve("live"));
        Files.writeString(root.resolve("live/day.conf"), "mine");
        Files.writeString(root.resolve("hashes.properties"), "bad=\\uNOPE");
        sync();
        assertEquals("mine", Files.readString(root.resolve("live/day.conf")));
    }

    @Test void readsProfilesFromAJarFileSystem() throws Exception {
        var uri = java.net.URI.create("jar:" + root.resolve("payload.zip").toUri());
        try (var zip = java.nio.file.FileSystems.newFileSystem(uri, java.util.Map.of("create", "true"))) {
            Path source = zip.getPath("/native/confs");
            Files.createDirectories(source.resolve("weather"));
            Files.writeString(source.resolve("weather/rain.conf"), "rain-v1");
            ShippedProfileUpdater.sync(source, root.resolve("live"), root.resolve("hashes.properties"));
            Files.writeString(source.resolve("weather/rain.conf"), "rain-v2");
            ShippedProfileUpdater.sync(source, root.resolve("live"), root.resolve("hashes.properties"));
            assertEquals("rain-v2", Files.readString(root.resolve("live/weather/rain.conf")));
        }
    }
}
