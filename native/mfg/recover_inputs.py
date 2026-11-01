# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: UP031
"""Recover exact build inputs from the verified public MFG 1.7.0 DLL, without loading it.

Generated kernel/shader bytes remain local build data and retain their original
license terms. This is not bit-for-bit release reproduction or an FG test.
"""

import argparse
import ast
import hashlib
import itertools
import json
import re
import struct
from pathlib import Path

RELEASE_SHA256 = "e6b6e6b70a6ed3af839c9647a32fc22660ae6b2d655062c5c072246c91fc10c7"


def recover_kernels(b, out):
    pe = struct.unpack_from("<I", b, 60)[0]
    n = struct.unpack_from("<H", b, pe + 6)[0]
    opt = pe + 24
    sz = struct.unpack_from("<H", b, pe + 20)[0]
    base = struct.unpack_from("<Q", b, opt + 24)[0]
    sections = [struct.unpack_from("<IIII", b, opt + sz + i * 40 + 8) for i in range(n)]

    def offset(rva):
        for vs, va, rs, rp in sections:
            if va <= rva < va + min(vs, rs):
                return rp + rva - va
        raise ValueError(hex(rva))

    def va_at(pos):
        for vs, va, rs, rp in sections:
            if rp <= pos < rp + rs:
                return base + va + pos - rp
        raise ValueError(pos)

    root = offset(struct.unpack_from("<I", b, opt + 112 + 16)[0])

    def entries(rel):
        pos = root + rel
        named, ids = struct.unpack_from("<HH", b, pos + 12)
        return [
            struct.unpack_from("<II", b, pos + 16 + i * 8) for i in range(named + ids)
        ]

    resources = []
    for kind, d in entries(0):
        if kind != 10:
            continue
        for rid, ld in entries(d & 0x7FFFFFFF):
            if rid & 0x80000000:
                continue
            for lang, data in entries(ld & 0x7FFFFFFF):
                rva, size, _cp, _ = struct.unpack_from("<IIII", b, root + data)
                blob = b[offset(rva) : offset(rva) + size]
                if blob[:4] == bytes.fromhex("50ed55ba"):
                    resources.append(
                        {
                            "id": rid,
                            "lang": lang,
                            "size": size,
                            "sha256": hashlib.sha256(blob).hexdigest().upper(),
                            "offset": offset(rva),
                        }
                    )
    hash_strings = {}
    for m in re.finditer(rb"(?<![0-9A-Fa-f])[0-9A-Fa-f]{64}\x00", b):
        hash_strings[va_at(m.start())] = m.group()[:-1].decode().upper()
    resource_hashes = {r["sha256"]: r for r in resources}
    entry_records = {}
    for vs, va, rs, rp in sections:
        for pos in range(rp, rp + rs - 24, 8):
            a, c, size = struct.unpack_from("<QQI", b, pos)
            if a in hash_strings and c in hash_strings:
                sha = hash_strings[c]
                if sha in resource_hashes and resource_hashes[sha]["size"] == size:
                    entry_records[va_at(pos)] = {
                        "ptx": hash_strings[a],
                        "native": sha,
                        "size": size,
                    }
    programs = []
    for vs, va, rs, rp in sections:
        for pos in range(rp, rp + rs - 40, 8):
            ea, en, ca, cn, rid = struct.unpack_from("<QQQQI", b, pos)
            if (
                ea in entry_records
                and 25 <= en <= 38
                and cn == en
                and 4000 <= rid <= 7337
            ) and all(ea + i * 24 in entry_records for i in range(en)):
                contracts = []
                try:
                    for i in range(cn):
                        co = offset(ca - base + i * 56)
                        name_ptr = struct.unpack_from("<Q", b, co)[0]
                        no = offset(name_ptr - base)
                        end = b.index(b"\0", no, no + 1024)
                        name = b[no:end].decode("ascii")
                        values = struct.unpack_from("<8I", b, co + 8)
                        meta = hash_strings[struct.unpack_from("<Q", b, co + 40)[0]]
                        count = struct.unpack_from("<I", b, co + 48)[0]
                        contracts.append(
                            {
                                "name": name,
                                "values": values,
                                "metadata_sha256": meta,
                                "parameter_count": count,
                            }
                        )
                except (ValueError, KeyError, UnicodeError):
                    continue
                programs.append(
                    {
                        "resource_base": rid,
                        "entries": [entry_records[ea + i * 24] for i in range(en)],
                        "contracts": contracts,
                    }
                )
    for r in resources:
        (out / (r["sha256"] + ".fatbin")).write_bytes(
            b[r["offset"] : r["offset"] + r["size"]]
        )
    (out / "inventory.json").write_text(
        json.dumps(
            {
                "source_sha256": hashlib.sha256(b).hexdigest(),
                "resources": resources,
                "programs": programs,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    if len(resources) != 131 or len(programs) != 13 or len(entry_records) != 387:
        raise ValueError("Pinned release inventory did not match")


def emit_manifests(root):
    data = json.loads((root / "inventory.json").read_text())

    def emit_program(program, suffix=""):
        entries = program["entries"]
        contracts = program["contracts"]
        lines = [
            f"constexpr std::array<Entry, {len(entries)}> kNativeManifest{suffix}{{{{"
        ]
        lines += [
            '    {"%s", "%s", %du},' % (e["ptx"], e["native"], e["size"])
            for e in entries
        ]
        lines += [
            "}};",
            f"constexpr std::array<NativeContract, {len(contracts)}> kNativeContracts{suffix}{{{{",
        ]
        for c in contracts:
            p, x, y, z, shared, regs, abi, flags = c["values"]
            lines.append(
                '    {%s, %du, {%du, %du, %du}, %du, %du, %du, %du, "%s", %du},'
                % (
                    json.dumps(c["name"]),
                    p,
                    x,
                    y,
                    z,
                    shared,
                    regs,
                    abi,
                    flags,
                    c["metadata_sha256"],
                    c["parameter_count"],
                )
            )
        lines += ["}};"]
        return "\n".join(lines) + "\n"

    byid = {p["resource_base"]: p for p in data["programs"]}
    for rid, filename in [
        (4000, "ampere_native_manifest.inc"),
        (4100, "ampere_native_manifest_3109.inc"),
    ]:
        (root / filename).write_text(
            "#define MFG_AMPERE_NATIVE_MANIFEST_HAS_CONTRACTS 1\n"
            + emit_program(byid[rid]),
            encoding="utf-8",
        )
    additional = [p for p in data["programs"] if p["resource_base"] >= 4200]
    text = "".join(emit_program(p, str(i)) for i, p in enumerate(additional))
    text += "constexpr NativeProgram kAdditionalNativePrograms[]{\n"
    text += "".join(
        "    {kNativeManifest%d, kNativeContracts%d, %du},\n"
        % (i, i, p["resource_base"])
        for i, p in enumerate(additional)
    )
    text += "};\n"
    manifest = root / "ampere_native_manifest_additional.inc"
    manifest.write_text(text, encoding="utf-8")
    resources = []
    for i, sha in enumerate(
        sorted({e["native"] for p in additional for e in p["entries"]})
    ):
        resources.append(
            {
                "id": 4200 + i,
                "sha256": sha,
                "bytes": (root / (sha + ".fatbin")).stat().st_size,
            }
        )
    (root / "additional-resources.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "manifest_sha256": hashlib.sha256(manifest.read_bytes())
                .hexdigest()
                .upper(),
                "resources": resources,
            },
            indent=2,
        )
    )
    # Validate every recovered contract with the unchanged upstream validator.
    harness = [
        '#include "ampere_native_cache.h"',
        "#include <fstream>",
        "#include <iterator>",
        "#include <iostream>",
        "int main(int argc,char**argv) { if(argc!=2) return 2; unsigned checked=0;",
    ]
    for p in data["programs"]:
        for e, c in zip(p["entries"], p["contracts"]):
            par, x, y, z, shared, regs, abi, flags = c["values"]
            initializer = '{%s,%du,{%du,%du,%du},%du,%du,%du,%du,"%s",%du}' % (
                json.dumps(c["name"]),
                par,
                x,
                y,
                z,
                shared,
                regs,
                abi,
                flags,
                c["metadata_sha256"],
                c["parameter_count"],
            )
            harness += [
                '{{ std::ifstream input(std::string(argv[1])+"/{}.fatbin",std::ios::binary); std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(input)),{{}}); ampere_native_cache::NativeContract contract{}; if(!ampere_native_cache::ValidateNativeContainer(bytes,contract)) {{std::cerr<<"contract failure {}";return 1;}} ++checked; }}'.format(
                    e["native"], initializer, e["native"]
                )
            ]
    harness += [
        'std::cout<<"PASS: "<<checked<<" recovered native contracts validated by upstream code\\n";return 0;}'
    ]
    (root / "validate_recovered.cpp").write_text("\n".join(harness))
    print(
        "Generated two 25-slot manifests, %d additional programs, %d deduplicated additional resources and native validation harness."
        % (len(additional), len(resources))
    )


def recover_shaders(binary, native, out):
    tree = ast.parse((native / "generate_dlss5_vk_shaders.py").read_text())
    variants = next(
        ast.literal_eval(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "VARIANTS" for t in n.targets)
    )
    wanted = {v[-1]: k for k, v in variants.items()}
    found = {}
    modules = {}
    for match in re.finditer(b"\x03\x02\x23\x07", binary):
        start = match.start()
        if start % 4 or start + 20 > len(binary):
            continue
        _magic, version, _generator, bound, reserved = struct.unpack_from(
            "<5I", binary, start
        )
        if (
            version not in (0x10000, 0x10300, 0x10500, 0x10600)
            or reserved
            or not 1 < bound < 100000
        ):
            continue
        at = start + 20
        end = None
        while at + 4 <= len(binary):
            instruction = struct.unpack_from("<I", binary, at)[0]
            count, opcode = instruction >> 16, instruction & 65535
            if not count or opcode > 6500 or at + count * 4 > len(binary):
                break
            at += count * 4
            if opcode == 56:
                end = at
                raw = binary[start:at]
                sha = hashlib.sha256(raw).hexdigest().upper()
                if sha in wanted:
                    found[wanted[sha]] = raw
        if end:
            raw = binary[start:end]
            modules[hashlib.sha256(raw).hexdigest().upper()] = raw

    header = [
        "#pragma once",
        "// Generated by generate_dlss5_vk_shaders.py from dlss5.cpp's kShader; do not edit.",
        "#include <cstdint>",
        "namespace dlss5::vulkan::spirv {",
    ]

    def array(name, raw):
        words = struct.unpack(f"<{len(raw) // 4}I", raw)
        lines = [f"inline constexpr uint32_t {name}[] = {{"]
        for at in range(0, len(words), 8):
            lines.append(
                "    " + ",".join(f"0x{w:08x}u" for w in words[at : at + 8]) + ","
            )
        return lines + ["};"]

    if set(found) != set(variants):
        raise ValueError(f"Missing shaders: {set(variants) - set(found)}")
    for name in variants:
        (out / (name + ".spv")).write_bytes(found[name])
        header += array(name, found[name])
    header += ["}"]
    (out / "dlss5_vk_spirv.h").write_text(
        "\n".join(header) + "\n", encoding="ascii", newline="\n"
    )

    # The UI compiler's exact output is pinned as a whole generated header. Test
    # permutations of three fragment modules, rather than accepting unpinned bytes.
    fragments = []
    for raw in modules.values():
        words = struct.unpack(f"<{len(raw) // 4}I", raw)
        at = 5
        while at < len(words):
            count, op = words[at] >> 16, words[at] & 65535
            if op == 15 and words[at + 1] == 4:
                fragments.append(raw)
                break
            at += count
    pin = json.loads((native / "generated_sha256.json").read_text())[
        "overlay_color_spv.h"
    ]
    for shaders in itertools.permutations(fragments, 3):
        lines = [
            "#pragma once",
            "#include <cstdint>",
            "namespace single_overlay::color {",
        ]
        for i, raw in enumerate(shaders, 1):
            lines += array(f"shader{i}", raw)
        text = "\n".join(lines + ["}"]) + "\n"
        if hashlib.sha256(text.encode()).hexdigest().upper() == pin:
            (out / "overlay_color_spv.h").write_text(
                text, encoding="ascii", newline="\n"
            )
            for i, raw in enumerate(shaders, 1):
                (out / f"ui_color_{i}.spv").write_bytes(raw)
            print(
                f"PASS: all 8 DLSS-stage shaders and pinned 3-shader UI header recovered; {len(modules)} unique SPIR-V modules"
            )
            break
    else:
        raise RuntimeError(
            f"UI shader header not found among {len(fragments)} fragment modules"
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dll", type=Path, required=True)
    parser.add_argument(
        "--source", type=Path, required=True, help="Pinned MFG source checkout root"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    binary = args.dll.read_bytes()
    if hashlib.sha256(binary).hexdigest() != RELEASE_SHA256:
        raise SystemExit(
            "Refusing unrecognized DLL; expected the unmodified public 1.7.0 release"
        )
    native = args.source / "source/native"
    if not (native / "generated_sha256.json").is_file():
        raise SystemExit("Expected MFG source/native/generated_sha256.json")
    args.output.mkdir(parents=True, exist_ok=True)
    recover_kernels(binary, args.output)
    emit_manifests(args.output)
    recover_shaders(binary, native, args.output)


if __name__ == "__main__":
    main()
