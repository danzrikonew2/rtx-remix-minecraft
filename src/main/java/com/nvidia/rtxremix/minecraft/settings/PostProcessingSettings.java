/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.settings;

import java.util.function.BiConsumer;
import java.util.function.Function;

/**
 * Tracks post-processing values exposed by the Fabric settings screen. The
 * authored defaults live in {@code rtx.conf}, so construction is write-free.
 * Live edits, persisted overrides, and Reset appliers call the writer.
 */
public final class PostProcessingSettings {

    private static final String EXPOSURE_KEY = "rtx.localtonemap.exposure";
    private static final String SHADOWS_KEY = "rtx.localtonemap.shadows";
    private static final String HIGHLIGHTS_KEY = "rtx.localtonemap.highlights";
    private static final String LOW_LIGHT_ADAPTATION_KEY = "rtx.autoExposure.evMinValue";
    private static final String HIGH_LIGHT_ADAPTATION_KEY = "rtx.autoExposure.evMaxValue";
    private static final String EYE_ADAPTATION_KEY = "rtx.autoExposure.enabled";
    private static final String ADAPTATION_SPEED_KEY = "rtx.autoExposure.autoExposureSpeed";

    private static final float DEFAULT_EXPOSURE = 0.21405728f;
    private static final float DEFAULT_SHADOWS = 1.4f;
    private static final float DEFAULT_HIGHLIGHTS = 2.5f;
    private static final float DEFAULT_LOW_LIGHT_ADAPTATION = -2.5f;
    private static final float DEFAULT_HIGH_LIGHT_ADAPTATION = 1.5f;

    private final BiConsumer<String, String> configWriter;

    private float exposure = DEFAULT_EXPOSURE;
    private float shadowLevel = DEFAULT_SHADOWS;
    private float highlightsLevel = DEFAULT_HIGHLIGHTS;
    private float lowLightAdaptation = DEFAULT_LOW_LIGHT_ADAPTATION;
    private float highLightAdaptation = DEFAULT_HIGH_LIGHT_ADAPTATION;
    private boolean eyeAdaptation = true;
    private float adaptationSpeed = 2.0f;

    public PostProcessingSettings(BiConsumer<String, String> configWriter) {
        this.configWriter = configWriter;
    }

    /** Seed new adaptation controls from resolved native settings without overwriting saved choices. */
    public PostProcessingSettings(BiConsumer<String, String> configWriter, Function<String, String> configReader) {
        this(configWriter);
        eyeAdaptation = Boolean.parseBoolean(configReader.apply(EYE_ADAPTATION_KEY));
        adaptationSpeed = Float.parseFloat(configReader.apply(ADAPTATION_SPEED_KEY));
    }

    public float getExposure() {
        return exposure;
    }

    public void setExposure(float value) {
        exposure = value;
        apply(EXPOSURE_KEY, value);
    }

    public float getShadowLevel() {
        return shadowLevel;
    }

    public void setShadowLevel(float value) {
        shadowLevel = value;
        apply(SHADOWS_KEY, value);
    }

    public float getHighlightsLevel() {
        return highlightsLevel;
    }

    public void setHighlightsLevel(float value) {
        highlightsLevel = value;
        apply(HIGHLIGHTS_KEY, value);
    }

    public float getLowLightAdaptation() {
        return lowLightAdaptation;
    }

    public void setLowLightAdaptation(float value) {
        lowLightAdaptation = value;
        apply(LOW_LIGHT_ADAPTATION_KEY, value);
    }

    public float getHighLightAdaptation() {
        return highLightAdaptation;
    }

    public void setHighLightAdaptation(float value) {
        highLightAdaptation = value;
        apply(HIGH_LIGHT_ADAPTATION_KEY, value);
    }

    private void apply(String key, float value) {
        configWriter.accept(key, Float.toString(value));
    }

    public boolean isEyeAdaptation() { return eyeAdaptation; }

    public void setEyeAdaptation(boolean value) {
        eyeAdaptation = value;
        configWriter.accept(EYE_ADAPTATION_KEY, Boolean.toString(value));
    }

    public float getAdaptationSpeed() { return adaptationSpeed; }

    public void setAdaptationSpeed(float value) {
        adaptationSpeed = value;
        apply(ADAPTATION_SPEED_KEY, value);
    }
}
