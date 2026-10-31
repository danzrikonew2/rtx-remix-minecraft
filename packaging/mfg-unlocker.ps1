# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$GameDir,
    [string]$JavaHome,
    [ValidateSet('Install','Disable')][string]$Mode = 'Install'
)
$ErrorActionPreference = 'Stop'
if (Get-Process -Name prismlauncher -ErrorAction SilentlyContinue) {
    throw 'Close Prism Launcher and the game before changing this addon installation.'
}
$addon = Join-Path ([IO.Path]::GetFullPath($GameDir)) 'rtx-remix-addons\mfg-unlocker'
$marker = Join-Path $addon 'enabled.txt'
if ($Mode -eq 'Disable') {
    if (Test-Path -LiteralPath $marker) { Remove-Item -LiteralPath $marker }
    Write-Output 'MFG Unlocker disabled for the next game launch.'
    exit 0
}
if (-not [Environment]::Is64BitProcess -or $env:PROCESSOR_ARCHITECTURE -eq 'ARM64') {
    throw 'This optional addon supports Windows x64 only.'
}
$dllHash = 'e6b6e6b70a6ed3af839c9647a32fc22660ae6b2d655062c5c072246c91fc10c7'
$archiveHash = '5bd19d03288e1ece1d0bb2030ac072b36758045028da192044dcaad73fd901dd'
$destination = Join-Path $addon 'MFGUnlocker.dll'
if ((Test-Path -LiteralPath $destination) -and
        (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant() -ne $dllHash) {
    throw 'An unrecognized addon DLL already exists; it was not overwritten.'
}
$privateJava = Join-Path $addon 'java'
if (-not (Test-Path -LiteralPath (Join-Path $privateJava 'bin\javaw.exe'))) {
    if (-not $JavaHome -or -not (Test-Path -LiteralPath (Join-Path $JavaHome 'bin\javaw.exe'))) {
        throw 'Provide -JavaHome pointing to a Java 25 x64 runtime for an isolated addon runtime.'
    }
    $javaSource = [IO.Path]::GetFullPath($JavaHome).TrimEnd('\')
    if ([IO.Path]::GetFullPath($privateJava).StartsWith($javaSource + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'The private Java destination cannot be inside its source runtime.'
    }
    if (Test-Path -LiteralPath $privateJava) { throw 'Incomplete private Java directory exists; nothing was overwritten.' }
    New-Item -ItemType Directory -Force -Path $addon | Out-Null
    Copy-Item -LiteralPath $JavaHome -Destination $privateJava -Recurse
}
$licenseCandidates = @((Join-Path $PSScriptRoot 'licenses\mfg-unlocker\LICENSE.txt'),
    (Join-Path $PSScriptRoot 'packaging\licenses\mfg-unlocker\LICENSE.txt'))
$license = $licenseCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $license) { throw 'The addon license notice is missing from this installer.' }
New-Item -ItemType Directory -Force -Path $addon | Out-Null
$download = [IO.Path]::GetTempFileName()
$staged = Join-Path $addon ('MFGUnlocker-' + [guid]::NewGuid().ToString('N') + '.tmp')
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/dashdogy/MFG-Unlocker/releases/download/v1.7.0/MFGUnlocker-v1.7.0.zip' -OutFile $download
    if ((Get-FileHash -LiteralPath $download -Algorithm SHA256).Hash.ToLowerInvariant() -ne $archiveHash) {
        throw 'Addon download checksum mismatch.'
    }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($download)
    try {
        $entry = $archive.GetEntry('MFGUnlocker.dll')
        if (-not $entry) { throw 'Pinned archive does not contain MFGUnlocker.dll.' }
        [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $staged)
    } finally { $archive.Dispose() }
    if ((Get-FileHash -LiteralPath $staged -Algorithm SHA256).Hash.ToLowerInvariant() -ne $dllHash) {
        throw 'Extracted addon checksum mismatch.'
    }
    Move-Item -LiteralPath $staged -Destination $destination -Force
    Copy-Item -LiteralPath $license -Destination (Join-Path $addon 'LICENSE.txt') -Force
    [IO.File]::WriteAllText($marker, '1.7.0')
    Write-Output 'Installed experimental MFG Unlocker 1.7.0 with private Java. Runtime compatibility is not yet verified.'
} finally {
    if (Test-Path -LiteralPath $download) { Remove-Item -LiteralPath $download }
    if (Test-Path -LiteralPath $staged) { Remove-Item -LiteralPath $staged }
}
exit 0
