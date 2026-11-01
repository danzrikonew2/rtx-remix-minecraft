/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.logic;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ClockDiscontinuityTest {
    @Test void normalTicksPausedClockAndMidnightWrapDoNotTriggerSettling() {
        assertFalse(ConfLayerDriver.isAbruptClockChange(5000, 5001));
        assertFalse(ConfLayerDriver.isAbruptClockChange(5000, 5000));
        assertFalse(ConfLayerDriver.isAbruptClockChange(23999, 24000));
        assertFalse(ConfLayerDriver.isAbruptClockChange(-1, 0));
        assertFalse(ConfLayerDriver.isAbruptClockChange(5000, 29000));
    }

    @Test void commandsJumpingDayNightInEitherDirectionTriggerSettling() {
        assertTrue(ConfLayerDriver.isAbruptClockChange(1000, 18000));
        assertTrue(ConfLayerDriver.isAbruptClockChange(18000, 1000));
        assertTrue(ConfLayerDriver.isAbruptClockChange(6000, 18000));
        assertFalse(ConfLayerDriver.isAbruptClockChange(23900, 100));
        assertTrue(ConfLayerDriver.isAbruptClockChange(23899, 100));
    }
}
