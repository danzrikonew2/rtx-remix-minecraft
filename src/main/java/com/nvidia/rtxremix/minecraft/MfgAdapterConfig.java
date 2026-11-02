/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

/** Migrates the adapter's old automatic menu keys before its DLL reads the INI. */
final class MfgAdapterConfig {
    private MfgAdapterConfig() {}

    static boolean prepare(Path directory) throws IOException {
        Path ini = directory.resolve("OptiScaler.ini");
        String before = Files.readString(ini);
        String after = migrate(before);
        return saveMigration(ini, before, after, "before-remix-menu-fix");
    }

    private static boolean saveMigration(Path ini, String before, String after, String suffix) throws IOException {
        if (before.equals(after)) return false;
        Path backup = ini.resolveSibling(ini.getFileName() + "." + suffix);
        if (Files.exists(ini) && !Files.exists(backup)) Files.copy(ini, backup);
        Files.writeString(ini, after);
        return true;
    }

    static String migrate(String ini) throws IOException {
        Map<String, String> missing = new LinkedHashMap<>();
        missing.put("overlaymenu", "OverlayMenu = true");
        missing.put("shortcutkey", "ShortcutKey = 45"); // Windows VK_INSERT, not SDL's key code.
        missing.put("fgshortcutkey", "FGShortcutKey = 35"); // Windows VK_END.
        return migrateSection(ini, "Menu", missing);
    }

    private static String migrateSection(String ini, String section, Map<String, String> missing) throws IOException {
        var controlledKeys = new HashSet<>(missing.keySet());
        String newline = ini.contains("\r\n") ? "\r\n" : "\n";
        String[] lines = ini.split("\\R", -1);
        boolean inMenu = false;
        boolean menuSeen = false;
        var seen = new HashSet<String>();
        StringBuilder result = new StringBuilder(ini.length() + 100);
        for (int i = 0; i < lines.length; i++) {
            String line = lines[i];
            String trimmed = line.replace("\uFEFF", "").split("[;#]", 2)[0].trim();
            if (trimmed.startsWith("[") && trimmed.endsWith("]")) {
                if (inMenu) appendMissing(result, missing, newline);
                inMenu = trimmed.equalsIgnoreCase("[" + section + "]");
                if (inMenu && menuSeen) throw new IOException("Duplicate addon " + section + " section");
                menuSeen |= inMenu;
            } else if (inMenu && !trimmed.startsWith(";") && !trimmed.startsWith("#")) {
                int equals = line.indexOf('=');
                if (equals >= 0) {
                    String key = line.substring(0, equals).trim().toLowerCase(Locale.ROOT);
                    if (controlledKeys.contains(key) && !seen.add(key)) {
                        throw new IOException("Duplicate addon menu key: " + key);
                    }
                    String replacement = missing.remove(key);
                    String value = line.substring(equals + 1).split("[;#]", 2)[0].trim();
                    // Never rewrite an explicit saved key, including a former shipped default.
                    if (replacement != null && (value.isEmpty() || value.equalsIgnoreCase("auto"))) {
                        int comment = line.indexOf(';', equals + 1);
                        if (comment < 0) comment = line.indexOf('#', equals + 1);
                        line = replacement + (comment >= 0 ? " " + line.substring(comment) : "");
                    }
                }
            }
            result.append(line);
            if (i < lines.length - 1) result.append(newline);
        }
        if (!missing.isEmpty()) {
            if (!result.isEmpty() && !result.toString().endsWith(newline)) result.append(newline);
            if (!menuSeen) result.append("[").append(section).append("]").append(newline);
            appendMissing(result, missing, newline);
        }
        return result.toString();
    }

    private static void appendMissing(StringBuilder result, Map<String, String> missing, String newline) {
        for (String setting : missing.values()) result.append(setting).append(newline);
        missing.clear();
    }
}
