@echo off
REM Daily pipeline with persistent logs and best-effort Discord gap alerts.
cd /d C:\Users\kizun\dev\keiba-yosou
if not exist data\logs mkdir data\logs
for /f %%D in ('.venv64\Scripts\python.exe -c "from datetime import date; d=date.today().isoformat(); print(d[0:4]+d[5:7]+d[8:10])"') do set RUNDATE=%%D
set LOGFILE=data\logs\auto_predict_daily_%RUNDATE%.log
call :run >> "%LOGFILE%" 2>&1
set FINALCODE=%errorlevel%
exit /b %FINALCODE%

:run
echo [%date% %time%] fetch_full (32-bit) start
.venv32\Scripts\python.exe -m scripts.fetch_full --since-last
if errorlevel 1 echo [WARN] fetch_full failed, continue with existing DB

echo [%date% %time%] fetch_mining (32-bit) start
.venv32\Scripts\python.exe -m scripts.fetch_mining --date today
if errorlevel 1 echo [WARN] fetch_mining failed, continue

echo [%date% %time%] fresh_odds_coverage start
.venv64\Scripts\python.exe -m scripts.fresh_odds_coverage --last 1 --check-gaps
set GAPCODE=%errorlevel%
if %GAPCODE% NEQ 0 echo [WARN] fresh odds fetch gap detected, continue
if %GAPCODE% NEQ 0 .venv64\Scripts\python.exe -m scripts.notify_discord --message "WARN: previous-day odds fetch gap detected (see %LOGFILE%)"

echo [%date% %time%] auto_predict (64-bit) start
.venv64\Scripts\python.exe -m scripts.auto_predict
set PREDICTCODE=%errorlevel%

REM Exit bits: 1=fresh odds gap, 2=prediction failure.
set EXITCODE=0
if %GAPCODE% NEQ 0 set /a EXITCODE+=1
if %PREDICTCODE% NEQ 0 set /a EXITCODE+=2
echo [%date% %time%] done exit=%EXITCODE%
exit /b %EXITCODE%
