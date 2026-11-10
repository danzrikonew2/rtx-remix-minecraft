# SPDX-License-Identifier: Apache-2.0
<#
.SYNOPSIS
  Run pinned FG OFF and FG ON visual probes from a real interactive Windows console.
.DESCRIPTION
  Opens only the isolated native test windows. The operator must focus each
  window when it appears. Collects independent source/DWM timestamps and DXGI
  local-memory estimates, then writes a cautious comparison report. A 2x DWM
  observation does not independently prove generated physical scanout frames.
#>
[CmdletBinding()]
param(
    [string]$RepoRoot,
    [ValidateRange(140,3600)][int]$Frames = 600,
    [ValidateRange(5,180)][int]$AwaitFocusSeconds = 45,
    [ValidateRange(60,1200)][int]$TimeoutSeconds = 240,
    [ValidateRange(200,10000)][int]$StatusIntervalMs = 250,
    [string]$PythonExe = 'python.exe',
    [string]$OffProbeName = 'mfg-fg-off-20261109-vram',
    [string]$OnProbeName = 'mfg-fg-on-20261109-vram',
    [switch]$OnDiagnosticPackage
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if (!$RepoRoot) { $RepoRoot = Join-Path $PSScriptRoot '..\..' }
$root = [IO.Path]::GetFullPath($RepoRoot)
if ($TimeoutSeconds -le $AwaitFocusSeconds + 15) {
    throw 'TimeoutSeconds must leave at least 15 seconds after the foreground gate.'
}
$runner = Join-Path $PSScriptRoot 'run_optiscaler_probe.ps1'
$analyzer = Join-Path $PSScriptRoot 'analyze_probe_frames.py'
$verifier = Join-Path $PSScriptRoot 'verify_optiscaler_probe.py'
$copier = Join-Path $PSScriptRoot 'prepare_ngx_run_copy.py'
$results = @{}
if ($OnDiagnosticPackage) {
    throw 'This comparison accepts the pinned NVIDIA DLSSG packages only; FSR diagnostic packages are unsupported.'
}

foreach ($mode in @('off', 'on')) {
    $name = if ($mode -eq 'off') { $OffProbeName } else { $OnProbeName }
    if ($name -cnotmatch '^[A-Za-z0-9][A-Za-z0-9-]{0,79}$') {
        throw "Invalid isolated probe directory name: $name"
    }
    $sourcePackage = Join-Path (Join-Path (Join-Path $root 'build') $name) 'Package'
    $metadata = Join-Path (Split-Path -Parent $sourcePackage) 'probe-inputs.json'
    if (!(Test-Path -LiteralPath $metadata -PathType Leaf)) {
        throw "Missing baseline probe metadata: $metadata"
    }
    $inputs = Get-Content -LiteralPath $metadata -Raw | ConvertFrom-Json
    if ($inputs.frame_generation_requested -ne $mode -or $inputs.frame_generation_output -notin @($null, 'dlssg')) {
        throw "Probe $name is not a verified NVIDIA FG $mode baseline"
    }
    $hash = [string]$inputs.optiscaler_fork_sha256
    # Each invocation uses fresh native files and independent logs. A provider
    # may rewrite OptiScaler.ini during teardown; signed baseline packages
    # must remain byte-for-byte unchanged.
    $runName = $name + '-run-' + [guid]::NewGuid().ToString('N')
    if ($runName.Length -gt 80) { throw "Probe name is too long for an isolated run: $name" }
    $runRoot = Join-Path (Join-Path $root 'build') $runName
    $runPackage = Join-Path $runRoot 'Package'
    & $PythonExe $copier --repo-root $root --source-package $sourcePackage `
        --run-package $runPackage --expected-dll-sha256 $hash
    if ($LASTEXITCODE -ne 0) { throw "FG $mode baseline copying/verification failed: $LASTEXITCODE" }
    & $PythonExe $verifier --repo-root $root --package $runPackage --installed-package $runPackage
    if ($LASTEXITCODE -ne 0) { throw "FG $mode isolated run verification failed: $LASTEXITCODE" }
    $logDir = Join-Path $runRoot 'probe-logs'
    # Every comparison owns an unpredictable run identifier: older traces
    # cannot accidentally satisfy this run's source/observer requirements.
    $tag = 'cmp-' + $mode + '-' + [guid]::NewGuid().ToString('N')
    $prefix = Join-Path $logDir "probe-visible-$Frames-$tag"
    $sourcePath = "$prefix.source-presents.csv"
    $desktopPath = "$prefix.desktop-frames.csv"
    $statusPath = "$prefix.status.ndjson"
    $observerLogPath = "$prefix.desktop-observer.log"
    $terminationPath = "$prefix.termination.json"
    Write-Host "FG $($mode.ToUpperInvariant()): open the native test window, then click it to give it focus."
    Write-Host "Baseline: $name; isolated run: $runName. This test does not run Minecraft or Prism."

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $runner `
        -RepoRoot $root -ProbeName $runName -Mode visible -Frames $Frames `
        -AwaitFocusSeconds $AwaitFocusSeconds -CaptureStatus -CaptureDisplayFrames -RunTag $tag `
        -TimeoutSeconds $TimeoutSeconds -StatusIntervalMs $StatusIntervalMs -PythonExe $PythonExe
    $runnerExitCode = $LASTEXITCODE

    if (!(Test-Path -LiteralPath $terminationPath -PathType Leaf)) {
        throw "FG $mode runner produced no termination report (exit=$runnerExitCode); inspect $logDir"
    }
    $termination = Get-Content -LiteralPath $terminationPath -Raw | ConvertFrom-Json
    if ($termination.schema -ne 'remix-native-probe-termination-v1') {
        throw "FG $mode termination report has an unknown schema: $terminationPath"
    }
    if ($runnerExitCode -ne 0) {
        if ($termination.result -ne 'shutdown_timeout_after_complete_render' -or
                $termination.process_timed_out -ne $true) {
            throw "FG $mode native runner failed (exit=$runnerExitCode; result=$($termination.result)); inspect $terminationPath"
        }
        Write-Warning "FG $mode rendered its requested frames but Remix shutdown timed out. Runner exit=$runnerExitCode; this is NOT a clean shutdown."
    } elseif ($termination.result -ne 'clean_shutdown') {
        throw "FG $mode runner exited 0 without clean-shutdown evidence; inspect $terminationPath"
    }
    if ($termination.observer_passed -ne $true) {
        throw "FG $mode independent display observer did not exit successfully; inspect $observerLogPath"
    }
    if (!(Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
        throw "FG $mode produced no source-present trace for its own run ID ($tag). Foreground focus or startup likely failed. Check $logDir"
    }
    if (!(Test-Path -LiteralPath $desktopPath -PathType Leaf)) {
        throw "FG $mode produced no desktop frame trace for its own run ID: $desktopPath; observer log: $observerLogPath"
    }
    if (!(Test-Path -LiteralPath $statusPath -PathType Leaf)) {
        throw "FG $mode produced no process-matched provider status: $statusPath"
    }
    $sourceSamples = @(Import-Csv -LiteralPath $sourcePath).Count
    $desktopSamples = @(Import-Csv -LiteralPath $desktopPath).Count
    Write-Host "FG $mode captured source=$sourceSamples DWM=$desktopSamples (not scanout proof)."
    $results[$mode] = @{
        source = $sourcePath; desktop = $desktopPath; status = $statusPath
        termination = $terminationPath; observer = $observerLogPath
    }
    if ($sourceSamples -lt 40 -or $desktopSamples -lt 40) {
        throw "FG $mode lacks sufficient source/DWM samples; observer log: $observerLogPath. Review display permissions and focus."
    }
}

$report = Join-Path (Join-Path $root 'build') (
    'mfg-fg-off-on-compare-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.json')
& $PythonExe $analyzer --off-source $results.off.source --off-desktop $results.off.desktop `
    --off-status $results.off.status --off-termination $results.off.termination `
    --off-observer-log $results.off.observer `
    --on-source $results.on.source --on-desktop $results.on.desktop `
    --on-status $results.on.status --on-termination $results.on.termination `
    --on-observer-log $results.on.observer --output $report
if ($LASTEXITCODE -ne 0) {
    throw "OFF/ON frame comparison has insufficient or invalid evidence; diagnostic report: $report"
}
Write-Host "OFF/ON frame diagnostic: $report"
Write-Host 'Gate H stays BLOCKED until generated frame identity and actual scanout are verified.'
