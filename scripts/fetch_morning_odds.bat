@echo off
setlocal
cd /d "%~dp0.."

if not exist data\logs mkdir data\logs
set "LOG_PATH=data\logs\fetch_morning_odds.log"
set "RUN_OUTPUT=%TEMP%\fetch_morning_odds_%RANDOM%_%RANDOM%.tmp"
set "EXIT_CODE=0"

echo [%DATE% %TIME%] morning odds start window=600 min_lead=0>> "%LOG_PATH%"

if not exist .venv32\Scripts\python.exe (
    echo ERROR: .venv32\Scripts\python.exe not found>> "%LOG_PATH%"
    exit /b 3
)

.venv32\Scripts\python.exe -u -m scripts.fetch_fresh_odds --window 600 --min-lead 0 > "%RUN_OUTPUT%" 2>&1
set "PYTHON_RC=%ERRORLEVEL%"
type "%RUN_OUTPUT%" >> "%LOG_PATH%"

if not "%PYTHON_RC%"=="0" set "EXIT_CODE=%PYTHON_RC%"
findstr /C:"window=0-600min" "%RUN_OUTPUT%" >nul
if errorlevel 1 (
    echo ERROR: effective window marker window=0-600min not found>> "%LOG_PATH%"
    if "%EXIT_CODE%"=="0" set "EXIT_CODE=2"
) else (
    echo CHECK: effective window=600 confirmed>> "%LOG_PATH%"
)

del /q "%RUN_OUTPUT%" >nul 2>&1
echo [%DATE% %TIME%] morning odds end rc=%EXIT_CODE%>> "%LOG_PATH%"
exit /b %EXIT_CODE%
