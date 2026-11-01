# SPDX-License-Identifier: Apache-2.0
param(
    [Parameter(Mandatory=$true)][string]$MfgSource,
    [Parameter(Mandatory=$true)][string]$Inputs,
    [Parameter(Mandatory=$true)][string]$StreamlineRoot,
    [Parameter(Mandatory=$true)][string]$ImGuiRoot,
    [Parameter(Mandatory=$true)][string]$VulkanInclude,
    [Parameter(Mandatory=$true)][string]$BuildDirectory,
    [string]$CmakeExe='cmake',
    [string]$PythonExe='python',
    [string]$Generator='Visual Studio 18 2026',
    [string]$WindowsSdk='10.0.26100.0'
)
$ErrorActionPreference='Stop'
function Absolute([string]$path) { return (Resolve-Path -LiteralPath $path).Path.Replace('\','/') }
$sourceRoot=Absolute $MfgSource
$inputRoot=Absolute $Inputs
$streamline=Absolute $StreamlineRoot
$imgui=Absolute $ImGuiRoot
$vulkan=Absolute $VulkanInclude
New-Item -ItemType Directory -Path $BuildDirectory -Force | Out-Null
$buildRoot=Absolute $BuildDirectory
& $PythonExe "$PSScriptRoot/verify_headers.py" --source $sourceRoot --streamline $streamline --imgui $imgui
if ($LASTEXITCODE -ne 0) { throw 'SDK input validation failed' }
& $PythonExe "$PSScriptRoot/patch_build.py" --source $sourceRoot
if ($LASTEXITCODE -ne 0) { throw 'Native build source patch failed' }
& $PythonExe "$PSScriptRoot/patch_remix.py" --source $sourceRoot
if ($LASTEXITCODE -ne 0) { throw 'Remix host source patch failed' }
$configure=@('-S',"$sourceRoot/source/native",'-B',$buildRoot,'-G',$Generator,'-A','x64',
    "-DCMAKE_SYSTEM_VERSION=$WindowsSdk","-DSTREAMLINE_ROOT=$streamline","-DIMGUI_ROOT=$imgui",
    "-DVULKAN_INCLUDE_DIR=$vulkan","-DPython3_EXECUTABLE=$PythonExe",
    '-DMFG_UNLOCK_BUILD_SINGLE_MODULE=ON','-DMFG_UNLOCK_XESS=OFF',
    '-DMFG_AMPERE_EMBEDDED_KERNELS=ON','-DMFG_AMPERE_KERNEL_IMAGE=CUBIN',
    "-DMFG_AMPERE_NATIVE_MANIFEST=$inputRoot/ampere_native_manifest.inc",
    "-DMFG_AMPERE_NATIVE_MANIFEST_3109=$inputRoot/ampere_native_manifest_3109.inc",
    "-DMFG_AMPERE_NATIVE_MANIFEST_ADDITIONAL=$inputRoot/ampere_native_manifest_additional.inc",
    "-DMFG_AMPERE_NATIVE_RESOURCES_ADDITIONAL=$inputRoot/additional-resources.json",
    "-DMFG_AMPERE_KERNEL_DIRECTORY=$inputRoot","-DMFG_AMPERE_KERNEL_DIRECTORY_3109=$inputRoot",
    "-DMFG_AMPERE_KERNEL_DIRECTORY_ADDITIONAL=$inputRoot","-DMFG_VERIFIED_SHADER_INPUTS=$inputRoot",
    '-DMFG_UNLOCK_SESSION_DIAGNOSTICS=ON','-DMFG_UNLOCK_NGX_CREATE_RESULT_DIAGNOSTICS=ON')
& $CmakeExe @configure
if ($LASTEXITCODE -ne 0) { throw 'Native configure failed' }
& $CmakeExe --build $buildRoot --config Release --parallel 8 --target RTXMFGUnified
if ($LASTEXITCODE -ne 0) { throw 'Native build failed' }
Get-FileHash -LiteralPath "$buildRoot/Release/MFGUnlocker.dll" -Algorithm SHA256
