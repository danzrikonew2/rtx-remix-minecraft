# SPDX-License-Identifier: Apache-2.0
<#
.SYNOPSIS
  Restore pinned MFG build SDKs in ignored build/ without touching Minecraft.
.DESCRIPTION
  Downloads the SHA-256-verified NVIDIA Streamline SDK v2.14.1 x64 release
  and fetches exact ImGui and Vulkan-Headers Git commits. Does not execute
  SDK binaries, alter system settings, or run the game. Existing vendor folders
  are preserved and validated; an unexpected folder is never overwritten.
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
$source = Join-Path $build 'mfg-source'
$streamline = Join-Path $build 'streamline'
$imgui = Join-Path $build 'imgui'
$vulkan = Join-Path $build 'vulkan'
$downloads = Join-Path $build 'mfg-downloads'
$zipFile = Join-Path $downloads 'streamline-sdk-v2.14.1.zip'
$zipSha256 = '92c4d954631a1710da86ca3fa8d5034f2b9503838c95fc4ae977ae149319781b'
$zipUrl = 'https://github.com/NVIDIA-RTX/Streamline/releases/download/v2.14.1/streamline-sdk-v2.14.1.zip'
$imguiSha = '3912b3d9a9c1b3f17431aebafd86d2f40ee6e59c'
$vulkanSha = '074fa3055cfee530992bcbfa0fcb23106a82c1ab'  # v1.2.176, peeled annotated tag
$stage = Join-Path $build ('mfg-sdks-staging-' + [guid]::NewGuid().ToString('N'))

function Assert-Hash([string]$path, [string]$expected) {
    if (!(Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing: $path" }
    $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $expected) {
        throw "SHA-256 mismatch for $path. Expected $expected; actual $actual"
    }
}

function Run-Git([string[]]$argsList) {
    & git.exe @argsList
    if ($LASTEXITCODE -ne 0) { throw "git failed: $($argsList -join ' ')" }
}

function Fetch-PinnedRepository([string]$url, [string]$sha, [string]$target, [string]$stagingDir) {
    if (Test-Path -LiteralPath $target) {
        if (!(Test-Path -LiteralPath (Join-Path $target '.git'))) {
            throw "Existing $target has no Git identity; preserving it for manual inspection."
        }
        $head = (& git.exe -C $target rev-parse HEAD)
        if ($LASTEXITCODE -ne 0 -or $head.Trim() -ne $sha) {
            throw "Existing $target is not the pinned commit $sha. It was not changed."
        }
        Write-Output "Keeping pinned vendor checkout: $target"
        return
    }
    New-Item -ItemType Directory -Path $stagingDir -Force | Out-Null
    Run-Git @('-C',$stagingDir,'init','-q')
    Run-Git @('-C',$stagingDir,'remote','add','origin',$url)
    Run-Git @('-C',$stagingDir,'-c','core.autocrlf=false','fetch','--depth','1','origin',$sha)
    Run-Git @('-C',$stagingDir,'-c','core.autocrlf=false','checkout','--detach','FETCH_HEAD')
    $actual = (& git.exe -C $stagingDir rev-parse HEAD)
    if ($LASTEXITCODE -ne 0 -or $actual.Trim() -ne $sha) {
        throw "Unexpected upstream commit for $url; expected $sha"
    }
    if (Test-Path -LiteralPath $target) { throw "Target appeared while staging: $target" }
    [IO.Directory]::Move($stagingDir, $target)
    Write-Output "Pinned Git checkout: $target @ $sha"
}

if (!(Test-Path -LiteralPath (Join-Path $source 'source\native\build.ps1') -PathType Leaf)) {
    throw "Pinned MFG checkout not found under $source"
}
$git = Get-Command git.exe -ErrorAction SilentlyContinue
if (!$git) { throw 'git.exe is required to fetch pinned source commits.' }
if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    $PythonExe = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
}
if (!(Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw "Python interpreter not found: $PythonExe. Pass -PythonExe ABSOLUTE_PYTHON_EXE."
}
& $PythonExe -c 'import sys;sys.exit(0 if sys.version_info >= (3,10) else 1)'
if ($LASTEXITCODE -ne 0) { throw "Python 3.10+ required: $PythonExe" }
New-Item -ItemType Directory -Path $downloads -Force | Out-Null
New-Item -ItemType Directory -Path $stage -Force | Out-Null

try {
    if (Test-Path -LiteralPath $streamline) {
        if (!(Test-Path -LiteralPath (Join-Path $streamline 'include\sl_dlss_g.h') -PathType Leaf) -or
                !(Test-Path -LiteralPath (Join-Path $streamline 'external\ngx-sdk\include\nvsdk_ngx.h') -PathType Leaf)) {
            throw "Existing $streamline is not a complete Streamline SDK. Preserving it."
        }
        Write-Output "Keeping existing Streamline SDK: $streamline"
    } else {
        if (!(Test-Path -LiteralPath $zipFile -PathType Leaf)) {
            $temporary = Join-Path $downloads ('streamline-' + [guid]::NewGuid().ToString('N') + '.tmp.zip')
            try {
                Write-Output 'Downloading official pinned Streamline 2.14.1 x64 SDK (~276 MB)...'
                Invoke-WebRequest -UseBasicParsing -Uri $zipUrl -OutFile $temporary
                Assert-Hash $temporary $zipSha256
                [IO.File]::Move($temporary, $zipFile)
            } finally {
                if (Test-Path -LiteralPath $temporary) {
                    Remove-Item -LiteralPath $temporary -Force
                }
            }
        }
        Assert-Hash $zipFile $zipSha256
        $expanded = Join-Path $stage 'streamline-extracted'
        New-Item -ItemType Directory -Path $expanded -Force | Out-Null
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [IO.Compression.ZipFile]::ExtractToDirectory($zipFile, $expanded)
        $hits = @(Get-ChildItem -LiteralPath $expanded -File -Filter sl_dlss_g.h -Recurse |
            Where-Object { $_.Directory.Name -eq 'include' -and
                (Test-Path -LiteralPath (Join-Path $_.Directory.Parent.FullName 'external\ngx-sdk\include\nvsdk_ngx.h') -PathType Leaf) })
        if ($hits.Count -ne 1) {
            throw "Streamline SDK archive has $($hits.Count) recognized roots; expected one. Nothing was installed."
        }
        $sdkRoot = $hits[0].Directory.Parent.FullName
        if (Test-Path -LiteralPath $streamline) { throw "Target appeared: $streamline" }
        [IO.Directory]::Move($sdkRoot, $streamline)
        Write-Output "Streamline SDK staged: $streamline"
    }

    Fetch-PinnedRepository 'https://github.com/ocornut/imgui.git' $imguiSha $imgui (Join-Path $stage 'imgui')
    Fetch-PinnedRepository 'https://github.com/KhronosGroup/Vulkan-Headers.git' $vulkanSha $vulkan (Join-Path $stage 'vulkan')
    if (!(Test-Path -LiteralPath (Join-Path $vulkan 'include\vulkan\vulkan.h') -PathType Leaf)) {
        throw "Pinned Vulkan headers missing from $vulkan"
    }

    # The official pins were computed from some Windows CRLF variants.
    # Normalize only the isolated vendor copies, and only when that byte
    # representation produces the exact expected upstream SHA-256.
    & $PythonExe (Join-Path $root 'native\mfg\verify_headers.py') --source $source --streamline $streamline --imgui $imgui --normalize-pinned-text
    if ($LASTEXITCODE -ne 0) { throw 'Upstream Streamline/ImGui SHA-256 pin verification failed' }
    Write-Output 'PASS: pinned Streamline/ImGui headers; Vulkan-Headers v1.2.176 commit.'
    Write-Output 'SDK prerequisites staged. Next: native/mfg/build.ps1 (does not install or launch Minecraft).'
} finally {
    if (Test-Path -LiteralPath $stage -PathType Container) {
        Remove-Item -LiteralPath $stage -Recurse -Force
    }
}
