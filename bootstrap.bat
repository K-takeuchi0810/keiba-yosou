@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM ===== fromtime ここを編集すれば期間が変わります =====
REM   20160101000000 = 過去 10 年
REM   20200101000000 = 過去 5 年（推奨）
REM   20210101000000 = 過去 4 年
set FROMTIME=20200101000000
REM ====================================================

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
