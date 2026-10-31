/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** Optional, instance-local native addon. Loading is not proof of frame-generation support. */
final class MfgUnlockerBootstrap {
    private static final Logger LOGGER = LoggerFactory.getLogger(MfgUnlockerBootstrap.class);
    static final String VERSION = "1.7.0";
    static final String DLL_SHA256 = "e6b6e6b70a6ed3af839c9647a32fc22660ae6b2d655062c5c072246c91fc10c7";
    private static boolean attempted;

    private MfgUnlockerBootstrap() {}

    static void load(Path gameDirectory, Path runtimeDirectory) {
        Path addon = gameDirectory.resolve("rtx-remix-addons/mfg-unlocker");
        Path enabled = addon.resolve("enabled.txt");
        if (attempted || !Files.isRegularFile(enabled)) return;
        attempted = true;
        try {
            if (!Path.of(System.getProperty("java.home")).toRealPath().equals(addon.resolve("java").toRealPath())) {
                throw new IOException("Addon requires its isolated Java runtime; shared Java was left untouched");
            }
            if (!VERSION.equals(Files.readString(enabled).trim())) {
                throw new IOException("Unsupported addon marker version; rerun the matching addon installer");
            }
            Path dll = addon.resolve("MFGUnlocker.dll");
            if (!DLL_SHA256.equals(sha256(dll))) throw new IOException("MFG Unlocker DLL checksum mismatch");
            // Use only the NVIDIA library already supplied by the selected runtime.
            // The unlocker searches beside its own module; never modify shared Java.
            Path neuralRendering = runtimeDirectory.resolve("nvngx_dlssnr.dll");
            Path localLibrary = addon.resolve("nvngx_dlssnr.dll");
            if (!Files.exists(localLibrary) && Files.isRegularFile(neuralRendering)) {
                Files.copy(neuralRendering, localLibrary);
            }
            System.load(dll.toAbsolutePath().toString());
            LOGGER.info("Experimental MFG Unlocker {} loaded. FG/DLSS 5 availability is unverified; "
                    + "check the addon and Remix runtime logs and menus.", VERSION);
        } catch (IOException | NoSuchAlgorithmException | UnsatisfiedLinkError failure) {
            LOGGER.warn("MFG Unlocker was not loaded; continuing normal Remix startup: {}", failure.toString());
        }
    }

    static String sha256(Path path) throws IOException, NoSuchAlgorithmException {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream input = Files.newInputStream(path)) {
            byte[] buffer = new byte[65536];
            int count;
            while ((count = input.read(buffer)) != -1) digest.update(buffer, 0, count);
        }
        return HexFormat.of().formatHex(digest.digest());
    }
}
