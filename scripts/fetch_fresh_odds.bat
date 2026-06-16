@echo off
REM 発走直前の fresh odds 取得 (Task Scheduler から 10 分おきに実行)
REM 32bit Python 必須 (JV-Link COM)
cd /d "%~dp0.."
if not exist data\logs mkdir data\logs
.venv32\Scripts\python.exe -u -m scripts.fetch_fresh_odds >> data\logs\fetch_fresh_odds.log 2>&1
