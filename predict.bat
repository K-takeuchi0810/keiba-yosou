@echo off
chcp 65001 >nul
cd /d "%~dp0"
REM Prediction runs on 64-bit (LightGBM ensemble + ML inference).
".venv64\Scripts\python.exe" -m scripts.predict %*
