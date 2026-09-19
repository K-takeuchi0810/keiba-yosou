# 収益性 / 投資判断専門家 採点 — auto_predict watchdog

## 判定: PASS

**改修タイプ**: type-C（データ取得・日次運用）。対象は commit `cb970a0` の日次JV-Linkパイプライン監視、時刻変更、ログ即時化であり、予測確率、買い目フィルタ、EV、Kelly、calibratorは変更していない。P25固有のROI / CI / paired baseline / market snapshotゲートは **N/A（対象外）**。

**理由**: 停止した `fetch_full` が後続の予想生成を永久に塞ぐ経路を20分で打ち切り、08:00失敗後に09:00の再試行機会を残す。追補 `903b74b` / `a3b13a4` により、kill失敗検知、孫プロセス消滅の動的試験、30秒上限のDiscord通知まで実装された。専用テスト6/6成功をこのセッションで再確認したため、運用改修として採用可能。

**根拠ファイル**: `scripts/run_auto_predict_daily.ps1:4-8,29-81`、`scripts/register_auto_predict_task.ps1:7-9,28-45`、`scripts/auto_predict_daily.bat:12-16,27-36`、`tests/test_auto_predict_task_runner.py:14-140`。

**次アクション**: 次回08:00の本番実走後にTask結果、watchdog `finish`、当日HTML生成の3点を確認する。timeoutが発生した場合は32bit Python / COM子が0件であることとDiscord実着信も確認し、fixture成功を実JV-Link成功と混同しない。

## 総合: 4.2 / 5（参考スコア）

## 採点対象とスコープ外

- **対象**: ハング時の取得・予想機会損失の上限、再試行時刻、終了コード、ログ可観測性、登録済みTaskの実状態。
- **スコープ外**: 回収率の改善、確率校正、買い目採用、資金配分。本差分はこれらを変更せず、収益改善を主張していない（`git show cb970a0 --stat` は scripts 3件と専用test 1件）。
- **追補**: レビュー中にHEADが `903b74b`、`a3b13a4` へ進み、`taskkill`失敗 / 10秒後の残存をexit 125にする検証、孫プロセス除去試験、timeout時Discord通知が追加された（現行 `scripts/run_auto_predict_daily.ps1:29-48,56-74`、`tests/test_auto_predict_task_runner.py:68-126`）。対象commitの方向性を変えず、停止・警告確認を強化する追補として評価へ反映した。

## 項目別

- **回収機会・日次生成継続性: 4/5** — 旧ログは8/1、8/4〜8/7が `fetch_full start` 1行だけで停止しており、停止が後続生成を全損させる実害を再確認した（`data/logs/auto_predict_daily_20260801.log:1`、同`20260804.log:1`〜`20260807.log:1`）。新runnerは全体を1200秒に制限し、プロセス木を終了する（`scripts/run_auto_predict_daily.ps1:50-74`）。
- **EV入力・データ鮮度への影響: 4/5** — 08:00 / 09:00の2回実行へ前倒しされ、正常時は `fetch_full` → mining → gap確認 → predictの順を保持する（`scripts/register_auto_predict_task.ps1:8-9,31-45`、`scripts/auto_predict_daily.bat:12-35`）。`fetch_full`を`-u`にしたため、JV-Linkがどの段階で止まったかをバッファ待ちせず残せる（`scripts/auto_predict_daily.bat:12-16`）。
- **Kelly / 資金管理: 5/5** — 資金配分、賭け金上限、購入処理は差分外。今回の変更による賭け金増加や破産確率上昇の経路はない（commit `cb970a0` の変更対象4ファイル）。
- **買い目フィルタ・公開経路の実用性: 4/5** — watchdogは正常子プロセスの終了コードをそのまま返し（`scripts/run_auto_predict_daily.ps1:52-56`）、fixtureのexit 7を保持することを再実測した（`tests/test_auto_predict_task_runner.py:14-36`）。したがって既存のgap / prediction / fetch失敗bitをTask Schedulerへ伝播できる（`scripts/auto_predict_daily.bat:31-36`）。
- **監視・不確実性開示: 4/5** — timeoutとtree終了は専用logに残り、exit 124/125の各経路からDiscord通知を呼ぶ。通知自体も30秒で打ち切り、通知障害がwatchdogを再び無期限停止させない（`scripts/run_auto_predict_daily.ps1:21-26,29-48,56-74`）。実Discord着信と本番Task実走は未確認のため5点にはしない。

## 実測した運用状態

- 登録済み `keiba-auto-predict` は `wscript.exe` → hidden runner → watchdogを起動し、Triggerは **2026-08-08 08:00 / 09:00**、`MultipleInstances=IgnoreNew`、`ExecutionTimeLimit=PT2H`だった（このセッションの`Get-ScheduledTask` / `Export-ScheduledTask`実測）。
- 確認時点の `LastRunTime=1999-11-30`、`LastTaskResult=267011`、`NextRunTime=2026-08-09 08:00`。登録が本日の両Trigger後だったため、**本改修による8/8の本番取得・予想生成は未実行**。これはコード採用の停止条件ではないが、8/8障害の復旧証拠には数えない。
- `.venv64\Scripts\python.exe -m pytest tests\test_auto_predict_task_runner.py -q` を追補後に再実行し **6 passed in 4.69s**。timeout fixtureはexit 124、正常fixtureはexit 7を返し、動的に起動した孫PowerShellのPID消滅も確認した（`tests/test_auto_predict_task_runner.py:14-114`）。
- 現行watchdog logはtimeout後に `tree terminated` まで記録した（`data/logs/auto_predict_watchdog.log:21-23`）。

## 停止条件チェック

- P25再現性メタ / paired baseline / market_snapshot / payout欠損: **N/A（type-C、収益性・モデル採用主張なし）**。
- [x] 正常終了コードを保持（exit 7を再実測）。
- [x] timeoutを有界化（1秒fixtureが10秒未満、exit 124を再実測）。
- [x] 完全な子プロセス木を `/T /F` で対象化（`scripts/run_auto_predict_daily.ps1:56-74`）。
- [x] kill失敗 / kill後残存を成功扱いしない（追補 `903b74b`、現行同`:60-74`）。
- [x] timeout / kill失敗をDiscord通知し、通知も30秒で有界化（追補 `a3b13a4`、現行 `scripts/run_auto_predict_daily.ps1:29-48,61-74`）。
- [x] 予測・filter・calibrator・資金管理は無変更。
- [x] 専門領域の停止条件に抵触なし。運用段階の昇格や利益エッジを主張していない。

## 反証の試み

- 主張「watchdogが正常終了コードを潰してTaskを成功扱いする」に対し、exit 7のCMDをrunnerへ渡して戻り値7を再実測したため不成立（`tests/test_auto_predict_task_runner.py:14-36`）。
- 主張「timeoutしても孫プロセスが残り、次の09:00実行を阻害する」に対し、動的に孫PowerShellを起動してPIDを書き出し、watchdog終了後にそのPIDが存在しないことを再実測したためfixture範囲では不成立（`tests/test_auto_predict_task_runner.py:68-114`）。実JV-Link COM子の本番timeoutは未検証。
- 主張「時刻変更だけで8/8の欠落が復旧した」に対し、登録済みTaskは一度も実行されず次回8/9 08:00だったため成立しない。8/8復旧は別途手動取得・生成の成功確認が必要。

## 主な改善提案

1. **本番受入を3点で自動判定する** — Task `LastTaskResult`、watchdogの当日`finish`、公開HTMLの当日日付をhealthcheckで同時確認し、どれか欠けたらDiscord警告する。現時点の最大の残課題は登録後の本番Task実走が0件であること。
2. **通知経路を注入可能にして試験する** — `scripts/run_auto_predict_daily.ps1:29-48` にテスト用notifier pathを渡せるようにし、成功・非0終了・30秒timeoutの3経路と元のexit 124/125保持を動的に確認する。現在の専用テストは`-SkipNotification`を使う（`tests/test_auto_predict_task_runner.py:31,58,93`）。
3. **実COM木のkill証跡を一度だけ固定する** — 次にJV-Linkが実際に停止した際、timeout後に32bit Python / COM子が0件であることをPID付きartifactへ残す。fixture成功だけを実COM成功と混同しない。

## 前回からの差分

- 直近の同系type-C評価 `20260802_2155_hidden_scheduled_tasks__profitability-judge.md` は **PASS / 4.4**。今回は実COM timeoutと初回定刻実走が未確認のため単純比較では **4.4 → 4.2**。追補により当初のtimeout無通知とkill確認不足は解消し、判定はPASSを維持する。
- 旧実害（`fetch_full start`で停止し後続予想が未生成）に対し、停止時間上限と09:00再試行は追加された。利益戦略そのものの評価・運用段階は変わらない。

## 運用段階

本改修は取得・公開基盤の可用性改善であり、戦略を「観察用」「紙運用」「実弾候補」の次段階へ昇格させる証拠ではない。既存戦略の段階は不変。
