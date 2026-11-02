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
import static org.junit.jupiter.api.Assertions.*;

class MfgAdapterConfigTest {
    @TempDir Path directory;

    @Test
    void migratesSharedMenuDefaultsWithoutChangingFrameGenerationOrPresets() throws Exception {
        String before = "[FrameGen]\r\nEnabled = true\r\n[Menu]\r\nShortcutKey = auto ; old default\r\n"
                + "OverlayMenu = auto\r\nFGShortcutKey = auto\r\n[DLSSG]\r\nInterpolationCount = 1\r\n";
        String after = MfgAdapterConfig.migrate(before);
        assertTrue(after.contains("ShortcutKey = 45 ; old default\r\n"));
        assertTrue(after.contains("OverlayMenu = true\r\nFGShortcutKey = 35\r\n"));
        assertTrue(after.startsWith("[FrameGen]\r\nEnabled = true\r\n"));
        assertTrue(after.endsWith("[DLSSG]\r\nInterpolationCount = 1\r\n"));
        assertEquals(after, MfgAdapterConfig.migrate(after));
    }

    @Test
    void preservesExplicitCustomKeysAndDisabledOverlay() throws Exception {
        String custom = "[Menu]\nShortcutKey=112\nFGShortcutKey=113\nOverlayMenu=false\n";
        assertEquals(custom, MfgAdapterConfig.migrate(custom));
        String savedInsert = "[Menu]\nShortcutKey=45\nFGShortcutKey=35\nOverlayMenu=true\n";
        assertEquals(savedInsert, MfgAdapterConfig.migrate(savedInsert));
        String savedBackspace = "[Menu]\nShortcutKey=8\nFGShortcutKey=35\nOverlayMenu=true\n";
        assertEquals(savedBackspace, MfgAdapterConfig.migrate(savedBackspace));
    }

    @Test
    void fillsMissingMenuKeysInsideTheirSectionAndRejectsAmbiguousSections() throws Exception {
        String after = MfgAdapterConfig.migrate("[Menu]\nScale=1.25\n[Log]\nLogLevel=1\n");
        assertTrue(after.contains("Scale=1.25\nOverlayMenu = true\nShortcutKey = 45\nFGShortcutKey = 35\n[Log]"));
        assertTrue(MfgAdapterConfig.migrate("[FrameGen]\nEnabled=true").contains("\n[Menu]\n"));
        assertThrows(IOException.class, () -> MfgAdapterConfig.migrate("[Menu]\n[Menu]\n"));
        assertThrows(IOException.class, () -> MfgAdapterConfig.migrate(
                "[Menu]\nShortcutKey=auto\nShortcutKey=auto\n"));
    }

    @Test
    void backsUpOnlyBeforeFirstMigrationAndDoesNotRewriteSettledConfig() throws Exception {
        Path ini = directory.resolve("OptiScaler.ini");
        String before = "[Menu]\nShortcutKey=auto\n";
        Files.writeString(ini, before);
        assertTrue(MfgAdapterConfig.prepare(directory));
        assertEquals(before, Files.readString(directory.resolve("OptiScaler.ini.before-remix-menu-fix")));
        assertFalse(MfgAdapterConfig.prepare(directory));
    }

}
