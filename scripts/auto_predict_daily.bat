@echo off
REM F4 日次予想パイプライン (Task Scheduler から呼ぶ)。
REM 1) 32-bit JV-Link で当日/翌日の出馬表+オッズを DB へ (fetch_full --since-last)
REM 2) 64-bit で予想生成 → docs/index.html を main へ push (Pages 自動デプロイ) → Discord 通知
REM 出馬表が無い日 (非開催) は auto_predict が静かに skip する。
cd /d C:\Users\kizun\dev\keiba-yosou

echo [%date% %time%] fetch_full (32-bit) start
.venv32\Scripts\python.exe -m scripts.fetch_full --since-last
if errorlevel 1 echo [WARN] fetch_full failed, continue with existing DB

echo [%date% %time%] auto_predict (64-bit) start
.venv64\Scripts\python.exe -m scripts.auto_predict
echo [%date% %time%] done exit=%errorlevel%
