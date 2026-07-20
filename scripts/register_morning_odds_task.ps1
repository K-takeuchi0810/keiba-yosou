# Register the F3 morning odds anchor task.
#
# The default 08:45 start is deliberate: recent first JRA posts are 09:50,
# so 09:30 cannot create a snapshot at least 60 minutes before every race.
# The existing keiba-fresh-odds task starts at 09:00. Both commands call the
# same Python module and therefore share its atomic single-run lock.

param(
    [string]$TaskName = "keiba-morning-odds",
    [string]$StartTime = "08:45",
    [int]$ExecutionTimeLimitMinutes = 60
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$batScript = Join-Path $projectRoot "scripts\fetch_morning_odds.bat"

if (-not (Test-Path -LiteralPath $batScript)) {
    throw "Morning odds batch file not found: $batScript"
}

$action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/d /c call `"$batScript`""
$trigger = New-ScheduledTaskTrigger -Daily -At $StartTime
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes $ExecutionTimeLimitMinutes)
$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "F3 morning odds anchor, fixed window=600 and min-lead=0" `
    -Force `
    -ErrorAction Stop | Out-Null

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
$info = $task | Get-ScheduledTaskInfo

Write-Host "Registered: $TaskName"
Write-Host ("State: {0}" -f $task.State)
Write-Host ("NextRunTime: {0:o}" -f $info.NextRunTime)
Write-Host ("Action: {0} {1}" -f $task.Actions.Execute, $task.Actions.Arguments)
Write-Host ("ExecutionTimeLimit: {0}" -f $task.Settings.ExecutionTimeLimit)
Write-Host "Merge coupling: the action path is in main; it can run only after this branch is merged."
