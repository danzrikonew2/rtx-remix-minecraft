# SPDX-License-Identifier: Apache-2.0
<#
.SYNOPSIS
  Verify and package the locally built MFG candidate into an opt-in test ZIP.
.DESCRIPTION
  Reconfigures/compiles CPU-only native tests, including exact v0.1.1 runtime
  host registration and two fake d3d9.dll negative controls. A passing test
  creates a separate local installable development ZIP based on the already
  verified release archive, with the custom DLL under experimental/mfg/.
  Does not modify the standard release ZIP, install or launch Minecraft,
  change Prism, or upload any binary to GitHub.
#>
[CmdletBinding()]
param(
    [string]$RepoRoot,
    [string]$BaseArchive,
    [string]$CmakeExe = 'C:\Program Files\Microsoft Visual Studio\18\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe',
    [string]$CtestExe = 'C:\Program Files\Microsoft Visual Studio\18\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\ctest.exe',
    [string]$ExpectedCandidateSha256 = '017a80c6e82bf275eb6ef6c852a4cc8fb38c933647f6546b1fc231f8c87409cd'
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Join-Path $PSScriptRoot '..\..'
}
$root = [IO.Path]::GetFullPath($RepoRoot)
$source = Join-Path $root 'build\mfg-source'
$inputs = Join-Path $root 'build\mfg-inputs'
$candidate = Join-Path $root 'build\mfg-native\Release\MFGUnlocker.dll'
$runtime = Join-Path $root 'remix-runtime\win64\d3d9.dll'
$checks = Join-Path $root 'build\mfg-profile-checks'
$distributions = Join-Path $root 'build\distributions'
$runtimePin = 'a8365272734cf5541e3600aeacb445c0fd102187dc3a167495a56809ce5891d9'

function Assert-Hash([string]$file, [string]$sha256) {
    if (!(Test-Path -LiteralPath $file -PathType Leaf)) {
        throw "Missing required build file: $file"
    }
    $actual = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $sha256) {
        throw "SHA-256 mismatch for $file; expected $sha256; actual $actual"
    }
}
function Run-Step([string]$label, [string]$program, [string[]]$parameters) {
    Write-Output "Running: $label"
    & $program @parameters
    if ($LASTEXITCODE -ne 0) { throw "$label failed with exit code $LASTEXITCODE" }
}
function Add-ArchiveFile($zip, [string]$entryName, [string]$sourceFile) {
    $item = $zip.CreateEntry($entryName, [IO.Compression.CompressionLevel]::Optimal)
    $stream = $item.Open()
    $sourceStream = [IO.File]::OpenRead($sourceFile)
    try { $sourceStream.CopyTo($stream) }
    finally { $sourceStream.Dispose(); $stream.Dispose() }
}
function Add-ArchiveText($zip, [string]$entryName, [string]$body) {
    $item = $zip.CreateEntry($entryName, [IO.Compression.CompressionLevel]::Optimal)
    $stream = $item.Open()
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes($body)
    try { $stream.Write($bytes, 0, $bytes.Length) }
    finally { $stream.Dispose() }
}
if ($ExpectedCandidateSha256 -notmatch '^[a-fA-F0-9]{64}$') {
    throw 'ExpectedCandidateSha256 must be a full SHA-256 hex digest.'
}
$expected = $ExpectedCandidateSha256.ToLowerInvariant()
Assert-Hash $candidate $expected
Assert-Hash $runtime $runtimePin
if (!(Test-Path -LiteralPath (Join-Path $source 'source\native\CMakeLists.txt') -PathType Leaf)) {
    throw 'MFG native source checkout missing.'
}
if (!(Test-Path -LiteralPath (Join-Path $inputs 'validate_recovered.cpp') -PathType Leaf)) {
    throw 'Recovered MFG contracts missing.'
}
foreach ($toolPath in @($CmakeExe, $CtestExe)) {
    if (!(Test-Path -LiteralPath $toolPath -PathType Leaf)) { throw "Missing build tool: $toolPath" }
}

# Force the current runtime/candidate paths into the existing CMake cache.
# Never select a previously cached, stale runtime or MFG binary.
$configure = @('-S',(Join-Path $root 'native\mfg'),'-B',$checks,
    "-DMFG_SOURCE=$source","-DMFG_INPUTS=$inputs",
    "-DMFG_DLL=$candidate","-DREMIX_DLL=$runtime","-DOLD_REMIX_DLL=")
Run-Step 'CMake native-test configuration' $CmakeExe $configure
Run-Step 'Compile native contracts, profile and host/negative controls' $CmakeExe @(
    '--build',$checks,'--config','Release','--target',
    'MfgRecoveredContracts','MfgRuntimeProfileTests','MfgRemixHostSmoke',
    'MfgNoRemixApi','MfgUnknownRemixApi'
)
Run-Step 'Pinned runtime, recovered contracts and native host registration' $CtestExe @(
    '--test-dir',$checks,'-C','Release','-R',
    '^(recovered_contracts|remix_runtime_profiles|remix_host_registration)$',
    '--output-on-failure','--no-tests=error'
)

# More than one old release ZIP is expected after multiple builds. Accept an
# explicit file path, but never silently choose one by modification time.
if (![string]::IsNullOrWhiteSpace($BaseArchive)) {
    $releasePath = if ([IO.Path]::IsPathRooted($BaseArchive)) {
        [IO.Path]::GetFullPath($BaseArchive)
    } else {
        [IO.Path]::GetFullPath((Join-Path $root $BaseArchive))
    }
    if (!(Test-Path -LiteralPath $releasePath -PathType Leaf) -or
            ![string]::Equals([IO.Path]::GetExtension($releasePath), '.zip', [StringComparison]::OrdinalIgnoreCase)) {
        throw "BaseArchive is not an existing ZIP file: $releasePath"
    }
    $release = Get-Item -LiteralPath $releasePath
} else {
    $archives = @(Get-ChildItem -LiteralPath $distributions -File -Filter '*.zip' |
        Where-Object { $_.Name -notmatch '(?i)mfg-experimental' } |
        Sort-Object LastWriteTime -Descending)
    if ($archives.Count -ne 1) {
        $available = ($archives | ForEach-Object { $_.Name }) -join ', '
        throw "Found $($archives.Count) ordinary installer ZIPs. Choose one explicitly with -BaseArchive. Available: $available"
    }
    $release = $archives[0]
}
if ($release.Name -match '(?i)mfg-experimental') {
    throw 'BaseArchive must be the original installer ZIP, not an experimental package.'
}
if ($release.Name -notmatch '(?i)^rtx-remix-renderer-.*-win64\.zip$') {
    throw "BaseArchive must be an original Windows x64 RTX Remix installer ZIP: $($release.Name)"
}
Write-Output "Selected base installer: $($release.FullName)"
$version = (& git.exe -C $root rev-parse --short=9 HEAD)
if ($LASTEXITCODE -ne 0 -or !$version) { throw 'Unable to read Git commit identity.' }
$outFile = Join-Path $distributions ($release.BaseName + '-mfg-experimental-' + $version.Trim() + '.zip')
if (Test-Path -LiteralPath $outFile) {
    throw "Existing experimental artifact preserved. No overwrite: $outFile"
}
$tempFile = $outFile + '.' + [guid]::NewGuid().ToString('N') + '.tmp'
$license = Join-Path $root 'native\mfg\LICENSE-MFG'
if (!(Test-Path -LiteralPath $license -PathType Leaf)) {
    throw 'MFG adapter license notice missing.'
}
$reader = $null
$writer = $null
try {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $reader = [IO.Compression.ZipFile]::OpenRead($release.FullName)
    $existing = @($reader.Entries | Where-Object { $_.FullName.StartsWith('experimental/mfg/', [StringComparison]::OrdinalIgnoreCase) })
    if ($existing.Count) { throw 'Base release already has experimental/mfg payload; refusing duplication.' }
    # Refuse source archives/unrelated ZIPs even if the filename resembles a
    # release. Every candidate must be built on the real Minecraft installer.
    $entryNames = @($reader.Entries | ForEach-Object { $_.FullName })
    foreach ($required in @('install.bat', 'installer.ps1', 'install-mfg.bat', 'README.md')) {
        if ($required -notin $entryNames) {
            throw "Base ZIP missing installer component: $required"
        }
    }
    $modFiles = @($entryNames | Where-Object { $_ -match '^mods/[^/]+\.jar$' })
    if ($modFiles.Count -ne 1) {
        throw "Base ZIP must contain exactly one mod JAR, found $($modFiles.Count)."
    }
    $writer = [IO.Compression.ZipFile]::Open($tempFile, [IO.Compression.ZipArchiveMode]::Create)
    foreach ($entry in $reader.Entries) {
        $copy = $writer.CreateEntry($entry.FullName, [IO.Compression.CompressionLevel]::Optimal)
        if ($entry.FullName.EndsWith('/')) { continue }
        $in = $entry.Open(); $out = $copy.Open()
        try { $in.CopyTo($out) }
        finally { $in.Dispose(); $out.Dispose() }
    }
    Add-ArchiveFile $writer 'experimental/mfg/MFGUnlocker.dll' $candidate
    Add-ArchiveFile $writer 'experimental/mfg/LICENSE-MFG' $license
    Add-ArchiveFile $writer 'experimental/mfg/stage_optiscaler.py' (Join-Path $root 'native\mfg\stage_optiscaler.py')
    $manifest = [ordered]@{
        schema = 1
        candidate_sha256 = $expected
        runtime_sha256 = $runtimePin
        base_archive_sha256 = (Get-FileHash -LiteralPath $release.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        branch_commit = $version.Trim()
        verified_native_checks = @('recovered_contracts','remix_runtime_profiles','remix_host_registration')
        status = 'experimental; native registration checks only; actual FG and Minecraft GPU presentation unverified'
    }
    Add-ArchiveText $writer 'experimental/mfg/manifest.json' ($manifest | ConvertTo-Json -Depth 4)
    $instructions = @'
EXPERIMENTAL MFG 1.7.0 / RTX Remix v0.1.1 adapter. NOT A CERTIFIED FG RELEASE.

This ZIP is the verified Minecraft installation package plus a separate
locally built experimental candidate at experimental/mfg/MFGUnlocker.dll.
The normal install.bat and install-mfg.bat DO NOT deploy this candidate.

Only the exact runtime SHA-256 in manifest.json is admitted. It is not
a .trex/version.dll override and must not be copied into the SDK folder.

To use the private OptiScaler route in a disposable Prism test instance:
  1. Install the normal mod and existing isolated MFG addon in that test
     instance using the unmodified installer.
  2. Obtain the exact pinned OptiScaler extracted package and its LICENSE
     and SOURCE.txt notices as documented in native/mfg/README.md.
  3. Use experimental/mfg/stage_optiscaler.py with the candidate file,
     its SHA-256 and your test instance's rtx-remix-addons/mfg-unlocker.
  4. Apply the TWO printed -Drtxremix.* hashes to only the test instance.
  5. Verify native device admission and true FG presentations (not just
     a checked menu box). Keep Remix native rtx.dlfg.enable=false.

Do not run the development adapter in your working instance or alongside
the unrelated direct-.trex sm86 proxy. Keep this ZIP local.
'@
    Add-ArchiveText $writer 'experimental/mfg/README.txt' $instructions
} finally {
    if ($writer) { $writer.Dispose() }
    if ($reader) { $reader.Dispose() }
}
try {
    # Validate that the newly embedded DLL matches the tested candidate.
    $opened = [IO.Compression.ZipFile]::OpenRead($tempFile)
    try {
        $item = $opened.GetEntry('experimental/mfg/MFGUnlocker.dll')
        if (!$item) { throw 'Packaged MFG candidate missing.' }
        $digest = [Security.Cryptography.SHA256]::Create()
        try {
            $stream = $item.Open()
            try { $computed = [BitConverter]::ToString($digest.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }
            finally { $stream.Dispose() }
        } finally { $digest.Dispose() }
        if ($computed -ne $expected) { throw 'Packaged MFG candidate hash mismatch.' }
    } finally { $opened.Dispose() }
    [IO.File]::Move($tempFile, $outFile)
} finally {
    if (Test-Path -LiteralPath $tempFile) { Remove-Item -LiteralPath $tempFile -Force }
}
Write-Output "PASS: native registration tests and package hash. Experimental ZIP: $outFile"
Write-Output "Custom MFG DLL: $candidate"
Write-Warning 'The experimental DLL is packaged but NOT automatically installed or verified to generate displayed frames.'
