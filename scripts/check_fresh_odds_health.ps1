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
    [string]$TaskName = "keiba-fresh-odds",
    # 同じ decision を鳴らし続けないための間隔 (時間)。0 で毎回通知。
    [double]$AlertThrottleHours = 3,
    # 通知だけ止めたいとき (手動実行・検証用)。
    [switch]$NoNotify
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

# 4. FAIL/HOLD を誰も見ていない事故の防止 (2026-08-16〜08-22)。
# fetch_fresh_odds の python がハングしてログファイルを掴み続け、以降の起動が
# 全て exit 1 になっていた 6 日間、本チェックは FAIL を出し続けていたが通知先が
# 無く、誰も気づかないまま fresh odds がゼロになった (2026-08 の backtest 適格
# レースが 216 → 32 に激減)。decision が PASS 以外なら Discord に流し、PASS に
# 戻ったときは復旧通知を 1 回だけ出す。
$alertStatePath = Join-Path $runtimeDir "fresh_odds_alert_state.json"
if ($NoNotify) {
    Write-LogLine "notify: skipped (-NoNotify)"
} else {
    try {
        $decision = "UNKNOWN"
        $reason = ""
        if ($latest) {
            $decision = [string]$latest.decision
            $reason = [string]$latest.reason
        }
        $prevDecision = ""
        $lastNotifiedAt = $null
        if (Test-Path $alertStatePath) {
            $prevState = Get-Content -Path $alertStatePath -Raw -Encoding UTF8 | ConvertFrom-Json
            $prevDecision = [string]$prevState.last_decision
            if ($prevState.last_notified_at) {
                $lastNotifiedAt = [datetime]$prevState.last_notified_at
            }
        }

        $shouldNotify = $false
        $message = ""
        if ($decision -ne "PASS") {
            $throttled = $false
            if ($decision -eq $prevDecision -and $lastNotifiedAt -ne $null) {
                $elapsedHours = ((Get-Date) - $lastNotifiedAt).TotalHours
                if ($elapsedHours -lt $AlertThrottleHours) { $throttled = $true }
            }
            if ($throttled) {
                Write-LogLine "notify: throttled (decision=$decision, within $AlertThrottleHours h)"
            } else {
                $shouldNotify = $true
                $message = ":rotating_light: fresh odds health = $decision (reason=$reason). " +
                           "date=$Date task=$TaskName log=data/logs/fresh_odds_health_$Date.log"
            }
        } elseif ($prevDecision -ne "" -and $prevDecision -ne "PASS") {
            $shouldNotify = $true
            $message = ":white_check_mark: fresh odds health recovered: $prevDecision -> PASS (date=$Date)"
        }

        if ($shouldNotify) {
            & $venv64 "-m" "scripts.notify_discord" "--message" $message
            Write-LogLine "notify: sent decision=$decision"
            $notifiedAt = (Get-Date).ToString("s")
        } else {
            if ($lastNotifiedAt -ne $null) {
                $notifiedAt = $lastNotifiedAt.ToString("s")
            } else {
                $notifiedAt = $null
            }
        }
        @{
            last_decision = $decision
            last_notified_at = $notifiedAt
            updated_at = (Get-Date).ToString("s")
        } | ConvertTo-Json | Out-File -FilePath $alertStatePath -Encoding utf8
    } catch {
        Write-LogLine "WARN: notify step failed: $($_.Exception.Message)"
    }
}

Write-LogLine "=== check_fresh_odds_health.ps1 done (exit=$exitCode) ==="
exit $exitCode
