@echo off
REM Daily pipeline with persistent logs and best-effort Discord gap alerts.
REM Usage: auto_predict_daily.bat [--dry-run]
REM   --dry-run skips JV-Link ingest (DB writes), Discord and the Pages push,
REM   and writes to a separate *_dryrun.log. Everything else is the same path.
REM Work in the repo that contains this script. The scheduler runs the main
REM checkout's copy, so this is the same directory as before; a worktree's
REM copy stays inside the worktree.
cd /d "%~dp0.."
if not exist data\logs mkdir data\logs
set "DRYRUN="
if /i "%~1"=="--dry-run" set "DRYRUN=1"
REM Log file date must match the prediction target date, so ask the same
REM single source the Python side uses (jst.current_jst_daystamp).
REM Keep stderr: if this fails there is no dated log to write it to.
set "RUNDATE="
set "DATEERR=data\logs\auto_predict_daily_rundate_stderr.txt"
for /f %%D in ('.venv64\Scripts\python.exe -c "from jst import current_jst_daystamp; print(current_jst_daystamp())" 2^>"%DATEERR%"') do set "RUNDATE=%%D"
REM Never fall back to an empty or malformed date (auto_predict_daily_.log).
echo(%RUNDATE%| findstr /r /x "20[0-9][0-9][01][0-9][0-3][0-9]" >nul
if errorlevel 1 goto :date_failure
set "LOGFILE=data\logs\auto_predict_daily_%RUNDATE%.log"
if defined DRYRUN set "LOGFILE=data\logs\auto_predict_daily_%RUNDATE%_dryrun.log"
call :run >> "%LOGFILE%" 2>&1
set FINALCODE=%errorlevel%
exit /b %FINALCODE%

:date_failure
REM Exit 8 = could not determine the run date. Nothing else ran.
>> "data\logs\auto_predict_daily_DATE_FAILURE.log" (
  echo [%date% %time%] could not determine the JST run date: RUNDATE=[%RUNDATE%] dryrun=[%DRYRUN%]
  if exist "%DATEERR%" type "%DATEERR%"
  echo [%date% %time%] abort exit=8
)
if not defined DRYRUN .venv64\Scripts\python.exe -m scripts.notify_discord --message "ERROR: auto_predict_daily could not determine the run date; nothing ran (see data/logs/auto_predict_daily_DATE_FAILURE.log)" >nul 2>&1
exit /b 8

:run
echo [%date% %time%] run date %RUNDATE% (JST) dryrun=[%DRYRUN%] cwd=%CD%
set FETCHCODE=0
if defined DRYRUN goto :skip_fetch
echo [%date% %time%] fetch_full (32-bit) start
.venv32\Scripts\python.exe -u -m scripts.fetch_full --ingest
set FETCHCODE=%errorlevel%
if %FETCHCODE% NEQ 0 echo [WARN] fetch_full failed (exit %FETCHCODE%), continue with existing DB
if %FETCHCODE% NEQ 0 .venv64\Scripts\python.exe -m scripts.notify_discord --message "WARN: fetch_full failed (exit %FETCHCODE%); predictions used existing DB (see %LOGFILE%)"

echo [%date% %time%] fetch_mining (32-bit) start
.venv32\Scripts\python.exe -m scripts.fetch_mining --date today
if errorlevel 1 echo [WARN] fetch_mining failed, continue
goto :after_fetch
:skip_fetch
echo [DRY-RUN] skip fetch_full / fetch_mining (no DB writes)
:after_fetch

echo [%date% %time%] fresh_odds_coverage start
if defined DRYRUN (
  .venv64\Scripts\python.exe -m scripts.fresh_odds_coverage --last 1 --check-gaps
) else (
  .venv64\Scripts\python.exe -m scripts.fresh_odds_coverage --last 1 --check-gaps --notify
)
set GAPCODE=%errorlevel%
if %GAPCODE% NEQ 0 echo [WARN] fresh odds fetch gap detected, continue

echo [%date% %time%] auto_predict (64-bit) start
if defined DRYRUN (
  .venv64\Scripts\python.exe -m scripts.auto_predict --dry-run
) else (
  .venv64\Scripts\python.exe -m scripts.auto_predict
)
set PREDICTCODE=%errorlevel%

REM Exit bits: 1=fresh odds gap, 2=prediction failure, 4=fetch_full failure.
REM 8 = run date could not be determined (see :date_failure).
set EXITCODE=0
if %GAPCODE% NEQ 0 set /a EXITCODE+=1
if %PREDICTCODE% NEQ 0 set /a EXITCODE+=2
if %FETCHCODE% NEQ 0 set /a EXITCODE+=4
echo [%date% %time%] done exit=%EXITCODE%
exit /b %EXITCODE%
