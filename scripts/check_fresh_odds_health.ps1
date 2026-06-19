# fresh odds 取得運用の健全性チェック (PowerShell orchestrator)。
#
# Get-ScheduledTaskInfo で keiba-fresh-odds の状態を取り、Python core に渡して
# JSONL + DB を判定させ、結果を data/runtime/ に保存する。Task Scheduler から
# 09:15 などに自動起動される想定。
#
# usage:
#   powershell -ExecutionPolicy Bypass -File scripts/check_fresh_odds_health.ps1
#   powershell -ExecutionPolicy Bypass -File scripts/check_fresh_odds_health.ps1 -Date 20260620
#
# exit code:
#   0: PASS
#   1: FAIL
#   2: HOLD
#   3: NOT_EVALUABLE
#   4: internal error
#
# 出力:
#   data/runtime/fresh_odds_health_<ts>.json
#   data/runtime/fresh_odds_health_latest.json
#   data/logs/fresh_odds_health_<YYYYMMDD>.log

param(
    [string]$Date = "",
    [string]$CheckAfterTime = "09:00",
    [string]$TaskName = "keiba-fresh-odds"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $projectRoot

if (-not $Date) {
    $Date = (Get-Date).ToString("yyyyMMdd")
}

$runtimeDir = Join-Path $projectRoot "data\runtime"
$logDir = Join-Path $projectRoot "data\logs"
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$logFile = Join-Path $logDir "fresh_odds_health_$Date.log"
function Write-LogLine {
    param([string]$msg)
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $msg"
    Add-Content -Path $logFile -Value $line -Encoding UTF8
    Write-Host $line
}

Write-LogLine "=== check_fresh_odds_health.ps1 start (date=$Date, threshold=$CheckAfterTime) ==="

# 1. scheduler 情報を Get-ScheduledTaskInfo で取得し、tempfile に書き出す
# (PowerShell → child Python の JSON 引数は quote escaping で壊れるため、
# tempfile 経由で渡す)
$schedulerHash = $null
try {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
    $info = $task | Get-ScheduledTaskInfo
    $schedulerHash = @{
        registered = $true
        last_run_time = $info.LastRunTime.ToString("yyyy-MM-ddTHH:mm:ss")
        last_task_result = [int]$info.LastTaskResult
        next_run_time = $info.NextRunTime.ToString("yyyy-MM-ddTHH:mm:ss")
        number_of_missed_runs = [int]$info.NumberOfMissedRuns
    }
} catch {
    Write-LogLine "scheduler '$TaskName' not registered or unreachable: $($_.Exception.Message)"
    $schedulerHash = @{ registered = $false }
}

$schedulerJsonText = $schedulerHash | ConvertTo-Json -Compress
Write-LogLine "scheduler info: $schedulerJsonText"

# Python が読む tempfile に書き出す (UTF-8 BOM なしで)
$schedulerTmpPath = [System.IO.Path]::Combine(
    [System.IO.Path]::GetTempPath(),
    "fresh_odds_scheduler_$(Get-Date -Format 'yyyyMMddHHmmss')_$PID.json"
)
[System.IO.File]::WriteAllText(
    $schedulerTmpPath,
    $schedulerJsonText,
    (New-Object System.Text.UTF8Encoding($false))
)

# 2. Python core を呼ぶ
$venv64 = Join-Path $projectRoot ".venv64\Scripts\python.exe"
if (-not (Test-Path $venv64)) {
    Write-LogLine "ERROR: .venv64 not found at $venv64"
    Remove-Item $schedulerTmpPath -Force -ErrorAction SilentlyContinue
    exit 4
}

Write-LogLine "invoking check_fresh_odds_health.py"
$pythonArgs = @(
    "-m", "scripts.check_fresh_odds_health",
    "--scheduler-json-path", $schedulerTmpPath,
    "--date", $Date,
    "--check-after-time", $CheckAfterTime,
    "--runtime-dir", $runtimeDir,
    "--quiet"
)
& $venv64 $pythonArgs
$exitCode = $LASTEXITCODE
Remove-Item $schedulerTmpPath -Force -ErrorAction SilentlyContinue

# 3. latest.json を読んで結果ログに残す
$latestPath = Join-Path $runtimeDir "fresh_odds_health_latest.json"
if (Test-Path $latestPath) {
    try {
        $latest = Get-Content -Path $latestPath -Raw -Encoding UTF8 | ConvertFrom-Json
        Write-LogLine "decision=$($latest.decision) reason=$($latest.reason)"
        Write-LogLine "scheduler.ok=$($latest.scheduler.ok) coverage.ok=$($latest.coverage.ok) db.ok=$($latest.db.ok)"
        Write-LogLine "coverage.ok_races_today=$($latest.coverage.ok_races_today) db.fresh_rows=$($latest.db.fresh_horse_rows_since_check_time)"
        if ($latest.coverage.contamination_detected) {
            Write-LogLine "WARN: coverage contamination detected. 例: $($latest.coverage.contamination_examples | ConvertTo-Json -Compress)"
        }
    } catch {
        Write-LogLine "WARN: cannot parse $latestPath : $($_.Exception.Message)"
    }
} else {
    Write-LogLine "WARN: $latestPath not found after python run"
}

Write-LogLine "=== check_fresh_odds_health.ps1 done (exit=$exitCode) ==="
exit $exitCode
