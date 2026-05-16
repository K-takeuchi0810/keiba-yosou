@echo off
chcp 65001 >nul
cd /d "%~dp0"
REM Weekly auto-monitor: detect Brier drift, optionally trigger retrain.
REM Schedule: every Sunday 10:00 via Windows Task Scheduler.
REM Threshold: 30-day rolling Brier > +20%% of baseline -> warning (exit 1).
REM See docs/OPERATION.md for full setup steps.

echo === %date% %time% Weekly Monitor Start ===
".venv64\Scripts\python.exe" -m scripts.monitor --days 30 --threshold 0.20
set EXITCODE=%errorlevel%
echo === %date% %time% Weekly Monitor End (exit %EXITCODE%) ===

if %EXITCODE% NEQ 0 (
    echo WARNING: Brier drift detected. Consider:
    echo   1. `scripts.filter_sweep --recent-3fold` to re-select robust filter
    echo   2. Update DATA_PERIODS, retrain `scripts.train_lgbm`, re-verify
    echo   3. Set BUY_FILTER_DEFAULT to retreat state (whitelist_tracks=[])
)

exit /b %EXITCODE%
