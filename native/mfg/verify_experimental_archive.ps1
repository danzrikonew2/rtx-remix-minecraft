# SPDX-License-Identifier: Apache-2.0
<#
.SYNOPSIS
  Read-only verification of an existing experimental MFG installer ZIP.
.DESCRIPTION
  Compares every base installer entry byte-for-byte by SHA-256 against
  the corresponding experimental ZIP entry; requires exactly five additional
  MFG files, validates the candidate DLL and its manifest, and refuses
  corrupted or unexpected archives. Does not install, overwrite or delete.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$BaseArchive,
    [Parameter(Mandatory=$true)][string]$ExperimentalArchive,
    [Parameter(Mandatory=$true)][string]$ExpectedCandidateSha256,
    [Parameter(Mandatory=$true)][string]$ExpectedRuntimeSha256
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
Add-Type -AssemblyName System.IO.Compression.FileSystem

function Sha256Stream($stream) {
    $hash = [Security.Cryptography.SHA256]::Create()
    try {
        return [BitConverter]::ToString($hash.ComputeHash($stream)).Replace('-','').ToLowerInvariant()
    } finally { $hash.Dispose() }
}
function Sha256ZipEntry($entry) {
    if (!$entry) { throw 'Required ZIP entry is missing.' }
    $stream = $entry.Open()
    try { return Sha256Stream $stream }
    finally { $stream.Dispose() }
}
function Require([bool]$condition, [string]$message) {
    if (!$condition) { throw "Experimental ZIP verification failed: $message" }
}

foreach ($file in @($BaseArchive,$ExperimentalArchive)) {
    Require (Test-Path -LiteralPath $file -PathType Leaf) "Missing ZIP: $file"
}
Require ($ExpectedCandidateSha256 -match '^[0-9a-fA-F]{64}$') 'Invalid candidate hash parameter'
Require ($ExpectedRuntimeSha256 -match '^[0-9a-fA-F]{64}$') 'Invalid runtime hash parameter'
$expected = $ExpectedCandidateSha256.ToLowerInvariant()
$runtime = $ExpectedRuntimeSha256.ToLowerInvariant()
$baseSha = (Get-FileHash -LiteralPath $BaseArchive -Algorithm SHA256).Hash.ToLowerInvariant()

$baseZip = [IO.Compression.ZipFile]::OpenRead([IO.Path]::GetFullPath($BaseArchive))
try {
    $experimentalZip = [IO.Compression.ZipFile]::OpenRead([IO.Path]::GetFullPath($ExperimentalArchive))
    try {
        $baseEntries = @($baseZip.Entries)
        $experimentalEntries = @($experimentalZip.Entries)
        $expectedExtra = @(
            'experimental/mfg/MFGUnlocker.dll',
            'experimental/mfg/LICENSE-MFG',
            'experimental/mfg/stage_optiscaler.py',
            'experimental/mfg/manifest.json',
            'experimental/mfg/README.txt'
        )
        Require ($experimentalEntries.Count -eq ($baseEntries.Count + $expectedExtra.Count)) 'Unexpected archive entry count'
        $baseNames = @($baseEntries | ForEach-Object { $_.FullName })
        $experimentalNames = @($experimentalEntries | ForEach-Object { $_.FullName })
        Require ((@($experimentalNames | Sort-Object -Unique)).Count -eq $experimentalNames.Count) 'Duplicate ZIP entry names'

        foreach ($item in $baseEntries) {
            $actual = $experimentalZip.GetEntry($item.FullName)
            Require ($null -ne $actual) "Missing base installer entry: $($item.FullName)"
            Require ($item.Length -eq $actual.Length) "Changed installer entry length: $($item.FullName)"
            $before = Sha256ZipEntry $item
            $after = Sha256ZipEntry $actual
            Require ($before -eq $after) "Changed installer content: $($item.FullName)"
        }
        foreach ($name in $expectedExtra) {
            Require ($null -ne $experimentalZip.GetEntry($name)) "Missing MFG item: $name"
        }
        $unknown = @($experimentalNames | Where-Object { $_ -notin $baseNames -and $_ -notin $expectedExtra })
        Require ($unknown.Count -eq 0) "Unexpected additional ZIP entries: $($unknown -join ', ')"
        $embedded = Sha256ZipEntry ($experimentalZip.GetEntry('experimental/mfg/MFGUnlocker.dll'))
        Require ($embedded -eq $expected) "Candidate DLL checksum mismatch ($embedded)"
        foreach ($name in @('experimental/mfg/LICENSE-MFG','experimental/mfg/stage_optiscaler.py','experimental/mfg/README.txt')) {
            Require ($experimentalZip.GetEntry($name).Length -gt 0) "Empty experimental payload: $name"
        }
        $manifestStream = $experimentalZip.GetEntry('experimental/mfg/manifest.json').Open()
        try {
            $reader = [IO.StreamReader]::new($manifestStream,[Text.Encoding]::UTF8)
            try { $manifest = $reader.ReadToEnd() | ConvertFrom-Json -ErrorAction Stop }
            finally { $reader.Dispose() }
        } finally { $manifestStream.Dispose() }
        Require ($manifest.schema -eq 1) 'Unexpected manifest schema'
        Require ($manifest.candidate_sha256 -eq $expected) 'Manifest candidate hash mismatch'
        Require ($manifest.runtime_sha256 -eq $runtime) 'Manifest runtime hash mismatch'
        Require ($manifest.base_archive_sha256 -eq $baseSha) 'Manifest base-archive SHA-256 mismatch'
        foreach ($test in @('recovered_contracts','remix_runtime_profiles','remix_host_registration')) {
            Require ($test -in @($manifest.verified_native_checks)) "Manifest missing native test: $test"
        }
        Require ($manifest.status -match 'experimental') 'Manifest does not identify this as experimental'
        Write-Output "PASS: existing experimental ZIP verified ($($experimentalEntries.Count) entries)."
        Write-Output "All $($baseEntries.Count) original installer entries match by SHA-256."
        Write-Output "Custom MFG candidate SHA-256: $embedded"
        Write-Output "Base installer SHA-256: $baseSha"
        Write-Output "Archive preserved unchanged: $ExperimentalArchive"
    } finally { $experimentalZip.Dispose() }
} finally { $baseZip.Dispose() }
