# 検証プロセス監査人 採点 — 3cd1871 中止レース是正 final2 (前回 HOLD 4867a0e の是正版: 内訳 / 実施日 / 監視の値・窓 / 返還◎ / 失格 / fail-open)

**subagent CWD 限定運用での評価 (worktree 絶対パス指定)**: 対象は `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\data-div-cancelled` (branch `data-div-cancelled`)、SHA **`3cd1871`** に固定。git 操作はすべて `git -C <worktree>`、Read / Bash も worktree 絶対パス。開始・終了時の `rev-parse HEAD` = `3cd18716…` で一致、終了時 `status --short` は **空**、親リポ (`C:\Users\kizun\dev\keiba-yosou`) の tracked 差分 **0** (本書以外の書き込み無し)。実 DB は `mode=ro` で読み、9/21・9/22 の races / horse_races / payouts を scratch DB に複製して production `main()` を走らせた。変異は `git archive 3cd1871` の隔離木 2 本 (`gate2_validation/iso`, `iso2`、`diff -r` で一致確認) のみ、1 変異ごとに `git checkout -- .` + porcelain 空を assert (終了時も空)。`config.SEALED_FROM = None` (封印未開始) を確認したうえで 9/21・9/22 を見た。

## 判定: PASS (最終ゲート。前回宣言した HOLD 条件 4 件がすべて閉じ、宣言済み変異 31 種 + 回帰 28 種 + 追加 5 種 = 64 種のうち有害クラスは全滅。生存 3 種は前回と同じ無害クラス)

**理由**: 前回 (20260923_0000) の HOLD 解除条件 (1) M25 (2) M54 (3) G1/G2 の値・text (4) 窓非依存 (5) 返還 ◎ を、すべて **実行で** 確認した。M25 は 3 変種 (総数で潰す / 理由を 1 種に潰す / 前方一致で合算) が `test_manifest_keeps_every_exclusion_reason_apart` 等で撃墜、M54 は 4 変種 (not_cancelled / result_resolved / payout_resolved / 無条件) が `test_only_an_evaluable_race_gets_an_execution_date` 等で撃墜。5 状態 fixture は `test_the_fixture_really_holds_five_states` が前提を自己検査している。監視は G1 (値に 1 着馬番) / G2 (top-level 追加キー) / G2b (days 追加キー) / G2c (件数を文字列化) / G3 (text に行追加) / G13 (`--json` にキー追加) がすべて撃墜。窓は G7 / G8 / H18 (検出を表示窓に縛る 3 通り) と G10 / G11 (下限撤去) が撃墜し、実 9/22 を速報に戻した模擬で **10/10 時点 `--days 14` → ERROR / 12 レース / 408h / 表 0 行 / 「※表示窓の外」** を確認 (前回は同条件で OK に戻っていた)。返還 ◎ は実 9/21 の ◎ (09-01 の 3 番、3 着) を出走取消に書き換えた模擬で、production `build_daily_results` → `analyze_misses` を通して `excluded_pick_refunded: 1` / 分母 11 (12 − 1) に落ちた。失格 5 は `NON_FINISHER` に入り (D1 / D2 / D3 / B3 撃墜)、`payout_final` はキーワード専用・必須 (D4 / D5 / D6 撃墜)。suite 実測 **767 passed / 11 skipped / 1 deselected** で主張と一致。

**改修タイプ**: type-B (答え合わせの状態モデル) + type-C (`db.py` 判定関数) + 運用監視スクリプト。P25 固有ゲート (factorial / market_snapshot / fresh odds / bonus_candidate / P25 PLAN / 6 agent 統合) は **N/A**。他 agent の final2 判定は本書執筆時点で未提出、type-B のため統合判定は N/A (本 agent 単独の最終ゲート)。

**根拠ファイル**: `db.py:133-198`、`scripts/build_daily_results.py:688-731,753-818,904-918`、`scripts/payout_finality_monitor.py:82-84,108-253`、`scripts/analyze_misses.py:177-195`、`tests/test_build_daily_results.py:466-545,692-716`、`tests/test_payout_finality_monitor.py:288-437`、`tests/test_analyze_misses_exclusion.py:83-200`、`tests/test_cancelled_races.py:643-661,831-847`、scratchpad `gate2_validation/mut2.py` / `mutC.json.out.json` / `mutD.json.out.json` / `mutE.json.out.json` / `out/2026092{1,2}` / `amroot` / `sim_refund.db` / `sim_window.db`

## 総合: 4.4 / 5 (参考スコア、前回 3.9 → +0.5)

## 項目別

- **バックテスト設計の正しさ (状態モデル / N / 金額の分離): 4.5/5** — 実 9/21: 320 行 → `cancelled 161 / evaluable 159` (前回の `payout_not_yet_final 159` が確定到着で evaluable に遷移、manifest `evaluation_exclusion_reasons = {cancelled: 161}`)、実 9/22: 161 行すべて evaluable、`actual_execution_date` は evaluable 行にだけ入る (161 空 / 159 日付)。返還馬 (09-04 の 7 番、無印) は profit 0 / settled 0。模擬の返還 ◎ は行として `evaluable=True / horse_refunded=True / profit 0 / settled 0` のまま残り (レース単位の評価可は正しい)、分析側で分母から外れる。減点: 本番 `data/results/` の **21 日ぶんすべて** の `evaluation_summary.csv` に `horse_refunded` 列が無い (列は 21cd03f で追加) → 過去日の返還 ◎ は再生成するまで不的中のまま (次回宣言 (3))。
- **時系列リーク防止 / 境界: 4.5/5** — 失格 5 が `NON_FINISHER` に入ったので「失格馬 1 頭で永久 result_not_yet_available」は閉じた。実 DB の JRA 2021 年以降で abnormal_code は `{0, 1, 3, 4, 7}` のみ、7 (降着) は 2 頭とも着順あり、4 (競走中止) は 1,227 頭すべて着順 0 — 仕様 (中止 = 返還なし・着順なし / 失格 = 同 / 降着 = 着順あり) と実データが一致。作者の「失格は 2024 年の地方 1 頭のみ」は **クリーン期 (2021+) の JRA については成立**、ただし 2016-2020 には code 5 が 3,459 頭 (2020 だけで 2,723 頭、うち 351 頭は着順あり) — これは 2020 以前の raw バイト破損期の値で意味を持たない (下記 監視の減点 (b))。減点: なし大。
- **calibration / 監視の継続: 4.0/5** — 検出は `PENDING_SCAN_FROM=20200101` 以降の全開催日 (728 日、実 DB で 2.4 秒)、表示だけが `--days`。実 DB の現在値は **OK / pending 0** (9/19-9/22 の確定払戻到着済、9/21 は `中止 12 / 実施 12 / 評価可 12`)。実 9/22 を速報に戻した模擬: 9/23 = INFO 0.5h → 10/10 `--days 14` = **ERROR 408h、表 0 行、text に「※表示窓の外」**、`--days 30` = 同 ERROR で表 2 行。全期間 (`scan_from=19000101`) だと 1954-1985 の 58 レースで永久 ERROR — 作者の下限根拠を実 DB で再現。減点 3 つ: (a) 結果待ち (`result_not_yet_available`) の滞留は依然監視対象外 (設計どおり、JRA 2021+ では該当ゼロを確認したのでリスクは空)。(b) 下限 2020 は raw 破損期を 1 年含む: 2020 の JRA 3,429 レースは確定払戻があるのに「着順が付くはずの馬」が 0 着 (abnormal_code が `@` `?` 等) → 永久に result_final にならず **鳴らないが表にも滞留として出ない**。誤警報は出ないが、下限は 2021 (クリーン期の開始) が正しい。(c) `main()` に `--db` が無く、config の DB_PATH 以外を指せない (worktree から直接叩くと `unable to open database file`、テストは build を差し替えて回避)。
- **A/B / 再現性 / 変異主張の裏取り: 4.5/5** — suite 実測 767 / 11 / 1 (主張と一致)。独立 64 変異: **撃墜 61 / 生存 3** (G6 深刻度境界 `<=`→`<`、G9 LEFT JOIN 空行スキップ削除、H1 `payout_resolved` の `tan_payout1 > 0` 要求削除 — いずれも無害・データ上等価)。宣言済みクラス (M25 系 3 / M54 系 4 / G1・G2 系 4 / text・json 2 / 窓 5 / 返還◎ 3 / 失格・降着 3 / fail-open 3 / bdr 2 / 監視その他 2 = 31) は **全滅**。前回撃墜済みの回帰 28 種は 26 撃墜 + 2 無害生存 (前回と同じ)。作者主張「24 種全撃墜」は、私の宣言クラス 31 種が全滅した事実と整合。減点: H1 の乖離クラス (bdr は `tan_payout1 > 0` を要求、monitor は要求しない) が依然テストで固定されていない。実 DB 2020+ で「確定払戻なのに tan_payout1 が NULL/0」は **0 件** なので現状は等価。
- **過適合監視 / 統合判定 / 監査プロセス: 4.5/5** — 採用戦略の変更なしで weekly_monitor は非該当。対象 SHA 固定・両 checkout 無編集・隔離木のみで変異、終了時 porcelain 空。監視と評価ロジックの独立は前回どおり (monitor は `db` の語彙と `config.DB_PATH` だけを import)。減点: 兄弟 agent の final2 判定が未提出で統合は N/A のまま。

## 変異テスト (独立設計 64 種、隔離 3cd1871、対象 5 test file → 生存時のみ全 suite `-x`、1 変異ごとに復元)

| ID | 変異 | 結果 | 撃墜した test |
|---|---|---|---|
| **M25** | bdr manifest 理由内訳を excluded 総数で潰す (前回まで 3 回生存) | **撃墜** | manifest_keeps_every_exclusion_reason_apart |
| M25b | bdr 理由を `["excluded"]` 1 種に潰す | 撃墜 | manifest_counts_split_evaluable_from_issued |
| M25c | bdr 理由を前方 7 文字一致で合算 (payout_* が合流) | 撃墜 | manifest_keeps_every_exclusion_reason_apart |
| **M54** | bdr `actual_execution_date` を not_cancelled 行にも記入 (前回まで 2 回生存) | **撃墜** | only_an_evaluable_race_gets_an_execution_date |
| M54b / M54c / M54d | 同 result_resolved / payout_resolved / 無条件 | 撃墜 | 同上 / a_cancelled_race_books_no_loss_through_main |
| **G1** | monitor `pending_race_ids` に 1 着馬番を埋め込む (前回生存) | **撃墜** | the_report_never_leaks_race_outcomes |
| **G2** | monitor top-level に `first_place_by_race` 追加 (前回生存) | **撃墜** | 同上 |
| G2b | monitor days に `finish_count` 追加 | 撃墜 | 同上 |
| G2c | monitor `evaluable` 件数を文字列にして成績を埋める | 撃墜 | a_preliminary_only_day_is_pending |
| G3 | monitor text 出力に `winners:` 行を追加 | 撃墜 | the_text_output_carries_no_outcomes |
| G13 | monitor `--json` に `winner` キー追加 | 撃墜 | the_json_output_carries_no_outcomes |
| G7 / G8 / H18 | monitor 検出を表示窓に縛る (Python 側 / SQL 側 / AND 追加) | 撃墜 | an_old_pending_day_stays_loud_outside_the_window |
| G10 / G11 | monitor 下限撤去 / 下限を 1900 に | 撃墜 | days_before_the_scan_floor_are_not_pending |
| G12 | monitor 「※表示窓の外」印を消す | 撃墜 | the_text_output_says_the_oldest_is_outside_the_window |
| G14 | monitor 速報 '1' も確定扱い | 撃墜 | a_preliminary_only_day_is_pending |
| G15 | monitor 経過時間の起点を当日 0:00 に | 撃墜 | severity_rises_with_age[1-INFO] |
| H10 | monitor `pending_race_count` を日数に | 撃墜 | a_preliminary_only_day_is_pending |
| A1 | am 返還 ◎ の除外を削除 | 撃墜 | only_evaluable_races_reach_the_analysis |
| A2 | am 0 着の ◎ を全部除外 (競走中止まで消す) | 撃墜 | 同上 |
| A3 / H16 | am 返還理由を cancelled に合算 / "false" も返還扱い | 撃墜 | each_exclusion_reason_is_counted_separately / 同上 |
| D1 | db 降着 7 を非完走集合に追加 | 撃墜 | a_disqualification_has_no_order_and_no_refund |
| D2 | db 失格 5 を非完走集合から除去 (改修前の状態) | 撃墜 | a_disqualified_pick_is_a_loss_and_the_race_still_finalises |
| D3 | db 失格 5 を返還集合に追加 | 撃墜 | 同上 |
| B3 | bdr 非完走 (4 / 5) を返還扱い | 撃墜 | 同上 |
| D4 / D6 | db `payout_final=True` 既定値を復活 (exclusion_reason / is_evaluable) | 撃墜 | payout_final_has_no_fail_open_default |
| D5 | db キーワード専用 `*` を外す | 撃墜 | 同上 |
| B7 | bdr manifest `evaluation_rows_excluded` を総数に | 撃墜 | manifest_keeps_every_exclusion_reason_apart |
| H17 | bdr `horse_refunded` 列を常に False | 撃墜 | a_refunded_horse_is_not_a_loss |
| 回帰 M4 / M5 / M6 / M6b / M16b / M17b / M23 / M30 / M32 / N1 | 前回撃墜済み 10 種 | 撃墜 | 前回と同じ test |
| 回帰 X1-X11 / X14 / X15a / X15b | 前回撃墜済み 14 種 (X8 は 5 を残して 4 を除去、X15 は `payout_final=True` 固定に変更) | 撃墜 | 5 状態 fixture / refunded / dead_heat / provisional 系 |
| 回帰 G4 / G5 | 結果待ち / 中止を滞留に | 撃墜 | 前回と同じ test |
| G6 | monitor 深刻度境界 `<=` → `<` | 生存 (無害、前回と同じ) | — |
| G9 | monitor LEFT JOIN 空行スキップ削除 | 生存 (無害: 出走馬 0 のレースのみ) | — |
| H1 | bdr `payout_resolved` から `tan_payout1 > 0` 要求を削除 | 生存 (実 DB 2020+ で該当 0 件、monitor と同じ定義になる) | — |

## 指示された 7 項目の検証 (実 9/21・9/22 データ + 模擬、production `main()` 経由)

1. **宣言済み変異がすべて落ちる (M25 / M54 / G1 / G2 + 前回の宣言分)** → **成立**。M25 系 3 / M54 系 4 / G1 / G2 系 3 がすべて撃墜。前回宣言分 (M6 / M16b / M17b / N1 / X 系) の回帰 26 種も撃墜。生存は無害 3 種のみ (G6 / G9 / H1)。
2. **監視出力に成績情報が混入しない (値・text・json)** → **成立**。値: G1 / G2 / G2b / G2c 撃墜 (`_assert_report_is_counts_only` がキー集合完全一致 + レース ID 正規表現 + 件数の型を検査)。text: G3 撃墜 (許可行ホワイトリスト 5 形)。json: G13 撃墜。実 DB の `main()` text 9 行 / json は同じ検査に **全部通る**。
3. **cancelled / result_not_yet_available / payout 待ち / 速報払戻 / evaluable が混同されない** → **成立**。5 状態同居 fixture で理由が完全一致固定 (M25 系 + X1-X4 + X15 系が同 fixture で撃墜)。実 9/21 = `cancelled 161 / evaluable 159`、9/22 = `evaluable 161`、模擬 (9/22 を速報に戻す) = monitor が `payout_not_yet_final` として滞留報告。
4. **返還馬を損失・miss にしない** → **成立**。実 9/21 の返還馬 (09-04 の 7 番) は profit 0 / settled 0。模擬の返還 ◎ (09-01 の 3 番) は bdr で profit 0 / settled 0、`analyze_misses` で `excluded_pick_refunded: 1`、分母 12 → 11。A1 / A3 / H16 / H17 / X5 / X6 / X9 / X11 撃墜。
5. **競走中止と失格・降着の扱い** → **成立**。中止 4 = 返還なし・着順なし (X7 / X8 撃墜、実 DB JRA 2021+ の 4 は 1,227 頭全部 0 着)、失格 5 = 返還なし・着順なし (D2 / D3 / B3 撃墜、`test_a_disqualified_pick_...` で profit −100 / settled 100 / レース確定)、降着 7 = 着順あり (D1 撃墜、実 DB JRA 2021+ の 7 は 2 頭とも着順あり)。A2 (競走中止の ◎ まで分母から消す) も撃墜。
6. **payout_final 未指定が fail-open しない** → **成立**。`exclusion_reason` / `is_evaluable` はキーワード専用・必須 (D4 / D5 / D6 撃墜、`f(True, True, True)` と位置 4 引数の両方で TypeError)。bdr は `payout_final=payout_final` で渡し (X15a / X15b は `=True` 固定で撃墜)。
7. **14 日表示窓の外でも滞留検出が消えない** → **成立**。G7 / G8 / H18 / G10 / G11 撃墜。実データ模擬で 10/10 `--days 14` = ERROR / 表 0 行 / 「※表示窓の外」(前回同条件は OK に戻っていた)。

## GATE_EXEMPT の固定は十分か

十分になった。`_assert_report_is_counts_only` が top-level / days のキー集合を完全一致で固定し、`pending_race_ids` はレース ID 正規表現、件数は `type is int`、`status` / `pending_reason` は列挙値。text は 5 形のホワイトリスト (形を増やすときはテストも増やす = 免除の根拠を見直す機会)。`--json` も同じ検査。実 DB の出力もこの検査に通る。残るのは前回指摘の「免除スクリプトの import 集合を固定するテスト」(封印ガード側) で、今回の改修範囲外 — 次回宣言に残す (HOLD 条件にはしない)。

## 停止条件チェック

- [x] git_sha / rule_version / env_overrides — N/A (backtest JSON 生成なし)。対象 SHA `3cd1871` 開始・終了で一致
- [x] baseline paired 比較 / market_snapshot / payout 欠損 — N/A (type-B/C)
- [x] 専門領域: 証拠を生む仕組み — **抵触なし** (宣言済み変異全滅、免除の固定が値・text・json まで、監視が窓非依存、金銭経路は前回 14 + 今回 8 の変異全滅 + 実データ 2 日 + 模擬 2 本で成立)
- [x] 他 agent との不整合 — final2 判定は未提出、type-B のため統合 N/A

## 前回からの差分 / 宣言の執行

- 前回 (20260923_0000、4867a0e): **3.9 / HOLD** → 今回 **4.4 / PASS** (+0.5)。項目別: 設計 4.5→4.5、リーク 4→4.5、監視 3.5→4.0、再現性 3.5→4.5、統合 4→4.5。-0.3 以上の低下なし
- 前回宣言「M25 または M54 が素通りなら FAIL」→ **両方撃墜 (各 3-4 変種)、非該当**
- 前回宣言「G1 / G2 のいずれかが素通り、または `--days 14` で 15 日以上前の滞留が OK になる挙動が残っていれば HOLD 上限」→ **G1 / G2 撃墜、窓非依存を実データ模擬で確認、非該当**
- 前回宣言「返還 ◎ が `analyze_misses` で不的中に数えられる状態が残っていれば HOLD 上限」→ **production 経路の模擬で除外を確認、非該当**
- 前回の次アクション (1)〜(5): **すべて執行済** (5 状態 fixture / 保留 3 状態の実施日 / 値・text・json 検査 / 窓分離 + 下限 / `excluded_pick_refunded`)
- **今回の新宣言 (次回この系列を見るとき)**: (1) 本番 `data/results/` 21 日ぶんの `evaluation_summary.csv` に `horse_refunded` 列が無い — マージ後に当該日を `build_daily_results` で再生成しないと過去の返還 ◎ は不的中のまま。**再生成せずに analyze_misses の集計を成績主張に使っていたら HOLD 上限**。(2) H1 乖離 (`payout_resolved` の `tan_payout1 > 0` 要求が bdr だけ) — 実 DB に「確定払戻で tan_payout1 が NULL/0」が 1 件でも現れたら HOLD 上限、現れなければテストで定義を片方に寄せる (P3)。(3) `PENDING_SCAN_FROM` は 2020 を含むが 2020 の abnormal_code は raw 破損 (3,429 レースが永久 result 待ち・監視外) — 2021 へ寄せるか docstring に明記 (P3、誤警報は出ない)。(4) monitor `main()` に `--db` (P3)。(5) 免除スクリプトの import 集合固定 (前回持ち越し、P3)。(1) 以外は HOLD / FAIL 条件にしない
