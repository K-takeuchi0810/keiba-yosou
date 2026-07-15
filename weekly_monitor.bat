@echo off
cd /d "%~dp0"
REM Weekly monitor: tests, model drift, mining coverage, and fetch gaps.
REM Schedule: every Sunday 10:00 via Windows Task Scheduler.

echo === %date% %time% Weekly Monitor Start ===

REM Keep errorlevel capture outside parenthesized blocks.
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
if %TESTCODE% NEQ 0 echo WARNING: pytest failed (exit %TESTCODE%).

".venv64\Scripts\python.exe" -m scripts.monitor --days 30 --threshold 0.20
set MONCODE=%errorlevel%

".venv64\Scripts\python.exe" -m scripts.fresh_odds_coverage --last 7 --check-gaps
set GAPCODE=%errorlevel%
if %GAPCODE% NEQ 0 echo WARNING: fresh odds fetch gap detected.

REM Exit bits: 1=monitor, 2=pytest, 4=fresh odds gap.
set EXITCODE=0
if %MONCODE% NEQ 0 set /a EXITCODE+=1
if %TESTCODE% NEQ 0 set /a EXITCODE+=2
if %GAPCODE% NEQ 0 set /a EXITCODE+=4
echo === %date% %time% Weekly Monitor End (exit %EXITCODE%) ===

if %MONCODE% NEQ 0 echo WARNING: monitor alert. Check Brier, mining, and horse placeholders.
exit /b %EXITCODE%
