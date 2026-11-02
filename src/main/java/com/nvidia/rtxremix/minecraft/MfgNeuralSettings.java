/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.time.Instant;
import java.util.UUID;

/** Reads and updates the MFG adapter's DLSS 5 controls without changing frame-generation settings. */
public final class MfgNeuralSettings {

    private static final int MAX_FILE_BYTES = 1024 * 1024;
    private static final int MIN_MULTIPLIER = 1;
    private static final int MAX_MULTIPLIER = 6;
    private static final int MIN_HOOK_STAGE = 0;
    private static final int MAX_HOOK_STAGE = 3;
    private static final int AUTO_STAGE = 0;
    private static final int AFTER_UPSCALING_STAGE = 2;
    private static final int STATE_RUNNING = 2;
    private static final int STATE_UNSUPPORTED = 4;
    private static final long MAX_STATUS_AGE_SECONDS = 5;
    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();

    private final Path configFile;
    private final Path statusFile;
    private final long expectedPid;

    public MfgNeuralSettings(Path gameDirectory) {
        this(gameDirectory, ProcessHandle.current().pid());
    }

    MfgNeuralSettings(Path gameDirectory, long expectedPid) {
        Path javaBin = gameDirectory.resolve("rtx-remix-addons")
                .resolve("mfg-unlocker").resolve("java").resolve("bin");
        this.configFile = javaBin.resolve("RTXMFG-Universal.json");
        this.statusFile = javaBin.resolve("RTXMFG-Universal.status.json");
        this.expectedPid = expectedPid;
    }

    /** Returns saved intent and status only when the status belongs to the expected process. */
    public Snapshot read() {
        Control control = Control.defaults();
        String controlError = "";
        try {
            if (Files.exists(configFile)) {
                control = parseControl(readObject(configFile));
            }
        } catch (IOException | RuntimeException e) {
            controlError = "MFG control settings are malformed or unavailable; saved values were not changed.";
        }

        NativeStatus status = readNativeStatus();
        String message = controlError.isEmpty() ? status.message : controlError + " " + status.message;
        return new Snapshot(control.enabled, control.stage, status.detected, status.state,
                status.result, status.evaluations, status.current, message);
    }

    /** Changes the saved DLSS 5 enable flag while preserving every other control-file field. */
    public void setEnabled(boolean enabled) throws IOException {
        ControlAndObject parsed = readControlForWrite();
        parsed.object.addProperty("dlss5", enabled);
        writeControl(parsed.object);
    }

    /** Changes the DLSS 5 hook stage to Auto (0) or After Upscaling (2). */
    public void setStage(int stage) throws IOException {
        if (stage != AUTO_STAGE && stage != AFTER_UPSCALING_STAGE) {
            throw new IllegalArgumentException("DLSS 5 hook stage must be Auto (0) or After Upscaling (2).");
        }
        ControlAndObject parsed = readControlForWrite();
        parsed.object.addProperty("dlss5HookStage", stage);
        writeControl(parsed.object);
    }

    private ControlAndObject readControlForWrite() throws IOException {
        if (!Files.exists(configFile)) {
            JsonObject object = new JsonObject();
            addDefaults(object);
            return new ControlAndObject(object);
        }
        JsonObject object = readObject(configFile);
        parseControl(object);
        // Native MFG treats a legacy file without followGame as an explicit override.
        if (!object.has("followGame")) object.addProperty("followGame", false);
        addDefaults(object);
        return new ControlAndObject(object);
    }

    private static void addDefaults(JsonObject object) {
        if (!object.has("followGame")) object.addProperty("followGame", true);
        if (!object.has("mode")) {
            object.addProperty("mode", object.get("followGame").getAsBoolean() ? "follow" : "fixed");
        }
        if (!object.has("multiplier")) object.addProperty("multiplier", 2);
        if (!object.has("dlss5")) object.addProperty("dlss5", false);
        if (!object.has("dlss5HookStage")) object.addProperty("dlss5HookStage", AUTO_STAGE);
    }

    private static Control parseControl(JsonObject object) throws IOException {
        boolean followGame = object.has("followGame") && booleanValue(object, "followGame");
        String mode = object.has("mode") ? stringValue(object, "mode") : (followGame ? "follow" : "fixed");
        if (!(mode.equals("fixed") || mode.equals("dynamic")
                || (mode.equals("follow") && followGame))) {
            throw new IOException("Invalid MFG mode.");
        }
        int multiplier = object.has("multiplier") ? intValue(object, "multiplier") : 2;
        if (multiplier < MIN_MULTIPLIER || multiplier > MAX_MULTIPLIER) {
            throw new IOException("Invalid MFG multiplier.");
        }
        boolean enabled = object.has("dlss5") ? booleanValue(object, "dlss5") : false;
        int stage = object.has("dlss5HookStage") ? intValue(object, "dlss5HookStage") : AUTO_STAGE;
        if (stage < MIN_HOOK_STAGE || stage > MAX_HOOK_STAGE) {
            throw new IOException("Invalid DLSS 5 hook stage.");
        }
        return new Control(enabled, stage);
    }

    private NativeStatus readNativeStatus() {
        try {
            if (!Files.exists(statusFile)) return NativeStatus.stale("Waiting for current MFG status.");
            JsonObject object = readObject(statusFile);
            long pid = longValue(object, "pid");
            if (pid != expectedPid) {
                return NativeStatus.stale("MFG status belongs to another process; live DLSS 5 status is unavailable.");
            }
            long processBirth = longValue(object, "processBirth");
            long heartbeat = longValue(object, "heartbeat");
            long now = Instant.now().getEpochSecond();
            if (processBirth <= 0 || heartbeat > now || now - heartbeat > MAX_STATUS_AGE_SECONDS) {
                return NativeStatus.stale("MFG status is stale or incomplete; live DLSS 5 status is unavailable.");
            }
            int state = intValue(object, "dlss5State");
            long result = longValue(object, "dlss5Result");
            long evaluations = longValue(object, "dlss5Evaluations");
            boolean detected = booleanValue(object, "dlss5Detected");
            if (state < 0 || evaluations < 0) {
                return NativeStatus.stale("MFG status is incomplete; live DLSS 5 status is unavailable.");
            }
            return new NativeStatus(true, detected, state, result, evaluations, statusMessage(state, evaluations));
        } catch (IOException | RuntimeException e) {
            return NativeStatus.stale("MFG status is missing, incomplete, or unreadable; live DLSS 5 status is unavailable.");
        }
    }

    private static String statusMessage(int state, long evaluations) {
        if (state == STATE_UNSUPPORTED) return "The DLSS 5 provider reports unsupported hardware or driver.";
        if (state == STATE_RUNNING && evaluations > 0) {
            return "DLSS 5 evaluations were recorded; visible output is not confirmed.";
        }
        if (state == STATE_RUNNING) return "DLSS 5 is initialized and waiting for an evaluation.";
        return "Current MFG status is available; DLSS 5 has not reported a running evaluation.";
    }

    private void writeControl(JsonObject object) throws IOException {
        Path parent = configFile.getParent();
        Files.createDirectories(parent);
        Path backup = configFile.resolveSibling(configFile.getFileName() + ".before-minecraft-neural-controls");
        if (Files.exists(configFile) && !Files.exists(backup)) {
            Files.copy(configFile, backup);
        }

        Path temporary = configFile.resolveSibling(configFile.getFileName() + ".tmp-" + UUID.randomUUID());
        try {
            Files.writeString(temporary, GSON.toJson(object) + System.lineSeparator(), StandardCharsets.UTF_8);
            try {
                Files.move(temporary, configFile, StandardCopyOption.REPLACE_EXISTING,
                        StandardCopyOption.ATOMIC_MOVE);
            } catch (AtomicMoveNotSupportedException e) {
                Files.move(temporary, configFile, StandardCopyOption.REPLACE_EXISTING);
            }
        } finally {
            Files.deleteIfExists(temporary);
        }
    }

    private static JsonObject readObject(Path file) throws IOException {
        byte[] bytes;
        try (InputStream input = Files.newInputStream(file)) {
            bytes = input.readNBytes(MAX_FILE_BYTES + 1);
        }
        if (bytes.length > MAX_FILE_BYTES) throw new IOException("MFG JSON file exceeds the size limit.");
        try {
            JsonElement parsed = JsonParser.parseString(new String(bytes, StandardCharsets.UTF_8));
            if (!parsed.isJsonObject()) throw new IOException("MFG JSON root must be an object.");
            return parsed.getAsJsonObject();
        } catch (RuntimeException e) {
            throw new IOException("MFG JSON is malformed.", e);
        }
    }

    private static boolean booleanValue(JsonObject object, String key) throws IOException {
        JsonElement value = required(object, key);
        if (!value.isJsonPrimitive() || !value.getAsJsonPrimitive().isBoolean()) {
            throw new IOException("Invalid boolean field.");
        }
        return value.getAsBoolean();
    }

    private static String stringValue(JsonObject object, String key) throws IOException {
        JsonElement value = required(object, key);
        if (!value.isJsonPrimitive() || !value.getAsJsonPrimitive().isString()) {
            throw new IOException("Invalid string field.");
        }
        return value.getAsString();
    }

    private static int intValue(JsonObject object, String key) throws IOException {
        long value = longValue(object, key);
        if (value < Integer.MIN_VALUE || value > Integer.MAX_VALUE) throw new IOException("Invalid integer field.");
        return (int) value;
    }

    private static long longValue(JsonObject object, String key) throws IOException {
        JsonElement value = required(object, key);
        if (!value.isJsonPrimitive() || !value.getAsJsonPrimitive().isNumber()) {
            throw new IOException("Invalid numeric field.");
        }
        try {
            return value.getAsBigDecimal().longValueExact();
        } catch (ArithmeticException | NumberFormatException e) {
            throw new IOException("Invalid integer field.", e);
        }
    }

    private static JsonElement required(JsonObject object, String key) throws IOException {
        JsonElement value = object.get(key);
        if (value == null || value.isJsonNull()) throw new IOException("Missing MFG JSON field.");
        return value;
    }

    public record Snapshot(boolean enabled, int stage, boolean providerDetected, int state,
            long result, long evaluations, boolean nativeStatusCurrent, String message) {}

    private record Control(boolean enabled, int stage) {
        static Control defaults() { return new Control(false, AUTO_STAGE); }
    }

    private record ControlAndObject(JsonObject object) {}

    private record NativeStatus(boolean current, boolean detected, int state, long result,
            long evaluations, String message) {
        static NativeStatus stale(String message) { return new NativeStatus(false, false, 0, 0, 0, message); }
    }
}
