# SPDX-License-Identifier: Apache-2.0
<#
.SYNOPSIS
  Run only the isolated, pinned OptiScaler/MFG Vulkan probe with a hard timeout.
.DESCRIPTION
  Verifies the published package, starts its native diagnostic executable in
  that package's directory, and writes stdout/stderr beside the package. It
  does not load or modify any Minecraft/Prism profile or system Java runtime.
#>
[CmdletBinding()]
param(
    [string]$RepoRoot,
    [string]$ProbeName = 'mfg-optiscaler-probe-fixed',
    [switch]$DiagnosticPackage,
    [string]$RunTag,
    [ValidateSet('hidden', 'visible')][string]$Mode = 'hidden',
    [switch]$RequestFocus,
    [ValidateRange(0, 180)][int]$AwaitFocusSeconds = 0,
    [ValidateRange(40, 3600)][int]$Frames = 60,
    [ValidateRange(10, 1200)][int]$TimeoutSeconds = 180,
    [switch]$CaptureWaitChain,
    [switch]$CaptureStacks,
    [switch]$CaptureStatus,
    [switch]$CaptureDisplayFrames,
    [ValidateRange(200, 10000)][int]$StatusIntervalMs = 1000,
    [string]$WaitChainTool,
    [string]$DisplayObserverTool,
    [ValidateRange(15, 120)][int]$DiagnosticsLeadSeconds = 30,
    [string]$PythonExe = 'python.exe'
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ([string]::IsNullOrWhiteSpace($RepoRoot)) { $RepoRoot = Join-Path $PSScriptRoot '..\..' }
if ($ProbeName -cnotmatch '^[A-Za-z0-9][A-Za-z0-9-]{0,79}$') {
    throw 'ProbeName must contain only letters, digits and hyphens.'
}
if ($RunTag -and $RunTag -cnotmatch '^[A-Za-z0-9][A-Za-z0-9-]{0,79}$') {
    throw 'RunTag must contain only letters, digits and hyphens.'
}
if ($RequestFocus -and $Mode -ne 'visible') { throw '-RequestFocus requires -Mode visible' }
if ($AwaitFocusSeconds -ne 0 -and ($Mode -ne 'visible' -or $AwaitFocusSeconds -lt 5)) {
    throw '-AwaitFocusSeconds requires -Mode visible and a value from 5 to 180.'
}
if ($AwaitFocusSeconds -ge $TimeoutSeconds -and $AwaitFocusSeconds -ne 0) {
    throw 'TimeoutSeconds must exceed AwaitFocusSeconds to allow the GPU render and shutdown diagnostics.'
}
if ($CaptureDisplayFrames -and $Mode -ne 'visible') {
    throw '-CaptureDisplayFrames requires -Mode visible.'
}
$root = [IO.Path]::GetFullPath($RepoRoot)
$probeRoot = Join-Path (Join-Path $root 'build') $ProbeName
$package = Join-Path $probeRoot 'Package'
$opti = Join-Path $package 'OptiScaler.dll'
$probe = Join-Path $package 'OptiRemixProbe.exe'
$runtime = Join-Path $root 'remix-runtime\win64\d3d9.dll'
$verifier = Join-Path $root 'native\mfg\verify_optiscaler_probe.py'
$classifier = Join-Path $root 'native\mfg\classify_probe_run.py'
if ($CaptureWaitChain) {
    if ([string]::IsNullOrWhiteSpace($WaitChainTool)) {
        $candidates = @(
            (Join-Path $root 'build\mfg-profile-wct-ninja\MfgWaitChainProbe.exe'),
            (Join-Path $root 'build\mfg-profile-checks\Release\MfgWaitChainProbe.exe')
        )
        $WaitChainTool = @($candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1)[0]
    }
    if ([string]::IsNullOrWhiteSpace($WaitChainTool) -or !(Test-Path -LiteralPath $WaitChainTool -PathType Leaf)) {
        throw 'Wait-chain executable missing. Build MfgWaitChainProbe or pass -WaitChainTool with an absolute path.'
    }
    $WaitChainTool = [IO.Path]::GetFullPath($WaitChainTool)
}
if ($CaptureWaitChain -and $DiagnosticsLeadSeconds -ge $TimeoutSeconds) {
    throw 'DiagnosticsLeadSeconds must be smaller than TimeoutSeconds.'
}
if ($CaptureStacks -and !$CaptureWaitChain) {
    throw 'CaptureStacks requires CaptureWaitChain.'
}
if ($CaptureDisplayFrames) {
    if ([string]::IsNullOrWhiteSpace($DisplayObserverTool)) {
        $candidates = @(
            (Join-Path $package 'MfgDisplayFrameObserver.exe'),
            (Join-Path $root 'build\mfg-profile-wct-ninja\MfgDisplayFrameObserver.exe'),
            (Join-Path $root 'build\mfg-profile-checks\Release\MfgDisplayFrameObserver.exe')
        )
        $DisplayObserverTool = @($candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1)[0]
    }
    if ([string]::IsNullOrWhiteSpace($DisplayObserverTool) -or !(Test-Path -LiteralPath $DisplayObserverTool -PathType Leaf)) {
        throw 'Display observer executable missing. Build MfgDisplayFrameObserver or pass -DisplayObserverTool.'
    }
    $DisplayObserverTool = [IO.Path]::GetFullPath($DisplayObserverTool)
}

if ($DiagnosticPackage) {
    $diagnosticVerifier = Join-Path $root 'native\mfg\prepare_fsrfg_diagnostic_package.py'
    & $PythonExe $diagnosticVerifier --repo-root $root --probe-name $ProbeName --verify-only
} else {
    & $PythonExe $verifier --repo-root $root --package $package --installed-package $package
}
if ($LASTEXITCODE -ne 0) { throw "Package verification failed: $LASTEXITCODE" }

$logDir = Join-Path $probeRoot 'probe-logs'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$tag = if ($RunTag) { $RunTag } else {
    (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '-' + [guid]::NewGuid().ToString('N')
}
$stdoutPath = Join-Path $logDir "probe-$Mode-$Frames-$tag.stdout.log"
$stderrPath = Join-Path $logDir "probe-$Mode-$Frames-$tag.stderr.log"
$waitChainPath = Join-Path $logDir "probe-$Mode-$Frames-$tag.wait-chain.log"
$statusPath = Join-Path $logDir "probe-$Mode-$Frames-$tag.status.ndjson"
$sourceFramesPath = Join-Path $logDir "probe-$Mode-$Frames-$tag.source-presents.csv"
$displayFramesPath = Join-Path $logDir "probe-$Mode-$Frames-$tag.desktop-frames.csv"
$displayObserverLogPath = Join-Path $logDir "probe-$Mode-$Frames-$tag.desktop-observer.log"
$terminationPath = Join-Path $logDir "probe-$Mode-$Frames-$tag.termination.json"
$statusSource = Join-Path $package 'RTXMFG-Universal.status.json'
foreach ($path in @($stdoutPath, $stderrPath, $statusPath, $sourceFramesPath,
                    $displayFramesPath, $displayObserverLogPath, $terminationPath,
                    $waitChainPath)) {
    if (Test-Path -LiteralPath $path) {
        throw "Probe run tag collides with an existing log: $path"
    }
}

$start = [Diagnostics.ProcessStartInfo]::new()
$start.FileName = $probe
$start.WorkingDirectory = $package
$start.Arguments = ('"{0}" "{1}" {2} {3}' -f $opti, $runtime, $Mode, $Frames)
if ($AwaitFocusSeconds -gt 0) {
    $start.Arguments += " await-focus=$AwaitFocusSeconds"
} elseif ($RequestFocus) { $start.Arguments += ' request-focus' }
$start.UseShellExecute = $false
$start.RedirectStandardOutput = $true
$start.RedirectStandardError = $true
$start.CreateNoWindow = ($Mode -eq 'hidden')
if ($CaptureDisplayFrames) {
    $start.EnvironmentVariables['MFG_PROBE_PRESENT_TRACE_PATH'] = $sourceFramesPath
}
$process = [Diagnostics.Process]::new()
$process.StartInfo = $start
$observer = $null
$observerOut = $null
$observerErr = $null
$started = $false
$observerStarted = $false
$observerFailure = $null
$observerCompleted = $false
$observerExitCode = $null

try {
    if (!$process.Start()) { throw 'Native probe process failed to start' }
    $started = $true
    # MFG processBirth is the Windows process-creation FILETIME. A stale
    # status file with a recycled PID must never count toward this run.
    $expectedBirth = [int64]$process.StartTime.ToUniversalTime().ToFileTimeUtc()
    Write-Host "Probe PID=$($process.Id) mode=$Mode frames=$Frames timeout=${TimeoutSeconds}s"
    $stdoutTask = $process.StandardOutput.ReadToEndAsync()
    $stderrTask = $process.StandardError.ReadToEndAsync()
    if ($CaptureDisplayFrames) {
        $observerStart = [Diagnostics.ProcessStartInfo]::new()
        $observerStart.FileName = $DisplayObserverTool
        $observerStart.WorkingDirectory = $logDir
        $observerStart.Arguments = ('{0} "{1}" {2}' -f $process.Id, $displayFramesPath, $TimeoutSeconds)
        $observerStart.UseShellExecute = $false
        $observerStart.CreateNoWindow = $true
        $observerStart.RedirectStandardOutput = $true
        $observerStart.RedirectStandardError = $true
        $observer = [Diagnostics.Process]::new()
        $observer.StartInfo = $observerStart
        if (!$observer.Start()) { throw 'Desktop observer process failed to start' }
        $observerStarted = $true
        $observerOut = $observer.StandardOutput.ReadToEndAsync()
        $observerErr = $observer.StandardError.ReadToEndAsync()
        Write-Host "Display observer PID=$($observer.Id) target=$($process.Id)"
    }
    $elapsed = [Diagnostics.Stopwatch]::StartNew()
    $statusSamples = [Collections.Generic.List[string]]::new()
    $nextSampleMs = [int64]0
    $statusReadFailures = 0
    $statusBirthMismatches = 0
    $diagnosticsDueMs = [int64]($TimeoutSeconds - $DiagnosticsLeadSeconds) * 1000
    $deadlineMs = [int64]$TimeoutSeconds * 1000
    $diagDue = $CaptureWaitChain
    $completed = $false
    while ($true) {
        $nowMs = $elapsed.ElapsedMilliseconds
        if ($CaptureStatus -and $nowMs -ge $nextSampleMs) {
            $nextSampleMs = $nowMs + $StatusIntervalMs
            if (Test-Path -LiteralPath $statusSource -PathType Leaf) {
                try {
                    $status = [IO.File]::ReadAllText($statusSource) | ConvertFrom-Json
                    # Older process snapshots may remain when a new probe starts.
                    if ([int]$status.pid -eq $process.Id -and
                            [int64]$status.processBirth -eq $expectedBirth) {
                        $sample = [ordered]@{
                            sampleUtc = [DateTime]::UtcNow.ToString('o')
                            # .NET Stopwatch uses the same Windows QPC clock as
                            # the native source and Desktop Duplication traces.
                            # Capture after reading the snapshot so status
                            # activity can be correlated with foreground time.
                            sampleQpc = [Diagnostics.Stopwatch]::GetTimestamp()
                            qpcHz = [Diagnostics.Stopwatch]::Frequency
                            elapsedMs = $nowMs
                            pid = $status.pid
                            processBirth = $status.processBirth
                            heartbeat = $status.heartbeat
                            route = $status.route
                            fgEnabled = $status.gameFrameGenerationOn
                            fgApplied = $status.appliedFrameGenerationOn
                            fgCreates = $status.ampereCreatedFeatures
                            fgEvaluations = $status.ampereEvaluateAttempts
                            fgBatches = $status.ampereSubmittedBatches
                            fgFailedBatches = $status.ampereFailedBatches
                            fgPresentationBuffers = $status.amperePresentationBuffers
                            fgFramesPresented = $status.actualFramesPresented
                            realFpsMilli = $status.realFpsMilli
                            fgFpsMilli = $status.dlssFpsMilli
                            fgState = $status.dlssgStatus
                            routeFailure = $status.universalRouteFailure
                            routeFailureReason = $status.universalRouteFailureReason
                            fgRejections = $status.ampereRejections
                            fgSuccessEvaluations = $status.ampereEvaluations
                            fgFirstFailure = $status.ampereFirstFailure
                            fgLastFailure = $status.ampereLastFailure
                            workingSetBytes = $process.WorkingSet64
                            privateMemoryBytes = $process.PrivateMemorySize64
                        }
                        $statusSamples.Add(($sample | ConvertTo-Json -Compress))
                    } elseif ([int]$status.pid -eq $process.Id) {
                        ++$statusBirthMismatches
                    }
                } catch {
                    # Writer and reader can race on a partially written JSON
                    # snapshot. The next sample can recover without changing it.
                    ++$statusReadFailures
                }
            }
        }
        if ($diagDue -and $nowMs -ge $diagnosticsDueMs -and !$process.HasExited) {
            $diagDue = $false
        # Run diagnostic out of process: a broken WCT call must never keep the
        # isolated GPU probe alive indefinitely or bypass the probe timeout.
        $diagStart = [Diagnostics.ProcessStartInfo]::new()
        $diagStart.FileName = $WaitChainTool
        $diagStart.Arguments = if ($CaptureStacks) { "$($process.Id) --stacks" } else { [string]$process.Id }
        $diagStart.WorkingDirectory = $logDir
        $diagStart.UseShellExecute = $false
        $diagStart.CreateNoWindow = $true
        $diagStart.RedirectStandardOutput = $true
        $diagStart.RedirectStandardError = $true
        $diag = [Diagnostics.Process]::new()
        $diag.StartInfo = $diagStart
        try {
            if (!$diag.Start()) { throw 'Failed to launch wait-chain diagnostic' }
            $diagOut = $diag.StandardOutput.ReadToEndAsync()
            $diagErr = $diag.StandardError.ReadToEndAsync()
            $diagCompleted = $diag.WaitForExit(10000)
            if (!$diagCompleted) { $diag.Kill(); $diag.WaitForExit(5000) | Out-Null }
            $diagText = $diagOut.GetAwaiter().GetResult() + $diagErr.GetAwaiter().GetResult()
            [IO.File]::WriteAllText($waitChainPath, $diagText)
            Write-Host "Wait chain: $waitChainPath (complete=$diagCompleted exit=$($diag.ExitCode))"
        } catch {
            [IO.File]::WriteAllText($waitChainPath, "Wait-chain capture failed: $_")
            Write-Warning "Wait-chain capture failed: $_"
        } finally { $diag.Dispose() }
        }
        $remainingMs = [Math]::Max(0, [int]($deadlineMs - $elapsed.ElapsedMilliseconds))
        if ($remainingMs -eq 0) { break }
        if ($process.WaitForExit([Math]::Min(250, $remainingMs))) {
            $completed = $true
            break
        }
    }
    if (!$completed) {
        $process.Kill()
        $process.WaitForExit(5000) | Out-Null
    }
    if ($CaptureDisplayFrames) {
        # Desktop Duplication observes only this process's window. Its lifetime
        # is bounded independently, even when stock Remix Shutdown hangs.
        $observerCompleted = $observer.WaitForExit(3000)
        if (!$observerCompleted) {
            $observer.Kill()
            $observer.WaitForExit(5000) | Out-Null
        }
        if (!$observer.HasExited) { throw 'Desktop observer did not exit after bounded termination' }
        $observerExitCode = $observer.ExitCode
        [IO.File]::WriteAllText($displayObserverLogPath,
            $observerOut.GetAwaiter().GetResult() + $observerErr.GetAwaiter().GetResult())
        Write-Host "Source presents: $sourceFramesPath"
        Write-Host "DWM frame samples: $displayFramesPath"
        Write-Host "Display observer: $displayObserverLogPath (complete=$observerCompleted exit=$observerExitCode)"
        Get-Content -LiteralPath $displayObserverLogPath
        if (!$observerCompleted -or $observerExitCode -ne 0) {
            $observerFailure = "Desktop observer failed (complete=$observerCompleted exit=$observerExitCode); inspect $displayObserverLogPath"
            Write-Warning 'Desktop observer failed or timed out. Source-frame timing alone does not establish displayed FG.'
        }
        if (Test-Path -LiteralPath $displayFramesPath -PathType Leaf) {
            $displaySamples = @(Get-Content -LiteralPath $displayFramesPath | Select-Object -Skip 1)
            Write-Host "Independent DWM samples=$($displaySamples.Count); distinct rendered interpolated frames NOT VERIFIED."
            if ($displaySamples.Count -eq 0) {
                Write-Warning 'No DWM foreground frame samples captured; check local desktop availability and probe focus.'
            }
        }
        if (!(Test-Path -LiteralPath $sourceFramesPath -PathType Leaf)) {
            Write-Warning 'Missing source-present trace; the native probe did not reach the instrumented frame loop.'
        }
        Write-Host 'DWM duplication records desktop-composited pixels; it does not prove physical monitor scanout.'
    }
    if ($CaptureStatus) {
        [IO.File]::WriteAllLines($statusPath, $statusSamples, [Text.UTF8Encoding]::new($false))
        Write-Host "Status samples: $statusPath (matched=$($statusSamples.Count) read-retries=$statusReadFailures birth-mismatches=$statusBirthMismatches)"
        if ($statusSamples.Count -gt 0) {
            $latest = $statusSamples[$statusSamples.Count - 1] | ConvertFrom-Json
            $maximumEvaluations = ($statusSamples | ForEach-Object { ($_ | ConvertFrom-Json).fgEvaluations } |
                Measure-Object -Maximum).Maximum
            Write-Host "Last MFG status: route=$($latest.route) fgEnabled=$($latest.fgEnabled) fgApplied=$($latest.fgApplied) creations=$($latest.fgCreates) evaluations=$($latest.fgEvaluations) successful=$($latest.fgSuccessEvaluations) batches=$($latest.fgBatches) failures=$($latest.fgFailedBatches)"
            Write-Host "MFG status reason: $($latest.routeFailureReason) (failure=$($latest.routeFailure), first=$($latest.fgFirstFailure), last=$($latest.fgLastFailure))"
            if ([long]$maximumEvaluations -gt 0) {
                Write-Host 'EVIDENCE: native FG provider evaluations observed; distinct displayed interpolated frames still NOT VERIFIED.'
            } else {
                Write-Warning 'No FG provider evaluations observed in captured process-matched status; displayed FG not verified.'
            }
            Write-Host 'Process working-set/private-memory counters are CPU-side process memory, not GPU VRAM.'
        }
    }
    [IO.File]::WriteAllText($stdoutPath, $stdoutTask.GetAwaiter().GetResult())
    [IO.File]::WriteAllText($stderrPath, $stderrTask.GetAwaiter().GetResult())
    if (!$process.HasExited) { throw 'Native probe did not exit after bounded termination' }
    # Record teardown separately from the GPU frame loop. A timeout stays a
    # runner failure, even when its completed rendering is diagnostic-eligible.
    $classificationArgs = @($classifier, '--stdout', $stdoutPath,
        '--output', $terminationPath, '--frames', [string]$Frames,
        '--exit-code', [string]$process.ExitCode, '--pid', [string]$process.Id,
        '--process-birth', [string]$expectedBirth)
    if ($CaptureStatus) { $classificationArgs += @('--status-trace', $statusPath) }
    if ($CaptureDisplayFrames) {
        $classificationArgs += @('--source-trace', $sourceFramesPath,
            '--desktop-trace', $displayFramesPath,
            '--observer-log', $displayObserverLogPath)
    }
    if (!$completed) { $classificationArgs += '--timed-out' }
    if ($CaptureDisplayFrames) {
        $classificationArgs += '--observer-required'
        $classificationArgs += @('--observer-exit-code', [string]$observerExitCode)
        if (!$observerCompleted) { $classificationArgs += '--observer-timed-out' }
    }
    & $PythonExe @classificationArgs
    if ($LASTEXITCODE -ne 0 -or !(Test-Path -LiteralPath $terminationPath -PathType Leaf)) {
        throw "Native probe termination classification failed; stdout: $stdoutPath"
    }
    Write-Host "Termination report: $terminationPath"
    Write-Host "Stdout: $stdoutPath"
    Write-Host "Stderr: $stderrPath"
    Get-Content -LiteralPath $stdoutPath
    if ($Mode -eq 'visible') {
        $text = [IO.File]::ReadAllText($stdoutPath)
        $matches = [regex]::Matches($text, 'Probe presents=(\d+) foreground presents=(\d+)')
        if ($matches.Count -gt 0) {
            $foregroundCount = [int]$matches[$matches.Count - 1].Groups[2].Value
            if ($foregroundCount -eq 0) {
                Write-Warning 'Visible probe never had foreground focus; this run cannot establish FG evaluation or displayed-frame evidence.'
            }
        }
    }
    if (!$completed) { throw "Native probe timed out after ${TimeoutSeconds}s and was terminated" }
    if ($process.ExitCode -ne 0) { throw "Native probe exited with code $($process.ExitCode)" }
    if ($observerFailure) { throw $observerFailure }
    Write-Host 'PASS: native probe exited cleanly; FG/displayed-frame evidence must be checked separately.'
} finally {
    if ($observer) {
        if ($observerStarted -and !$observer.HasExited) {
            $observer.Kill()
            $observer.WaitForExit(5000) | Out-Null
        }
        $observer.Dispose()
    }
    if ($started -and !$process.HasExited) {
        $process.Kill()
        $process.WaitForExit(5000) | Out-Null
    }
    $process.Dispose()
}
