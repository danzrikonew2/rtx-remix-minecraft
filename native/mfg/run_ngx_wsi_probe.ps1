# SPDX-License-Identifier: Apache-2.0
# Disposable Vulkan NGX diagnostic. Never run against Minecraft or Prism.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Dll,
    [Parameter(Mandatory = $true)][string]$ExpectedSha256,
    [string]$RepoRoot,
    [ValidateSet('device', 'plain', 'skip')][string]$ShutdownMode = 'device',
    [ValidateRange(1, 1000)][int]$Frames = 4,
    [ValidateRange(0, 100)][int]$IntervalMs = 20,
    [ValidateRange(10, 120)][int]$TimeoutSeconds = 30,
    [switch]$TraceShutdownAv,
    [switch]$NgxInitOnly,
    [switch]$GpuContent,
    [switch]$CaptureWaitChain,
    [switch]$CaptureStacks,
    [string]$WaitChainTool,
    [ValidateRange(5, 30)][int]$DiagnosticsLeadSeconds = 12,
    [string]$PythonExe = 'python.exe',
    [Parameter(Mandatory = $true)][ValidatePattern('^[A-Za-z0-9-]+$')][string]$Tag
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if (!$RepoRoot) { $RepoRoot = Join-Path $PSScriptRoot '..\..' }
$root = [IO.Path]::GetFullPath($RepoRoot)
$dllPath = [IO.Path]::GetFullPath($Dll)
$exe = Join-Path $root 'build\mfg-profile-ngx-ninja\MfgVulkanWsiProbe.exe'
$logDir = Join-Path $root 'build\mfg-profile-ngx-ninja\validation-20261109'
$outPath = Join-Path $logDir "$Tag.stdout.log"
$errPath = Join-Path $logDir "$Tag.stderr.log"
$wctPath = Join-Path $logDir "$Tag.wait-chain.log"
$sourcePackage = Split-Path -Parent $dllPath
$runPackage = Join-Path $logDir "$Tag.package\Package"
$runDll = Join-Path $runPackage 'OptiScaler.dll'
if ((Split-Path -Leaf $dllPath) -cne 'OptiScaler.dll' -or
    (Split-Path -Leaf $sourcePackage) -cne 'Package') {
    throw 'The isolated NGX runner requires a verified OptiScaler.dll within a Package directory.'
}
if ($CaptureStacks -and !$CaptureWaitChain) { throw '-CaptureStacks requires -CaptureWaitChain' }
if ($TraceShutdownAv -and $ShutdownMode -ne 'device') {
    throw '-TraceShutdownAv requires -ShutdownMode device'
}
if ($NgxInitOnly -and $ShutdownMode -eq 'skip') {
    throw '-NgxInitOnly requires -ShutdownMode device or plain'
}
if ($GpuContent -and
    !(Test-Path -LiteralPath (Join-Path (Split-Path -Parent $sourcePackage) 'gpucontent-build-manifest.json') -PathType Leaf) -and
    !(Test-Path -LiteralPath (Join-Path (Split-Path -Parent $sourcePackage) 'motion-build-manifest.json') -PathType Leaf) -and
    !(Test-Path -LiteralPath (Join-Path (Split-Path -Parent $sourcePackage) 'color-build-manifest.json') -PathType Leaf)) {
    throw '-GpuContent requires a verified r5, r6 or r7 diagnostic source package'
}
if ($GpuContent -and $NgxInitOnly) { throw '-GpuContent requires an NGX evaluation run' }
if ($CaptureWaitChain) {
    if ($DiagnosticsLeadSeconds -ge $TimeoutSeconds) {
        throw '-DiagnosticsLeadSeconds must be less than -TimeoutSeconds'
    }
    if (!$WaitChainTool) {
        $WaitChainTool = Join-Path $root 'build\mfg-profile-ngx-ninja\MfgWaitChainProbe.exe'
    }
    $WaitChainTool = [IO.Path]::GetFullPath($WaitChainTool)
    if (!(Test-Path -LiteralPath $WaitChainTool -PathType Leaf)) {
        throw "Missing read-only wait-chain diagnostic executable: $WaitChainTool"
    }
}
if (!(Test-Path -LiteralPath $dllPath -PathType Leaf)) { throw "DLL not found: $dllPath" }
if (!(Test-Path -LiteralPath $exe -PathType Leaf)) { throw "Probe not built: $exe" }
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $dllPath).Hash
if ($hash -ne $ExpectedSha256.Trim().ToUpperInvariant()) { throw "Pinned OptiScaler hash mismatch: $hash" }
if (@(Get-Process MfgVulkanWsiProbe -ErrorAction SilentlyContinue |
        Where-Object { $_.Threads.Count -gt 0 }).Count -ne 0) {
    throw 'An active MfgVulkanWsiProbe is already running; refuse overlapping GPU probes.'
}
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
foreach ($path in @($outPath, $errPath, $wctPath)) {
    if (Test-Path -LiteralPath $path) { throw "Log already exists: $path" }
}
if (Test-Path -LiteralPath (Split-Path -Parent $runPackage)) {
    throw "Isolated run copy already exists: $runPackage"
}
# Only the verified source package is an input. OptiScaler may update its INI
# and log, so the child must run out of a newly verified disposable copy.
$copyTool = Join-Path $root 'native\mfg\prepare_ngx_run_copy.py'
& $PythonExe $copyTool --repo-root $root --source-package $sourcePackage `
    --run-package $runPackage --expected-dll-sha256 $hash
if ($LASTEXITCODE -ne 0) { throw "Verified NGX run copy failed (exit=$LASTEXITCODE)" }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $runDll).Hash -ne $hash) {
    throw 'Isolated child DLL hash changed after publication'
}

$start = [Diagnostics.ProcessStartInfo]::new()
$start.FileName = $exe
$start.WorkingDirectory = $runPackage
$stimulus = if ($NgxInitOnly) { '--ngx-init-only' } else { '--ngx-evaluate' }
$start.Arguments = ('--optiscaler "{0}" {1} --skip-vendor-detach --ngx-shutdown-mode {2} --frames {3} --interval-ms {4}' -f $runDll, $stimulus, $ShutdownMode, $Frames, $IntervalMs)
if ($TraceShutdownAv) { $start.Arguments += ' --trace-ngx-shutdown-av' }
$start.UseShellExecute = $false
$start.RedirectStandardOutput = $true
$start.RedirectStandardError = $true
$start.CreateNoWindow = $true
if ($GpuContent) { $start.Environment['RTX_REMIX_FG_GPUCONTENT'] = '1' }
$proc = [Diagnostics.Process]::new()
$proc.StartInfo = $start
$timely = $false
try {
    if (!$proc.Start()) { throw 'Unable to start disposable probe' }
    Write-Host "Probe PID=$($proc.Id) mode=$ShutdownMode stimulus=$stimulus gpuContent=$([bool]$GpuContent) frames=$Frames timeout=${TimeoutSeconds}s sha256=$hash runPackage=$runPackage"
    $stdout = $proc.StandardOutput.ReadToEndAsync()
    $stderr = $proc.StandardError.ReadToEndAsync()
    $clock = [Diagnostics.Stopwatch]::StartNew()
    $diagnosticDueMs = ($TimeoutSeconds - $DiagnosticsLeadSeconds) * 1000
    $capturePending = [bool]$CaptureWaitChain
    while ($clock.ElapsedMilliseconds -lt $TimeoutSeconds * 1000) {
        if ($proc.WaitForExit(250)) { $timely = $true; break }
        if ($capturePending -and $clock.ElapsedMilliseconds -ge $diagnosticDueMs) {
            $capturePending = $false
            $diagStart = [Diagnostics.ProcessStartInfo]::new()
            $diagStart.FileName = $WaitChainTool
            $diagStart.Arguments = if ($CaptureStacks) { "$($proc.Id) --stacks" } else { [string]$proc.Id }
            $diagStart.WorkingDirectory = $logDir
            $diagStart.UseShellExecute = $false
            $diagStart.CreateNoWindow = $true
            $diagStart.RedirectStandardOutput = $true
            $diagStart.RedirectStandardError = $true
            $diag = [Diagnostics.Process]::new()
            $diag.StartInfo = $diagStart
            $diagStarted = $false
            try {
                if (!$diag.Start()) { throw 'Wait-chain diagnostic did not start' }
                $diagStarted = $true
                $diagOut = $diag.StandardOutput.ReadToEndAsync()
                $diagErr = $diag.StandardError.ReadToEndAsync()
                $done = $diag.WaitForExit(6000)
                if (!$done) { $diag.Kill(); $diag.WaitForExit(3000) | Out-Null }
                [IO.File]::WriteAllText($wctPath, $diagOut.GetAwaiter().GetResult() +
                    $diagErr.GetAwaiter().GetResult())
                Write-Host "Wait-chain diagnostic: $wctPath (complete=$done exit=$($diag.ExitCode))"
            } catch {
                [IO.File]::WriteAllText($wctPath, "Wait-chain capture failed: $_")
                Write-Warning "Wait-chain capture failed: $_"
            } finally {
                if ($diagStarted -and !$diag.HasExited) {
                    $diag.Kill(); $diag.WaitForExit(3000) | Out-Null
                }
                $diag.Dispose()
            }
        }
    }
    if (!$timely -and $proc.HasExited) { $timely = $true }
    if (!$timely) {
        Write-Host "TIMEOUT: terminating owned probe PID=$($proc.Id)"
        # This Process object is the directly created child, so no unrelated
        # PID can be selected or killed by name.
        $proc.Kill()
        if (!$proc.WaitForExit(10000)) { throw 'Owned probe could not be terminated' }
    }
    [IO.File]::WriteAllText($outPath, $stdout.Result)
    [IO.File]::WriteAllText($errPath, $stderr.Result)
    Write-Host "ExitCode=$($proc.ExitCode) completed=$timely stdout=$outPath stderr=$errPath providerLog=$(Join-Path $runPackage 'OptiScaler.log')"
    $stdout.Result -split "`n" | Select-Object -Last 35
    if ($stderr.Result) { Write-Host ('stderr=' + $stderr.Result) }
    if (!$timely) { exit 124 }
    if ($proc.ExitCode -ne 0) { exit $proc.ExitCode }
    exit 0
} finally {
    if (!$proc.HasExited) { $proc.Kill(); $proc.WaitForExit(10000) | Out-Null }
    $proc.Dispose()
}
