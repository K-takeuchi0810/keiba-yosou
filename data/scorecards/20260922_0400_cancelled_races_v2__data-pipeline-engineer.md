# データパイプライン技術者 採点 (再レビュー) — db39d55 中止レース除外 v2

## 判定: PASS (留保つき)

**理由**: 前回 HOLD の 3 指摘は **すべて実挙動で閉じたことを実測確認**。(1) `build_view_model("20260921")` を worktree コード + 実 DB (mode=ro) で通し、`predict_race` 呼出しは **12 回・全て阪神 (track 09, data_div='6')**、中山 12R (data_div='9') は 0 回。9/22 も 12 回・全て中山 (順延先、data_div='2')。(2) 全中止日は最終起動時のみ `_final_confirmation` が 1 通 (payload `{"reason": "予定 N レースすべて中止"}` は run 間で安定 → dedup で 1 通)。(3) `fetch_fresh_odds` / `fresh_odds_coverage` に述語が入り、AST ガードの parametrize にも登録済。停止条件抵触なし。留保は「ガードが **token 検査のみ** で、述語を無効化する変異 2 種が素通りする」(M-A / M-D、下記) と「`result_resolved` が払戻の有無を見ない」の 2 点。いずれも現状データでは実害ゼロで、merge を止める理由にはならない。
**根拠ファイル**: `web/generator.py:319-349`、`scripts/auto_predict.py:76-138,307-375`、`scripts/build_daily_results.py:672-770,853-870`、`scripts/fetch_fresh_odds.py:190-199`、`scripts/fresh_odds_coverage.py:162-172`、`db.py:67-127,330-355`、`jvlink_client/ingest.py:350-372`、`tests/test_cancelled_races.py`、`tests/test_build_daily_results.py`。
**次アクション**: (a) `build_view_model` と fetch_fresh_odds の対象レース選択を fixture DB で通す **振る舞いテスト** を 1 本ずつ追加 (M-A / M-D を殺す)、(b) `result_resolved` に payouts 行の存在を AND する (または `payout_missing` フラグ)、(c) merge 後に `build_daily_results 2026-09-21` を新コードで実行し `evaluation_exclusion_reasons` が `{"cancelled": N}` のみ・track 06 の stake 合計 0 を確認。

## 対象・改修タイプ

- 対象: worktree `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\data-div-cancelled`、branch `data-div-cancelled-20260922`、**HEAD `db39d55`** (レビュー中に不変、最後に `git status` clean を再確認)。merge-base = main `afd9ac3`。main は `6cb23d7` (9/22 publish) に進んでおり **ff 不可、`merge-tree` は衝突なし** (tree `20ee5f0`)。
- 改修タイプ: **type-B/C/D 混成**。`fetch_fresh_odds.py` (取得対象の選択) を触るので type-C 要素あり → スケジューラ稼働 / coverage は実測した。market_snapshot / bonus_candidate / paired backtest は **N/A** (採用主張なし)。
- 実 DB は `file:…keiba.db?mode=ro` で読取のみ。本番 checkout への書込みなし。変異は worktree 内で 1 件ずつ適用 → pytest → `git checkout --` で復元、最終 `git status --short` は空。

## 総合: 3.8 / 5

## 項目別

- **述語設計 / ingest 整合: 4/5** — `upsert_race` は `ON CONFLICT DO UPDATE SET data_div=excluded.data_div` (`db.py:330-355`) で '2'→'9' が届く。`ingest_all` は RACE→その他→0B の順、ファイル名 sort、**1 回の `open_db()` = 単一トランザクション** (`ingest.py:359-362`、commit は context 終了時のみ) なので raw 全量再構築でも最後に来た '9' が残り、SE と HR は同 ingest 内では原子的に現れる。実 DB: `data_div` 分布 2:12 / 6:60 / 7:44,183 / 9:79 / A:18,486 / B:576、NULL 0。'9' かつ着順ありは 2020-03-29 中山 3R/4R の 2 件のみ (破損 raw、前回と同じ) → `backtest.list_races` は 2020 窓でこの 2 レースが減る (**注記必須**、2021+ は不変)。順延の実データ: 9/22 中山 12R は同 kaiji/nichiji `04/07`、`race_month_day='0922'`、SE 161 頭、`start_time_changes` 0 件 → PK に month_day を含むので旧 '9' 行と衝突しない。留保: `is_evaluable_race` は `.strip()`、SQL 側はしない (前回指摘、未変更、実データに空白なしで無害)。
- **生成経路 (generator / auto_predict): 4/5** — 上記のとおり **予想ループが中止レースを回らないことを `build_view_model` 経由で実測** (55 秒、例外なし)。`NOT EXISTS(中止)` の選択で races 未取込の horse_races は残る (安全側)。`_entry_coverage` 4 値は 9/21 `(12,12,24,12)`。全中止日の経路: `_race_days` 空 → `scheduled_all>0` → 「すべて中止」を出力し `_final_confirmation` (11 時以降 or `--final-attempt`)。`test_a_fully_cancelled_day_is_not_a_coverage_failure` が通常起動 0 通 / 最終 1 通を main() 経由で固定。留保: この fallback は `sqlite3.connect(DB_PATH)` (rw、ファイル無ければ作成) で既存 3 箇所と同じ癖。`open_db_readonly` に統一すべきだが新規リスクではない。
- **評価経路 (result_resolved / build_daily_results / analyze_misses): 4/5** — 3 分離は正しく、`stake_yen_100unit` を分母にする設計も正しい。**質問「1 頭でも confirmed_order>0 なら resolved は部分取込で妥当か」**: 実 DB 2026 JRA では horse_races の data_div は 2/6/7/9 のみ (速報 3/4/5 は取り込んでいない)、着順が 1〜3 頭だけのレース **0 件**、着順ありで payouts なし **0 件**。よって現行の取込構成 (`fetch_results` = 0B12、`fetch_full` = RACE、いずれも単一トランザクション) では部分状態は発生せず、判定は妥当。**ただし結合が弱い**: `result_resolved` は着順だけを見、`win_pay` は別テーブル。将来 SE と HR が別 ingest で来る (別 job / 片方失敗) と「勝った◎が payout 0 → profit=-100」になる。`resolved = 着順あり AND payouts 行あり` にすれば閉じる (1 行)。前回指摘の `race_status='RUN'` が data_div='2' (未施行) でも RUN になる点は未変更 — `result_resolved=False` で救われるが名前は依然誤解を招く。馬単位 (出走取消の買い候補 → -100) は既知の範囲外、`race_scratches` 表があるので次候補。
- **fresh odds 取得運用: 4/5** — `schtasks`: `keiba-fresh-odds` 登録済 (次回 9/22 09:00、準備完了)、`keiba-morning-odds` 08:45、`keiba-fresh-odds-healthcheck` 09:15。`fresh_odds_coverage --last 7`: 9/19 83/83 ok 100% → 9/20 81/81 100% → **9/21 83/83 ok 55.4% (46 records)**、JSONL の `total_races_in_db: 24` が中止込みで数えていた証拠 (差 37 = 中山 12R への no_data 取得)。述語導入で 9/22 以降は `total_races_in_db=12` 相当になる。**順延先で困る経路は無い**: 順延は新 PK 行 (`0922`) として来るので target_date=当日の列挙に自然に入る。限界 (非回帰): 当日中に発表される中止は `races.data_div` を更新する job が無い (fresh odds は O1 のみ ingest) ので翌朝 `fetch_full` まで取りに行き続ける — 改修前と同じ挙動。留保: 9/21 の 37 件 no_data は `failed_reasons` に「-」で分類されていない (`no_data_races` は別カウンタ)。既存仕様だが rubric の「理由分類」からは外れる。
- **テスト / 変異耐性: 3/5** — 対象 7 ファイル **114 passed / 1 skipped** (`.venv64`、worktree)。自分で設計した変異 5 種の結果:

| # | 変異 | 結果 |
|---|---|---|
| M-A | generator `cancelled=sql_cancelled_race("r.data_div")` → `cancelled="1=0"` (token は残す) | **素通り (81/81 pass)** |
| M-B | `resolved_race_ids` の `> 0` → `>= 0` | 検出 (`test_a_race_without_results_is_pending_not_a_loss`) |
| M-D | fetch_fresh_odds `.format(evaluable=sql_evaluable_race())` → `"1=1"` | **素通り (81/81 pass)** |
| M-E | `is_evaluable_race(None)` → False | 検出 (`test_a_missing_data_div_is_kept`) |
| M-F | `evaluable = not_cancelled or result_resolved` | 検出 (4 failed) |

  M-A / M-D が抜けるのは AST ガードが「`{cancelled}` / `{evaluable}` という **文字列 token の存在**」しか見ないため。generator の実挙動は今回私が実 DB で確認したが、CI にその検査は無い (`tests/` に `build_view_model` を呼ぶテストは 0 本)。fixture DB で `build_view_model` を通し「中止 race の key が `horses_by_race` に無い」を assert するテスト、fetch_fresh_odds は対象選択を `_target_races(conn, date)` に抽出して同様に通すテストで塞げる。

## 停止条件チェック

- [x] ingest 部分失敗 rollback / 0 byte raw / lock / tail timeout / JVOpen rc: **経路不変** (`jvlink_client/` 差分なし)
- [x] partial row を残す新経路: なし
- [x] post-start snapshot 混入: N/A (backtest 採用主張なし)。9/22 中山の `odds_snapshots` は 08 時台で 0 件 (発走前、正常)
- [x] スケジューラ記録 / coverage JSONL: あり (上記実測)
- [x] 別系統データ混入: なし

## 反証の試み

| # | 主張 | 結果 |
|---|---|---|
| R1 | 予想ループは中止レースを回らない | **成立** (9/21: predict_race 12 回・全て track 09 / 9/22: 12 回・全て track 06、実 DB) |
| R2 | 全中止日は最終起動で 1 通出る | **成立** (main() 経由テスト + dedup payload が安定) |
| R3 | fresh odds は中止を数えない | **成立** (述語 + AST 登録)。9/21 の 55.4% は改修前の記録として残る |
| R4 | 「1 頭でも着順あり = resolved」は部分取込で誤らない | **現行構成では成立** (部分着順 0 / 着順ありで payouts なし 0)。設計としては payouts 未結合 |
| R5 | 順延先の取得が漏れる | **不成立 (漏れない)**: 順延は新 PK 行で当日列挙に入る |
| R6 | ガードは述語の無効化を検出する | **不成立**: M-A / M-D 素通り |

## merge 前 pre-flight (9/22 11:00 起動終了後)

1. 親 `git status --short` は `?? .claude/skills/html-ui-ux-review/` と data 配下の untracked のみ → merge を阻害しない (ルール 1-ter (3) OK)。ff 不可なので merge commit (衝突なし確認済)。
2. sanity (1-ter (2)): main 上で `python -c "from db import sql_evaluable_race, sql_cancelled_race, EXCLUSION_RESULT_PENDING; from scripts.auto_predict import _entry_coverage"` を 1 回。
3. `data/results/2026-09-21/` は **source HTML 3 本のみで未ビルド** (build_daily_results はスケジューラ未登録、手動)。merge 前に旧コードで作らないこと。新コードで作り `counts.evaluation_exclusion_reasons` が `{"cancelled": N}` のみ・track 06 の `stake_yen_100unit` 合計 0 を確認。対照で 2026-09-20 も作り excluded 0 を確認。
4. `prediction_log` には 9/21 中山の予想 483 行 (3 run × 161 頭) が残る。`prediction_accuracy` は `NOT EXISTS(中止)` で除外するので集計上は無害。削除はしない (発行記録)。
5. 2020 窓を含む backtest / monitor baseline は 2 レース減 (2020-03-29 中山 3R/4R)。baseline 再凍結時に注記。
6. ガード対象外で `FROM races` を無条件に読む主要経路: `scripts/verify_roi_independent.py:93` (着順=1 の EXISTS で副作用除外)、`scripts/predict_t10.py:134`、`scripts/fetch_mining.py:45` (件数ログのみ)、`gui/app.py`、`webapp/aggregate.py`。次サイクルで parametrize に追加候補。
7. 中止の当日発表を `races` に反映する job が無い点は既知の限界として記録 (fresh odds の no_data がその日だけ増える)。
