@echo off
REM Fetch fresh odds before each race (runs every 10 minutes via Task Scheduler).
REM JV-Link COM requires 32-bit Python.
REM
REM The log file name is date-stamped on purpose: on 2026-08-16 this script's
REM python process hung and kept the single log file handle open for 6 days, so
REM every later run failed at the redirect ("another process is using the file",
REM exit 1) and fresh odds collection was dead for 6 days (found 2026-08-22).
REM Per-date log files keep a hung process from blocking the next day's runs.
cd /d "%~dp0.."
if not exist data\logs mkdir data\logs
for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set STAMP=%%d
if "%STAMP%"=="" set STAMP=unknown
.venv32\Scripts\python.exe -u -m scripts.fetch_fresh_odds >> data\logs\fetch_fresh_odds_%STAMP%.log 2>&1
