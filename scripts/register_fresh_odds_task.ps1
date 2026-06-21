# Windows Task Scheduler に keiba-fresh-odds (本体) を登録する。
#
# 09:00 から 16:40 まで 10 分おきに scripts/fetch_fresh_odds.bat を起動。
#
# 重要 (2026-06-21 新規):
#   従来は手動 `schtasks /create /sc minute /sd ... /st ... /et ...` で登録
#   していたが、これは `<TimeTrigger>` (1 日限り) として保存され、翌日以降
#   発火しないバグが発覚 (2026-06-21 Day2 監視で検出)。
#   本スクリプトは `Register-ScheduledTask` + Daily CalendarTrigger +
#   Repetition の組み合わせで毎日繰り返す形に登録する。
#
# usage:
#   powershell -ExecutionPolicy Bypass -File scripts/register_fresh_odds_task.ps1

param(
    [string]$TaskName = "keiba-fresh-odds",
    [string]$StartTime = "09:00",
    [int]$IntervalMinutes = 10,
    [int]$DurationMinutes = 460  # 09:00 → 16:40 = 7h40m = 460 分
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

$batScript = Join-Path $projectRoot "scripts\fetch_fresh_odds.bat"
if (-not (Test-Path $batScript)) {
    Write-Error "$batScript が無い。先に作成してください"
    exit 1
}

Write-Host "登録中: $TaskName"
Write-Host "  実行ファイル: $batScript"
Write-Host "  Schedule: 毎日 ${StartTime} 開始、${IntervalMinutes} 分おき、${DurationMinutes} 分間"

# 既存タスクの削除
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "既存タスクあり (State=$($existing.State)) → Unregister-ScheduledTask で削除"
    try {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
    } catch {
        Write-Error "Unregister-ScheduledTask 失敗: $($_.Exception.Message)"
        exit 1
    }
} else {
    Write-Host "既存タスクなし (初回登録)"
}

# Action: cmd.exe /c で .bat を実行
$action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$batScript`""

# Trigger: 毎日 $StartTime に発火、$DurationMinutes 分間 $IntervalMinutes 分おきに繰り返し
$dailyTrigger = New-ScheduledTaskTrigger -Daily -At $StartTime
$tmpOnceTrigger = New-ScheduledTaskTrigger -Once -At $StartTime `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Minutes $DurationMinutes)
$dailyTrigger.Repetition = $tmpOnceTrigger.Repetition

# Settings: バッテリ実行許可、PC 起動遅れ時の追いつき起動を許可
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable

# 登録
try {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $dailyTrigger `
        -Settings $settings `
        -Description "fresh odds 取得 (P25 Plan Step 4 / 2026-06-21 daily trigger 修正版)" `
        -ErrorAction Stop | Out-Null
} catch {
    Write-Error "Register-ScheduledTask 失敗: $($_.Exception.Message)"
    exit 1
}

# 確認
$registered = Get-ScheduledTask -TaskName $TaskName
$info = $registered | Get-ScheduledTaskInfo
Write-Host ""
Write-Host "登録完了:"
Write-Host ("  State:        {0}" -f $registered.State)
Write-Host ("  NextRunTime:  {0}" -f $info.NextRunTime)
Write-Host ("  LastRunTime:  {0}" -f $info.LastRunTime)
Write-Host ""
Write-Host "確認コマンド:"
Write-Host "  Get-ScheduledTask -TaskName $TaskName | Get-ScheduledTaskInfo"

exit 0
