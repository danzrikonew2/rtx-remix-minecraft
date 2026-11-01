# SPDX-License-Identifier: MIT
# Derived from MFG-Unlocker; see LICENSE-MFG.
import argparse
import hashlib
import shutil
from pathlib import Path

parser = argparse.ArgumentParser(
    description="Apply local verified-input build support to pinned MFG source"
)
parser.add_argument("--source", type=Path, required=True)
args = parser.parse_args()
native = args.source / "source/native"
backup = args.source / ".remix-original"

PINS = {
    "CMakeLists.txt": "2722fe5ef67d887f2ebe5e3f4a0f71d3de182056dbe2b39bf927843aca609cb2",
    "generate_build_inputs.py": "fab3e55c3103574b7f031b3b8c949e153e387b4b28fec5b473bb45e75e893cce",
    "generate_dlss5_vk_shaders.py": "06a0e51935683ebe32c82fb65989ba27cbd659e2f8b9bdf92bf741e732f2ec45",
    "overlay_application_imports.cpp": "6b6f1053084590824beae5fc0540e8fa03eeb51aeebabecd759c809edaa59377",
}
for name, expected in PINS.items():
    original = backup / name if (backup / name).is_file() else native / name
    if (
        hashlib.sha256(original.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        != expected
    ):
        raise SystemExit(f"Unrecognized MFG source input: {name}")

backup.mkdir(exist_ok=True)
for name in [
    "CMakeLists.txt",
    "generate_build_inputs.py",
    "generate_dlss5_vk_shaders.py",
    "overlay_application_imports.cpp",
]:
    if not (backup / name).exists():
        shutil.copyfile(native / name, backup / name)


def replace(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"Source patch context mismatch: {old[:120]}")
    return text.replace(old, new)


def write_patch(path, text):
    current = path.read_text(encoding="utf-8")
    original = (backup / path.name).read_text(encoding="utf-8")
    if current not in (original, text):
        raise SystemExit(f"Preserving edited source; use a fresh MFG copy: {path.name}")
    path.write_text(text, encoding="utf-8", newline="\n")


p = native / "generate_build_inputs.py"
s = (backup / p.name).read_text()
s = replace(
    s,
    "parser.add_argument('--glslang', type=Path, required=True)",
    "parser.add_argument('--glslang', type=Path, required=True)\nparser.add_argument('--shader-inputs', type=Path)",
)
s = replace(
    s, "if digest(glslang) !=", "if not args.shader_inputs and digest(glslang) !="
)
s = replace(
    s,
    "    subprocess.run([str(glslang), '-V', f'-DMFG_COLOR={mode}',\n                    '-o', str(spv), str(source_dir / 'ui_color.frag')], check=True)",
    "    if args.shader_inputs:\n        shutil.copyfile(args.shader_inputs / f'ui_color_{mode}.spv', spv)\n    else:\n        subprocess.run([str(glslang), '-V', f'-DMFG_COLOR={mode}',\n                        '-o', str(spv), str(source_dir / 'ui_color.frag')], check=True)",
)
write_patch(p, s)
p = native / "generate_dlss5_vk_shaders.py"
s = (backup / p.name).read_text()
s = replace(s, "import struct\n", "import struct\nimport shutil\n")
s = replace(
    s,
    'parser.add_argument("--dxc",',
    'parser.add_argument("--shader-inputs", type=Path)\nparser.add_argument("--dxc",',
)
s = replace(
    s,
    'version = subprocess.run([str(args.dxc), "--version"], capture_output=True, text=True, check=True).stdout.strip()\nif version != PINNED_DXC:',
    'version = PINNED_DXC if args.shader_inputs else subprocess.run([str(args.dxc), "--version"], capture_output=True, text=True, check=True).stdout.strip()\nif version != PINNED_DXC:',
)
s = replace(
    s,
    '    subprocess.run([str(args.dxc), *FLAGS, "-E", entry, "-Fo", str(spv), str(hlsl)], check=True)\n    if args.spirv_val:',
    '    if args.shader_inputs:\n        shutil.copyfile(args.shader_inputs / f"{name}.spv", spv)\n    else:\n        subprocess.run([str(args.dxc), *FLAGS, "-E", entry, "-Fo", str(spv), str(hlsl)], check=True)\n    if args.spirv_val and not args.shader_inputs:',
)
write_patch(p, s)
p = native / "CMakeLists.txt"
s = (backup / p.name).read_text()
s = replace(
    s,
    "set(STREAMLINE_ROOT",
    'set(MFG_VERIFIED_SHADER_INPUTS "" CACHE PATH "Verified release shader inputs for local compatibility builds")\nset(MFG_SHADER_INPUT_ARGS)\nif(MFG_VERIFIED_SHADER_INPUTS)\n    list(APPEND MFG_SHADER_INPUT_ARGS --shader-inputs "${MFG_VERIFIED_SHADER_INPUTS}")\nendif()\nset(STREAMLINE_ROOT',
)
s = replace(
    s,
    'if(NOT EXISTS "${GLSLANG_VALIDATOR}")',
    'if(NOT MFG_VERIFIED_SHADER_INPUTS AND NOT EXISTS "${GLSLANG_VALIDATOR}")',
)
s = replace(
    s,
    '--output "${MFG_GENERATED}" --imgui "${IMGUI_ROOT}" --glslang "${GLSLANG_VALIDATOR}"',
    '--output "${MFG_GENERATED}" --imgui "${IMGUI_ROOT}" --glslang "${GLSLANG_VALIDATOR}"\n        ${MFG_SHADER_INPUT_ARGS}',
)
s = replace(
    s,
    'if(NOT EXISTS "${DLSS5_VK_DXC}")',
    'if(NOT MFG_VERIFIED_SHADER_INPUTS AND NOT EXISTS "${DLSS5_VK_DXC}")',
)
s = replace(
    s,
    '--source "${CMAKE_CURRENT_SOURCE_DIR}" --output "${MFG_GENERATED}"\n        COMMAND_ERROR_IS_FATAL ANY)\n    set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS generate_dlss5_vk_shaders.py dlss5.cpp)',
    '--source "${CMAKE_CURRENT_SOURCE_DIR}" --output "${MFG_GENERATED}"\n        ${MFG_SHADER_INPUT_ARGS}\n        COMMAND_ERROR_IS_FATAL ANY)\n    set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS generate_dlss5_vk_shaders.py dlss5.cpp)',
)
write_patch(p, s)
print("Prepared cache-backed native build; all existing shader output pins retained")
