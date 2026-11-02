/*
 * SPDX-FileCopyrightText: Copyright (c) 2024-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
package com.nvidia.rtxremix.minecraft.logic;

import com.nvidia.rtxremix.minecraft.RtxRemixCommonMod;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.ListTag;
import net.minecraft.nbt.NbtAccounter;
import net.minecraft.nbt.NbtIo;
import net.minecraft.nbt.NumericTag;
import net.minecraft.resources.Identifier;
import net.minecraft.server.MinecraftServer;
import net.minecraft.util.datafix.DataFixTypes;
import net.minecraft.world.level.saveddata.SavedData;
import net.minecraft.world.level.saveddata.SavedDataType;
import net.minecraft.world.level.storage.LevelResource;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.Collection;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

/**
 * World-save owner for zones authored with {@code /rtx zone define} in an
 * integrated single-player server. The renderer consumes a copied projection
 * in {@link ZoneRegistry}; it never reads this server-thread state directly.
 *
 * <p>The state is attached to the server's save-wide storage so all
 * definitions live in one {@code data/rtx-remix-renderer/zones.dat} file, and a
 * zone is global to the save rather than scoped to a dimension. When that file
 * is absent, definitions are imported from this port's earlier 26.3 overworld
 * file, or from the 1.21.1 file, in that order. Original files stay untouched.</p>
 */
public final class ZonePersistentState extends SavedData {
    private static final Logger LOGGER = LoggerFactory.getLogger(ZonePersistentState.class);
    private static final int SCHEMA_VERSION = 1;

    private static final String VERSION_KEY = "version";
    private static final String ZONES_KEY = "zones";
    private static final String NAME_KEY = "name";
    private static final String CHANNEL_KEY = "channel";
    private static final String SHAPE_KEY = "shape";
    private static final String SPHERE_SHAPE = "sphere";
    private static final String BOX_SHAPE = "box";

    static final SavedDataType<ZonePersistentState> TYPE = new SavedDataType<>(
            Identifier.fromNamespaceAndPath(RtxRemixCommonMod.MOD_ID, "zones"),
            ZonePersistentState::new,
            CompoundTag.CODEC.xmap(ZonePersistentState::fromNbt, ZonePersistentState::toNbt),
            DataFixTypes.SAVED_DATA_COMMAND_STORAGE);

    private final Map<String, ZoneDefinition> zonesByName = new HashMap<>();
    private final boolean writable;

    ZonePersistentState() {
        this(true);
    }

    private ZonePersistentState(boolean writable) {
        this.writable = writable;
    }

    /**
     * Gets the state attached to this integrated server's world save, creating
     * it when absent. Server thread only.
     *
     * <p>Use this only on a path that is about to store a definition.
     * Read-only callers must use {@link #getIfPresent(MinecraftServer)} so a
     * world that never uses {@code /rtx zone define} is not given a state
     * object it does not need.</p>
     */
    public static ZonePersistentState getOrCreate(MinecraftServer server) {
        ZonePersistentState existing = getIfPresent(server);
        return existing != null ? existing : server.getDataStorage().computeIfAbsent(TYPE);
    }

    /**
     * The saved state for this world, or null when the world has none.
     *
     * <p>{@code zones.dat} is optional: a map can define its zones
     * entirely with command blocks, which are stored as blocks in the region
     * files and never touch this state. Reading through the nullable lookup
     * keeps that structural rather than incidental. Minecraft would not write
     * an un-dirtied state either way, but this way an unused world is not
     * handed a state object at all, and nothing about the published world
     * depends on that behavior staying as it is.</p>
     */
    public static ZonePersistentState getIfPresent(MinecraftServer server) {
        ZonePersistentState state = server.getDataStorage().get(TYPE);
        if (state != null) return state;
        ZonePersistentState recovered = recoverPriorState(server.getWorldPath(LevelResource.ROOT));
        if (recovered == null) return null;
        server.getDataStorage().set(TYPE, recovered);
        // SavedDataStorage.set dirties even a read-only state. A failed/future
        // file must remain protected rather than being serialized as empty.
        if (!recovered.writable) recovered.setDirty(false);
        return recovered;
    }

    /** Called only after save-wide lookup returned null; never merges or overwrites a current file. */
    static ZonePersistentState recoverPriorState(Path saveRoot) {
        Path current = saveRoot.resolve("data").resolve(RtxRemixCommonMod.MOD_ID).resolve("zones.dat");
        if (Files.exists(current)) {
            LOGGER.warn("Could not load current RTX zone file {}; preserving it and blocking edits", current);
            return new ZonePersistentState(false);
        }
        Path previous = saveRoot.resolve("dimensions/minecraft/overworld/data")
                .resolve(RtxRemixCommonMod.MOD_ID).resolve("zones.dat");
        Path legacy = saveRoot.resolve("data/rtx_remix_zones.dat");
        Path source = Files.exists(previous) ? previous : Files.exists(legacy) ? legacy : null;
        if (source == null) return null;
        try {
            CompoundTag envelope = NbtIo.readCompressed(source, NbtAccounter.unlimitedHeap());
            ZonePersistentState state = fromNbt(envelope.getCompoundOrEmpty("data"));
            if (state.writable) LOGGER.info("Imported {} RTX zone(s) from {}; original file preserved",
                    state.zonesByName.size(), source);
            return state;
        } catch (IOException | RuntimeException e) {
            LOGGER.warn("Could not read prior RTX zone file {}; preserving it and blocking edits: {}",
                    source, e.getMessage());
            return new ZonePersistentState(false);
        }
    }

    /** Immutable, name-sorted copy safe to publish to the client/render registry. */
    public Collection<ZoneDefinition> snapshot() {
        ArrayList<ZoneDefinition> zones = new ArrayList<>(zonesByName.values());
        zones.sort(Comparator.comparing(ZoneDefinition::name));
        return List.copyOf(zones);
    }

    /** Adds or replaces a definition and dirties the save only for an effective change. */
    public boolean put(ZoneDefinition zone) {
        requireWritable();
        Objects.requireNonNull(zone, "zone");
        ZoneDefinition previous = zonesByName.get(zone.name());
        if (zone.equals(previous)) {
            return false;
        }
        zonesByName.put(zone.name(), zone);
        setDirty();
        return true;
    }

    /** Removes a saved definition and dirties the save only when it existed. */
    public boolean remove(String name) {
        requireWritable();
        if (zonesByName.remove(name) == null) {
            return false;
        }
        setDirty();
        return true;
    }

    CompoundTag toNbt() {
        CompoundTag nbt = new CompoundTag();
        nbt.putInt(VERSION_KEY, SCHEMA_VERSION);
        ListTag zones = new ListTag();
        for (ZoneDefinition zone : snapshot()) {
            zones.add(writeZone(zone));
        }
        nbt.put(ZONES_KEY, zones);
        return nbt;
    }

    static ZonePersistentState fromNbt(CompoundTag nbt) {
        if (nbt.getInt(VERSION_KEY).isEmpty()) {
            LOGGER.warn("Ignoring RTX Remix zone state without a schema version");
            return new ZonePersistentState(false);
        }
        int version = nbt.getIntOr(VERSION_KEY, 0);
        if (version != SCHEMA_VERSION) {
            LOGGER.warn("Ignoring RTX Remix zone state schema version {} (expected {})",
                    version, SCHEMA_VERSION);
            return new ZonePersistentState(false);
        }
        ZonePersistentState state = new ZonePersistentState();
        if (!(nbt.get(ZONES_KEY) instanceof ListTag zones)) {
            return state;
        }

        for (int i = 0; i < zones.size(); i++) {
            try {
                if (!(zones.get(i) instanceof CompoundTag zoneNbt)) {
                    throw new IllegalArgumentException("not a compound");
                }
                ZoneDefinition zone = readZone(zoneNbt);
                ZoneDefinition previous = state.zonesByName.put(zone.name(), zone);
                if (previous != null) {
                    LOGGER.warn("Duplicate saved RTX Remix zone '{}'; using the last definition", zone.name());
                }
            } catch (IllegalArgumentException e) {
                LOGGER.warn("Ignoring malformed saved RTX Remix zone at index {}: {}", i, e.getMessage());
            }
        }
        return state;
    }

    private void requireWritable() {
        if (!writable) {
            throw new IllegalStateException(
                    "saved zone data is unreadable or uses an unsupported schema; refusing to overwrite it");
        }
    }

    private static CompoundTag writeZone(ZoneDefinition zone) {
        CompoundTag nbt = new CompoundTag();
        nbt.putString(NAME_KEY, zone.name());
        nbt.putString(CHANNEL_KEY, zone.channel());
        if (zone.isBox()) {
            nbt.putString(SHAPE_KEY, BOX_SHAPE);
            nbt.putDouble("minX", zone.minX());
            nbt.putDouble("minY", zone.minY());
            nbt.putDouble("minZ", zone.minZ());
            nbt.putDouble("maxX", zone.maxX());
            nbt.putDouble("maxY", zone.maxY());
            nbt.putDouble("maxZ", zone.maxZ());
            nbt.putDouble("fade", zone.fade());
        } else {
            nbt.putString(SHAPE_KEY, SPHERE_SHAPE);
            nbt.putDouble("centerX", zone.centerX());
            nbt.putDouble("centerY", zone.centerY());
            nbt.putDouble("centerZ", zone.centerZ());
            nbt.putDouble("innerRadius", zone.innerRadius());
            nbt.putDouble("outerRadius", zone.outerRadius());
        }
        return nbt;
    }

    private static ZoneDefinition readZone(CompoundTag nbt) {
        String name = requireString(nbt, NAME_KEY);
        String channel = requireString(nbt, CHANNEL_KEY);
        String shape = requireString(nbt, SHAPE_KEY);
        return switch (shape) {
            case SPHERE_SHAPE -> ZoneDefinition.storedSphere(name, channel,
                    requireDouble(nbt, "centerX"),
                    requireDouble(nbt, "centerY"),
                    requireDouble(nbt, "centerZ"),
                    requireDouble(nbt, "innerRadius"),
                    requireDouble(nbt, "outerRadius"));
            case BOX_SHAPE -> ZoneDefinition.storedBox(name, channel,
                    requireDouble(nbt, "minX"),
                    requireDouble(nbt, "minY"),
                    requireDouble(nbt, "minZ"),
                    requireDouble(nbt, "maxX"),
                    requireDouble(nbt, "maxY"),
                    requireDouble(nbt, "maxZ"),
                    requireDouble(nbt, "fade"));
            default -> throw new IllegalArgumentException("unknown shape '" + shape + "'");
        };
    }

    private static String requireString(CompoundTag nbt, String key) {
        return nbt.getString(key).orElseThrow(
                () -> new IllegalArgumentException("missing string '" + key + "'"));
    }

    private static double requireDouble(CompoundTag nbt, String key) {
        if (!(nbt.get(key) instanceof NumericTag number)) {
            throw new IllegalArgumentException("missing number '" + key + "'");
        }
        return number.doubleValue();
    }
}
