@echo off
chcp 65001 >nul
cd /d "%~dp0"
REM Weekly auto-monitor: detect Brier drift, optionally trigger retrain.
REM Schedule: every Sunday 10:00 via Windows Task Scheduler.
REM Threshold: 30-day rolling Brier > +20%% of baseline -> warning (exit 1).
REM See docs/OPERATION.md for full setup steps.

echo === %date% %time% Weekly Monitor Start ===

REM Regression tests: detect contract breaks in shared helpers
REM (predictor/portfolio.py etc). Skip silently if pytest is not installed
REM so unconfigured envs do not emit a false weekly failure
REM (see requirements-dev.txt). NOTE: capture %errorlevel% on a plain line,
REM not inside a () block (parse-time expansion would grab a stale value).
set TESTCODE=0
".venv64\Scripts\python.exe" -c "import pytest" 2>nul
if errorlevel 1 goto :pytest_skip
echo --- pytest tests/ ---
".venv64\Scripts\python.exe" -m pytest tests/ -q
set TESTCODE=%errorlevel%
goto :pytest_done
:pytest_skip
echo --- pytest skip (not installed: pip install -r requirements-dev.txt) ---
:pytest_done
if %TESTCODE% NEQ 0 (
    echo WARNING: pytest failed ^(exit %TESTCODE%^). Possible shared-helper regression.
)

".venv64\Scripts\python.exe" -m scripts.monitor --days 30 --threshold 0.20
set MONCODE=%errorlevel%

REM Distinct exit codes so Task Scheduler can triage without reading the log:
REM   bit0 (=1) = Brier drift, bit1 (=2) = pytest regression, both = 3.
set EXITCODE=0
if %MONCODE% NEQ 0 set /a EXITCODE+=1
if %TESTCODE% NEQ 0 set /a EXITCODE+=2
echo === %date% %time% Weekly Monitor End (exit %EXITCODE%) ===

if %MONCODE% NEQ 0 (
    echo WARNING: Brier drift detected. Consider:
    echo   1. `scripts.filter_sweep --recent-3fold` to re-select robust filter
    echo   2. Update DATA_PERIODS, retrain `scripts.train_lgbm`, re-verify
    echo   3. Set BUY_FILTER_DEFAULT to retreat state ^(whitelist_tracks=[]^)
)

exit /b %EXITCODE%
