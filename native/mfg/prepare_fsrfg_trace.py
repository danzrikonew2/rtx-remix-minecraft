# SPDX-License-Identifier: Apache-2.0
"""Stage source-only FSRFG Vulkan tracing from the pinned OptiScaler fork.

This never changes the pinned checkout or loads a GPU provider. The resulting
overlays must be rebuilt against the *exact* pinned OptiScaler dependencies
before use. Log events are diagnostics, not proof of generated scanout frames.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


PINNED_COMMIT = "aeb1f29783106b96c89ba71ce9b6db80eacdae46"
ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "build" / "optiscaler-source-pinned"
DEFAULT_OUTPUT = ROOT / "build" / "optiscaler-fsrfg-trace-source-20261109"
FFX = "OptiScaler/framegen/ffx/FSRFG_Vk.cpp"
HOOKS = "OptiScaler/hooks/Vulkan_Hooks.cpp"


def replace_once(source: str, old: str, new: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"Expected one source anchor, found {count}: {old[:100]!r}")
    return source.replace(old, new, 1)


def trace_ffx(text: str) -> str:
    text = replace_once(text, '#include "FSRFG_Vk.h"\n',
                        '#include "FSRFG_Vk.h"\n#include <functional>\n')
    text = replace_once(
        text,
        "    return _functions.pOutGetSwapchainImagesKHR(device, swapchain, pSwapchainImageCount, pSwapchainImages);",
        """    const auto result = _functions.pOutGetSwapchainImagesKHR(device, swapchain, pSwapchainImageCount,
                                                              pSwapchainImages);
    LOG_INFO("FGTRACE swapchain_images pid={} tid={} result={} count={} has_images={}",
             GetCurrentProcessId(), GetCurrentThreadId(), (int) result,
             pSwapchainImageCount != nullptr ? *pSwapchainImageCount : 0U, pSwapchainImages != nullptr);
    if ((result == VK_SUCCESS || result == VK_INCOMPLETE) && pSwapchainImageCount && pSwapchainImages)
        for (uint32_t i = 0; i < *pSwapchainImageCount; ++i)
            LOG_INFO("FGTRACE swapchain_image pid={} index={} image_hash={}", GetCurrentProcessId(), i,
                     std::hash<VkImage>{}(pSwapchainImages[i]));
    return result;""",
    )
    text = replace_once(
        text, "    return _functions.pOutQueuePresentKHR(queue, pPresentInfo);",
        """    const auto result = _functions.pOutQueuePresentKHR(queue, pPresentInfo);
    LOG_INFO("FGTRACE adapter_present pid={} tid={} result={} swapchains={}", GetCurrentProcessId(),
             GetCurrentThreadId(), (int) result, pPresentInfo ? pPresentInfo->swapchainCount : 0U);
    if (pPresentInfo && pPresentInfo->pImageIndices && pPresentInfo->pSwapchains)
        for (uint32_t i = 0; i < pPresentInfo->swapchainCount; ++i)
            LOG_INFO("FGTRACE adapter_present_image pid={} index={} swapchain_hash={} result={}",
                     GetCurrentProcessId(), pPresentInfo->pImageIndices[i],
                     std::hash<VkSwapchainKHR>{}(pPresentInfo->pSwapchains[i]), (int) result);
    return result;""",
    )
    text = replace_once(
        text,
        "ffxReturnCode_t FSRFG_Vk::DispatchCallback(ffxDispatchDescFrameGeneration* params)\n{",
        """ffxReturnCode_t FSRFG_Vk::DispatchCallback(ffxDispatchDescFrameGeneration* params)
{
    LOG_INFO("FGTRACE callback_enter pid={} tid={} frame={} requested={} reset_before={} present_color_input={}",
             GetCurrentProcessId(), GetCurrentThreadId(), params->frameID, params->numGeneratedFrames,
             params->reset, static_cast<const void*>(params->presentColor.resource));""",
    )
    text = replace_once(
        text,
        "        LOG_WARN(\"Dispatched with the same frame id! frameID: {}\", params->frameID);",
        """        LOG_INFO("FGTRACE callback_skip_duplicate pid={} frame={}", GetCurrentProcessId(), params->frameID);
        LOG_WARN("Dispatched with the same frame id! frameID: {}", params->frameID);""",
    )
    text = replace_once(
        text,
        '        LOG_WARN("Cancel dispatch, frameID: {}", params->frameID);',
        """        LOG_INFO("FGTRACE callback_cancel pid={} frame={}", GetCurrentProcessId(), params->frameID);
        LOG_WARN("Cancel dispatch, frameID: {}", params->frameID);""",
    )
    text = replace_once(
        text,
        "    DispatchHudShaders(params);\n\n    return _ffx->Dispatch(&_fgContext, &params->header);",
        """    DispatchHudShaders(params);

    LOG_INFO("FGTRACE callback_dispatch_begin pid={} tid={} frame={} requested={} reset={}",
             GetCurrentProcessId(), GetCurrentThreadId(), params->frameID, params->numGeneratedFrames,
             params->reset);
    const auto result = _ffx->Dispatch(&_fgContext, &params->header);
    LOG_INFO("FGTRACE callback_dispatch_end pid={} tid={} frame={} requested={} result={}",
             GetCurrentProcessId(), GetCurrentThreadId(), params->frameID, params->numGeneratedFrames,
             FfxApiProxy::ReturnCodeToString(result));
    return result;""",
    )
    return text


def trace_hooks(text: str) -> str:
    text = replace_once(text, "#include <unordered_map>\n",
                        "#include <unordered_map>\n#include <functional>\n")
    text = replace_once(
        text,
        "    MenuCommon::FGOutputPresent();\n    return o_QueuePresentKHR(queue, pPresentInfo);",
        """    MenuCommon::FGOutputPresent();
    const auto result = o_QueuePresentKHR(queue, pPresentInfo);
    LOG_INFO("FGTRACE provider_output_present pid={} tid={} result={} swapchains={}",
             GetCurrentProcessId(), GetCurrentThreadId(), (int) result,
             pPresentInfo ? pPresentInfo->swapchainCount : 0U);
    if (pPresentInfo && pPresentInfo->pImageIndices && pPresentInfo->pSwapchains)
        for (uint32_t i = 0; i < pPresentInfo->swapchainCount; ++i)
            LOG_INFO("FGTRACE provider_output_image pid={} index={} swapchain_hash={} result={}",
                     GetCurrentProcessId(), pPresentInfo->pImageIndices[i],
                     std::hash<VkSwapchainKHR>{}(pPresentInfo->pSwapchains[i]), (int) result);
    return result;""",
    )
    return text


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def git(source: Path, *args: str) -> str:
    completed = subprocess.run(["git", "-C", str(source), *args], check=True,
                               capture_output=True, text=True, encoding="utf-8")
    return completed.stdout.strip()


def stage(source: Path, output: Path) -> dict:
    source, output = source.resolve(), output.resolve()
    if git(source, "rev-parse", "HEAD") != PINNED_COMMIT:
        raise ValueError("OptiScaler checkout does not match the pinned source commit")
    if git(source, "status", "--porcelain"):
        raise ValueError("Pinned OptiScaler source checkout is dirty")
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing trace overlay: {output}")
    files = {}
    for relative, inject in ((FFX, trace_ffx), (HOOKS, trace_hooks)):
        original = (source / relative).read_bytes()
        patched = inject(original.decode("utf-8-sig").replace("\r\n", "\n")).encode("utf-8")
        files[relative] = (patched, {"pinned_source_sha256": sha256(original),
                                     "instrumented_sha256": sha256(patched)})
    submodules = git(source, "submodule", "status").splitlines()
    manifest = {
        "status": "SOURCE_ONLY_UNBUILT",
        "pinned_commit": PINNED_COMMIT,
        "pinned_source_checkout": str(source),
        "files": {relative: item[1] for relative, item in files.items()},
        "missing_submodules": [line.strip() for line in submodules if line.startswith("-")],
        "observations_are_not": ["GPU-completed generated output", "unique displayed pixel content",
                                 "physical scanout", "2x FPS or latency acceptance"],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".fsrfg-trace-staging-", dir=output.parent))
    try:
        for relative, (payload, _) in files.items():
            target = temporary / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
        (temporary / "trace-source-manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        temporary.rename(output)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    destination = args.output.resolve()
    if not destination.is_relative_to((ROOT / "build").resolve()):
        parser.error("Instrumented source must be staged within this repository's ignored build tree")
    report = stage(args.source, destination)
    print(json.dumps({"output": str(destination), **report}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
