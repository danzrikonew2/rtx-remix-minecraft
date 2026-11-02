/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

class UnfocusedFramerateLimitTest {
    @AfterEach
    void restoreDefault() {
        UnfocusedFramerateLimit.set(UnfocusedFramerateLimit.DEFAULT);
    }

    @Test
    void backgroundCapNeverLimitsTheFocusedGame() {
        UnfocusedFramerateLimit.set(10);
        assertEquals(240, UnfocusedFramerateLimit.apply(240, true, false));
        assertEquals(10, UnfocusedFramerateLimit.apply(240, false, false));
        assertEquals(5, UnfocusedFramerateLimit.apply(5, false, false));
    }

    @Test
    void minimizedCapWorksEvenWithUnlimitedBackgroundOrStaleFocus() {
        UnfocusedFramerateLimit.set(UnfocusedFramerateLimit.UNLIMITED);
        assertEquals(1, UnfocusedFramerateLimit.apply(10, false, true));
        assertEquals(1, UnfocusedFramerateLimit.apply(10, true, true));
        assertEquals(240, UnfocusedFramerateLimit.apply(240, false, false));
    }
}
