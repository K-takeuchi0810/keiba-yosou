# Register the T-10 prediction runner (reform R1-1) in Windows Task Scheduler.
# Run:     powershell -ExecutionPolicy Bypass -File scripts\register_predict_t10_task.ps1
# Remove:  add -Unregister
# NOTE: ASCII-only on purpose. Windows PowerShell 5.1 reads .ps1 as the ANSI codepage
#       (cp932 on JP Windows); non-ASCII here breaks parsing.
param(
    [string]$TaskName = "keiba-predict-t10",
    [string]$StartTime = "09:00",
    [int]$RepeatMinutes = 5,
    [string]$EndTime = "17:00",
    [switch]$Unregister
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $PSScriptRoot "predict_t10.bat"
$hiddenRunner = Join-Path $env:LOCALAPPDATA "ScheduledTaskRunner\run-scheduled-task-hidden.vbs"

if (-not (Test-Path $runner)) { Write-Error "runner not found: $runner"; exit 1 }
if (-not (Test-Path $hiddenRunner)) { Write-Error "hidden runner not found: $hiddenRunner"; exit 1 }

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "removed existing task: $TaskName"
}
if ($Unregister) { Write-Host "unregister only: done"; exit 0 }

$actionArgs = "//B //NoLogo `"$hiddenRunner`" cmd `"$runner`""
$action = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\wscript.exe" -Argument $actionArgs

# Repeat every N minutes across the race-day window. Non-race days cost one cheap
# DB read (the runner finds no races and exits), so no date filter is needed.
$span = (Get-Date $EndTime) - (Get-Date $StartTime)
$trigger = New-ScheduledTaskTrigger -Daily -At $StartTime
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At $StartTime `
    -RepetitionInterval (New-TimeSpan -Minutes $RepeatMinutes) `
    -RepetitionDuration $span).Repetition

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 20)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings `
    -Description "Reform R1-1: recompute predictions at T-10 using PIT market state" | Out-Null

Write-Host "registered: $TaskName (every $RepeatMinutes min, $StartTime to $EndTime)"
Write-Host "  runner: $runner"
Write-Host "  output: data\runtime\t10\<date>.json + prediction_log table"
Write-Host "  idempotent: a race already recorded is skipped, so overlapping runs are safe"
