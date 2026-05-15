@echo off
chcp 65001 >nul
cd /d "%~dp0"
REM 週次自動監視: 戦略の Brier ドリフトを検知し、必要なら再訓練 trigger。
REM
REM 推奨運用 (Windows Task Scheduler 登録):
REM   - 実行頻度: 毎週日曜 10:00
REM   - 条件: 1 週間内で 30 日 rolling Brier が baseline 比 >+20%% で警告
REM   - exit code 1 = 警告発火、0 = OK
REM
REM 月次 rolling 再訓練 (Brier drift 発火時の自動対応):
REM   既存の `scripts.monitor --auto-retrain` フラグで .venv64 が起動して LGBM
REM   再訓練が走る。ただし TRAIN 期間は config.DATA_PERIODS["train"] を更新
REM   しない限り 2021-2023 固定。rolling forward が必要なら別途 config 編集。
REM
REM 採用戦略の賞味期限管理:
REM   採用日から 3 ヶ月経過したら、必ず `scripts.filter_sweep --recent-3fold`
REM   を実行して再選定すべき (P12 反省: 通年 sweep だけでは不十分)。

echo === %date% %time% Weekly Monitor Start ===
".venv64\Scripts\python.exe" -m scripts.monitor --days 30 --threshold 0.20
set EXITCODE=%errorlevel%
echo === %date% %time% Weekly Monitor End (exit %EXITCODE%) ===

if %EXITCODE% NEQ 0 (
    echo WARNING: Brier drift detected. Consider:
    echo   1. `scripts.filter_sweep --recent-3fold` to re-select robust filter
    echo   2. Update DATA_PERIODS, retrain `scripts.train_lgbm`, re-verify
    echo   3. Set BUY_FILTER_DEFAULT to retreat state (whitelist_tracks=[])
)

exit /b %EXITCODE%
