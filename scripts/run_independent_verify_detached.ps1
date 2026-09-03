# Launch the independent ROI recalculation detached from the caller.
# Run: powershell -ExecutionPolicy Bypass -File scripts\run_independent_verify_detached.ps1
#
# Purpose: recompute the headline ROI with a separate implementation
# (scripts/verify_roi_independent.py) so a bug in scripts/backtest.py's
# aggregation cannot be the reason the number looks the way it does.
# ASCII-only on purpose (Windows PowerShell 5.1 reads .ps1 as the ANSI codepage).
param([string]$From = "20260101", [string]$To = "20260816", [switch]$WhatIfOnly)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
$py = Join-Path $repo ".venv64\Scripts\python.exe"
if (-not (Test-Path $py)) { Write-Error "venv64 not found: $py"; exit 1 }

$logDir = Join-Path $repo "data\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$log = Join-Path $logDir "independent_verify_$stamp.log"

$body = @"
`$env:PYTHONIOENCODING = "utf-8"
Add-Content -Path "$log" -Value ("--- independent (all races) start " + (Get-Date -Format HH:mm))
& "$py" -m scripts.verify_roi_independent --from $From --to $To --save *>> "$log"
Add-Content -Path "$log" -Value ("--- independent (require market) start " + (Get-Date -Format HH:mm))
& "$py" -m scripts.verify_roi_independent --from $From --to $To --require-market --save *>> "$log"
Add-Content -Path "$log" -Value ("=== all done " + (Get-Date -Format HH:mm))
"@

$script = Join-Path $env:TEMP "independent_verify_$stamp.ps1"
$body | Out-File -FilePath $script -Encoding utf8

if ($WhatIfOnly) { Get-Content $script; exit 0 }

Start-Process -FilePath "powershell.exe" `
    -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $script `
    -WorkingDirectory $repo -WindowStyle Hidden
Write-Host "launched detached. log: $log"
Write-Host "  window: $From to $To (2 runs, about 2 hours each)"
