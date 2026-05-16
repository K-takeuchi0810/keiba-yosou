@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Start: %date% %time% ===
echo cwd: %cd%
echo.
REM GUI runs on 32-bit (.venv32) because pywebview/pythonnet has no wheel
REM for Python 3.14 64-bit yet. JV-Link COM also needs 32-bit, so this is
REM consistent. ML inference is invoked via subprocess to .venv64.
".venv32\Scripts\python.exe" -m gui.app
echo.
echo === Exit code: %errorlevel% ===
echo Press Enter to close.
pause >nul
