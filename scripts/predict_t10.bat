@echo off
REM T-10 prediction runner (reform R1-1). Runs every 5 minutes on race days.
REM 64-bit Python: reads odds_snapshots only, no JV-Link COM involved.
REM
REM The per-date log name follows the fetch_fresh_odds convention: on 2026-08-16 a
REM hung process kept a single log handle for 6 days and killed every later run at
REM the redirect. Per-date files keep one bad run from blocking the next day.
cd /d "%~dp0.."
if not exist data\logs mkdir data\logs
for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set STAMP=%%d
if "%STAMP%"=="" set STAMP=unknown
.venv64\Scripts\python.exe -u -m scripts.predict_t10 >> data\logs\predict_t10_%STAMP%.log 2>&1
