/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.NoSuchAlgorithmException;
import java.util.HashSet;
import java.util.Set;

/** Explicitly pinned, development-only OptiScaler payload; never downloaded on game startup. */
final class MfgOptiScalerPayload {
    static final String OPTISCALER_SHA256 = "0b70d723f61fcf1cc38c26e4033666bd08936f435a848f624222c77dc86ca7fe";
    static final String MANIFEST_PROPERTY = "rtxremix.mfgOptiScalerManifestSha256";
    static final String DIRECTORY = "optiscaler-development";

    private MfgOptiScalerPayload() {}

    static void validate(Path directory, String manifestHash, String developmentHash)
            throws IOException, NoSuchAlgorithmException {
        Path root = directory.toRealPath();
        Path manifest = root.resolve("payload.sha256");
        if (!manifestHash.matches("[a-f0-9]{64}")
                || !manifestHash.equals(MfgUnlockerBootstrap.sha256(manifest))) {
            throw new IOException("OptiScaler development manifest checksum mismatch");
        }
        if (Files.size(manifest) > 1024 * 1024) throw new IOException("Oversized adapter manifest");
        Set<Path> listed = new HashSet<>();
        for (String line : Files.readAllLines(manifest)) {
            if (line.length() < 67 || !line.substring(0, 64).matches("[a-f0-9]{64}")
                    || !line.substring(64, 66).equals("  ")) {
                throw new IOException("Malformed adapter manifest");
            }
            Path relative = Path.of(line.substring(66));
            Path file = root.resolve(relative).normalize();
            if (relative.isAbsolute() || !file.startsWith(root) || !Files.isRegularFile(file)
                    || !file.toRealPath().startsWith(root) || !listed.add(file)
                    || !line.substring(0, 64).equals(MfgUnlockerBootstrap.sha256(file))) {
                throw new IOException("Adapter manifest entry is invalid or modified");
            }
        }
        try (var files = Files.walk(root)) {
            for (Path file : files.toList()) {
                String name = file.getFileName().toString().toLowerCase(java.util.Locale.ROOT);
                if ((name.endsWith(".dll") || name.endsWith(".asi")) && !listed.contains(file)) {
                    throw new IOException("Unlisted native adapter library");
                }
            }
        }
        Path adapter = root.resolve("OptiScaler.dll");
        Path plugin = root.resolve("OptiScaler/plugins/MFGUnlocker.asi");
        if (!listed.contains(adapter) || !listed.contains(plugin)
                || !OPTISCALER_SHA256.equals(MfgUnlockerBootstrap.sha256(adapter))
                || !MfgUnlockerBootstrap.acceptedHash(MfgUnlockerBootstrap.sha256(plugin), developmentHash)) {
            throw new IOException("OptiScaler or MFG development library checksum mismatch");
        }
        if (!Files.isRegularFile(root.resolve("OptiScaler.ini"))) {
            throw new IOException("OptiScaler development configuration is missing");
        }
    }

    static void load(Path directory) throws IOException {
        // Match the native probe: Vulkan must be present before OptiScaler installs its hooks.
        String systemRoot = System.getenv("SystemRoot");
        if (systemRoot == null) throw new IOException("Windows SystemRoot is unavailable");
        System.load(Path.of(systemRoot, "System32", "vulkan-1.dll").toAbsolutePath().toString());
        System.load(directory.resolve("OptiScaler.dll").toAbsolutePath().toString());
        // OptiScaler loads this plugin synchronously. Register the same module with this
        // class loader too, so loaderLookup() can query its documented status export.
        System.load(directory.resolve("OptiScaler/plugins/MFGUnlocker.asi").toAbsolutePath().toString());
    }
}
