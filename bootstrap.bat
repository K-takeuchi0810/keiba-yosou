@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM ===== Edit FROMTIME below to change fetch period =====
REM   20160101000000 = past 10 years
REM   20200101000000 = past 5 years (recommended)
REM   20210101000000 = past 4 years
set FROMTIME=20200101000000
REM ======================================================

echo ============================================================
echo  Bootstrap: past JV-Data setup-fetch
echo  fromtime = %FROMTIME%
echo  Will run for several hours.
echo ============================================================
echo.
echo Press Ctrl+C now to abort, or Enter to start.
pause
echo.
echo === Start: %date% %time% ===
".venv32\Scripts\python.exe" scripts\bootstrap.py --fromtime %FROMTIME%
echo.
echo === End: %date% %time% / exit code: %errorlevel% ===
pause >nul
