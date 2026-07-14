# F4 予想自動生成タスクを Windows Task Scheduler に登録する (毎朝実行)。
# 実行: PowerShell で
#   powershell -ExecutionPolicy Bypass -File scripts\register_auto_predict_task.ps1
# 解除: -Unregister を付ける。
param(
    [string]$TaskName = "keiba-auto-predict",
    [string]$StartTime = "09:30",
    [switch]$Unregister
)

$ErrorActionPreference = "Stop"
$repo = "C:\Users\kizun\dev\keiba-yosou"
$batScript = Join-Path $repo "scripts\auto_predict_daily.bat"

if (-not (Test-Path $batScript)) { Write-Error "bat が無い: $batScript"; exit 1 }

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "既存タスク削除: $TaskName"
}
if ($Unregister) { Write-Host "解除のみ完了"; exit 0 }

$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$batScript`""
# 毎朝 $StartTime に 1 回。開催日判定は auto_predict 側 (非開催日は skip) が行う。
$trigger = New-ScheduledTaskTrigger -Daily -At $StartTime
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings `
    -Description "F4 日次予想生成 + Pages 公開 + Discord 通知 (2026-07-12)" | Out-Null
Write-Host "登録完了: $TaskName ($StartTime 毎日)"
Write-Host "  → fetch_full(32bit) → auto_predict(64bit) → main push → Pages/Discord"
Write-Host "手動テスト: Start-ScheduledTask -TaskName $TaskName"
