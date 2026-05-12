@echo off
chcp 65001 >nul
cd /d "%~dp0"
REM 予測は 64-bit (LightGBM ensemble + ML 推論を使う)
".venv64\Scripts\python.exe" -m scripts.predict %*
