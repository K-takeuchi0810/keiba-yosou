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
REM pytest runs in the production checkout while other scheduled tasks (fresh
REM odds every 10 min, healthcheck every 15 min) write data\logs. A before/after
REM snapshot cannot tell who wrote, so tests\conftest.py's runtime-log guard is
REM switched off for this run only (KEIBA_RUNTIME_GUARD=off; any other value
REM than strict/off aborts pytest). Only this outer pytest is off: tests that
REM start pytest themselves build the child env with runtime_guard.py, which
REM always sets strict. pytest's own output goes outside data\logs, stdout and
REM stderr in one file.
if not exist data\monitor_runs mkdir data\monitor_runs
set "PYTESTLOG=data\monitor_runs\weekly_pytest_%RUNDATE%.log"
echo --- pytest tests/ runtime_guard=off (output: %PYTESTLOG%) ---
set "KEIBA_RUNTIME_GUARD=off"
REM $null=$p.Handle is REQUIRED: PowerShell 5.1 leaves $p.ExitCode null after
REM WaitForExit(ms) unless the process Handle was touched before it exits, which
REM would silently turn a red pytest into exit 0 (verified 2026-07-19).
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$p=Start-Process -FilePath '.venv64\Scripts\python.exe' -ArgumentList '-m','pytest','tests/','-q' -NoNewWindow -PassThru -RedirectStandardOutput '%PYTESTLOG%' -RedirectStandardError '%PYTESTLOG%.stderr'; $null=$p.Handle; if(-not $p.WaitForExit(600*1000)){taskkill.exe /PID $p.Id /T /F | Out-Null; exit 124}; exit $p.ExitCode"
set TESTCODE=%errorlevel%
set "KEIBA_RUNTIME_GUARD="
REM Keep stdout and stderr in one file (a usage error such as an unknown guard
REM value is printed on stderr only). Do not leave an empty .stderr behind.
if exist "%PYTESTLOG%.stderr" call :merge_stderr
echo runtime_guard=off pytest_exit=%TESTCODE% full_output=%PYTESTLOG%
goto :pytest_done
:merge_stderr
for %%F in ("%PYTESTLOG%.stderr") do if %%~zF GTR 0 (
  >> "%PYTESTLOG%" echo --- stderr ---
  type "%PYTESTLOG%.stderr" >> "%PYTESTLOG%"
)
del "%PYTESTLOG%.stderr"
exit /b 0
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
