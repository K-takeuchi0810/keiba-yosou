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

# 既存タスクの確認。
# PowerShell 5.1 + $ErrorActionPreference="Stop" の下では `schtasks /query` が
# 未存在時に stderr へ「指定されたファイルが見つかりません」を出し、
# NativeCommandError として停止する。これを避けるため Get-ScheduledTask を使う。
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "既存タスクあり (State=$($existing.State)) → 削除して再登録"
    # schtasks /delete の stderr 経路も NativeCommandError 化を避けるため
    # try/catch + LASTEXITCODE で安全に処理する
    try {
        $deleteOut = & schtasks /delete /tn "$TaskName" /f 2>&1
    } catch {
        # 例外まで上がるケースは稀だが catch しておく
        $deleteOut = $_.Exception.Message
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Error "schtasks /delete 失敗 (exit=$LASTEXITCODE): $deleteOut"
        exit 1
    }
} else {
    Write-Host "既存タスクなし (初回登録)"
}

# /f で「同名が残っていたら上書き」も担保 (Get-ScheduledTask の TOCTOU 対策)
$createOut = $null
try {
    $createOut = & schtasks /create `
        /tn "$TaskName" `
        /tr "$tr" `
        /sc minute /mo $IntervalMinutes `
        /st $StartTime /et $EndTime `
        /sd $StartDate `
        /f 2>&1
} catch {
    $createOut = $_.Exception.Message
}
if ($LASTEXITCODE -ne 0) {
    Write-Error "schtasks /create 失敗 (exit=$LASTEXITCODE): $createOut"
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
