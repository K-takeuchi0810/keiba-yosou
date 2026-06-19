# OS 管理プロセスで OOS backtest を再実行するための PowerShell スクリプト。
#
# 2026-06-18 の bg backtest 死亡 (Claude セッション切断で子プロセス kill) を受け、
# 親セッション寿命に依存しない形で長時間 backtest を走らせる。
#
# 使い方:
#   1. fresh odds 取得が安定稼働していることを確認:
#        Get-ScheduledTask -TaskName "keiba-fresh-odds" | Get-ScheduledTaskInfo
#        python -m scripts.fresh_odds_coverage --last 7
#      coverage で fresh_horses > 0 が確認できないなら、本スクリプトは実行しない。
#
#   2. 再実行:
#        powershell -ExecutionPolicy Bypass -File scripts/rerun_oos_backtest.ps1
#
#   3. 進捗確認 (別ターミナルから):
#        Get-Content data/logs/rerun_oos_*.log -Wait -Tail 30
#
# 出力:
#   data/logs/rerun_oos_<timestamp>.log     — stdout + stderr
#   data/backtest/<ts>_tan_p25-pop-*-oos-rerun-filtered.json + _records.json
#
# 親 PowerShell を閉じても Start-Process -WindowStyle Hidden は継続するので、
# セッション切断 / リモートデスクトップ切断にも耐える。

$ErrorActionPreference = "Stop"

# プロジェクトルートに移動
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $projectRoot

# log ディレクトリ確保
$logDir = Join-Path $projectRoot "data\logs"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
}

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = Join-Path $logDir "rerun_oos_$ts.log"

# pre-flight (CLAUDE.md ルール 1-ter)
Write-Host "=== Pre-flight checks ==="
Write-Host "Project root: $projectRoot"
Write-Host "Log file: $logFile"

# git status (uncommitted がある場合だけ警告)
$gitStatus = git -C $projectRoot status --short 2>$null
if ($gitStatus) {
    Write-Host "WARN: uncommitted changes detected:" -ForegroundColor Yellow
    Write-Host $gitStatus
    Write-Host "提案: commit してから走らせるか、変更が無関係なら続行可"
}

# fresh odds coverage の事前確認 (Plan Step 4 完了の参考)
$coveragePath = Join-Path $projectRoot "data\logs\fresh_odds_coverage.jsonl"
if (Test-Path $coveragePath) {
    $coverageLines = (Get-Content $coveragePath | Measure-Object -Line).Lines
    Write-Host "Coverage JSONL lines: $coverageLines"
} else {
    Write-Host "WARN: $coveragePath が無い。Plan Step 4 (fresh odds 安定稼働) が未確認" -ForegroundColor Yellow
}

# 再実行コマンド (順次 pop_0_0_0 → pop_7_4_2)
# Start-Process -WindowStyle Hidden で detach。-NoNewWindow にしない (親終了で子も死ぬ可能性)
$venv64 = Join-Path $projectRoot ".venv64\Scripts\python.exe"
if (-not (Test-Path $venv64)) {
    Write-Error ".venv64 が無い: $venv64"
    exit 1
}

$bashCmd = @"
echo "=== rerun_oos started at \$(date +%H:%M:%S) ===" > "$logFile"
echo "" >> "$logFile"
echo "=== pop_0_0_0 OOS start at \$(date +%H:%M:%S) ===" >> "$logFile"
PRED_W_popularity_first=0 PRED_W_popularity_second=0 PRED_W_popularity_third=0 \
  "$venv64" -m scripts.backtest \
  --from 20260101 --to 20260614 \
  --save --save-records \
  --rule-version p25-pop-0-0-0-oos-rerun \
  >> "$logFile" 2>&1

echo "" >> "$logFile"
echo "=== pop_0_0_0 done at \$(date +%H:%M:%S), pop_7_4_2 start ===" >> "$logFile"
"$venv64" -m scripts.backtest \
  --from 20260101 --to 20260614 \
  --save --save-records \
  --rule-version p25-pop-7-4-2-oos-rerun \
  >> "$logFile" 2>&1

echo "" >> "$logFile"
echo "=== rerun_oos done at \$(date +%H:%M:%S) ===" >> "$logFile"
"@

# bash 経由で実行 (Windows 上の Git Bash で env override を扱うため)
# Start-Process で detach すれば、本 PowerShell を閉じても継続する
Write-Host ""
Write-Host "=== Launching backtest in detached process ==="
Write-Host "推定所要時間: 45-60 分 (1620 races x 2 variants)"
Write-Host "進捗を見るには別ターミナルで: Get-Content $logFile -Wait -Tail 30"
Write-Host ""

# bash -c を Start-Process で hidden + detach
$bashPath = (Get-Command bash -ErrorAction SilentlyContinue).Source
if (-not $bashPath) {
    # Git Bash の典型パス fallback
    $bashPath = "C:\Program Files\Git\bin\bash.exe"
    if (-not (Test-Path $bashPath)) {
        Write-Error "bash が見つからない。Git for Windows がインストールされているか確認してください"
        exit 1
    }
}

# 一時 bash ファイルに書き出す (PowerShell から bash -c で直接渡すと quoting 地獄)
$tmpBashFile = Join-Path $env:TEMP "rerun_oos_$ts.sh"
$bashCmd | Out-File -FilePath $tmpBashFile -Encoding UTF8

# Hidden + detach 起動
Start-Process -FilePath $bashPath `
              -ArgumentList "-c", "`"$tmpBashFile`"" `
              -WorkingDirectory $projectRoot `
              -WindowStyle Hidden
              # -NoNewWindow を付けない (親終了で子も道連れになる可能性)

Write-Host "起動完了。PID は task manager または ps で確認可能"
Write-Host ""
Write-Host "完了後の確認手順:"
Write-Host "  1. ls -la data/backtest/*oos-rerun*.json"
Write-Host "  2. python -c `"import json; d=json.load(open('data/backtest/<JSON>', encoding='utf-8')); print(d.get('buy_only_return_rate'), d.get('buy_only_return_rate_ci95'))`""
Write-Host "  3. expert-review メタスキルで scorecard 生成"
