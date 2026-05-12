@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Start: %date% %time% ===
echo cwd: %cd%
echo.
REM GUI は 32-bit に残す (pywebview の pythonnet が Python 3.14 用 wheel 未提供)。
REM JV-Link COM ingest も 32-bit が必須なので統合都合も良い。
REM ML 推論を呼ぶ箇所は GUI 内で subprocess "%~dp0.venv64\Scripts\python.exe" 起動する。
".venv32\Scripts\python.exe" -m gui.app
echo.
echo === Exit code: %errorlevel% ===
echo Press Enter to close.
pause >nul
