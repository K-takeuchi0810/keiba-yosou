# 予想ロジック分析官 採点

## 判定: PASS

**改修タイプ**: type-C（データ取得・日次実行経路）。対象は日次パイプラインの watchdog、タスク時刻、標準出力 buffering と回帰テストであり、`predictor/`、重み、calibrator、確率変換、買い判定は変更していない。したがって type-A の P25 固有ゲート（C1/C2/C3/C5、market snapshot、bonus subset、calibrator refit）は **N/A（対象外）**。

**採点対象**: commit `cb970a0`、追補 commit `903b74b`、第二追補 commit `a3b13a4`。予測シグナル・収益性の採用判断はスコープ外。

**理由**: 1200秒の上限で固着した日次処理を終了し、08:00失敗後も09:00に再試行できる構成は、本日のレースデータ欠落を長時間固定する train-serve skew を縮小する。`taskkill` の終了コードと親プロセスの10秒以内終了を検査し、停止不能を124（正常なtimeout停止）と区別した125で記録する。第二追補では実際に孫プロセスを生成してtimeout後のPID消滅を検証し、124/125通知も30秒で上限化したため、初回レビューの中核指摘は解消した。

**根拠ファイル**: `scripts/run_auto_predict_daily.ps1:5-8`、`scripts/run_auto_predict_daily.ps1:29-81`、`scripts/register_auto_predict_task.ps1:8-9`、`scripts/register_auto_predict_task.ps1:28-43`、`scripts/auto_predict_daily.bat:12-16`、`tests/test_auto_predict_task_runner.py:14-140`

**次アクション**: 2026-08-09の自然スケジュール実行後に、08:00/09:00のTask Scheduler結果、watchdogログ、当日成果物の更新を突合する。コード上の中核欠陥ではなく実運用の最終観測である。

## 総合: 4.8 / 5（参考スコア）

## 項目別

- **シグナル網羅性と市場残差性: 5/5** — 予測シグナルの追加・削除はない。`git show cb970a0 --stat` で変更は `scripts/` 3件と runner テスト1件のみで、`predictor/` は対象外。
- **重み妥当性 / 過適合リスク: 5/5** — 重み、特徴量、filter、backtest の変更と確率品質改善の主張はない。P25 paired ablation は N/A。
- **信頼度判定 / 確率推定の構造: 5/5** — calibrator、raw→blend→calibrate→normalize、race内正規化に差分はなく、予測値の意味は不変。
- **デッドコード / 設計の整合性: 4.5/5** — watchdog は存在確認、固定上限、正常終了コード伝播、timeout=124、停止不能=125を一経路にまとめた（`scripts/run_auto_predict_daily.ps1:16-19,50-81`）。`taskkill` 非ゼロかつ親が生存する場合と、10秒後も親が生存する場合を明示ログ付きで失敗させる（同:58-74）。動的テストでは孫PowerShellのPIDを採取し、timeout後に `Get-Process` 不在を確認する（`tests/test_auto_predict_task_runner.py:68-114`）。125分岐と通知timeout分岐の動的テストがない点だけを留保する。
- **本番運用との乖離リスク（train-serve skew）: 4.5/5** — 08:00/09:00の二段実行（`scripts/register_auto_predict_task.ps1:8-9,31-39`）、fetch_full の unbuffered 出力（`scripts/auto_predict_daily.bat:12-16`）により、朝データ欠落の検知・再試行性は改善する。124/125はDiscordへ通知し、通知自体も30秒で打ち切るため監視経路が本処理を再固着させない（`scripts/run_auto_predict_daily.ps1:29-48,61-74`）。2026-08-08の実機確認では登録タスクは `Ready`、次回 2026-08-09 08:00、`MultipleInstances=IgnoreNew`、Action は hidden runner→watchdog だった。自然スケジュールでの完走のみ未観測。

## 停止条件チェック

- [x] 改修タイプを type-C と分類し、予測ロジック不変を差分で確認
- [x] 正常終了コード伝播を実測（fixture exit 7 → runner exit 7）
- [x] timeoutを実測（1秒上限 → runner exit 124、10秒未満）
- [x] 第二追補後も対象回帰テスト6件成功（`.venv64/Scripts/python.exe -m pytest tests/test_auto_predict_task_runner.py -q`、2026-08-08、6 passed in 4.74s）
- [x] 登録済みタスクの Action、2 trigger、多重起動設定、次回時刻を read-only 確認
- [x] `taskkill` 非ゼロと親プロセスの停止不能を125で fail-closed に記録（`scripts/run_auto_predict_daily.ps1:58-74`）
- [x] 孫プロセス消滅を動的検証（`tests/test_auto_predict_task_runner.py:68-114`）
- [x] 124/125通知を30秒で上限化（`scripts/run_auto_predict_daily.ps1:29-48,61-74`）
- P25 再現性メタ / paired baseline / market snapshot / payout欠損 / 専門領域別P25停止条件: **N/A（type-Aではない）**

## 反証の試み

- 改修の主張「timeout時に complete child process tree を停止する」に対し、「親だけ終了し JV-Link 相当の孫が残る」シナリオを確認した。テストfixtureは `cmd → PowerShell孫` を生成し、timeout=2秒後にrunner=124、PIDファイル作成済み、同PIDの `Get-Process` 不在を実測したため反証は不成立（`tests/test_auto_predict_task_runner.py:68-114`、本セッションで6 tests passed）。
- 改修の主張「1200秒で正常処理を誤停止しない」に対し、既存ログを再確認した。成功開催日の実測は 2026-08-02 09:30:02→09:31:38（約97秒）、11:30:02→11:31:39（約97秒）で1200秒未満だった。一方、2026-08-04〜07は `fetch_full start` だけで停止しており、無制限待機の実害と watchdog の必要性を確認した。過去成功例だけで将来すべての正常runが1200秒未満とは断定しない。

## 主な改善提案

1. **自然スケジュールを1回観測する** — 2026-08-09 09:00後にTask Schedulerの結果、`data/logs/auto_predict_watchdog.log`、当日HTML/通知更新を突合し、fixtureではなく実JV-Link経路を閉じる。
2. **125・通知timeout分岐を実行テストする** — `taskkill` と通知コマンドを注入可能にし、停止失敗時の125、通知30秒超過時のcleanupとログを確認する（`scripts/run_auto_predict_daily.ps1:29-48,58-74`）。
3. **テストログと運用ログを分離する** — runnerテストは `scripts/run_auto_predict_daily.ps1:21-26` の固定運用ログへ start/timeout を書き込む。テスト用ログディレクトリを注入可能にし、実運用監査ログへの混入を防ぐ。

## 前回からの差分

- 前回（`20260802_2155_hidden_scheduled_tasks__prediction-logic-analyst.md`）: PASS、4.8/5。今回も type-C で予測ロジック不変。
- デッドコード / 設計整合性: 初回 4.0 → 第一追補 4.5 → 第二追補 4.5。孫消滅は実証済み。125/通知異常分岐のテスト不足のみ継続。
- train-serve skew: 初回 4.0 → 第二追補 4.5（+0.5）。timeout通知を有界化し、無人運用での検知経路を追加。自然実行未観測のみ継続。
- 総合: 前回別改修 4.8 → 初回レビュー 4.6 → 第一追補 4.7 → 第二追補 4.8。1点を超える変動はない。
