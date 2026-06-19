# Windows Task Scheduler に OOS backtest 自動起動タスクを登録する。
#
# **重要**: 登録時点では DISABLED で作成する。
# 1〜2 開催日ぶん healthcheck タスクが正常に動くことを確認したあと、
# ユーザーが明示的に enable してから動作させる。
#
# 起動時刻: 開催日終了後 (17:30)。fresh odds 取得 (09:00-16:40) と DB ingest が
# 完了したあと、その日のデータを反映した OOS backtest を健全性チェック経由で
# 起動する。
#
# usage:
#   powershell -ExecutionPolicy Bypass -File scripts/register_oos_backtest_auto_task.ps1
#
# 登録後の有効化手順 (ユーザの明示判断を要求):
#   Enable-ScheduledTask -TaskName keiba-oos-backtest-auto
#
# 削除:
#   schtasks /delete /tn keiba-oos-backtest-auto /f

param(
    [string]$TaskName = "keiba-oos-backtest-auto",
    [string]$StartTime = "17:30",
    [string]$StartDate = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if (-not $StartDate) {
    $StartDate = (Get-Date).ToString("yyyy/MM/dd")
}

$psScript = Join-Path $projectRoot "scripts\run_oos_backtest_if_fresh_ok.ps1"
if (-not (Test-Path $psScript)) {
    Write-Error "$psScript が無い。先に作成してください"
    exit 1
}

$tr = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$psScript`""

Write-Host "登録中: $TaskName (**初期 disabled**)"
Write-Host "  TR: $tr"
Write-Host "  Schedule: 毎日 ${StartTime} (開催日後) / 開始日=${StartDate}"

# 既存があれば削除
$exists = schtasks /query /tn "$TaskName" 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "既存タスクあり、削除して再登録"
    schtasks /delete /tn "$TaskName" /f 2>&1 | Out-Null
}

# /sc daily で毎日起動 (開催日でない日は exit 2 (HOLD) で早期 return する想定)
$result = schtasks /create `
    /tn "$TaskName" `
    /tr "$tr" `
    /sc daily `
    /st $StartTime `
    /sd $StartDate `
    /f

if ($LASTEXITCODE -ne 0) {
    Write-Error "schtasks /create 失敗 (exit=$LASTEXITCODE): $result"
    exit 1
}

# 登録直後に **無効化** する
# schtasks /change /tn ... /disable は標準的な方法
$disableResult = schtasks /change /tn "$TaskName" /disable
if ($LASTEXITCODE -ne 0) {
    Write-Warning "disable 失敗 (exit=$LASTEXITCODE): $disableResult"
    Write-Warning "手動で Disable-ScheduledTask -TaskName $TaskName を実行してください"
}

# 確認: 状態が Disabled になっているか
try {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
    $state = $task.State
    Write-Host ""
    Write-Host "登録完了。現在の State: $state"
    if ($state -ne "Disabled") {
        Write-Warning "想定と異なり State が $state になっている。Disable-ScheduledTask で明示的に無効化推奨"
    }
} catch {
    Write-Warning "状態確認失敗: $($_.Exception.Message)"
}

Write-Host ""
Write-Host "有効化するには (1〜2 開催日ぶん healthcheck が正常稼働したことを確認してから):"
Write-Host "  Enable-ScheduledTask -TaskName $TaskName"
Write-Host ""
Write-Host "動作テスト (有効化前でも単発実行可):"
Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\run_oos_backtest_if_fresh_ok.ps1 -DryRun"

exit 0
