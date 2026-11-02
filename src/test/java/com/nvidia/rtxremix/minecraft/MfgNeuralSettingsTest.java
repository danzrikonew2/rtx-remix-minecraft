/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;

class MfgNeuralSettingsTest {

    @TempDir Path gameDirectory;

    private Path javaBin() {
        return gameDirectory.resolve("rtx-remix-addons/mfg-unlocker/java/bin");
    }

    private Path configFile() {
        return javaBin().resolve("RTXMFG-Universal.json");
    }

    private Path statusFile() {
        return javaBin().resolve("RTXMFG-Universal.status.json");
    }

    private String currentStatus(int state, long result, long evaluations, boolean detected) {
        return "{\"pid\":42,\"processBirth\":1,\"heartbeat\":" + Instant.now().getEpochSecond()
                + ",\"dlss5State\":" + state + ",\"dlss5Result\":" + result
                + ",\"dlss5Evaluations\":" + evaluations + ",\"dlss5Detected\":" + detected + "}";
    }

    @Test
    void preservesFrameGenerationAndUnknownFieldsAndBacksUpOriginalOnce() throws Exception {
        Files.createDirectories(javaBin());
        String original = "{\"followGame\":false,\"mode\":\"fixed\",\"multiplier\":4,"
                + "\"dlss5\":false,\"dlss5HookStage\":3,\"dlss5Preset\":1,"
                + "\"otherAddonField\":{\"keep\":true}}";
        Files.writeString(configFile(), original);
        MfgNeuralSettings settings = new MfgNeuralSettings(gameDirectory, 42);

        settings.setEnabled(true);
        settings.setStage(2);

        JsonObject saved = JsonParser.parseString(Files.readString(configFile())).getAsJsonObject();
        assertFalse(saved.get("followGame").getAsBoolean());
        assertEquals("fixed", saved.get("mode").getAsString());
        assertEquals(4, saved.get("multiplier").getAsInt());
        assertTrue(saved.get("dlss5").getAsBoolean());
        assertEquals(2, saved.get("dlss5HookStage").getAsInt());
        assertEquals(1, saved.get("dlss5Preset").getAsInt());
        assertTrue(saved.getAsJsonObject("otherAddonField").get("keep").getAsBoolean());
        assertEquals(original, Files.readString(configFile().resolveSibling(
                "RTXMFG-Universal.json.before-minecraft-neural-controls")));
    }

    @Test
    void malformedConfigIsNotOverwrittenOrBackedUp() throws Exception {
        Files.createDirectories(javaBin());
        String malformed = "{\"dlss5\":";
        Files.writeString(configFile(), malformed);
        MfgNeuralSettings settings = new MfgNeuralSettings(gameDirectory, 42);

        assertThrows(IOException.class, () -> settings.setEnabled(true));
        assertEquals(malformed, Files.readString(configFile()));
        assertFalse(Files.exists(configFile().resolveSibling(
                "RTXMFG-Universal.json.before-minecraft-neural-controls")));
        assertFalse(settings.read().nativeStatusCurrent());
    }

    @Test
    void legacyFixedFrameGenerationModeDoesNotBecomeFollowGame() throws Exception {
        Files.createDirectories(javaBin());
        Files.writeString(configFile(), "{\"mode\":\"fixed\",\"multiplier\":3}");
        new MfgNeuralSettings(gameDirectory, 42).setEnabled(true);
        JsonObject saved = JsonParser.parseString(Files.readString(configFile())).getAsJsonObject();
        assertFalse(saved.get("followGame").getAsBoolean());
        assertEquals("fixed", saved.get("mode").getAsString());
        assertEquals(3, saved.get("multiplier").getAsInt());
    }

    @Test
    void invalidExistingMultiplierOrHookStagePreventsWrites() throws Exception {
        Files.createDirectories(javaBin());
        MfgNeuralSettings settings = new MfgNeuralSettings(gameDirectory, 42);
        for (String invalid : new String[] {
                "{\"multiplier\":7,\"dlss5\":false}",
                "{\"multiplier\":2,\"dlss5HookStage\":4,\"dlss5\":false}"
        }) {
            Files.writeString(configFile(), invalid);
            assertThrows(IOException.class, () -> settings.setEnabled(true));
            assertEquals(invalid, Files.readString(configFile()));
        }
        assertFalse(Files.exists(configFile().resolveSibling(
                "RTXMFG-Universal.json.before-minecraft-neural-controls")));
    }

    @Test
    void stalePidStatusIsNotReportedAsCurrentAndItsCountersAreZeroed() throws Exception {
        Files.createDirectories(javaBin());
        Files.writeString(statusFile(), "{\"pid\":41,\"dlss5State\":2,\"dlss5Result\":0,"
                + "\"dlss5Evaluations\":900,\"dlss5Detected\":true}");

        MfgNeuralSettings.Snapshot snapshot = new MfgNeuralSettings(gameDirectory, 42).read();

        assertFalse(snapshot.nativeStatusCurrent());
        assertFalse(snapshot.providerDetected());
        assertEquals(0, snapshot.state());
        assertEquals(0, snapshot.result());
        assertEquals(0, snapshot.evaluations());
        assertFalse(snapshot.message().contains(gameDirectory.toString()));
        assertTrue(snapshot.message().contains("another process"));
    }

    @Test
    void partialCurrentPidStatusIsNotReportedAsCurrent() throws Exception {
        Files.createDirectories(javaBin());
        Files.writeString(statusFile(), "{\"pid\":42,\"processBirth\":1,\"heartbeat\":"
                + Instant.now().getEpochSecond() + ",\"dlss5State\":2}");

        MfgNeuralSettings.Snapshot snapshot = new MfgNeuralSettings(gameDirectory, 42).read();

        assertFalse(snapshot.nativeStatusCurrent());
        assertEquals(0, snapshot.state());
        assertEquals(0, snapshot.evaluations());
        assertTrue(snapshot.message().contains("incomplete"));
    }

    @Test
    void stageSetterAllowsOnlyAutoAndAfterUpscaling() throws Exception {
        MfgNeuralSettings settings = new MfgNeuralSettings(gameDirectory, 42);

        assertThrows(IllegalArgumentException.class, () -> settings.setStage(1));
        assertFalse(Files.exists(configFile()));
        settings.setStage(2);
        JsonObject saved = JsonParser.parseString(Files.readString(configFile())).getAsJsonObject();
        assertEquals(2, saved.get("dlss5HookStage").getAsInt());
        assertFalse(saved.get("dlss5").getAsBoolean());
        settings.setStage(0);
        assertEquals(0, JsonParser.parseString(Files.readString(configFile())).getAsJsonObject()
                .get("dlss5HookStage").getAsInt());
    }

    @Test
    void partialControlFileGetsModeDefaultConsistentWithFollowGameFlag() throws Exception {
        Files.createDirectories(javaBin());
        Files.writeString(configFile(), "{\"followGame\":false,\"multiplier\":3}");

        new MfgNeuralSettings(gameDirectory, 42).setEnabled(true);

        JsonObject saved = JsonParser.parseString(Files.readString(configFile())).getAsJsonObject();
        assertEquals("fixed", saved.get("mode").getAsString());
        assertEquals(3, saved.get("multiplier").getAsInt());
        assertTrue(saved.get("dlss5").getAsBoolean());
        assertEquals(0, saved.get("dlss5HookStage").getAsInt());
    }

    @Test
    void readDoesNotCreateOrModifyFilesAndUsesMissingConfigDefaults() throws Exception {
        MfgNeuralSettings settings = new MfgNeuralSettings(gameDirectory, 42);

        MfgNeuralSettings.Snapshot snapshot = settings.read();

        assertFalse(snapshot.enabled());
        assertEquals(0, snapshot.stage());
        assertFalse(snapshot.nativeStatusCurrent());
        assertFalse(Files.exists(javaBin()));
    }

    @Test
    void matchingStatusReportsUnsupportedProviderWithoutClaimingEvaluation() throws Exception {
        Files.createDirectories(javaBin());
        Files.writeString(statusFile(), currentStatus(4, 3120562177L, 0, true));

        MfgNeuralSettings.Snapshot snapshot = new MfgNeuralSettings(gameDirectory, 42).read();

        assertTrue(snapshot.nativeStatusCurrent());
        assertTrue(snapshot.providerDetected());
        assertEquals(4, snapshot.state());
        assertEquals(0, snapshot.evaluations());
        assertTrue(snapshot.message().contains("unsupported hardware or driver"));
    }
}
