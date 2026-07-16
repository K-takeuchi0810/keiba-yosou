# Register the F4 daily prediction task in Windows Task Scheduler.
# Run:     powershell -ExecutionPolicy Bypass -File scripts\register_auto_predict_task.ps1
# Remove:  add -Unregister
# NOTE: ASCII-only on purpose. Windows PowerShell 5.1 reads .ps1 as the ANSI codepage
#       (cp932 on JP Windows); non-ASCII here breaks parsing. Keep messages ASCII.
param(
    [string]$TaskName = "keiba-auto-predict",
    [string]$StartTime = "09:30",
    [switch]$Unregister
)

$ErrorActionPreference = "Stop"
$repo = "C:\Users\kizun\dev\keiba-yosou"
$batScript = Join-Path $repo "scripts\auto_predict_daily.bat"

if (-not (Test-Path $batScript)) { Write-Error "bat not found: $batScript"; exit 1 }

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "removed existing task: $TaskName"
}
if ($Unregister) { Write-Host "unregister only: done"; exit 0 }

$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$batScript`""
# Daily at $StartTime once. Non-race days are skipped by auto_predict itself.
$trigger = New-ScheduledTaskTrigger -Daily -At $StartTime
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings `
    -Description "F4 daily: fetch+mining -> gap check -> auto_predict -> Pages/Discord" | Out-Null
Write-Host "registered: $TaskName (daily $StartTime)"
Write-Host "  chain: fetch_full(32bit) -> fetch_mining(32bit) -> gap check -> auto_predict(64bit)"
Write-Host "  exit bits: 1=fresh odds gap, 2=prediction failure"
Write-Host "manual test: Start-ScheduledTask -TaskName $TaskName"
