# SPDX-License-Identifier: Apache-2.0
<#
.SYNOPSIS
  Recover locally pinned MFG 1.7.0 native build inputs without loading its DLL.
.DESCRIPTION
  Reuses or downloads the exact public MFG 1.7.0 archive, verifies GitHub's
  SHA-256 asset digest and the inner DLL's repository-pinned SHA-256, then runs
  recover_inputs.py against the already pinned, disposable MFG source checkout.
  Never launches Minecraft, installs a game addon, or ships third-party binaries.
#>
[CmdletBinding()]
param(
    [string]$RepoRoot,
    [string]$PythonExe = 'python'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# $PSScriptRoot may not be populated while PowerShell binds parameter
# default expressions. Resolve the script's directory after binding.
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Join-Path $PSScriptRoot '..\..'
}
$root = [IO.Path]::GetFullPath($RepoRoot)
$source = Join-Path $root 'build\mfg-source'
$sourcePin = Join-Path $source 'source\native\generated_sha256.json'
$recoveryScript = Join-Path $root 'native\mfg\recover_inputs.py'
$downloadDirectory = Join-Path $root 'build\mfg-downloads'
$archive = Join-Path $downloadDirectory 'MFGUnlocker-v1.7.0.zip'
$dll = Join-Path $downloadDirectory 'MFGUnlocker.dll'
$output = Join-Path $root 'build\mfg-inputs'
$staging = Join-Path $root ('build\mfg-inputs.staging-' + [guid]::NewGuid().ToString('N'))
$archiveUrl = 'https://github.com/dashdogy/MFG-Unlocker/releases/download/v1.7.0/MFGUnlocker-v1.7.0.zip'
$archiveHash = '5bd19d03288e1ece1d0bb2030ac072b36758045028da192044dcaad73fd901dd'
$dllHash = 'e6b6e6b70a6ed3af839c9647a32fc22660ae6b2d655062c5c072246c91fc10c7'

function Assert-Hash([string]$path, [string]$hash) {
    $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $hash) {
        throw "SHA-256 mismatch for $path. Expected $hash; got $actual. Refusing to proceed."
    }
}

if (!(Test-Path -LiteralPath $sourcePin -PathType Leaf)) {
    throw "Missing pinned MFG source checkout or generated_sha256.json: $sourcePin"
}
if (!(Test-Path -LiteralPath $recoveryScript -PathType Leaf)) {
    throw "Missing trusted recovery script: $recoveryScript"
}
if (!(Get-Command $PythonExe -ErrorAction SilentlyContinue)) {
    throw "Python is unavailable as '$PythonExe'; use -PythonExe ABSOLUTE_PYTHON_EXE"
}
if (Test-Path -LiteralPath $output) {
    $required = @('ampere_native_manifest.inc',
                  'ampere_native_manifest_3109.inc',
                  'ampere_native_manifest_additional.inc',
                  'additional-resources.json', 'validate_recovered.cpp',
                  'inventory.json', 'dlss5_vk_spirv.h', 'overlay_color_spv.h')
    $missing = @($required | Where-Object {
        !(Test-Path -LiteralPath (Join-Path $output $_) -PathType Leaf)
    })
    if ($missing.Count -eq 0) {
        Write-Output 'Recovered MFG inputs already exist. Keeping them unchanged.'
        Write-Output "Inputs: $output"
        exit 0
    }
    throw "Existing incomplete MFG inputs at $output; refusing overwrite. Missing: $($missing -join ', ')"
}

New-Item -ItemType Directory -Path $downloadDirectory -Force | Out-Null
if (!(Test-Path -LiteralPath $archive -PathType Leaf)) {
    $temporary = Join-Path $downloadDirectory ('download-' + [guid]::NewGuid().ToString('N') + '.zip')
    try {
        Invoke-WebRequest -Uri $archiveUrl -UseBasicParsing -OutFile $temporary
        Assert-Hash $temporary $archiveHash
        [IO.File]::Move($temporary, $archive)
    }
    finally {
        if (Test-Path -LiteralPath $temporary) {
            Remove-Item -LiteralPath $temporary -Force
        }
    }
}
Assert-Hash $archive $archiveHash

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [IO.Compression.ZipFile]::OpenRead($archive)
try {
    $entry = $zip.GetEntry('MFGUnlocker.dll')
    if ($null -eq $entry) {
        throw 'Verified release archive is missing its expected MFGUnlocker.dll entry.'
    }
    if (!(Test-Path -LiteralPath $dll -PathType Leaf)) {
        [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $dll)
    }
}
finally {
    $zip.Dispose()
}
Assert-Hash $dll $dllHash

New-Item -ItemType Directory -Path $staging -Force | Out-Null
try {
    & $PythonExe $recoveryScript --dll $dll --source $source --output $staging
    if ($LASTEXITCODE -ne 0) {
        throw "MFG input recovery failed: Python exit $LASTEXITCODE"
    }
    $required = @('ampere_native_manifest.inc',
                  'ampere_native_manifest_3109.inc',
                  'ampere_native_manifest_additional.inc',
                  'additional-resources.json', 'validate_recovered.cpp',
                  'inventory.json', 'dlss5_vk_spirv.h', 'overlay_color_spv.h')
    foreach ($filename in $required) {
        if (!(Test-Path -LiteralPath (Join-Path $staging $filename) -PathType Leaf)) {
            throw "Recovery did not generate $filename"
        }
    }
    if (Test-Path -LiteralPath $output) {
        throw "Another process created $output; preserving it."
    }
    [IO.Directory]::Move($staging, $output)
}
finally {
    if (Test-Path -LiteralPath $staging) {
        Remove-Item -LiteralPath $staging -Recurse -Force
    }
}

Write-Output "PASS: pinned MFG 1.7.0 archive and DLL SHA-256; recovered native inputs."
Write-Output "Downloaded DLL (build-only input): $dll"
Write-Output "Recovered manifests, shaders, and validator: $output"
Write-Output 'Remaining SDK inputs: Streamline 2.14.1, pinned ImGui, Vulkan-Headers 1.2.176.'
Write-Warning 'MFGUnlocker.dll was not rebuilt. FG presentation remains unverified.'
