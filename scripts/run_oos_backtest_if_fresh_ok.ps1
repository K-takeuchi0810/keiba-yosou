# fresh odds health が PASS のときだけ OOS backtest を起動する条件付き launcher。
#
# - data/runtime/fresh_odds_health_latest.json を読む
# - decision=PASS のときだけ scripts/rerun_oos_backtest.ps1 を呼ぶ
# - PASS 以外は logs に理由を残してスキップ
# - lock ファイルで多重起動防止
# - 既存 backtest Python プロセスが居れば起動しない
#
# usage:
#   powershell -ExecutionPolicy Bypass -File scripts/run_oos_backtest_if_fresh_ok.ps1
#
# exit code:
#   0: PASS で起動した
#   1: PASS だが起動できず (lock / existing process)
#   2: HOLD でスキップ (再試行で PASS になりうる)
#   3: FAIL / NOT_EVALUABLE でスキップ (採用判断に進めない)
#   4: internal error

param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $projectRoot

$today = (Get-Date).ToString("yyyyMMdd")
$logDir = Join-Path $projectRoot "data\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir "oos_backtest_auto_$today.log"

function Write-LogLine {
    param([string]$msg)
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $msg"
    Add-Content -Path $logFile -Value $line -Encoding UTF8
    Write-Host $line
}

Write-LogLine "=== run_oos_backtest_if_fresh_ok.ps1 start (dry_run=$DryRun) ==="

# 1. latest health JSON を読む
$latestPath = Join-Path $projectRoot "data\runtime\fresh_odds_health_latest.json"
if (-not (Test-Path $latestPath)) {
    Write-LogLine "SKIP: $latestPath が無い。先に scripts/check_fresh_odds_health.ps1 を走らせてください"
    Write-LogLine "=== exit 3 (NOT_EVALUABLE) ==="
    exit 3
}

try {
    $health = Get-Content -Path $latestPath -Raw -Encoding UTF8 | ConvertFrom-Json
} catch {
    Write-LogLine "ERROR: cannot parse $latestPath : $($_.Exception.Message)"
    exit 4
}

Write-LogLine "health decision=$($health.decision) reason=$($health.reason)"
Write-LogLine "health checked_at=$($health.checked_at) date=$($health.date)"

# 2. health JSON の鮮度確認 (古すぎる latest を流用しない)
try {
    $checkedAt = [datetime]::Parse($health.checked_at)
    $ageMin = [int](((Get-Date) - $checkedAt).TotalMinutes)
    Write-LogLine "health age: ${ageMin} min"
    if ($ageMin -gt 60) {
        Write-LogLine "WARN: health JSON が ${ageMin} 分前のもの。古すぎるので採用しない"
        Write-LogLine "=== exit 3 (NOT_EVALUABLE) ==="
        exit 3
    }
} catch {
    Write-LogLine "WARN: cannot parse checked_at: $($_.Exception.Message)"
}

# 3. decision 別の分岐 (PowerShell 5.1 + non-BOM UTF-8 で switch が parse 失敗する
# 事例があるため if/elseif で記述)
$decision = $health.decision
if ($decision -eq "PASS") {
    Write-LogLine "decision=PASS, OOS backtest 起動条件を確認"
} elseif ($decision -eq "HOLD") {
    Write-LogLine "SKIP (HOLD): $($health.reason)"
    Write-LogLine "=== exit 2 (HOLD) ==="
    exit 2
} elseif ($decision -eq "FAIL") {
    Write-LogLine "SKIP (FAIL): $($health.reason)"
    Write-LogLine "=== exit 3 (FAIL) ==="
    exit 3
} elseif ($decision -eq "NOT_EVALUABLE") {
    Write-LogLine "SKIP (NOT_EVALUABLE): $($health.reason)"
    Write-LogLine "=== exit 3 (NOT_EVALUABLE) ==="
    exit 3
} else {
    Write-LogLine "ERROR: unknown decision: $decision"
    exit 4
}

# 4. lock ファイル (多重起動防止)
$lockFile = Join-Path $projectRoot "data\runtime\oos_backtest_auto.lock"
$lockParent = Split-Path $lockFile -Parent
New-Item -ItemType Directory -Force -Path $lockParent | Out-Null

if (Test-Path $lockFile) {
    $lockContent = Get-Content -Path $lockFile -Raw -Encoding UTF8
    $lockAge = [int](((Get-Date) - (Get-Item $lockFile).LastWriteTime).TotalMinutes)
    Write-LogLine "lock file exists (age=${lockAge}min): $lockContent"
    # 6 時間以上古ければ stale lock とみなし削除して継続
    if ($lockAge -gt 360) {
        Write-LogLine "stale lock (>6h), removing and continuing"
        Remove-Item $lockFile -Force
    } else {
        Write-LogLine "SKIP: 別プロセスが起動中の可能性。lock が残っている"
        Write-LogLine "=== exit 1 (lock held) ==="
        exit 1
    }
}

# 5. 既存 Python backtest プロセスの検知
# scripts.backtest を引数に持つ python.exe が居れば skip
$existingBacktest = $null
try {
    $existingBacktest = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction Stop |
        Where-Object { $_.CommandLine -like "*scripts.backtest*" } |
        Select-Object -First 1
} catch {
    Write-LogLine "WARN: cannot enumerate processes via WMI: $($_.Exception.Message)"
}
if ($existingBacktest) {
    Write-LogLine "SKIP: 既存 backtest プロセス検出 (pid=$($existingBacktest.ProcessId))"
    Write-LogLine "=== exit 1 (existing process) ==="
    exit 1
}

# 6. lock 取得 + rerun_oos_backtest.ps1 を起動
$lockPayload = @{
    pid = $PID
    started_at = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
    health_checked_at = $health.checked_at
} | ConvertTo-Json -Compress
$lockPayload | Out-File -FilePath $lockFile -Encoding UTF8

if ($DryRun) {
    Write-LogLine "DRY-RUN: rerun_oos_backtest.ps1 起動はスキップ。lock のみ作成"
    Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
    Write-LogLine "=== exit 0 (dry-run PASS) ==="
    exit 0
}

$rerunScript = Join-Path $projectRoot "scripts\rerun_oos_backtest.ps1"
if (-not (Test-Path $rerunScript)) {
    Write-LogLine "ERROR: $rerunScript が無い"
    Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
    exit 4
}

Write-LogLine "起動: $rerunScript"
try {
    # rerun_oos_backtest.ps1 自体が Start-Process で detach するため、
    # 本スクリプトは launcher 側 PS の終了を待たずに戻る
    & powershell -NoProfile -ExecutionPolicy Bypass -File $rerunScript
    $rerunExit = $LASTEXITCODE
    Write-LogLine "rerun_oos_backtest.ps1 returned exit=$rerunExit"
} catch {
    Write-LogLine "ERROR: rerun_oos_backtest.ps1 起動失敗: $($_.Exception.Message)"
    Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
    exit 4
}

# lock は rerun が detach 起動したあと、本スクリプトの終了時に解放してよい
# (rerun_oos_backtest.ps1 自体が長時間プロセスではない。起動して即終了する)
Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
Write-LogLine "=== exit 0 (launched) ==="
exit 0
