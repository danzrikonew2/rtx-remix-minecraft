// SPDX-License-Identifier: Apache-2.0
#pragma once

#include <Windows.h>
#include <cstddef>
#include <cstdint>
#include "sha256_util.h"

namespace remix_runtime_profile {

enum class Id {
    unsupported,
    v0_1_0_71a581da,
    v0_1_1_a00da12a,
};

inline bool IsAmd64Pe(const uint8_t* bytes, size_t size) noexcept {
    if (!bytes || size < sizeof(IMAGE_DOS_HEADER)) return false;
    const auto* dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(bytes);
    if (dos->e_magic != IMAGE_DOS_SIGNATURE || dos->e_lfanew < 0) return false;
    const size_t ntOffset = static_cast<size_t>(dos->e_lfanew);
    if (ntOffset > size || sizeof(IMAGE_NT_HEADERS64) > size - ntOffset) return false;
    const auto* nt = reinterpret_cast<const IMAGE_NT_HEADERS64*>(bytes + ntOffset);
    return nt->Signature == IMAGE_NT_SIGNATURE
        && nt->FileHeader.Machine == IMAGE_FILE_MACHINE_AMD64
        && nt->FileHeader.SizeOfOptionalHeader >= sizeof(IMAGE_OPTIONAL_HEADER64)
        && nt->OptionalHeader.Magic == IMAGE_NT_OPTIONAL_HDR64_MAGIC;
}

inline Id Identify(const uint8_t* bytes, size_t size) noexcept {
    if (!IsAmd64Pe(bytes, size)) return Id::unsupported;
    if (sha256_util::EqualsUpperHex(bytes, size,
            "44A313F6D2A6FFA3ECCAAB683C472D14F22080BE7C61D07342D8E199A039D1AD", 512ull << 20))
        return Id::v0_1_0_71a581da;
    if (sha256_util::EqualsUpperHex(bytes, size,
            "A8365272734CF5541E3600AEACB445C0FD102187DC3A167495A56809CE5891D9", 512ull << 20))
        return Id::v0_1_1_a00da12a;
    return Id::unsupported;
}

} // namespace remix_runtime_profile
