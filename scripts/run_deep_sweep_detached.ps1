# Launch the remaining lambda/rank sweep runs detached from the caller.
# Run: powershell -ExecutionPolicy Bypass -File scripts\run_deep_sweep_detached.ps1
#
# Why detached: a sweep launched as a child of the agent shell dies when the
# session tears down (2026-06-18 and 2026-08-24 both lost multi-hour runs this
# way). Start-Process without -NoNewWindow survives the parent exiting.
# ASCII-only on purpose (Windows PowerShell 5.1 reads .ps1 as the ANSI codepage).
param([switch]$WhatIfOnly)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
$py = Join-Path $repo ".venv64\Scripts\python.exe"
if (-not (Test-Path $py)) { Write-Error "venv64 not found: $py"; exit 1 }

# name, rank_by, lambda_fade, lambda_boost
# name, rank_by, lambda_fade, lambda_boost, extra_args
$runs = @(
    @("p33-live-window-all",     "score", "0.0", "0.0", ""),
    @("p33-live-window-require", "score", "0.0", "0.0", "--require-market")
)
# 2 本目は期間が違う (通年)。下のループで名前を見て切り替える。

$logDir = Join-Path $repo "data\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$log = Join-Path $logDir "deep_sweep_detached_$stamp.log"

$lines = @()
foreach ($r in $runs) {
    $lines += '$env:PRED_RANK_BY = "' + $r[1] + '"'
    $lines += '$env:PRED_BLEND_MODE = "residual"'
    $lines += '$env:PRED_W_residual_lambda_fade = "' + $r[2] + '"'
    $lines += '$env:PRED_W_residual_lambda_boost = "' + $r[3] + '"'
    $lines += '$env:PYTHONIOENCODING = "utf-8"'
    $lines += 'Add-Content -Path "' + $log + '" -Value ("--- ' + $r[0] + ' start " + (Get-Date -Format HH:mm))'
    if ($r[0] -like "*live-window*") { $from = "20260718" } else { $from = "20260504" }
    $extra = ""
    if ($r.Count -gt 4) { $extra = " " + $r[4] }
    $lines += '& "' + $py + '" -m scripts.backtest --from ' + $from + ' --to 20260816 --pit-odds' + $extra + ' --save --rule-version ' + $r[0] + ' *>> "' + $log + '"'
}
$lines += 'Add-Content -Path "' + $log + '" -Value ("=== all done " + (Get-Date -Format HH:mm))'

$script = Join-Path $env:TEMP "deep_sweep_$stamp.ps1"
$lines -join "`r`n" | Out-File -FilePath $script -Encoding utf8

if ($WhatIfOnly) { Write-Host "would run: $script"; Get-Content $script; exit 0 }

Start-Process -FilePath "powershell.exe" `
    -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $script `
    -WorkingDirectory $repo -WindowStyle Hidden
Write-Host "launched detached. log: $log"
Write-Host "  runs: $($runs.Count) settings, about 1 hour each"
Write-Host "  survives session teardown (not a child of the caller)"
