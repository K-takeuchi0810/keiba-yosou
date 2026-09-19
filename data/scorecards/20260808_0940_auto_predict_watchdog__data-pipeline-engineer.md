# データパイプライン技術者 採点 — auto predict watchdog

## 判定: PASS

**理由**: type-C（JV-Link 取得運用／日次スケジューラ）として、RACE/HOSE scoped ingest、厳密なrc=-1判定による前週月曜からのoption=2回復、catch-up後RACE no-dataの曜日非依存fail-closed、tree watchdog、通知、08:00/09:00回帰が揃った。実runで2026-08-08の36R/462頭、fresh odds、72R予想生成まで一気通貫で復旧し、全423テストも成功した。

**根拠ファイル**: `scripts/auto_predict_daily.bat:12-20`、`scripts/fetch_full.py:25-47,91-178`、`jvlink_client/client.py:69-77,297-300,326-347,400-430`、`scripts/run_auto_predict_daily.ps1:29-74`、`tests/test_auto_predict_task_runner.py:68-329`、`data/logs/auto_predict_daily_20260808.log`、`data/logs/fresh_odds_coverage.jsonl`

**次アクション**: Task登録は先行Unregisterをやめ `Register-ScheduledTask -Force` の非破壊更新にする。前週月曜からのfallback所要時間を開催日ログで継続監視し、1200秒watchdog内に収まることを確認する。

## 対象・改修タイプ

- 対象コミット: `cb970a0`、`903b74b`、`a3b13a4`、`99681dd`、`05d68a9`、`c04b1d5`、`5f1a5f9`、`e685c19`、`986598b`、`0f90945`。
- 改修タイプ: **type-C（データ取得／スケジューラ運用）**。watchdog、Task trigger、取得ログ、失敗通知を採点した。
- スコープ外: 予測重み・収益性・calibrator の採用判断。P25 paired backtest / market snapshot 採用ゲートは N/A。
- worktree は `scripts/fetch_fresh_odds.bat` ほか未追跡 scorecard を含む dirty 状態。採点は上記10コミットの差分と read-only 実測に限定した。

## 総合: 4.0 / 5（参考スコア）

## 項目別

- **JV-Link エラー回復: 4/5** — 全体timeoutは1200秒で有界化され、孫プロセスを含むtree kill、124/125終了、30秒上限付きDiscord通知がある（`scripts/run_auto_predict_daily.ps1:29-74`）。dataspec errorと-402/-403 `bad_files` をfail-closedにし、option=1 RACE rc=-1時は前週月曜00:00からoption=2 catch-upする（`scripts/fetch_full.py:27-53,97-138`）。前週開始で祝日月曜カードも探索し、catch-up後もRACE rc=-1なら曜日を問わずエラーを維持する一方、HOSE等だけno-data正常化する（`scripts/fetch_full.py:128-146`）。厳密regexは近傍rcを誤認しない（`scripts/fetch_full.py:41-42`）。
- **ingest 冪等性／クラッシュ一貫性: 4/5** — `--ingest` はdataspec別filenamesを `ingest_all(dataspecs=[dataspec], only_files=filenames)` に渡し、file errorを2で返す（`scripts/fetch_full.py:154-178`）。実ログはRACE 5 files、RA=38、SE=492、errors=0、HOSE 1 file/errors=0。DBを再計測して2026-08-08は36 races/462 horse_racesだった。mock試験もscopeとfetch/ingest/bad-file終了コードを固定する（`tests/test_auto_predict_task_runner.py:143-249`）。
- **データ鮮度管理（SLO）: 4/5** — triggerは08:00/09:00へ前倒しされ、回帰テストも両時刻を固定する（`scripts/register_auto_predict_task.ps1:7-9,31-39`、`tests/test_scheduled_bat_args.py:81-88`）。実runは10:26:59開始、10:29:17に72 races生成・push成功・exit=0まで記録した。前週月曜開始は土日・祝日月曜・変則開催のカードを同じ回復窓に含め、fallback後もRACEが空なら成功に降格しない（`scripts/fetch_full.py:30-38,128-146`）。
- **スキーマ進化／復旧: 4/5** — schema 自体は変更なし。既存 `ingest_all` の未取込raw回収と、取得filenamesの強制再取込を日次経路から利用できる（`scripts/fetch_full.py:85-105`、`jvlink_client/ingest.py:301-315,349-399`）。登録処理は既存Taskを先に削除してから再登録するため（`scripts/register_auto_predict_task.ps1:21-24,39-41`）、登録失敗時に旧Taskを失う留保がある。
- **fresh odds 取得運用: 4/5** — RACE ingest後のcoverage実測は10:29と10:30の各runで `total_races_in_db=36, eligible=2, fetched=2, ok=2, error=0`、各2 files ingest成功（`data/logs/fresh_odds_coverage.jsonl`）。DB再計測で `fetched_at=2026-08-08T10:29:26` は2 races/28 snapshot rows。取得前の0対象から上流復旧後に自動回復した時系列が一致する。

## 停止条件チェック

- [x] watchdog、ingest scope、fetch/ingest/bad-file終了コードの動的試験あり。
- [x] 孫プロセスを含む timeout tree kill の反証試験あり（`tests/test_auto_predict_task_runner.py:68-115`）。
- [x] timeout / kill失敗通知は30秒で有界（`scripts/run_auto_predict_daily.ps1:29-54`）。
- [x] RACE/HOSE取得summaryからdataspec別SQLite ingestへ配線あり（`scripts/fetch_full.py:85-103`）。
- [x] dataspec error=1、ingest error=2としてbatch/watchdogへ伝播（`scripts/fetch_full.py:104-112`）。
- [x] 実JV-Link取得・RACE/HOSE ingest・mining ingest・72R生成・push・exit=0の実runあり（`data/logs/auto_predict_daily_20260808.log`）。
- [x] DB再計測: 2026-08-08は36 races / 462 horse_races。fresh coverageも2/2取得から回復。
- [x] catch-up後RACE no-dataは曜日を問わず終了1、非RACE no-dataのみ正常化（`scripts/fetch_full.py:128-146`、`tests/test_auto_predict_task_runner.py:311-330`）。
- [x] 全テストを再実行し423成功/4 skip（20.43秒）。focused watchdog/pipeline testは14成功。08:00/09:00期待も2箇所で整合。
- [x] P25収益性、paired baseline、calibrator、payout欠損は **N/A（対象外）**。

## 反証の試み

- 主張「timeout時に子孫プロセスが残らない」に対し、batchがPowerShell孫プロセスをspawnしてhangする試験を実行 → **反証不成立**。runnerは124、保存PIDは終了済み（`tests/test_auto_predict_task_runner.py:68-115`、focused test 9件成功）。
- 主張「取得filenamesだけを対象にingestする」に対し、mock summaryを用いたscope試験を実行 → **反証不成立**。`dataspecs=['RACE']` と `only_files={'RATEST.jvd'}` が渡り成功した（`tests/test_auto_predict_task_runner.py:143-178`）。
- 主張「取得・ingestエラーは非0終了する」に対し、catch済みJV-Link errorとingest file errorを注入 → **反証不成立**。それぞれ1、2を返した（`tests/test_auto_predict_task_runner.py:181-224`）。
- 主張「破損rawを成功扱いしない」に対し、`bad_files=['CORRUPT.jvd']` を返すfake clientを注入 → **反証不成立**。`fetch_full.main()` は1を返す（`tests/test_auto_predict_task_runner.py:226-249`）。
- 主張「option=1 rc=-1からRACEを回復し、祝日月曜カードも探索できる」に対し、option=2呼出し、前週月曜fromtime、scoped ingestを検証 → **反証不成立**（`tests/test_auto_predict_task_runner.py:252-302`）。8/8は`20260727000000`、8/10は`20260803000000`を返し、実運用でもDB36Rまで成立。
- 主張「catch-up後もRACEが空ならfail-closed」に対し、2回ともRACE rc=-1を返すfake clientを注入 → **反証不成立**。曜日に依存せず終了1（`tests/test_auto_predict_task_runner.py:311-330`）。
- 主張「rc=-1近傍コードをno-dataと誤認しない」に対し、-10/-101/-111/-116を注入 → **反証不成立**（`tests/test_auto_predict_task_runner.py:303-310`、focused 14成功）。
- 主張「trigger変更を含め回帰がない」に対し、全suiteを再実行 → **反証不成立**。423成功/4 skip（35.43秒）。

## 主な改善提案

1. **Task更新を非破壊化** — `scripts/register_auto_predict_task.ps1:21-41` は先行Unregisterをやめ `Register-ScheduledTask -Force` にし、登録失敗時も旧Taskを保持する。
2. **fallback時間SLOを監視** — 前週月曜からのoption=2取得が1200秒watchdog内に収まるか、開催日ごとの経過秒・files/recordsをwatchdogログへ集計する。

## 前回からの差分

- 初回レビューは日次RACE ingest不在とsoft error成功扱いにより **FAIL / 2.4**。`99681dd` で **HOLD / 3.4**、`05d68a9` と `c04b1d5` で **HOLD / 3.6**。`5f1a5f9` と実運用E2Eで **PASS / 4.0**、`e685c19`・`986598b`・`0f90945` でrc厳密化、祝日月曜回復窓、曜日非依存fail-closedまで整備し判定維持。
- 前回同担当 `20260802_2155_hidden_scheduled_tasks` の PASS / 4.0へ復帰。変則開催判定とTask非破壊更新を次の運用強化として残す。
