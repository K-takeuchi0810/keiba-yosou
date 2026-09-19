# データパイプライン技術者 採点 — F3 morning anchor

## 判定: HOLD

**総合: 4.1 / 5**（公式前回 4.6 → 今回 4.1、差分 **-0.5 ⚠ 後退**。
初回監査 3.8 → 最終 +0.3）

対象は最終 HEAD `e5eaf34`、`scripts/fetch_morning_odds.bat`、
`scripts/register_morning_odds_task.ps1`、`tests/test_f3_morning_anchor.py`、
`docs/F3_morning_anchor_result.md`、Task Scheduler 実状態と実ログ。
指定の `.Codex/agents/_rubric.md` はリポジトリに存在しないため、担当プロンプトの
5軸と直前の同担当 scorecard の形式で採点した。

既存 JV-Link/ingest/DB の回復性を利用した実装は妥当で、固定 window、32bit Python、
共有 atomic lock、WAL/busy timeout、Task の多重起動抑止を確認した。初回指摘後、
共有lock競合を30秒間隔・最大6回試行し、残存時rc=4でfail-closedにするwrapperと、
既存Taskを先に削除せず `Register-ScheduledTask -Force` で更新する処理が追加された。
一方、実行日は
DB内レース0件で、同時起動した2プロセスはいずれもロック取得・COM・ingestへ進んでいない。
したがって、指示書の数値受入（全レース lead>=60分、wide_drift>0、欠落分布、実増分）と
実JV-Link/SQLite競合確認は未完了であり、go-live受入は **HOLD** とする。

## 項目別

### 1. JV-Link エラー回復: 4.6 / 5

- morning は `.venv32\\Scripts\\python.exe` で既存 `scripts.fetch_fresh_odds` を呼び、
  32bit COM 制約を守る（`fetch_morning_odds.bat:12-17`）。
- 共通経路の `fetch_realtime` は JVRTOpen の `rc=-1` を正常な no-data として返し、
  transient open rc を retry、JVGets `rc=-3` を既定30秒でtimeout、`finally` で
  `JVClose` を実行する（`jvlink_client/client.py:448-508,537-629`）。
- ただし今回のsmokeは `eligible_races=0` で、この回復経路を実機では通っていない。

### 2. ingest idempotency / 二重取込防止: 4.5 / 5

- morning/live は同じ `single_run_lock` を利用し、O_EXCLによるatomic取得とstale回収、
  finally削除を行う（`scripts/fetch_fresh_odds.py:40-69,201-205`）。
- lock保持中にJV-Link取得から `ingest_all(only_files=fetched_files)` まで進むため、
  COMとDB writeの主要区間は直列化される。同名更新は `only_files` で強制再取込され、
  DB側UPSERTの既存冪等性を使う。
- 単体テストは同一プロセス内の二重取得拒否のみで、独立2プロセス、stale回収、
  lock保持中のingestを検証しない（`tests/test_f3_morning_anchor.py:34-43`）。
- wrapperは共通moduleのlock競合メッセージを検出し、30秒間隔で最大6回試行する。
  一時的なlive重複ならmorningを即時dropせず、競合残存時もrc=4で上位監視へ通知できる。
- race選択時の `open_db()` はlock外で `init_db()` を通る。WAL/busy timeoutで緩和されるが、
  「DB全区間の直列化」を厳密には満たしていない。

### 3. データ鮮度管理 / no-op検出: 3.2 / 5

- 引数は `--window 600 --min-lead 0` に固定され、`%*` を転送しない。出力の
  `window=0-600min` が無ければrc=2とするため、元のwindow引数静的no-opは防げる
  （`fetch_morning_odds.bat:17-28`）。ログではmarkerとrc=0を確認した。
- しかし実測は `total_races=0 / eligible=0 / fetched=0`。最新snapshotは
  `2026-07-19T16:20:02` のままで、lead>=60分カバレッジ、wide_drift、朝オッズ欠落分布は未評価。
- 共通module自体はlock競合時に `lock_skipped=true` を記録してrc=0だが、最終wrapperは
  `another fetch_fresh_odds run is active` を検出し、6回残存時はrc=4とする
  （`fetch_morning_odds.bat:20-35`）。初回指摘の「競合で全件skipしてもTask成功」は解消した。
- ただし対象レースが存在するのにJV-Link no-data/timeout/emptyで取得0となるケースは、
  共通moduleがrc=0のため依然Task成功になり得る。開催日の数値受入と併せて監視条件が必要。

### 4. スキーマ整合性 / DB競合: 4.4 / 5

- 実DBは `journal_mode=wal`、`busy_timeout=5000`。`open_db()` とingest接続は共通
  `connect()` を通り、morningだけの設定漏れはない（`db.py:126-149`）。
- `odds_snapshots` はrace indexと複合PKを持ち、現状38,066行。schema/ingest本体に変更なし。
- 初期race SELECTがread-only helperでなく `open_db()` を使い、毎回schema実行/migration可能な
  接続になる点は、lock外の朝/live同時起動時に不要なwriter競合を増やす余地がある。

### 5. リトライ・Task登録・性能/観測性: 3.8 / 5

- 実Task `keiba-morning-odds` はReady、次回 `2026-07-21 08:45 JST`、
  `MultipleInstances=IgnoreNew`、limit=PT1H、actionは指定bat。LastResult=0を確認した。
- 同時19:03:49起動ではmorning/liveとも19:03:51にwindowログを残したが、当日レース0件のため
  lock、COM、DB write競合を観察しておらず、競合試験の証拠にはならない。
- 日次増加479 rows / 33.9 KiBは過去データからの推定であり、window=600の1回実増分ではない。
- 登録処理は先行 `Unregister-ScheduledTask` を廃止し、`Register-ScheduledTask -Force` で
  既存Taskを更新する。初回指摘の「登録失敗前に旧Taskを失う」手順上のリスクは解消した。
- `Interactive` principalなので、ログオフ状態では実行されない運用制約は残る。
- 現branchがmainへ未mergeの間、登録action先のbatはmainに存在しないことを報告書が明示しており、
  次回Taskの機能発火はmerge完了まで保証されない。

## 実測根拠

- `git log --stat -3`: `3ce4810` でbat/登録/test追加、`6d512ba` でログ値展開、
  `1163c83` でlock retry/fail-closedとTask `-Force` 更新、`e5eaf34` で
  retry秒数からping回数を算出して二重管理を解消。
- focused test: `4 passed in 0.12s`。全体は親実行報告 **370 passed / 4 skipped**。
  ASCII、固定引数、fail-closed文字列、非破壊Task更新、nested lockを確認。
- Scheduler: morning/freshともReady、LastRun `2026-07-20 19:03:49`、LastResult 0。
- coverage末尾: morning `window=600` とlive `window=25` は同秒だが、双方0 races、
  `lock_skipped=false`。これは同時COM/ingest試験ではない。
- DB: WAL、busy_timeout=5000、`odds_snapshots=38066`、latest fetched_at
  `2026-07-19T16:20:02`。raw 0B31は3,022,857 bytes。
- `data/fetch_state.json`、raw先頭10種、DB table/index一覧を確認。raw本体は読んでいない。

## HOLD解除条件（次のJRA開催日、merge後）

1. 08:45実行で対象全レースのlead>=60分snapshot率、非zero fetched/ingested、
   `wide_drift>0`、朝オッズno-data/timeout/欠落分布を保存する。
2. 09:00 liveとの実際の重なりで、wrapper retryまたはrc=4が働く事実と、COM rc・DB lockなしを確認する。
3. 1回分のraw byte、`odds_snapshots`行、JV読取records/filesのbefore/afterを実測する。
4. merge済みbatの存在/hashを登録後に検証し、Interactive principalの運用条件を明記する。

## 優先課題

**P0: 開催日のend-to-end受入を完了し、対象ありno-data/timeout/emptyを監視する。**
lock競合のfail-closedは実装されたが、F3 driftに必要な朝snapshotの取得実績、実競合時の
retry/rc=4、対象あり取得0の異常判定はまだ証明されていない。
