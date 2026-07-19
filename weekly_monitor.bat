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

.venv64\Scripts\python.exe -m scripts.monitor --days 30 --threshold 0.20
set MONCODE=%errorlevel%
.venv64\Scripts\python.exe -m scripts.fresh_odds_coverage --last 7 --check-gaps
set GAPCODE=%errorlevel%

set TESTCODE=0
.venv64\Scripts\python.exe -c "import pytest" 2>nul
if errorlevel 1 goto :pytest_skip
echo --- pytest tests/ ---
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$p=Start-Process -FilePath '.venv64\Scripts\python.exe' -ArgumentList '-m','pytest','tests/','-q' -NoNewWindow -PassThru; if(-not $p.WaitForExit(600*1000)){taskkill.exe /PID $p.Id /T /F | Out-Null; exit 124}; exit $p.ExitCode"
set TESTCODE=%errorlevel%
goto :pytest_done
:pytest_skip
echo --- pytest skip (not installed: pip install -r requirements-dev.txt) ---
:pytest_done
if %TESTCODE% NEQ 0 echo WARNING: pytest failed (exit %TESTCODE%).

REM Exit bits: 1=monitor, 2=pytest, 4=fresh odds gap.
set EXITCODE=0
if %MONCODE% NEQ 0 set /a EXITCODE+=1
if %TESTCODE% NEQ 0 set /a EXITCODE+=2
if %GAPCODE% NEQ 0 set /a EXITCODE+=4
echo === %date% %time% Weekly Monitor End (exit %EXITCODE%) ===

if %MONCODE% NEQ 0 echo ACTION 1: suspend buying by setting whitelist_tracks=[]
if %MONCODE% NEQ 0 echo ACTION 2: run scripts.filter_sweep --recent-3fold
if %MONCODE% NEQ 0 echo ACTION 3: if needed, retrain with scripts.train_lgbm
if %EXITCODE% NEQ 0 .venv64\Scripts\python.exe -m scripts.notify_discord --message "WARN: weekly monitor alert (monitor=%MONCODE% pytest=%TESTCODE% gap=%GAPCODE%; see %LOGFILE%)"
exit /b %EXITCODE%
