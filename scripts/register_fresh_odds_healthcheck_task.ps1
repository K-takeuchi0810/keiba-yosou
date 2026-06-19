# Windows Task Scheduler に fresh odds health check タスクを登録する。
#
# 9:15 から 16:55 まで 15 分おきに自動起動。
# (= keiba-fresh-odds の各起動 (HH:00, HH:10, HH:20, HH:30, HH:40, HH:50 のうち) のあと
#   5 分以内に health check が走る配置)
#
# 初期状態: enabled。1〜2 開催日ぶん観察した後、必要なら手動で /change /disable できる。
#
# usage:
#   powershell -ExecutionPolicy Bypass -File scripts/register_fresh_odds_healthcheck_task.ps1
#
# 既存タスクがあれば /f で上書き。

param(
    [string]$TaskName = "keiba-fresh-odds-healthcheck",
    [string]$StartTime = "09:15",
    [string]$EndTime = "16:55",
    [string]$StartDate = "",
    [int]$IntervalMinutes = 15
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if (-not $StartDate) {
    # 今日の日付 (yyyy/MM/dd)
    $StartDate = (Get-Date).ToString("yyyy/MM/dd")
}

$psScript = Join-Path $projectRoot "scripts\check_fresh_odds_health.ps1"
if (-not (Test-Path $psScript)) {
    Write-Error "$psScript が無い。先に作成してください"
    exit 1
}

# schtasks /create 用の TR (Task Runs) 文字列
$tr = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$psScript`""

Write-Host "登録中: $TaskName"
Write-Host "  TR: $tr"
Write-Host "  Schedule: 毎 ${IntervalMinutes} 分 ${StartTime}-${EndTime} 開始日=${StartDate}"

# 既存があれば削除してから作成 (/f で上書きより明示的)
$exists = schtasks /query /tn "$TaskName" 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "既存タスクあり、削除して再登録"
    schtasks /delete /tn "$TaskName" /f 2>&1 | Out-Null
}

$result = schtasks /create `
    /tn "$TaskName" `
    /tr "$tr" `
    /sc minute /mo $IntervalMinutes `
    /st $StartTime /et $EndTime `
    /sd $StartDate `
    /f

if ($LASTEXITCODE -ne 0) {
    Write-Error "schtasks /create 失敗 (exit=$LASTEXITCODE): $result"
    exit 1
}

Write-Host ""
Write-Host "登録完了。次回確認:"
Write-Host "  Get-ScheduledTask -TaskName $TaskName | Get-ScheduledTaskInfo"
Write-Host ""
Write-Host "無効化したい場合:"
Write-Host "  Disable-ScheduledTask -TaskName $TaskName"
Write-Host ""
Write-Host "削除したい場合:"
Write-Host "  schtasks /delete /tn $TaskName /f"

exit 0
