# Register the F4 daily prediction task in Windows Task Scheduler.
# Run:     powershell -ExecutionPolicy Bypass -File scripts\register_auto_predict_task.ps1
# Remove:  add -Unregister
# NOTE: ASCII-only on purpose. Windows PowerShell 5.1 reads .ps1 as the ANSI codepage
#       (cp932 on JP Windows); non-ASCII here breaks parsing. Keep messages ASCII.
param(
    [string]$TaskName = "keiba-auto-predict",
    [string]$StartTime = "08:00",
    [string]$SecondStartTime = "09:00",
    # Third attempt: on 2026-07-25 and 2026-08-01 the entries (SE) were still
    # missing at 09:30 and only arrived around 11:30, so both earlier runs had
    # nothing to predict with. auto_predict now refuses to publish an empty page
    # (exit 2) and needs a later retry to still deliver that day's predictions.
    [string]$ThirdStartTime = "11:00",
    [switch]$Unregister
)

$ErrorActionPreference = "Stop"
$repo = "C:\Users\kizun\dev\keiba-yosou"
$watchdogScript = Join-Path $repo "scripts\run_auto_predict_daily.ps1"
$hiddenRunner = Join-Path $env:LOCALAPPDATA "ScheduledTaskRunner\run-scheduled-task-hidden.vbs"

if (-not (Test-Path $watchdogScript)) { Write-Error "watchdog not found: $watchdogScript"; exit 1 }
if (-not (Test-Path $hiddenRunner)) { Write-Error "hidden runner not found: $hiddenRunner"; exit 1 }

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "removed existing task: $TaskName"
}
if ($Unregister) { Write-Host "unregister only: done"; exit 0 }

$actionArgs = "//B //NoLogo `"$hiddenRunner`" ps1 `"$watchdogScript`""
$action = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\wscript.exe" -Argument $actionArgs
# Daily at both times. Non-race days are skipped by auto_predict itself.
$trigger = @(
    New-ScheduledTaskTrigger -Daily -At $StartTime
    New-ScheduledTaskTrigger -Daily -At $SecondStartTime
    New-ScheduledTaskTrigger -Daily -At $ThirdStartTime
)
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings `
    -Description "F4 daily: fetch+mining -> gap check -> auto_predict -> Pages/Discord" | Out-Null
Write-Host "registered: $TaskName (daily $StartTime, $SecondStartTime and $ThirdStartTime)"
Write-Host "  watchdog: 1200 sec; timeout kills the complete child process tree"
Write-Host "  chain: fetch_full(32bit) -> fetch_mining(32bit) -> gap check -> auto_predict(64bit)"
Write-Host "  exit bits: 1=fresh odds gap, 2=prediction failure, 4=fetch_full failure"
Write-Host "manual test: Start-ScheduledTask -TaskName $TaskName"
