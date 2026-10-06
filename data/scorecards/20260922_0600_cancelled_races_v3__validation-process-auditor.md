# 検証プロセス監査人 採点 — 7f5d8de 中止レース是正 v3 (払戻待ち独立状態 + planned/settled 分離 + analyze_misses behavioral test)

## 判定: HOLD (自分の前回宣言の執行。マージ前提として要求した是正 1・2 は一次データで成立)

**理由**: 前回 (db39d55、HOLD 3.2) で指摘した 4 件は **すべて解消を実証**した。(a) M23 分岐順序入替 → `db.exclusion_reason` に集約され、変異 M23 (db 側順序入替) / M23b (呼び出し側の引数入替) とも撃墜。前回宣言「M23 相当が素通りなら FAIL」は **非該当**。(b) 述語の文字列差し替え → M70 (`cancelled="1=0"`) を AST 検査が撃墜、backtest `list_races` (M4) / generator horse_rows (M6b) は実行テストが撃墜。(c) analyze_misses → production `build()` を通す behavioral test が M31 / M57 / M59 / M60 (綴りを変えた無効化 4 通り) をすべて撃墜。(d) result_resolved が payouts を待たない → 実 9/22 データ (161 行) から払戻を消すと 145 行が `payout_not_yet_available` / profit 0 / settled 0 になり、戻すと同じ 145 行が evaluable に遷移。中止 (9/21 中山 161 行) に着順・払戻を注入しても `cancelled` のまま。指示された 5 点は **すべて成立**。一方、前回の宣言「M4/M5/M6/M6b/M16b/M17b/M30/M32 のいずれかが素通りなら HOLD 上限」のうち **M6 / M16b / M17b が今回も生存** (generator races 側 `OR 1=1`、prediction_accuracy / monitor の `(1=1 OR NOT EXISTS (...))`) — 7f5d8de の対象外ファイルだが、宣言は執行する。加えて新規に **中間結果状態 (data_div 3/4 = 3/5 着まで速報) が evaluable になる** 設計欠陥を実データで確認 (下記 N1)。金銭影響は現状ゼロなので FAIL ではない。

**改修タイプ**: type-B (答え合わせ / 分析ツールの状態モデル) + type-C (`db.py` 判定関数)。P25 固有ゲート (factorial / market_snapshot / fresh odds / bonus_candidate / P25 PLAN / 6 agent 統合) は **N/A**。他 agent 統合は type-A のみだが参考: profitability-judge v3 = **PASS 4.2** (執筆時点で提出済の唯一の兄弟判定)。矛盾はない — 同 agent も生存変異と横穴を「P2 (マージ阻害ではない)」と整理しており、本 agent の HOLD 理由は金銭ではなく宣言執行と状態モデル。

**運用条件**: ルール 1-bis (b)。対象 SHA `7f5d8de` を開始・終了時に `git -C <worktree> rev-parse HEAD` で確認 (**両時点で一致、worktree clean、親リポ tracked 差分 0**)。変異は `git archive 7f5d8de` で展開した隔離木 2 本 (scratchpad `iso` = 変異 / `iso2` = 実データ模擬) のみ、1 変異ごとに `git checkout --` + `status --porcelain` 空を assert (終了時 `clean=True`)。実 DB は `file:...keiba.db?mode=ro` で読み、9/21・9/22 の races / horse_races / payouts を scratch DB に複製して production `main()` を向けた。9/22 HTML は親リポの git object (`50fc046:data/results/2026-09-22/...`) から取得、本番 checkout には書き込んでいない。

**根拠ファイル**: `db.py:79-135` (`exclusion_reason` / `is_evaluable`)、`scripts/build_daily_results.py:675-689,723-735,764-778,863-877`、`scripts/analyze_misses.py:139-187`、`tests/test_cancelled_races.py:603-663,692-727,739-779`、`tests/test_build_daily_results.py:347-493`、`tests/test_analyze_misses_exclusion.py`、scratchpad `mut.py` / `mut_v3.json` / `out0921` / `out0922` / `sim1_a` / `sim1_b` / `sim2`

**次アクション (HOLD 解除条件、いずれも小さい)**: (1) `test_the_real_query_text_still_excludes_cancelled` を実行型にする: `two_race_db` に `hr.confirmed_order > 0` を外した形で prediction_accuracy / monitor の SQL を流し、中止 06 が出ないことを assert (M16b / M17b を殺す。「confirmed_order の副作用に頼らない」がこの系列の主命題なので、文字列検査のままでは主命題の担保が無い)。(2) generator races 側 SQL を `two_race_db` で実行し 06 が出ないことを assert (M6)。(3) N1: `result_resolved` を「1 頭でも着順あり」から「全馬着順確定」(races.data_div ∈ {5,6,7} または着順頭数 = 出走頭数 − 取消/除外) にするか、`result_partial` を一時状態として追加し、evaluable=True かつ ◎ confirmed_order=0 という行を出さない。(4) manifest `evaluation_exclusion_reasons` を 2 理由以上混在する fixture で assert (M25、2 回連続生存)。(5) 一時状態 (`result_not_yet_available` / `payout_not_yet_available`) の **滞留日数**を manifest か monitor に出す (N2)。

## 総合: 3.4 / 5 (参考スコア、前回 3.2 → +0.2)

## 項目別

- **バックテスト設計の正しさ (対象集合 / N / 金額の分離): 4/5** — production `main()` を実データで再実行: **9/21** = 320 行 → 中山 161 行 `CANCELLED / cancelled / result_resolved=False / payout_resolved=False`、阪神 159 行 evaluable、manifest `total 320 / evaluable 159 / excluded 161 / {cancelled:161}`。**9/22 (本日 11:24 HTML、レース中)** = 161 行 → 145 evaluable / 16 `result_not_yet_available` (12R、順延分)。planned/settled の分離は仕様どおり (中止・保留の買い候補は planned=100 / settled=0、fixture で確認。実データは買い候補 0 件で金銭 0 円)。減点 **N1**: 9/22 の R07/R08/R09/R11 は races.data_div=3/4 (3 着 / 5 着まで速報) で、着順があるのは 14-16 頭中 3-5 頭、しかし単勝払戻 (payouts data_div='1' 速報) は到着済 → `evaluable=True` になり、◎ が 4 着以下の 3 レースは **evaluable なのに ◎ confirmed_order=0** で記録された (`analyze_misses` の `pick_finish=0` が実出力に 3 行)。commit message が区別すると述べた「走ったが 0 着」が馬単位で再発している。勝者と払戻は確定しているので金銭は正しく、再実行で manifest が supersede するが、状態モデルに「部分結果」が無いため CSV 単体では見分けられない。
- **時系列リーク防止 / 境界: 3/5** — 生成側 `data_div=9` は前日公開情報でリークではない。`actual_execution_date` は evaluable のときのみ (順延先への誤紐付け入口は閉じたまま)。境界の弱点: (a) N1 の「1 頭でも着順」境界。(b) 述語の効果を実行で見るのは backtest `list_races` と generator horse_rows のみで、generator races 側 (M6) と prediction_accuracy / monitor (M16b / M17b) は `(1=1 OR NOT EXISTS ...)` でも素通り = 3 経路は `confirmed_order > 0` の副作用に戻れる。(c) M54 (保留行に実施日を入れる) が生存 — 保留でも `actual_execution_date` は空であるべきだが、保留 fixture はこの列を見ていない。
- **calibration / reliability 計測の継続: 3/5** — monitor の中止除外は M7 / M17 (前回) は撃墜だが M17b は今回も生存。加えて **N2**: 一時状態に滞留監視が無い。実 DB には 2026 年で「着順あり・単勝払戻なし」のレースが **629** ある (月別 21〜111 件、うち result 日付 21 日分に 14 件)。すべて地方交流 / 海外 (track_code 30-55, A6、data_div A/B) で予想対象外のため **現時点の評価への影響はゼロ**と確認したが、JRA の払戻取込が 1 日欠けると同じ経路で「一時」のまま永久に落ち、何も鳴らない。commit message 自身が警告した「後者が永久に評価から落ちたまま気付けなくなる」を防ぐ仕組みが今回も無い。
- **A/B / 再現性 / 変異主張の裏取り: 4/5** — suite 実測 (隔離 7f5d8de、`.venv64`): **1 failed (既知 data/ 欠如) / 722 passed / 11 skipped / 34 s** (前回 696 → +26)。独立 25 変異: **撃墜 18 / 生存 7**。前回宣言の FAIL 条件 (M23) は撃墜、前回の主要生存 (M30/M32 系 = 今回 M31/M59、M4、M6b) も撃墜。生存 7 のうち害のあるものは M6 / M16b / M17b / M25 / M54、無害 2 (M50 `>= 0`: 実 DB に払戻 0 の行は 2025 年以降 0 件。M58: 冗長ガード)。analyze_misses の behavioral test は production `build()` を実際に通す (指示 1 点目: **成立**)。ただし fixture CSV は手書きで、production 出力に無い列 `rationale` / `track_type_code` を持つ (「実スキーマを読む」のは DB 側のみ)。bdr 出力 → am の直結テストは無いので本監査で実出力を `build()` に流し、rows 23 / `excluded_cancelled 12` / `excluded_result_not_yet_available 1` を確認した。
- **過適合監視 / 統合判定 / 監査プロセス: 3/5** — 採用戦略の変更なしで weekly_monitor は非該当。対象 SHA 固定・作業停止は守られた (開始・終了で 7f5d8de 一致)。兄弟判定は profitability PASS 4.2 のみ提出済 (data-pipeline v3 は未提出)。スコープ外だが同型の事故クラスとして記録: **同着** (payouts `tan_horse_num2`、2024 年以降 14 件) は `win_payout_by` が 1 頭目しか見ないため 2 頭目の買い候補が -100 になる / **取消・除外** (abnormal_code 1/3/4、2026 年 377 頭、すべて confirmed_order=0) の買い候補は返還なのに -100 かつ settled=100 になる (過去 111 買い候補行に該当 0 件)。いずれも「勝った (賭けていない) 買い候補が -100」の同型で、状態モデルに入っていない。

## 変異テスト (独立設計 25 種、隔離 7f5d8de、全 suite `-x`、1 変異ごとに復元)

| ID | 変異 | 結果 | 撃墜した test |
|---|---|---|---|
| **M23** | db `exclusion_reason` の分岐順序入替 (着順判定を先に) | **撃墜** | cancelled_books_no_loss (+ truth_table) |
| M23b | bdr 呼び出しの引数入替 (`result_resolved, not_cancelled`) | 撃墜 | manifest_counts_split |
| M51 | bdr `payout_resolved = result_resolved` (払戻を待たない = 前回指摘 d) | 撃墜 | finished_race_without_payouts |
| M52 | bdr profit ゲートを `result_resolved` に | 撃墜 | finished_race_without_payouts |
| M53 | bdr settled ゲートを `not_cancelled` に | 撃墜 | race_without_results_is_pending |
| M63 | bdr 着順判定 `> 0` → `>= 0` | 撃墜 | race_without_results_is_pending |
| M66 | bdr `evaluable = is_evaluable(...) or not_cancelled` | 撃墜 | race_without_results_is_pending |
| M74 | bdr `not_cancelled = ... or result_resolved` (着順があれば中止扱い解除) | 撃墜 | cancelled_books_no_loss |
| M75 | bdr `race_status` を exclusion 有無で決める (保留が CANCELLED に) | 撃墜 | race_without_results_is_pending |
| M61 | db `is_evaluable` が払戻を無視 | 撃墜 | finished_race_without_payouts |
| M62 | db 払戻待ちを `result_not_yet_available` に潰す | 撃墜 | finished_race_without_payouts |
| M31 | am `if False and reason:` (前回 M30/M31 相当) | 撃墜 | each_exclusion_reason_counted |
| M57 | am `if reason == "cancelled":` (保留が分析に復活) | 撃墜 | each_exclusion_reason_counted |
| M59 | am 理由をまとめて数える (前回 M32 相当) | 撃墜 | each_exclusion_reason_counted |
| M60 | am `reason and race_status == "CANCELLED"` | 撃墜 | each_exclusion_reason_counted |
| M4 | backtest `({evaluable} OR 1=1)` (前回生存) | 撃墜 | backtest_list_races_excludes_cancelled_when_run |
| M6b | generator horse_rows `({cancelled} AND 1=0)` (前回生存) | 撃墜 | generator_prediction_query_excludes_cancelled |
| M70 | generator `.format(cancelled="1=0")` (述語の文字列差し替え) | 撃墜 | predicate_is_a_call_not_a_literal |
| **M6** | generator races 側 `({evaluable} OR 1=1)` | **生存** (3 回連続) | — |
| **M16b** | prediction_accuracy `(1=1 OR NOT EXISTS (...))` | **生存** (2 回連続) | — |
| **M17b** | monitor `(1=1 OR NOT EXISTS (...))` | **生存** (2 回連続) | — |
| **M25** | bdr manifest 理由内訳を潰す (全理由に excluded 総数) | **生存** (2 回連続) | — |
| **M54** | bdr `actual_execution_date` を保留行にも記入 | **生存** | — |
| M50 | bdr 払戻判定 `> 0` → `>= 0` | 生存 (無害: 実 DB に該当行 0) | — |
| M58 | am `evaluable` 冗長ガード削除 | 生存 (無害: 理由列が常に先に効く) | — |

前回生存 8 (M4 / M5 / M6 / M6b / M16b / M17b / M30 / M32) の再判定: M4 K / M6b K / M30・M32 相当 K / **M6 S / M16b S / M17b S** (M5 = backtest 節削除は M4 と同じ test が殺すため省略)。

## 指示された 5 点の検証

1. **am behavioral test は production 経路を見ているか** → **成立**。`analyze_misses.build()` 本体を tmp `RESULTS_DIR` + schema.sql 由来 DB で実走し、4 通りの無効化変異 (M31/M57/M59/M60) をすべて撃墜。留意: fixture CSV は手書き (production 出力と列が 2 つ乖離)、bdr→am 直結テストは無い (本監査で実出力を流して互換を確認)。
2. **payout 未取得を意図的に作ると ROI から除外されるか** → **成立** (実データ)。9/22 の payouts 全削除 → 着順ありの 145 行が `payout_not_yet_available` / evaluable=False / profit 0 / settled 0、12R の 16 行は `result_not_yet_available` のまま。単体では M51/M52/M53/M61/M62 撃墜。
3. **payout 到着後に同じレースが resolved へ遷移するか** → **成立** (実データ)。同 scratch DB に payouts を戻して再実行 → 同じ 145 行が evaluable=True / reason 空。`test_payout_arrival_moves_the_race_to_resolved` が構造として固定。
4. **中止は永久に resolved へ遷移しないか** → **成立** (実データ)。9/21 中山 12 レースに全馬着順 + 単勝払戻 350 円を注入 → 161 行すべて `CANCELLED / cancelled / evaluable=False` (`result_resolved=True / payout_resolved=True` と記録されつつ除外)。M74 撃墜。
5. **前回の主要変異が生存しないか** → M23 系 K / 述語差替 (M70, M4, M6b) K / am 系 K。**ただし M6 / M16b / M17b は生存** (7f5d8de の対象外ファイル、前回「HOLD 上限」と宣言した集合)。

## 停止条件チェック

- [x] git_sha / rule_version / env_overrides — N/A (backtest JSON 生成なし)。対象 SHA `7f5d8de` を明記、開始・終了で一致
- [x] baseline paired 比較 / market_snapshot / payout 欠損 — N/A (type-B/C)
- [ ] 専門領域: 証拠を生む仕組み — **部分抵触** (3 経路で述語の効果が未検査 = M6/M16b/M17b、状態モデルに部分結果が無い = N1、一時状態の滞留監視なし = N2)。金銭経路 (-100 復活 / 分母) は 3 方向から固定されており FAIL ではない
- [x] 他 agent との不整合 — profitability v3 PASS 4.2 と矛盾なし (同 agent も P2 を残す)。data-pipeline v3 は未提出。type-B のため統合判定は N/A

## 反証の試み

- 「8 セル真理値表で分岐順序を固定した」→ M23 (db) / M23b (呼び出し側) とも撃墜 → **成立**
- 「着順だけで評価可にすると -100 になる事故を塞いだ」→ M51/M52 撃墜、実 9/22 で 145 行が保留に → **成立**
- 「払戻が届けば同じレースが resolved へ遷移」→ 実データで 145 行遷移 → **成立**
- 「中止は永久に遷移しない」→ 着順・払戻を注入しても cancelled → **成立**
- 「fixture は実スキーマを読む」→ DB 側は成立、CSV 側は手書きで 2 列乖離 → **部分成立**
- 「走ったが全馬 0 着と結果待ちを区別できる」→ 馬単位では不成立 (9/22 R08/R09: evaluable=True で ◎ confirmed_order=0) → **N1、不成立**
- 「対象 SHA を固定し作業停止」→ HEAD・作業木とも不変 → **成立**

## 前回からの差分 / 宣言の執行

- 前回 (20260922_0400、db39d55): **3.2 / HOLD** → 今回 **3.4 / HOLD** (+0.2)。項目別: 設計 4→4、リーク 3→3、calibration 3→3、再現性 3→4、統合 3→3。-0.3 以上の低下なし
- 前回宣言「M23 が素通りなら FAIL」→ 撃墜、**非該当**
- 前回宣言「M4/M5/M6/M6b/M16b/M17b/M30/M32 のいずれかが素通りなら HOLD 上限」→ **M6 / M16b / M17b 生存、執行 → HOLD**。要求した是正 1・2 (今回 commit の範囲) は一次データで成立しており、HOLD の残り理由は (i) 対象外 3 経路の実行テスト 2 本、(ii) N1 部分結果状態、(iii) N2 滞留監視、(iv) M25/M54
- 前回の改善提案: (1) 中止 fixture confirmed_order=0 → 執行済。(2) 導出関数 + 真理値表 → 執行済 (8 セル)。(3) am behavioral → 執行済。(4) backtest / generator の実行テスト → **半分執行** (list_races と horse_rows のみ、generator races 側なし)。(5) real_query_text を実行型に → **未執行** (M16b/M17b が示す通り)
- **今回の新宣言**: 次回この系列で **M16b または M17b が素通りなら FAIL** (「confirmed_order の副作用に頼らない」が系列の主命題であり、3 回目の持ち越しは許容しない)。M6 / M25 / M54 のいずれかが素通りなら HOLD 上限。N1 (evaluable=True かつ ◎ confirmed_order=0 の行が実出力に出る) が残っていれば HOLD 上限。上記がすべて解消され、data-pipeline の v3 判定が FAIL/NOT_EVALUABLE でなければ PASS を出す
