# GUI / UX 監査人 採点

## 判定: HOLD

**理由**: 今回は GUI/HTML を変更しない type-C の取得・定期実行改修で、GUI 回帰はない。一方、修正後タスクは本日分をまだ一度も実行しておらず、タイムアウトもローカルログにしか現れないため、利用者が「本日の予想が無い」状態から自力で復旧できるところまでは閉じていない。
**根拠ファイル**: `scripts/run_auto_predict_daily.ps1:20-45`、`scripts/register_auto_predict_task.ps1:28-46`、`tests/test_auto_predict_task_runner.py:14-84`
**次アクション**: 登録直後に当日分を一度手動実行して正常完了を確認し、タイムアウト時は Discord に「対象・経過時間・終了コード124・ログ場所・再実行方法」を通知する。

**改修タイプ**: type-C（JV-Link 取得を含む日次データパイプラインの運用・復旧改修。watchdog の診断は type-B 的だが、type-D の GUI/HTML 差分はない）
**採点対象**: 08:00/09:00 の定期実行、1200秒 watchdog、プロセスツリー終了、ログ即時出力が無人運用の発見性・回復性へ与える影響。
**スコープ外**: 予測精度、収益性、P25 採用判断、MAIBuilder 側の画面表示。
**GUI 非影響確認**: `git show cb970a0 --stat` は batch/PowerShell/test の4ファイルだけで、`gui/app.py`、`web/templates/`、`web/generator.py` に変更なし。したがって GUI 本体は直近監査値を維持し、CONTROL_HTML の JS/P25表示ゲートは N/A。

## 総合: 3.6 / 5（参考スコア、GUI本体は前回維持）

今回の運用UX単体は **3/5**。無限待ちを有限化しログを残す改善は確認できたが、修正当日の自動回復と異常の能動通知が未完了である。GUI本体は直近監査 `data/scorecards/20260802_2155_hidden_scheduled_tasks__gui-ux-auditor.md` の 3.6 / HOLD を維持する。

## 項目別

- **タスクフロー / 発見性: 4/5** — 起動時刻を 09:30/11:30 から 08:00/09:00 へ前倒しし、同じ watchdog 経路へ統一した（`scripts/register_auto_predict_task.ps1:7-9,28-44`）。ただし登録時点で当日の両時刻を過ぎている場合は自動実行せず、操作案内は `Start-ScheduledTask` の1行だけである（同`:46`）。監査時の実測では登録タスクの次回実行は `2026-08-09 08:00`、最終実行は未実行相当だった。
- **エラーの人間化 / 回復支援: 4/5** — 通常の `fetch_full` 非ゼロ終了は Discord に原因・終了コード・ログ場所を通知する（`scripts/auto_predict_daily.bat:14-16`）。一方、watchdog のタイムアウトは `timeout pid=...` をファイルへ書いて終了コード124を返すだけで（`scripts/run_auto_predict_daily.ps1:34-38`）、Discord通知と再実行案内がない。Nielsen 9 の「認識・診断・回復支援」はバックグラウンド異常経路で不足する。
- **システム状態の可視性: 3/5** — watchdog は start/timeout/finish、PID、制限秒、終了コードを永続ログへ残し（`scripts/run_auto_predict_daily.ps1:20-25,32-45`）、`fetch_full` は `-u` により長時間処理中のログを即時化した（`scripts/auto_predict_daily.bat:12-13`）。ただし hidden runner からの実行では進捗・タイムアウトが利用者へ能動表示されず、監査時点で `data/logs/auto_predict_watchdog.log` も未生成だった。
- **状態整合性 / 誤読防止: 4/5** — タイムアウトは親だけでなく `/T /F` で子プロセスツリーを終了し、124で失敗を伝播する（`scripts/run_auto_predict_daily.ps1:34-38`）。自分で対象テストを再実行し、終了コード保持、1秒タイムアウト、登録スクリプト、非バッファログを含む **5件が1.93秒で全件成功**した（`tests/test_auto_predict_task_runner.py:14-84`）。実タスクも 08:00/09:00・watchdog Action で登録済みと実測したが、定刻実走は未確認。
- **レイアウト / 入力効率 / アクセシビリティ: 3/5** — GUI/HTMLに差分はなく前回値を維持する。定期処理を hidden 実行することでフォーカス奪取は防げるが、異常まで不可視にするため、Discord等の非侵襲通知が必要である。

## 停止条件チェック

- [x] GUI / HTML 差分なし（前回スコア維持）
- [x] watchdog の有限待ち、終了コード保持、プロセスツリー終了命令あり
- [x] 対象テスト 5/5 成功（本セッション実測）
- [x] 実タスクの Action と 08:00/09:00 トリガー登録を read-only 確認
- [ ] 修正後経路の実タスク正常完了と watchdog ログ生成は未確認
- [x] 今回差分に適用される専門領域の Hard Fail なし
- P25 固有の paired baseline / market_snapshot / payout / CONTROL_HTML 表示ゲート: N/A（予測採用・GUI表示を変更しない type-C 改修）

## 反証の試み

- **仮説**: 1200秒制限は正常な日次処理まで途中終了させ、「本日の予想なし」を再発させる可能性がある。
- **確認**: 直近の完走例は `data/logs/auto_predict_daily_20260802.log:1-34` が約97秒、同`:35-68` が約97秒、`data/logs/auto_predict_daily_20260803.log:1-30` が約4秒で、1200秒は実測完走時間の12倍以上。一方、同ログ`:31` は `fetch_full start` のまま完了行がなく、watchdog が狙う停止症状を再確認した。
- **結論**: 直近正常 run を誤停止する仮説は現データでは不成立。ただし開催日・回線障害時の最長正常時間分布は未計測であり、1200秒の妥当性は運用ログを蓄積して再評価する必要がある。

## 主な改善提案

1. **修正当日の即時回復を登録フローに含める** — 当日の両トリガー通過後に登録した場合、確認付きで `Start-ScheduledTask -TaskName $TaskName` を実行するか、少なくとも「本日分は未実行」と明示する。`scripts/register_auto_predict_task.ps1:39-46`。
2. **timeout を Discord へ能動通知する** — `scripts/run_auto_predict_daily.ps1:34-38` で tree kill 後に、PID・1200秒・exit 124・watchdog/dailyログ場所・手動再実行コマンドを送る。ローカルログだけではスマホ利用者が異常を発見できない。
3. **定刻実走を監視する** — 完了ログが予定時刻から一定時間内に無い場合を週次ではなく当日監視し、08:00失敗後に09:00で復旧したかを1メッセージへ集約する。

## 前回からの差分

- タスクフロー / 発見性: 4 → 4（時刻前倒しと共通watchdog経路を追加。本日分の即時実行は手動）
- エラー人間化 / 復旧支援: 4 → 4（GUI本体は不変。運用経路単体では timeout 通知不足）
- 進捗表示 / ETA / キャンセル: 3 → 3（無限待ちは有限化したが、スマホへの状態通知なし）
- 状態整合性 / 誤読防止: 4 → 4（tree kill・exit 124・テストを確認。実タスク定刻 run は未確認）
- レイアウト / アクセシビリティ: 3 → 3（GUI差分なし）
- 前回判定: HOLD、今回も HOLD。総合 3.6 → 3.6（差分0.0）。今回改修に GUI 回帰はないが、修正当日の復旧と異常通知が継続課題。
