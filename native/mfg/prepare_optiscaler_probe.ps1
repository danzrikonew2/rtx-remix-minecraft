# SPDX-License-Identifier: Apache-2.0
<#
.SYNOPSIS
  Prepare a pinned, disposable OptiScaler+MFG Vulkan probe directory.
.DESCRIPTION
  Downloads checksum-pinned OptiScaler nightly and fork files. Extracts the
  verified nightly with Windows tar.exe (or 7z.exe fallback), then stages the
  pinned fork, local MFG candidate, Streamline 2.14.1 runtime binaries,
  available nvngx_dlss*.dll from the exact Remix runtime, probe executable,
  and local RTX config. It configures only the disposable probe INI.
  This script NEVER launches any native DLL, installs the game, changes Prism,
  overwrites an existing prepared directory, or edits game configuration.
#>
[CmdletBinding()]
param(
    [string]$RepoRoot,
    [string]$PythonExe
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Join-Path $PSScriptRoot '..\..'
}
$root = [IO.Path]::GetFullPath($RepoRoot)
$build = Join-Path $root 'build'
$cache = Join-Path $build 'mfg-downloads'
$destination = Join-Path $build 'mfg-optiscaler-probe'
$stage = Join-Path $build ('mfg-opti-staging-' + [guid]::NewGuid().ToString('N'))
$package = Join-Path $stage 'Package'
$extract = Join-Path $stage 'extracted'
$candidate = Join-Path $build 'mfg-native\Release\MFGUnlocker.dll'
$runtimeDir = Join-Path $root 'remix-runtime\win64'
$runtime = Join-Path $runtimeDir 'd3d9.dll'
$sdkBin = Join-Path $build 'streamline\bin\x64'
$probe = Join-Path $build 'mfg-profile-checks\Release\OptiRemixProbe.exe'
$javaProbe = Join-Path $build 'mfg-profile-checks\Release\MfgJavaHostProbe.dll'
$configurator = Join-Path $root 'native\mfg\configure_probe_ini.py'
$expectedMfg = '017a80c6e82bf275eb6ef6c852a4cc8fb38c933647f6546b1fc231f8c87409cd'
$expectedRemix = 'a8365272734cf5541e3600aeacb445c0fd102187dc3a167495a56809ce5891d9'
$expectedFork = '0b70d723f61fcf1cc38c26e4033666bd08936f435a848f624222c77dc86ca7fe'

function Assert-Hash([string]$path, [string]$expected) {
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required file missing: $path"
    }
    $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $expected) {
        throw "SHA-256 mismatch for $path; expected $expected, got $actual"
    }
}
function Fetch-PinnedFile([string]$filename, [string]$url, [string]$sha256) {
    $path = Join-Path $cache $filename
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) {
        $temporary = Join-Path $cache ($filename + '.' + [guid]::NewGuid().ToString('N') + '.download')
        try {
            Write-Output "Downloading pinned asset: $filename"
            Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $temporary
            Assert-Hash $temporary $sha256
            [IO.File]::Move($temporary, $path)
        } finally {
            if (Test-Path -LiteralPath $temporary) {
                Remove-Item -LiteralPath $temporary -Force
            }
        }
    }
    Assert-Hash $path $sha256
    return $path
}
function Copy-Safe([string]$source, [string]$target) {
    if (!(Test-Path -LiteralPath $source -PathType Leaf)) { throw "Missing source: $source" }
    Copy-Item -LiteralPath $source -Destination $target -Force
}

if (Test-Path -LiteralPath $destination) {
    throw "Preserving existing isolated probe directory. Choose a fresh checkout or move it aside first: $destination"
}
if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    $PythonExe = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
}
if (!(Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw "Python 3.12 missing: $PythonExe"
}
foreach ($f in @($candidate,$runtime,$probe,$javaProbe,$configurator)) {
    if (!(Test-Path -LiteralPath $f -PathType Leaf)) {
        throw "Required MFG build or runtime file missing: $f"
    }
}
Assert-Hash $candidate $expectedMfg
Assert-Hash $runtime $expectedRemix
foreach ($filename in @('sl.interposer.dll','sl.common.dll','sl.dlss_g.dll','NvLowLatencyVk.dll')) {
    if (!(Test-Path -LiteralPath (Join-Path $sdkBin $filename) -PathType Leaf)) {
        throw "Pinned Streamline 2.14.1 runtime binary missing: $filename in $sdkBin"
    }
}
$runtimeProviders = @(Get-ChildItem -LiteralPath $runtimeDir -File -Filter 'nvngx_dlss*.dll')
if (!$runtimeProviders.Count) {
    Write-Warning "No nvngx_dlss*.dll found in $runtimeDir; will require provider files from the verified nightly."
}
New-Item -ItemType Directory -Path $cache -Force | Out-Null
New-Item -ItemType Directory -Path $stage,$package,$extract -Force | Out-Null
try {
    $nightly = Fetch-PinnedFile 'OptiScaler_v10.0.0-pre1_20261024.7z' `
        'https://github.com/optiscaler/OptiScaler-nightly/releases/download/nightly-20261024/OptiScaler_v10.0.0-pre1_20261024.7z' `
        '74f20189e0ec76288c86d69057b3feb4750f4680118a9852fb743b343274ac1d'
    $fork = Fetch-PinnedFile 'MFG-OptiScaler-v1.7.0.dll' `
        'https://github.com/dashdogy/OptiScaler/releases/download/mfgunlocker-v1.7.0/OptiScaler.dll' `
        $expectedFork
    $forkLicense = Fetch-PinnedFile 'MFG-OptiScaler-v1.7.0-LICENSE' `
        'https://github.com/dashdogy/OptiScaler/releases/download/mfgunlocker-v1.7.0/LICENSE' `
        '3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986'
    $forkSource = Fetch-PinnedFile 'MFG-OptiScaler-v1.7.0-SOURCE.txt' `
        'https://github.com/dashdogy/OptiScaler/releases/download/mfgunlocker-v1.7.0/SOURCE.txt' `
        'f80ae294870180eb4c733330b6bdcbd0f1d80a825ed20ca28f2640f2053f726d'

    # Windows 11's libarchive tar.exe normally reads 7z archives. Fall back
    # to an existing local 7-Zip executable; never download an extractor.
    $extracted = $false
    $tar = Get-Command tar.exe -ErrorAction SilentlyContinue
    if ($tar) {
        Write-Output 'Extracting verified nightly with Windows tar.exe...'
        try {
            & $tar.Source -xf $nightly -C $extract 2>$null
            $extracted = ($LASTEXITCODE -eq 0)
        } catch {
            $extracted = $false
        }
    }
    if (!$extracted) {
        $seven = Get-Command 7z.exe -ErrorAction SilentlyContinue
        $sevenPath = if ($seven) { $seven.Source } else { 'C:\Program Files\7-Zip\7z.exe' }
        if (!(Test-Path -LiteralPath $sevenPath -PathType Leaf)) {
            throw 'Windows tar could not extract this 7z file. Install the official 7-Zip app, then rerun; verified downloads are cached.'
        }
        Write-Output 'Extracting verified nightly with installed 7-Zip...'
        & $sevenPath x "-o$extract" '-y' $nightly
        if ($LASTEXITCODE -ne 0) { throw "7-Zip extraction failed with code $LASTEXITCODE" }
    }

    $candidates = @(Get-ChildItem -LiteralPath $extract -File -Recurse -Filter 'OptiScaler.ini' |
        Where-Object {
            (Test-Path -LiteralPath (Join-Path $_.Directory.FullName 'OptiScaler') -PathType Container) -and
            (Test-Path -LiteralPath (Join-Path $_.Directory.FullName 'Licenses') -PathType Container)
        })
    if ($candidates.Count -ne 1) {
        throw "Nightly archive has $($candidates.Count) recognized OptiScaler package roots, expected exactly one."
    }
    $nightlyRoot = $candidates[0].Directory.FullName
    Get-ChildItem -LiteralPath $nightlyRoot -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $package -Recurse -Force
    }
    Copy-Safe $fork (Join-Path $package 'OptiScaler.dll')
    Copy-Safe $forkLicense (Join-Path $stage 'LICENSE')
    Copy-Safe $forkSource (Join-Path $stage 'SOURCE.txt')
    Copy-Safe $forkLicense (Join-Path $package 'Licenses\MFG-OptiScaler-GPL3-LICENSE.txt')
    Copy-Safe $forkSource (Join-Path $package 'Licenses\MFG-OptiScaler-SOURCE.txt')
    $optiRoot = Join-Path $package 'OptiScaler'
    $streamline = Join-Path $optiRoot 'streamline'
    $plugins = Join-Path $optiRoot 'plugins'
    New-Item -ItemType Directory -Path $streamline,$plugins -Force | Out-Null
    # Copy all signed runtime plugins from the exact pinned SDK, never from
    # arbitrary system directories. Preserve notices shipped with the nightly.
    $slDlls = @(Get-ChildItem -LiteralPath $sdkBin -File -Filter 'sl.*.dll')
    foreach ($dll in $slDlls) {
        Copy-Safe $dll.FullName (Join-Path $streamline $dll.Name)
    }
    Copy-Safe (Join-Path $sdkBin 'NvLowLatencyVk.dll') (Join-Path $streamline 'NvLowLatencyVk.dll')
    $licenseTxt = @(Get-ChildItem -LiteralPath $sdkBin -File -Filter '*license*.txt')
    foreach ($notice in $licenseTxt) {
        Copy-Safe $notice.FullName (Join-Path $streamline $notice.Name)
    }
    # The runtime is SHA-256 pinned before reading these files. No NVIDIA
    # provider is downloaded from an unrelated modding or OTA mirror.
    foreach ($provider in $runtimeProviders) {
        Copy-Safe $provider.FullName (Join-Path $optiRoot $provider.Name)
        Copy-Safe $provider.FullName (Join-Path $streamline $provider.Name)
    }
    if (!(Test-Path -LiteralPath (Join-Path $optiRoot 'nvngx_dlssnr.dll') -PathType Leaf)) {
        throw 'No nvngx_dlssnr.dll in the pinned runtime or nightly. Do not substitute an unverified third-party provider.'
    }
    Copy-Safe $candidate (Join-Path $plugins 'MFGUnlocker.asi')
    Copy-Safe $probe (Join-Path $package 'OptiRemixProbe.exe')
    Copy-Safe $javaProbe (Join-Path $package 'MfgJavaHostProbe.dll')
    Copy-Safe (Join-Path $root 'packaging\rtx.conf') (Join-Path $package 'rtx.conf')

    & $PythonExe $configurator --ini (Join-Path $package 'OptiScaler.ini') --package $package
    if ($LASTEXITCODE -ne 0) { throw "Probe INI configuration failed with exit code $LASTEXITCODE" }
    Assert-Hash (Join-Path $package 'OptiScaler.dll') $expectedFork
    Assert-Hash (Join-Path $plugins 'MFGUnlocker.asi') $expectedMfg

    $metadata = [ordered]@{
        schema = 1
        mode = 'local isolated native OptiScaler Vulkan probe, not Minecraft installation'
        nightly_archive_sha256 = '74f20189e0ec76288c86d69057b3feb4750f4680118a9852fb743b343274ac1d'
        optiscaler_fork_sha256 = $expectedFork
        mfg_candidate_sha256 = $expectedMfg
        remix_runtime_sha256 = $expectedRemix
        streamline_sdk = '2.14.1'
        status = 'staged only; GPU FG and displayed frames unverified'
    }
    $metadata | ConvertTo-Json -Depth 4 | Out-File -LiteralPath (Join-Path $stage 'probe-inputs.json') -Encoding UTF8

    # Staging is isolated until all required hashes and source files pass.
    if (Test-Path -LiteralPath $destination) { throw "Destination appeared while staging: $destination" }
    [IO.Directory]::Move($stage, $destination)
    Write-Output 'PASS: pinned OptiScaler native probe package staged without running DLLs.'
    Write-Output "Probe root: $destination"
    Write-Output "Run directory: $(Join-Path $destination 'Package')"
    Write-Output 'OptiScaler configured for DLSSG x2; actual generated/presented frames remain unverified.'
    Write-Warning 'Do not copy this package into a working Prism instance. Next gate is isolated GPU presentation.'
} finally {
    if (Test-Path -LiteralPath $stage -PathType Container) {
        Remove-Item -LiteralPath $stage -Recurse -Force
    }
}
