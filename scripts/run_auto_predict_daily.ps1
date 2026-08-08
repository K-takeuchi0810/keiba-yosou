# Runs the daily pipeline in a bounded child process and always removes the
# whole process tree when JV-Link or a child command stops responding.
# Keep this file ASCII-only for Windows PowerShell 5.1.
param(
    [ValidateRange(1, 86400)]
    [int]$TimeoutSeconds = 1200,
    [string]$CommandPath = "",
    [switch]$SkipNotification
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
if (-not $CommandPath) {
    $CommandPath = Join-Path $PSScriptRoot "auto_predict_daily.bat"
}
if (-not (Test-Path -LiteralPath $CommandPath -PathType Leaf)) {
    Write-Error "command not found: $CommandPath"
    exit 2
}

$logDir = Join-Path $repo "data\logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$watchdogLog = Join-Path $logDir "auto_predict_watchdog.log"
function Write-WatchdogLog([string]$Message) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -LiteralPath $watchdogLog -Value $line -Encoding ASCII
}

function Send-WatchdogAlert([string]$Reason) {
    if ($SkipNotification) { return }
    $python = Join-Path $repo ".venv64\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        Write-WatchdogLog "notification skipped: python not found"
        return
    }
    $message = "WARN: keiba auto predict watchdog $Reason; see data/logs/auto_predict_watchdog.log"
    $notifyArgs = '-m scripts.notify_discord --message "{0}"' -f $message
    $notify = Start-Process -FilePath $python -ArgumentList $notifyArgs `
        -WorkingDirectory $repo -WindowStyle Hidden -PassThru
    $null = $notify.Handle
    if (-not $notify.WaitForExit(30000)) {
        & taskkill.exe /PID $notify.Id /T /F | Out-Null
        Write-WatchdogLog "notification timed out"
        return
    }
    $notify.Refresh()
    Write-WatchdogLog "notification exit=$($notify.ExitCode)"
}

$arguments = @("/d", "/c", ('"{0}"' -f $CommandPath))
$process = Start-Process -FilePath $env:ComSpec -ArgumentList $arguments `
    -WorkingDirectory $repo -WindowStyle Hidden -PassThru
$null = $process.Handle
Write-WatchdogLog "start pid=$($process.Id) timeout_sec=$TimeoutSeconds command=$CommandPath"

if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
    Write-WatchdogLog "timeout pid=$($process.Id); terminating process tree"
    if (-not $process.HasExited) {
        & taskkill.exe /PID $process.Id /T /F | Out-Null
        $killExitCode = $LASTEXITCODE
        if ($killExitCode -ne 0 -and -not $process.HasExited) {
            Write-WatchdogLog "tree termination failed pid=$($process.Id) taskkill_exit=$killExitCode"
            Send-WatchdogAlert "tree termination failed"
            exit 125
        }
    }
    if (-not $process.WaitForExit(10000)) {
        Write-WatchdogLog "tree still running after termination pid=$($process.Id)"
        Send-WatchdogAlert "tree still running after termination"
        exit 125
    }
    Write-WatchdogLog "tree terminated pid=$($process.Id)"
    Send-WatchdogAlert "timed out after $TimeoutSeconds seconds"
    exit 124
}

$process.WaitForExit()
$process.Refresh()
$exitCode = [int]$process.ExitCode
Write-WatchdogLog "finish pid=$($process.Id) exit=$exitCode"
exit $exitCode
