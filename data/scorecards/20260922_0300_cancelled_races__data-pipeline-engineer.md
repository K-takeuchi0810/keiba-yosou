# データパイプライン技術者 採点 — b1733d7 中止レース (data_div='9') の評価除外

## 判定: HOLD

**理由**: 停止条件抵触なし (ingest / 取得 / スキーマ不変、partial row 経路なし)。述語設計と評価側の明示化は妥当で、実 DB の 4 値も期待どおり (9/21 = scheduled 24 / cancelled 12 / eligible 12 / covered 12)。HOLD の対象は (a) `web/generator.py` の「防御的除外」が **描画だけ** に効いていて、中止レースは依然 `predict_race` され `insert_prediction_log(conn, race={}, …)` に流れる (本番は `--log-predictions` 付き → `prediction_log.race_year NOT NULL` で毎 run 12 件の WARN が出る新規ノイズ経路)、(b) 全レース中止日が **Discord 無音** (最終確認 heartbeat も出ない)、(c) fresh odds 側 (`fetch_fresh_odds.py:194` / `fresh_odds_coverage.py:166`) が未対応で 9/21 は中止 12R に対し 37 回の no_data 取得を実行 (ok/fetched 46/83、前日 81/81)。3 件とも 10 行規模の補完で次サイクル再評価できる。
**根拠ファイル**: `db.py:79-118,322-346`、`scripts/auto_predict.py:96-138,307-350,393-394`、`web/generator.py:319-327,376-421,513`、`scripts/build_daily_results.py:570-580,692-747`、`scripts/monitor.py:170-195`、`scripts/prediction_accuracy.py:74-82`、`scripts/backtest.py:590-596`、`tests/test_cancelled_races.py`、実測は下記。
**次アクション**: generator.py:381 で `race_by_key` に無い key を skip / eligible==0 で `_final_confirmation` を「全 N レース中止」で 1 通出す / fetch_fresh_odds と fresh_odds_coverage に述語を足し AST テストの parametrize に追加。

## 対象・改修タイプ

- 対象: worktree `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\data-div-cancelled` ブランチ `data-div-cancelled-20260922` HEAD `b1733d7` (merge-base = 親 main `afd9ac3`、ff 可)。**subagent CWD 限定運用 (ルール 1-bis (b))**、git は全て `git -C <worktree>`。
- 改修タイプ: **type-B/D 混成** (評価・生成のゲート。`jvlink_client/` / fetch / schema.sql 不変)。P25 固有ゲート (fresh odds スケジューラ / coverage JSONL 必須項目 / market_snapshot / bonus_candidate) は **N/A (対象外)**。fresh odds を総合判定のゲートにはしない。
- 実 DB は `file:...keiba.db?mode=ro` で読取のみ。本番 checkout への書込みなし。変異テストは再実行していない (commit 記載の 18 種は **未検証**)。

## 総合: 3.6 / 5 (参考スコア)

## 項目別

- **述語設計 (NULL / EXISTS / upsert 整合): 4/5** — `upsert_race` は `ON CONFLICT … DO UPDATE SET data_div=excluded.data_div` (`db.py:322-346`) なので '2' → '9' の上書きは届く。実 DB でも 9/21 中山 12R は `data_div='9'`、`data_created='20260920'` (前日発行)。**NULL を評価可能に倒す判断は妥当**: 全 63,396 行に NULL は 0 件 (分布 7:44,183 / A:18,486 / B:576 / 9:79 / 6:60 / 2:12) で、実害の出る側は「取込途中を黙って捨てる」方。**`NOT EXISTS(中止)` の選択も妥当**: `races` 未取込の horse_races を残す方向は上記と一貫。反証: `data_div='9'` かつ `confirmed_order>0` の馬がいるレースは **2 件のみ、いずれも 2020-03-29 中山 3R/4R** (race_name が `?@?@…`、confirmed_order 84/49 = 既知の 2020 以前 raw バイト破損)。2021 以降は 0 件 → '9' は信頼できる。留保: `is_evaluable_race` は `.strip()` するが SQL 側はしない (契約テストは一致を見るがデータが `' 9'` なら乖離)。
- **生成経路 (auto_predict / _entry_coverage / generator): 3/5** — 実 DB 実測: 9/20 `(24,24,24,0)`、9/21 `(12,12,24,12)`、9/22 `(12,12,12,0)`、`_race_days` = 9/21→12、9/22→12。期待値と一致。9/22 の代替 12R は同じ kaiji/nichiji `04/07` で `race_month_day='0922'`、`data_div='2'`、SE 161 頭取込済 → PK が month_day を含むので衝突なし。**欠陥**: `generator.py:381` は `raw_horses_by_race` (horse_races 由来、未フィルタ) を回し `race_by_key.get(key, {})` で空 dict にフォールバックする。中止 12R も `predict_race(raws, race={})` され (実行 71 秒のうち相当分が無駄)、`--log-predictions` 時は `insert_prediction_log(conn, {}, …)` が `race_year NOT NULL` で IntegrityError → `generator.py:420` の except で **毎 run 12 行 WARN**。9/21 は 3 run × 161 頭 = 483 行が既に `prediction_log` に入っており (中止レースの予想ログ)、改修後は「入らない代わりに毎回警告」に変わるだけ。描画は `for r in races` (`:513`) なので HTML には出ない (実測: 9/21 で 12 レース描画、empty 0、例外なし)。
- **評価経路 (backtest / monitor / prediction_accuracy / build_daily_results): 4/5** — 明示化は正しい。**paired 中立性を確認**: 2021 以降に '9' かつ着順ありのレースが無いため、`require_confirmed` 下の backtest 集合は不変 (2020 窓のみ破損 2 レースが落ちる。以後の比較で 2020 を含む run は 2 レース減を注記すること)。`build_daily_results` は行を消さず 5 属性で区別する設計は正しい。留保 2 点: `actual_execution_date` は中止時 None だが順延先 (0922) は同 kaiji/nichiji で導出可能 — 名前が示す情報が入っていない。`race_status` は `data_div='2'` (未施行) でも `RUN` になる — 施行前に走らせると「走った」と記録される。
- **監視 / 無音性 / fresh odds 側: 3/5** — 全レース中止日を coverage_abort 通知にしないのは正しいが、`main:344-350` は `_final_confirmation` を呼ばず `return 0` → **Discord に 1 通も出ない**。09-19 の通知 dedup 設計「抑止は沈黙を作るので heartbeat で読み分ける」と矛盾。stdout の「評価対象レースなし」は bat 経由でログには残る。**fresh odds は未対応**: `fetch_fresh_odds.py:190-199` は当日 `races` を無条件に列挙 → 9/21 は eligible 24 (中止込み)、no_data 37 / fetched 83、ok 46 (9/20 は 81/81、no_data 0)。healthcheck は `ok_races_today=34` で PASS したので実害は無かったが、中止 12R への JV-Link 呼出しと ok 率の希釈は残る。`fresh_odds_coverage._load_open_dates` (`:162-171`) も同様。AST 契約テストの parametrize にこの 2 本が無い。
- **テスト / 変異耐性 / 再現性: 4/5** — 自分で再実行: 対象 6 モジュール **83 passed / 1 skipped** (`.venv64`, worktree)。AST 検査 (`test_every_races_query_applies_the_predicate`) は f-string 連結 + 免除を本文ごと登録する形で、`.format` 残しや inline コメント免除の抜けを潰している (設計として正しい)。fixture への `data_div TEXT` 追加は `schema.sql:12` と一致、既存テストの期待値変更は 4 値化と payload キー改名 (`with_entries`→`covered`) に限られ意味は不変。留保: `test_3` と `test_a_cancelled_race_is_recorded_but_not_evaluated` は計算式・分岐を **テスト内で再実装** しており本体を通さない (tautology)。5 属性テストは文字列 grep。

## 停止条件チェック

- [x] git_sha / rule_version / env_overrides: N/A (artifact 生成なし)
- [x] baseline paired 比較: N/A (採用主張なし)。副次確認: 2021+ の backtest 集合は不変 (上記)
- [x] market_snapshot / payout 欠損 / P25 fresh odds ゲート: N/A (type-B/D)
- [x] 専門領域: ingest 部分失敗 rollback → 経路不変。0 byte raw / lock → 不変。partial row を残す新経路 → なし (`insert_prediction_log` の失敗は executemany 単位で 0 行)。**すべて不抵触**

## 反証の試み

| # | 主張 | 結果 |
|---|---|---|
| R1 | 「'9' = 中止」は信頼できる | **成立 (2021+)**。破綻は 2020-03-29 の破損 2 行のみ |
| R2 | 9/21 は 12/12/24/12 になる | **成立** (実 DB、worktree コードで実測) |
| R3 | generator の防御的除外で「中止を描画しない」 | **描画は成立**、予測・ログ経路は **不成立** (`:381-421`) |
| R4 | 全中止日は「静かに終わる」のが正しい | **部分的に不成立**: heartbeat まで消える |
| R5 | 「除外なしは build_daily_results の 1 箇所だけ」 | **不成立**: `fetch_fresh_odds.py:194` / `fresh_odds_coverage.py:166` が残る (評価ではなく取得側だが、9/21 に実害 37 回) |
| R6 | 9/22 の本番は改修が無いと壊れる | **不成立**: 0922 は cancelled=0 なので旧コードでも 12/12 |

## 主な改善提案

1. **generator.py:381 で中止レースを予測経路からも外す** — `for key, raws in raw_horses_by_race.items(): if key not in race_by_key: continue`。WARN 12 行/run と無駄な `predict_race` を消し、「防御的除外」を本命経路に当てる。
2. **全中止日にも最終確認 heartbeat を 1 通** — `auto_predict.py:344-350` の `return 0` 前に `_final_confirmation(args, day, f"予定 {scheduled} レースすべて中止")`。抑止と無音を区別する既定に揃える。
3. **fresh odds 2 本に述語 + AST テストへ登録** — `fetch_fresh_odds.py:194` と `fresh_odds_coverage.py:166` に `AND {sql_evaluable_race()}`、`tests/test_cancelled_races.py:194` の parametrize に追加。9/21 型の日で eligible/ok が実力値になる。

## 9/22 本番 (08:00) より前に main へ入れるべきか

**後にすべき (11:00 run 終了後、当日中)**。根拠: (1) R6 のとおり 9/22 は cancelled=0 で旧コードと結果が一致し、朝に入れる利益が無い。(2) 利益が無い日に、本番未実走の生成側変更 + 提案 1 の WARN 経路を 03:00 に入れると、08:00 失敗時に人が起きていない。(3) -100 計上の実害は `build_daily_results` にあり、これは **スケジューラ登録も bat 参照も無い手動ツール** (`data/results/2026-09-20`, `2026-09-21` は HTML のみで evaluation_summary 未生成) → 待っても artifact は汚れない。(4) `keiba-auto-predict` は 08/09/11 に main へ publish commit を積むので、ff は 11:00 以降にどうせ merge になる。手順: 11:00 の publish commit 後に merge → `build_daily_results 20260921` を新コードで初回実行 → 9/22 の答え合わせも同コードで。

## 前回からの差分

- 直近の本 agent scorecard は `20260919_2100_notify_dedup` (**3.6 / HOLD**)。依頼文の `20260921_0040_jst_date_unify (3.8/HOLD)` は `data/scorecards/` に存在せず参照不能。
- 3.6 → 3.6 (±0)。対象サブシステムが異なるため項目は置換。今回の低点 2 項目 (生成経路 3 / 監視 3) はいずれも「防御が本命経路に当たっていない」型で、09-19 の `record()` 無音失敗と同じ欠陥クラス。
- 前回判定 HOLD → 今回 HOLD。理由: 停止条件なし、実 DB 数値は正しいが、補完 3 件が本番 1 開催日の前に必要。
