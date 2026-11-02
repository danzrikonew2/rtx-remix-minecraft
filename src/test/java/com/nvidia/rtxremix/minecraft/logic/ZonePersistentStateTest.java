/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.logic;

import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.ListTag;
import net.minecraft.nbt.NbtAccounter;
import net.minecraft.nbt.NbtIo;
import net.minecraft.nbt.NbtOps;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ZonePersistentStateTest {

    @Test
    void importsPrevious263BeforeLegacyWithoutChangingEitherFile(@TempDir Path root) throws Exception {
        Path previous = root.resolve("dimensions/minecraft/overworld/data/rtx-remix-renderer/zones.dat");
        Path legacy = root.resolve("data/rtx_remix_zones.dat");
        ZoneDefinition newer = ZoneDefinition.parse("rtx zone define newer", 0, 0, 0);
        writePrior(previous, newer);
        writePrior(legacy, ZoneDefinition.parse("rtx zone define legacy", 0, 0, 0));
        byte[] original = Files.readAllBytes(previous);

        assertEquals(List.of(newer), new ArrayList<>(ZonePersistentState.recoverPriorState(root).snapshot()));
        assertTrue(java.util.Arrays.equals(original, Files.readAllBytes(previous)));
        assertTrue(Files.exists(legacy));
        assertFalse(Files.exists(root.resolve("data/rtx-remix-renderer/zones.dat")));
    }

    @Test
    void importsLegacyAndHonorsAnIntentionallyEmptyPrevious263State(@TempDir Path root) throws Exception {
        Path legacy = root.resolve("data/rtx_remix_zones.dat");
        ZoneDefinition old = ZoneDefinition.parse("rtx zone define old", 0, 0, 0);
        writePrior(legacy, old);
        assertEquals(List.of(old), new ArrayList<>(ZonePersistentState.recoverPriorState(root).snapshot()));
        writePrior(root.resolve("dimensions/minecraft/overworld/data/rtx-remix-renderer/zones.dat"));
        assertTrue(ZonePersistentState.recoverPriorState(root).snapshot().isEmpty());
    }

    @Test
    void failedCurrentFileLoadNeverResurrectsLegacyDefinitions(@TempDir Path root) throws Exception {
        writePrior(root.resolve("data/rtx_remix_zones.dat"),
                ZoneDefinition.parse("rtx zone define old", 0, 0, 0));
        Path current = root.resolve("data/rtx-remix-renderer/zones.dat");
        Files.createDirectories(current.getParent());
        Files.writeString(current, "unreadable current file");
        ZonePersistentState protectedState = ZonePersistentState.recoverPriorState(root);
        assertTrue(protectedState.snapshot().isEmpty());
        assertThrows(IllegalStateException.class, () -> protectedState.put(
                ZoneDefinition.parse("rtx zone define overwrite", 0, 0, 0)));
        assertEquals("unreadable current file", Files.readString(current));
    }

    @Test
    void corruptOrFuturePreviousStateBlocksFallbackAndEditing(@TempDir Path root) throws Exception {
        Path previous = root.resolve("dimensions/minecraft/overworld/data/rtx-remix-renderer/zones.dat");
        writePrior(root.resolve("data/rtx_remix_zones.dat"),
                ZoneDefinition.parse("rtx zone define legacy", 0, 0, 0));
        Files.createDirectories(previous.getParent());
        Files.writeString(previous, "not nbt");
        assertThrows(IllegalStateException.class, () -> ZonePersistentState.recoverPriorState(root).put(
                ZoneDefinition.parse("rtx zone define overwrite", 0, 0, 0)));
        CompoundTag future = new CompoundTag();
        CompoundTag data = new CompoundTag();
        data.putInt("version", 999);
        future.put("data", data);
        NbtIo.writeCompressed(future, previous);
        assertThrows(IllegalStateException.class, () -> ZonePersistentState.recoverPriorState(root).put(
                ZoneDefinition.parse("rtx zone define overwrite", 0, 0, 0)));
    }

    @Test
    void noPriorZoneFilesCreatesNoStateOrDirectories(@TempDir Path root) {
        assertEquals(null, ZonePersistentState.recoverPriorState(root));
        assertFalse(Files.exists(root.resolve("data")));
    }

    private static void writePrior(Path file, ZoneDefinition... zones) throws Exception {
        ZonePersistentState state = new ZonePersistentState();
        for (ZoneDefinition zone : zones) state.put(zone);
        CompoundTag envelope = new CompoundTag();
        envelope.put("data", state.toNbt());
        envelope.putInt("DataVersion", 3955);
        Files.createDirectories(file.getParent());
        NbtIo.writeCompressed(envelope, file);
    }

    @Test
    void sphereRoundTripsThroughNbt() {
        ZoneDefinition zone = ZoneDefinition.parse(
                "rtx zone define cave --center 10.5 20 -30.25 --inner 8 --outer 24 --channel mc.zone.underground",
                0, 0, 0);

        ZonePersistentState loaded = roundTrip(zone);

        assertEquals(1, loaded.snapshot().size());
        assertEquals(zone, loaded.snapshot().iterator().next());
    }

    @Test
    void normalizedBoxRoundTripsThroughNbt() {
        ZoneDefinition zone = ZoneDefinition.parse(
                "rtx zone define hall --box 10 20 30 -5 4 6 --fade 12 --channel mc.zone.interior",
                0, 0, 0);

        ZoneDefinition restored = roundTrip(zone).snapshot().iterator().next();

        assertEquals(zone, restored);
        assertEquals(-5.0, restored.minX());
        assertEquals(10.0, restored.maxX());
        assertEquals(4.0, restored.minY());
        assertEquals(20.0, restored.maxY());
    }

    @Test
    void effectiveChangesAloneDirtyTheState() {
        ZonePersistentState state = new ZonePersistentState();
        ZoneDefinition first = ZoneDefinition.parse(
                "rtx zone define cave --center 0 0 0 --inner 5 --outer 10", 0, 0, 0);
        ZoneDefinition moved = ZoneDefinition.parse(
                "rtx zone define cave --center 100 0 0 --inner 5 --outer 10", 0, 0, 0);

        assertFalse(state.isDirty());
        assertTrue(state.put(first));
        assertTrue(state.isDirty());

        state.setDirty(false);
        assertFalse(state.put(first));
        assertFalse(state.isDirty(), "an identical redefinition must not dirty the save");

        assertTrue(state.put(moved));
        assertTrue(state.isDirty());

        state.setDirty(false);
        assertFalse(state.remove("missing"));
        assertFalse(state.isDirty());
        assertTrue(state.remove("cave"));
        assertTrue(state.isDirty());
    }

    @Test
    void malformedEntryDoesNotDiscardValidZones() {
        ZoneDefinition valid = ZoneDefinition.parse(
                "rtx zone define valid --center 1 2 3 --inner 4 --outer 8", 0, 0, 0);
        ZonePersistentState source = new ZonePersistentState();
        source.put(valid);
        CompoundTag nbt = source.toNbt();

        CompoundTag malformed = new CompoundTag();
        malformed.putString("name", "broken");
        malformed.putString("channel", "mc.zone.broken");
        malformed.putString("shape", "sphere");
        nbt.getListOrEmpty("zones").add(malformed);

        ZonePersistentState loaded = ZonePersistentState.fromNbt(nbt);

        assertEquals(1, loaded.snapshot().size());
        assertEquals(valid, loaded.snapshot().iterator().next());
    }

    @Test
    void unsupportedSchemaLoadsAsEmptyWithoutDirtying() {
        CompoundTag nbt = new CompoundTag();
        nbt.putInt("version", 999);
        nbt.put("zones", new ListTag());

        ZonePersistentState loaded = ZonePersistentState.fromNbt(nbt);

        assertTrue(loaded.snapshot().isEmpty());
        assertFalse(loaded.isDirty());
        assertThrows(IllegalStateException.class,
                () -> loaded.put(ZoneDefinition.parse("rtx zone define newer", 0, 0, 0)));
        assertThrows(IllegalStateException.class, () -> loaded.remove("anything"));
        assertFalse(loaded.isDirty(), "an older mod must never overwrite a newer schema");
    }

    @Test
    void duplicateNamesUseLastDefinition() {
        ZoneDefinition first = ZoneDefinition.parse(
                "rtx zone define cave --center 0 0 0 --inner 5 --outer 10", 0, 0, 0);
        ZoneDefinition second = ZoneDefinition.parse(
                "rtx zone define cave --center 100 0 0 --inner 5 --outer 10", 0, 0, 0);

        CompoundTag firstNbt = writeOne(first);
        CompoundTag secondNbt = writeOne(second);
        ListTag zones = new ListTag();
        zones.add(firstNbt);
        zones.add(secondNbt);
        CompoundTag root = new CompoundTag();
        root.putInt("version", 1);
        root.put("zones", zones);

        ZoneDefinition restored = ZonePersistentState.fromNbt(root).snapshot().iterator().next();

        assertEquals(second, restored);
        assertEquals(1.0f, restored.weight(100, 0, 0), 1e-6f);
    }

    @Test
    void snapshotIsImmutableAndNameSorted() {
        ZonePersistentState state = new ZonePersistentState();
        state.put(ZoneDefinition.parse("rtx zone define zed", 0, 0, 0));
        state.put(ZoneDefinition.parse("rtx zone define alpha", 0, 0, 0));

        Collection<ZoneDefinition> snapshot = state.snapshot();
        ArrayList<String> names = new ArrayList<>();
        snapshot.forEach(zone -> names.add(zone.name()));

        assertEquals(List.of("alpha", "zed"), names);
        assertThrows(UnsupportedOperationException.class, snapshot::clear);
    }

    @Test
    void roundTripsThroughSavedDataTypeCodec(@TempDir Path tempDir) throws Exception {
        ZoneDefinition zone = ZoneDefinition.parse(
                "rtx zone define saved --center 4 5 6 --inner 7 --outer 11", 0, 0, 0);
        ZonePersistentState state = new ZonePersistentState();
        state.put(zone);
        Path file = tempDir.resolve("zones.dat");

        // The same envelope SavedDataStorage writes: the codec's tag under "data".
        CompoundTag written = new CompoundTag();
        written.put("data", ZonePersistentState.TYPE.codec().encodeStart(NbtOps.INSTANCE, state).getOrThrow());
        NbtIo.writeCompressed(written, file);

        CompoundTag root = NbtIo.readCompressed(file, NbtAccounter.unlimitedHeap());
        ZonePersistentState loaded = ZonePersistentState.TYPE.codec()
                .parse(NbtOps.INSTANCE, root.getCompoundOrEmpty("data")).getOrThrow();
        assertEquals(List.of(zone), new ArrayList<>(loaded.snapshot()));
    }

    private static ZonePersistentState roundTrip(ZoneDefinition zone) {
        ZonePersistentState state = new ZonePersistentState();
        state.put(zone);
        CompoundTag nbt = state.toNbt();
        return ZonePersistentState.fromNbt(nbt);
    }

    private static CompoundTag writeOne(ZoneDefinition zone) {
        ZonePersistentState state = new ZonePersistentState();
        state.put(zone);
        return state.toNbt()
                .getListOrEmpty("zones")
                .getCompoundOrEmpty(0)
                .copy();
    }

}
