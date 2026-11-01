/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Properties;

/** Updates only defaults whose on-disk bytes still match a recorded shipped version. */
final class ShippedProfileUpdater {
    private static final org.slf4j.Logger LOGGER = org.slf4j.LoggerFactory.getLogger(ShippedProfileUpdater.class);
    private ShippedProfileUpdater() {}

    static void sync(Path bundled, Path installed, Path manifest) throws IOException {
        if (!Files.isDirectory(bundled)) return;
        rejectLinks(installed);
        rejectLinks(manifest);
        Properties previous = new Properties();
        boolean validMetadata = true;
        if (Files.exists(manifest)) {
            try (InputStream input = Files.newInputStream(manifest)) {
                previous.load(input);
            } catch (IllegalArgumentException invalidMetadata) {
                validMetadata = false;
                previous.clear();
                LOGGER.warn("Invalid lighting profile hash metadata; preserving unrecognized existing profiles");
            }
        }
        Properties next = new Properties();
        try (var paths = Files.walk(bundled)) {
            for (Path source : (Iterable<Path>) paths::iterator) {
                if (!Files.isRegularFile(source) || !source.toString().endsWith(".conf")) continue;
                Path relative = bundled.relativize(source);
                String key = relative.toString().replace('\\', '/');
                Path target = installed.resolve(relative.toString());
                rejectLinks(target);
                String shipped = sha256(source);
                String recorded = previous.getProperty(key);
                String current = Files.exists(target) ? sha256(target) : null;
                if (current == null || current.equals(recorded)) {
                    if (!shipped.equals(current)) replace(source, target);
                    next.setProperty(key, shipped);
                } else if (current.equals(shipped)) {
                    // Safely adopt an older installation only when its bytes
                    // are exactly the default currently bundled with this build.
                    next.setProperty(key, shipped);
                } else if (recorded != null) {
                    // Keep the prior identity: reverting an edit to the recorded
                    // default allows a subsequent update, without adopting edits.
                    next.setProperty(key, recorded);
                }
            }
        }
        if (validMetadata && next.equals(previous) && Files.exists(manifest)) return;
        Files.createDirectories(manifest.toAbsolutePath().getParent());
        Path staging = Files.createTempFile(manifest.toAbsolutePath().getParent(), "profile-hashes-", ".tmp");
        try {
            try (var output = Files.newOutputStream(staging)) {
                next.store(output, "SHA-256 of last installed lighting defaults; edited profiles are preserved");
            }
            Files.move(staging, manifest, StandardCopyOption.REPLACE_EXISTING);
        } finally {
            Files.deleteIfExists(staging);
        }
    }

    private static void rejectLinks(Path path) throws IOException {
        for (Path part = path.toAbsolutePath(); part != null; part = part.getParent()) {
            if (Files.isSymbolicLink(part)) throw new IOException("Lighting profile path contains a symbolic link: " + part);
        }
        if (Files.exists(path, LinkOption.NOFOLLOW_LINKS) && !Files.isRegularFile(path)
                && !Files.isDirectory(path)) throw new IOException("Unsupported lighting profile path: " + path);
    }

    private static void replace(Path source, Path target) throws IOException {
        Files.createDirectories(target.toAbsolutePath().getParent());
        Path staging = Files.createTempFile(target.toAbsolutePath().getParent(), "profile-update-", ".tmp");
        try {
            Files.copy(source, staging, StandardCopyOption.REPLACE_EXISTING);
            Files.move(staging, target, StandardCopyOption.REPLACE_EXISTING);
        } finally {
            Files.deleteIfExists(staging);
        }
    }

    private static String sha256(Path path) throws IOException {
        try (InputStream input = Files.newInputStream(path)) {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] buffer = new byte[8192];
            int read;
            while ((read = input.read(buffer)) != -1) digest.update(buffer, 0, read);
            return HexFormat.of().formatHex(digest.digest());
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException(impossible);
        }
    }
}
