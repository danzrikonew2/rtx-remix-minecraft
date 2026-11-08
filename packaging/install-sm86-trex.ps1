# SPDX-License-Identifier: Apache-2.0
<#
.SYNOPSIS
  Optional, EXPERIMENTAL direct-.trex smoke-test installer for dlssg_for_sm86.
.DESCRIPTION
  Downloads the pinned author's sm86-7 Vulkan archive, verifies its publisher-
  reported SHA-256, and stages ONLY version.dll + dlssg_sm86.ini in an existing
  Minecraft 26.3 RTX Remix runtime's remix-sdk/.trex directory.

  Installing a proxy does NOT prove that Minecraft's javaw.exe/Remix renderer
  loads it, nor that native DLSS-FG presents unique frames. Do not combine this
  experiment with the existing OptiScaler/MFG adapter. This is not the default
  RTX Remix/Prism installer, and it never launches or terminates game processes.

  The native extractor replaces remix-sdk on a mod/runtime update. Rerun Install
  after a full extraction, not before the first Minecraft launch.
#>
[CmdletBinding()]
param(
    [ValidateSet('Inspect','Install','Remove')][string]$Action = 'Inspect',
    [Parameter(Mandatory=$true)][string]$GameDir
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$downloadUrl = 'https://github.com/pipotoufikxyz-lgtm/dlssg_for_sm86-MFG-version/releases/download/sm86-7/dlssg_sm86.zip'
$downloadSha256 = 'fc394c984d77aba9948c66dc85833a22fdf264381137e921d82ca0d3520c429c'
$game = [IO.Path]::GetFullPath($GameDir)
$sdk = Join-Path $game 'remix-sdk'
$renderer = Join-Path $sdk 'd3d9.dll'
$target = Join-Path $sdk '.trex'
$manifestRoot = Join-Path $game 'rtx-remix-addons\sm86-trex'
$manifestPath = Join-Path $manifestRoot 'installed.json'
$names = @('version.dll','dlssg_sm86.ini')

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Assert-NotLink([string]$Path) {
    if (Test-Path -LiteralPath $Path) {
        $item = Get-Item -LiteralPath $Path -Force
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Refusing a linked/reparse-point target: $Path"
        }
    }
}
function Read-Manifest {
    if (!(Test-Path -LiteralPath $manifestPath -PathType Leaf)) { return $null }
    $record = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if ($record.schema -ne 1 -or $record.sourceArchiveSha256 -ne $downloadSha256) {
        throw 'Unrecognized sm86-trex installation record: refusing to overwrite or delete files.'
    }
    return $record
}
function Assert-UnmodifiedOwnedFiles($record) {
    foreach ($name in $names) {
        $expected = [string]($record.files.$name)
        if ($expected -notmatch '^[0-9a-f]{64}$') { throw "Invalid manifest checksum for $name" }
        $path = Join-Path $target $name
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            Assert-NotLink $path
            if ((Get-Sha256 $path) -ne $expected) {
                throw "The installed $name was modified. Preserving it; manual review required."
            }
        }
    }
}
if (!(Test-Path -LiteralPath $game -PathType Container)) {
    throw "Minecraft game directory does not exist: $game"
}
Assert-NotLink $sdk
Assert-NotLink $target
Assert-NotLink $manifestRoot
Assert-NotLink $manifestPath
$record = Read-Manifest

if ($Action -eq 'Inspect') {
    Write-Output "Minecraft game directory: $game"
    Write-Output "Expected renderer: $renderer"
    Write-Output "Target for this experimental method: $target"
    Write-Output "Renderer present: $(Test-Path -LiteralPath $renderer -PathType Leaf)"
    Write-Output ".trex present: $(Test-Path -LiteralPath $target -PathType Container)"
    Write-Output "Owned installation record present: $($null -ne $record)"
    foreach ($name in $names) {
        $path = Join-Path $target $name
        Write-Output "$name present: $(Test-Path -LiteralPath $path -PathType Leaf)"
    }
    if ($record) {
        Assert-UnmodifiedOwnedFiles $record
        if ((Test-Path -LiteralPath $renderer -PathType Leaf) -and
                (Get-Sha256 $renderer) -ne [string]$record.runtimeSha256) {
            Write-Warning 'Runtime changed since installing: re-install after the runtime has extracted.'
        }
    }
    Write-Warning 'A file existing in .trex does not show whether javaw.exe actually loads this proxy.'
    exit 0
}

# Never install/uninstall files while a Java/Minecraft/Prism process might use them.
$running = @(Get-Process -Name javaw,minecraft,prismlauncher -ErrorAction SilentlyContinue)
if ($running.Count -gt 0) {
    throw 'Close Minecraft and Prism first. This installer does not terminate any processes.'
}
if ($Action -eq 'Remove') {
    if (!$record) { Write-Output 'No owned sm86-trex installation. Nothing removed.'; exit 0 }
    Assert-UnmodifiedOwnedFiles $record
    foreach ($name in $names) {
        $path = Join-Path $target $name
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            Remove-Item -LiteralPath $path
        }
    }
    Remove-Item -LiteralPath $manifestPath
    Write-Output 'Removed only the two verified, installer-owned sm86 files; existing runtime untouched.'
    exit 0
}
if (!(Test-Path -LiteralPath $renderer -PathType Leaf)) {
    throw "Remix runtime is not extracted yet: $renderer. Launch the development build once, close it, and retry."
}
if (!(Test-Path -LiteralPath $target -PathType Container)) {
    throw "No .trex directory in this Minecraft runtime: $target. The Reddit-style method is not applicable to this layout; refusing to invent a target."
}
if ($record) {
    Assert-UnmodifiedOwnedFiles $record
    $present = @($names | Where-Object { Test-Path -LiteralPath (Join-Path $target $_) -PathType Leaf })
    if ($present.Count -eq $names.Count -and (Get-Sha256 $renderer) -eq [string]$record.runtimeSha256) {
        Write-Output 'Already installed with matching hashes and runtime. No changes made.'
        exit 0
    }
    if ($present.Count -gt 0) {
        throw 'Partial previous installation found. Run Remove before reinstalling; refusing to overwrite.'
    }
} else {
    foreach ($name in $names) {
        if (Test-Path -LiteralPath (Join-Path $target $name)) {
            throw "An unowned $name already exists in .trex; refusing to overwrite."
        }
    }
}

$temp = Join-Path ([IO.Path]::GetTempPath()) ('sm86-trex-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temp -Force | Out-Null
$installed = @()
try {
    $archivePath = Join-Path $temp 'dlssg_sm86.zip'
    Invoke-WebRequest -Uri $downloadUrl -UseBasicParsing -OutFile $archivePath
    if ((Get-Sha256 $archivePath) -ne $downloadSha256) {
        throw 'Third-party archive SHA-256 mismatch. Installation aborted.'
    }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($archivePath)
    try {
        $checksums = @{}
        foreach ($name in $names) {
            # Ignore alternative-name proxies; only the author-listed files
            # are accepted. A duplicate matching filename is ambiguous.
            $matches = @($zip.Entries | Where-Object {
                $_.Name -ieq $name -and $_.FullName -notmatch '(^|/)altnative/'
            })
            if ($matches.Count -ne 1) {
                throw "Expected exactly one $name in the pinned archive; found $($matches.Count)."
            }
            $stage = Join-Path $temp $name
            [IO.Compression.ZipFileExtensions]::ExtractToFile($matches[0], $stage)
            if ((Get-Item -LiteralPath $stage).Length -eq 0) {
                throw "Empty extracted file: $name"
            }
            $checksums[$name] = Get-Sha256 $stage
        }
        # Do not change unrelated .trex DLLs, override existing files, or
        # mutate NVIDIA's actual Remix runtime d3d9.dll.
        foreach ($name in $names) {
            $destination = Join-Path $target $name
            if (Test-Path -LiteralPath $destination) { throw "Destination appeared during installation: $name" }
            [IO.File]::Copy((Join-Path $temp $name), $destination, $false)
            $installed += $destination
        }
        New-Item -ItemType Directory -Path $manifestRoot -Force | Out-Null
        $manifest = [ordered]@{
            schema = 1
            sourceRelease = 'sm86-7'
            sourceArchiveSha256 = $downloadSha256
            runtimeSha256 = (Get-Sha256 $renderer)
            files = $checksums
        }
        $manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
        Write-Output "Installed pinned sm86-7 version.dll and dlssg_sm86.ini into $target"
        Write-Warning 'Experimental only. Check the process/module logs before claiming native FG or unique frames.'
        Write-Warning 'A Minecraft update may replace remix-sdk; use Inspect and reinstall after extraction if needed.'
    } finally { $zip.Dispose() }
} catch {
    foreach ($path in $installed) {
        if (Test-Path -LiteralPath $path -PathType Leaf) { Remove-Item -LiteralPath $path }
    }
    throw
} finally {
    if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Recurse -Force }
}
