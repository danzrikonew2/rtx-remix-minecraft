/*
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 */
import com.nvidia.rtxremix.RemixBridge;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class MatrixCopySmoke {
    public static void main(String[] args) {
        System.load(args[0]);
        float[] matrix = new float[12];
        for (int i = 0; i < matrix.length; i++) matrix[i] = i * 0.25f - 1.5f;
        for (int repeat = 0; repeat < 10000; repeat++) {
            long pointer = RemixBridge.allocDomeExt(matrix, 1234, 0.75f, 1, 0);
            if (pointer == 0) throw new AssertionError("Allocation failed");
            try {
                MemorySegment bytes = MemorySegment.ofAddress(pointer).reinterpret(80);
                for (int i = 0; i < matrix.length; i++) {
                    if (bytes.get(ValueLayout.JAVA_FLOAT, 16 + i * 4) != matrix[i])
                        throw new AssertionError("Matrix element " + i);
                }
                if (bytes.get(ValueLayout.JAVA_LONG, 64) != 1234
                        || bytes.get(ValueLayout.JAVA_FLOAT, 72) != 0.75f)
                    throw new AssertionError("Adjacent fields corrupted");
            } finally {
                RemixBridge.freeExt(pointer);
            }
        }
        try {
            RemixBridge.allocDomeExt(new float[11], 0, 1, 1, 0);
            throw new AssertionError("Short matrix accepted");
        } catch (ArrayIndexOutOfBoundsException expected) {
            System.out.println("PASS: 10,000 JNI matrix roundtrips and short-array exception");
        }
    }
}
