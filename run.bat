@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Start: %date% %time% ===
echo cwd: %cd%
echo.
".venv32\Scripts\python.exe" -m gui.app
echo.
echo === Exit code: %errorlevel% ===
echo Press Enter to close.
pause >nul
