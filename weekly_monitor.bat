@echo off
REM Weekly monitor with persistent logs and best-effort Discord alerts.
cd /d "%~dp0"
if not exist data\logs mkdir data\logs
for /f %%D in ('.venv64\Scripts\python.exe -c "from datetime import date; d=date.today().isoformat(); print(d[0:4]+d[5:7]+d[8:10])"') do set RUNDATE=%%D
set LOGFILE=data\logs\weekly_monitor_%RUNDATE%.log
call :run >> "%LOGFILE%" 2>&1
set FINALCODE=%errorlevel%
exit /b %FINALCODE%

:run
echo === %date% %time% Weekly Monitor Start ===
set TESTCODE=0
.venv64\Scripts\python.exe -c "import pytest" 2>nul
if errorlevel 1 goto :pytest_skip
echo --- pytest tests/ ---
.venv64\Scripts\python.exe -m pytest tests/ -q
set TESTCODE=%errorlevel%
goto :pytest_done
:pytest_skip
echo --- pytest skip (not installed: pip install -r requirements-dev.txt) ---
:pytest_done
if %TESTCODE% NEQ 0 echo WARNING: pytest failed (exit %TESTCODE%).

.venv64\Scripts\python.exe -m scripts.monitor --days 30 --threshold 0.20
set MONCODE=%errorlevel%
.venv64\Scripts\python.exe -m scripts.fresh_odds_coverage --last 7 --check-gaps
set GAPCODE=%errorlevel%

REM Exit bits: 1=monitor, 2=pytest, 4=fresh odds gap.
set EXITCODE=0
if %MONCODE% NEQ 0 set /a EXITCODE+=1
if %TESTCODE% NEQ 0 set /a EXITCODE+=2
if %GAPCODE% NEQ 0 set /a EXITCODE+=4
echo === %date% %time% Weekly Monitor End (exit %EXITCODE%) ===

if %MONCODE% NEQ 0 echo ACTION 1: suspend buying by setting whitelist_tracks=[]
if %MONCODE% NEQ 0 echo ACTION 2: run scripts.filter_sweep --recent-3fold
if %MONCODE% NEQ 0 echo ACTION 3: if needed, retrain with scripts.train_lgbm
if %EXITCODE% NEQ 0 .venv64\Scripts\python.exe -m scripts.notify_discord --message "WARN: weekly monitor alert (exit %EXITCODE%; see %LOGFILE%)"
exit /b %EXITCODE%
