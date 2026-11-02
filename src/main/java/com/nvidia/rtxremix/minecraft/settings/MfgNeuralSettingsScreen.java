/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.settings;

import com.nvidia.rtxremix.minecraft.MfgNeuralSettings;
import java.io.IOException;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.MultiLineTextWidget;
import net.minecraft.client.gui.components.StringWidget;
import net.minecraft.client.gui.layouts.HeaderAndFooterLayout;
import net.minecraft.client.gui.layouts.LinearLayout;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.CommonComponents;
import net.minecraft.network.chat.Component;

/** Controls the experimental neural-rendering request and reports actual provider status. */
public final class MfgNeuralSettingsScreen extends Screen {
    private final Screen parent;
    private final MfgNeuralSettings settings;
    private final HeaderAndFooterLayout layout = new HeaderAndFooterLayout(this, 33, 33);
    private MultiLineTextWidget status;
    private int ticks;

    public MfgNeuralSettingsScreen(Screen parent, MfgNeuralSettings settings) {
        super(Component.literal("DLSS 5 Neural Rendering (Experimental)"));
        this.parent = parent;
        this.settings = settings;
    }

    @Override
    protected void init() {
        layout.addToHeader(new StringWidget(title, font));
        var snapshot = settings.read();
        LinearLayout contents = LinearLayout.vertical().spacing(10);
        contents.addChild(new MultiLineTextWidget(Component.literal(
                "Separate from frame generation. Enabling requests the provider; support and successful "
                + "evaluations are reported below. Default: off."), font).setMaxWidth(Math.min(330, width - 30)));
        contents.addChild(Button.builder(Component.literal("DLSS 5: " + (snapshot.enabled() ? "Requested on" : "Off")),
                button -> change(() -> settings.setEnabled(!settings.read().enabled()))).width(220).build());
        contents.addChild(Button.builder(Component.literal("Hook: " + (snapshot.stage() == 2 ? "After upscaling" : "Auto")),
                button -> change(() -> settings.setStage(settings.read().stage() == 2 ? 0 : 2))).width(220).build());
        status = contents.addChild(new MultiLineTextWidget(statusText(snapshot), font)
                .setMaxWidth(Math.min(330, width - 30)));
        layout.addToContents(contents);
        layout.addToFooter(Button.builder(CommonComponents.GUI_DONE, button -> onClose()).width(220).build());
        layout.visitWidgets(this::addRenderableWidget);
        repositionElements();
    }

    private interface Change { void apply() throws IOException; }

    private void change(Change change) {
        try {
            change.apply();
            minecraft.gui.setScreen(new MfgNeuralSettingsScreen(parent, settings));
        } catch (IOException failure) {
            status.setMessage(Component.literal("Could not save neural-rendering settings. Existing settings were preserved."));
        }
    }

    @Override
    public void tick() {
        if (++ticks % 20 == 0) {
            status.setMessage(statusText(settings.read()));
            repositionElements();
        }
    }

    @Override
    protected void repositionElements() { layout.arrangeElements(); }

    private static Component statusText(MfgNeuralSettings.Snapshot snapshot) {
        String text = snapshot.message();
        if (snapshot.nativeStatusCurrent()) {
            text += "\nNeural evaluations: " + snapshot.evaluations()
                    + String.format(java.util.Locale.ROOT, "; result: 0x%08X", snapshot.result());
        }
        return Component.literal(text);
    }

    @Override
    public void onClose() { minecraft.gui.setScreen(parent); }
}
