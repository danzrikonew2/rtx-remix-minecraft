// SPDX-License-Identifier: Apache-2.0
#include "remix_runtime_profile.h"

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <string>
#include <vector>

namespace {
bool Check(const wchar_t* path, remix_runtime_profile::Id expected) {
    std::ifstream input(std::filesystem::path(path), std::ios::binary);
    if (!input) return false;
    std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(input)), {});
    if (remix_runtime_profile::Identify(bytes.data(), bytes.size()) != expected) {
        std::wcerr << L"FAIL: runtime profile " << path << L"\n";
        return false;
    }
    return true;
}
}

int wmain(int argc, wchar_t** argv) {
    using remix_runtime_profile::Id;
    // Always validate the new runtime even when the old known-good runtime is
    // unavailable. The optional legacy input adds a backward-compatibility
    // regression without blocking v0.1.1-only CI/build environments.
    if (argc != 2 && argc != 3) {
        std::wcerr << L"Usage: MfgRuntimeProfileTests NEW_REMIX_DLL\n"
                   << L"   or: MfgRuntimeProfileTests OLD_REMIX_DLL NEW_REMIX_DLL\n";
        return 2;
    }
    const wchar_t* newRuntime = argv[argc - 1];
    if (argc == 3 && !Check(argv[1], Id::v0_1_0_71a581da)) return 1;
    if (!Check(newRuntime, Id::v0_1_1_a00da12a)) return 1;

    std::ifstream input(std::filesystem::path(newRuntime), std::ios::binary);
    if (!input) return 1;
    std::vector<uint8_t> original((std::istreambuf_iterator<char>(input)), {});
    if (original.size() < sizeof(IMAGE_NT_HEADERS64)) return 1;
    const auto* dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(original.data());
    if (dos->e_magic != IMAGE_DOS_SIGNATURE || dos->e_lfanew < 0) return 1;
    const size_t ntOffset = static_cast<size_t>(dos->e_lfanew);

    auto changed = original;
    changed[ntOffset + offsetof(IMAGE_NT_HEADERS64, OptionalHeader.CheckSum)] ^= 0x01;
    if (remix_runtime_profile::Identify(changed.data(), changed.size()) != Id::unsupported) {
        std::cerr << "FAIL: unknown SHA-256 accepted\n";
        return 1;
    }

    changed = original;
    auto* nt = reinterpret_cast<IMAGE_NT_HEADERS64*>(changed.data() + ntOffset);
    nt->FileHeader.Machine = IMAGE_FILE_MACHINE_I386;
    if (remix_runtime_profile::Identify(changed.data(), changed.size()) != Id::unsupported) {
        std::cerr << "FAIL: x86 PE accepted\n";
        return 1;
    }

    if (remix_runtime_profile::Identify(original.data(), ntOffset + sizeof(IMAGE_NT_HEADERS64) - 1)
            != Id::unsupported
        || remix_runtime_profile::Identify(nullptr, original.size()) != Id::unsupported) {
        std::cerr << "FAIL: truncated or null image accepted\n";
        return 1;
    }
    std::cout << "PASS: v0.1.1 SHA-256 PE32+ profile"
              << (argc == 3 ? ", old runtime profile" : "")
              << ", unknown hash, x86 image, truncation and null input\n";
    return 0;
}
