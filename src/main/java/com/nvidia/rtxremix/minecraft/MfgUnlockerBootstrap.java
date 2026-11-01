/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft;

import java.io.IOException;
import java.io.InputStream;
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
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
    private static boolean loaded;

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
            loaded = true;
            LOGGER.info("Experimental MFG Unlocker {} loaded. FG/DLSS 5 availability is unverified; "
                    + "check the addon and Remix runtime logs and menus.", VERSION);
        } catch (IOException | NoSuchAlgorithmException | UnsatisfiedLinkError failure) {
            LOGGER.warn("MFG Unlocker was not loaded; continuing normal Remix startup: {}", failure.toString());
        }
    }

    /** Queries the addon's documented 64-byte v1 status ABI only on explicit request. */
    static String status() {
        if (!loaded) return "MFG addon is not loaded. Check the enable marker, private Java and startup log.";
        try (Arena arena = Arena.ofConfined()) {
            var symbol = SymbolLookup.loaderLookup().find("MfgUnlockSingleModuleQuery").orElseThrow();
            var query = Linker.nativeLinker().downcallHandle(symbol,
                    FunctionDescriptor.of(ValueLayout.JAVA_INT, ValueLayout.ADDRESS));
            var status = arena.allocate(64, 8);
            status.set(ValueLayout.JAVA_INT, 0, 64);
            int accepted = (int) query.invokeExact(status);
            if (accepted == 0) return "MFG addon rejected its status query.";
            boolean hooked = status.get(ValueLayout.JAVA_INT, 16) != 0
                    || status.get(ValueLayout.JAVA_INT, 20) != 0;
            return "MFG loaded; graphics hook=" + hooked
                    + ", menu key (Windows VK)=" + status.get(ValueLayout.JAVA_INT, 32)
                    + ", DXGI/Vulkan/menu frames=" + status.get(ValueLayout.JAVA_LONG, 40)
                    + "/" + status.get(ValueLayout.JAVA_LONG, 48)
                    + "/" + status.get(ValueLayout.JAVA_LONG, 56)
                    + (hooked ? ". This does not prove frame generation."
                            : ". Native menu is unattached; resetting its shortcut cannot attach it.");
        } catch (Throwable failure) {
            return "MFG native status unavailable: " + failure.getClass().getSimpleName();
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
