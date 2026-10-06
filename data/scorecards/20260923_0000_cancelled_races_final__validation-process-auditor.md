# 検証プロセス監査人 採点 — 4867a0e 中止レース是正 final (返還 / 速報 / 同着 / 4 段階評価 / 確定払戻滞留監視)

## 判定: HOLD (最終ゲート。宣言済み HOLD 条件の変異 2 件 (M25 / M54) が「全滅」の主張に反して生存。金銭経路と指示 7 項目はすべて一次データで成立)

**理由**: 指示された 7 項目は **すべて成立** (下記)。金銭経路 (返還 / 速報 / 同着 / -100 復活 / 分母) は独立変異 14 種を全部撃墜し、実 9/21・9/22 データでも production `main()` が仕様どおりに遷移した。一方、改修サマリの「宣言済み M 系 12 種がすべて死亡」は **12 中 10 が正しく、M25 / M54 は生存**。M25 は `analyze_misses` 側の内訳テストが追加されたが、宣言した変異は **bdr manifest の `evaluation_exclusion_reasons` を潰す**もので、manifest 側を見るテストは無い (`test_manifest_counts_split_evaluable_from_issued` は `cancelled` 1 理由のみ)。M54 (保留行に `actual_execution_date` を記入) は中止 fixture でのみ空を assert しており、保留 fixture は列を見ていない。前回宣言「M6 / M25 / M54 のいずれかが素通りなら HOLD 上限」を執行する。新規の重大生存変異は無いが、GATE_EXEMPT の「成績を出さない」固定はキー名だけの検査で **値**と **text 出力**を見ておらず (G1 / G2 生存)、滞留監視は既定窓 14 日を過ぎると **自動で黙る** (実 DB で確認) — いずれも小さい是正で閉じる。

**改修タイプ**: type-B (答え合わせの状態モデル) + type-C (`db.py` 判定関数) + 運用監視スクリプト新設。P25 固有ゲート (factorial / market_snapshot / fresh odds / bonus_candidate / P25 PLAN / 6 agent 統合) は **N/A**。兄弟 agent の final 判定は執筆時点で未提出 (`data/scorecards/20260923_*` 無し) — type-B のため統合判定は N/A。

**運用条件**: ルール 1-bis (b)。対象 SHA `4867a0e` を開始・終了時に `git -C <worktree> rev-parse HEAD` で確認 (両時点一致、worktree porcelain 0 行、親リポ tracked 差分 0)。変異は `git archive 4867a0e` の隔離木 (`iso` = batch A、`iso4` = batch B、`iso5` = 実データ模擬) のみ、1 変異ごとに `git checkout -- .` + porcelain 空を assert。**注意**: 前回監査の残骸 `iso2` / `iso3` (7f5d8de 期の木) が同じ scratchpad に残っており、初回の batch B と模擬はそこで走って無効化した → 破棄して新規 archive で再実行 (本書の結果はすべて再実行後のもの)。`iso` は新規 archive と `diff -r` で一致を確認。実 DB は `mode=ro` で読み、9/21・9/22 の races / horse_races / payouts を scratch DB に複製。9/21・9/22 HTML は親リポ git object `50fc046:data/results/...` から取得。本番 checkout への書き込みは無し。

**根拠ファイル**: `db.py:93-192`、`scripts/build_daily_results.py:681-731,753-818,906-917`、`scripts/payout_finality_monitor.py:94-202`、`scripts/analyze_misses.py:170-194`、`tests/test_payout_finality_monitor.py:259-292`、`tests/test_sealed_holdout.py:443-515`、`tests/test_build_daily_results.py:398,421-436`、`tests/test_analyze_misses_exclusion.py:149-166`、scratchpad `mut.py` / `mutA.json.out.json` / `mutB.json.out.json` / `sim.py` / `real/out_*`

**次アクション (HOLD 解除条件、いずれも小さい)**: (1) M25: `test_manifest_counts_split_evaluable_from_issued` を 2 理由以上の fixture にして `evaluation_exclusion_reasons` の各値を個別に assert。(2) M54: 保留 3 状態 (result / payout / not_final) の fixture で `actual_execution_date in ("", "None")` を assert。(3) G1 / G2: 監視の漏洩テストを **値**にも掛ける (`pending_race_ids` がレース ID 形式に一致、top-level キー集合を完全一致で固定) + `main()` の text 出力にも同じ検査。(4) 滞留監視の窓: pending 検出を `--days` に依存させない (最古の未確定を窓に関係なく報告) — 実 DB で 10/10 時点 `--days 14` = OK/0、`--days 30` = ERROR/72 を確認済。(5) 返還された ◎ が `analyze_misses` で不的中に数えられる (実測 hit=0 / pick_finish=0): `horse_refunded` の pick を `skipped["refunded_pick"]` で除外。(1)〜(3) が閉じれば PASS。(4)(5) は次回の HOLD 条件に格上げする。

## 総合: 3.9 / 5 (参考スコア、前回 3.4 → +0.5)

## 項目別

- **バックテスト設計の正しさ (状態モデル / N / 金額の分離): 4.5/5** — 段階 `中止 → 着順確定 → 払戻最終確定 → evaluable` が `db.exclusion_reason` 1 箇所に集約され、production `main()` を実データで再実行: **9/21** = 320 行 → `cancelled 161 / payout_not_yet_final 159 / evaluable 0`、**9/22** = 161 行 → `payout_not_yet_final 161 / evaluable 0` (速報払戻では evaluable にならない: **成立**)。返還は馬単位で分離 (9/21 実データに返還馬 1 頭、profit 0 / settled 0)。同着は `tan_horse_num2` まで (実 DB 67 件、3 頭同着 `tan_horse_num3` は 0 件で未対応 = P3)。減点: 返還された ◎ は evaluable=True かつ confirmed_order=0 の行になり、`analyze_misses` が不的中に数える (模擬で確認)。金銭は正しいが N が水増しされる。
- **時系列リーク防止 / 境界: 4/5** — N1 (部分結果) は「着順が付くはずの馬が全員そろう」定義で閉じ、変異 N1 (1 頭でも着順) は撃墜、実データ模擬 (R01 の 1 頭を 0 着に) で 14 行が `result_not_yet_available` に落ちた。中止に着順 + 確定払戻を注入しても 161 行 `cancelled` のまま (永久除外: **成立**)。減点: M54 生存 (保留行の実施日)。境界の穴: 失格 (abnormal 5) は `expects_a_finishing_order` = True だが confirmed_order=0 (2024 年に 1 頭) → そのレースは永久に `result_not_yet_available`、かつ滞留監視は結果待ちを見ないので **黙る**。
- **calibration / 監視の継続: 3.5/5** — `payout_finality_monitor` は実 DB で `ERROR / pending 72 / 最古 20260919 / 72.5h` を出し、9/21 は中止 12 を滞留に数えない (**成立**)。翌日 WARN / 48h 超 ERROR、到着で自動解消もテスト固定。減点 3 つ: (a) 既定窓 14 日を過ぎると滞留日が窓から消えて **OK に戻る** (実 DB: 10/10 時点 `--days 14` → OK/0、`--days 30` → ERROR/72)。監視の存在理由 (黙って落ちない) と正反対の挙動。(b) 結果待ち (`result_not_yet_available`) の滞留は監視対象外 (テストが明示的に OK を要求) → 失格・欠損行で黙る。(c) 深刻度境界 (24.0h / 48.0h ちょうど) は parametrize に無く G6 生存 (無害)。
- **A/B / 再現性 / 変異主張の裏取り: 3.5/5** — suite 実測 (worktree、`.venv64`): **753 passed / 11 skipped / 1 deselected** (主張と一致)。独立 32 変異: **撃墜 26 / 生存 6**。宣言済み 12: **10 撃墜 / M25・M54 生存** — サマリの「すべて死亡」は誤り。新規 14 (X 系: 速報を確定扱い / 払戻確定条件の除去 / 返還ゲート除去 / 競走中止を返還扱い / 同着 1 頭目のみ / 引数落ち等) は **全滅**。監視 G 系 6: G4 (結果待ちを滞留) / G5 (中止を滞留) 撃墜、G1 (pending_race_ids に 1 着馬番を埋め込む) / G2 (`first_place_by_race` キー追加) **生存** = GATE_EXEMPT の固定はキー名の部分一致とキー集合だけで、値・text 出力・blacklist 外の語 (place / first / finish / rank) を通す。`payout_final: bool = True` の既定値は fail-open (呼び出し側が落とすと速報が確定扱い) — X15a/b は挙動テストで撃墜されたが keyword-only 必須にすべき。
- **過適合監視 / 統合判定 / 監査プロセス: 4/5** — 採用戦略変更なしで weekly_monitor は非該当。対象 SHA 固定・作業停止は守られた。監視と評価ロジックの独立: monitor は `db` の語彙 (`FINAL_PAYOUT_DATA_DIV` / `expects_a_finishing_order` / `is_evaluable_race`) と `config.DB_PATH` のみ import、`exclusion_reason` / `build_daily_results` は import せず導出を自前 SQL で持つ (**結合なし**)。語彙を共有するのは「確定」「中止」の定義が二重化しないための正しい共有。ただし導出は二重化しており、監視の `payout_final` は `tan_payout1 > 0` を要求しない (評価側は要求) → 乖離クラス。実 DB では乖離 0 (確定払戻で tan_payout1 なし 0 件 / 確定レースで payouts 無し 0 件)。

## 変異テスト (独立設計 32 種、隔離 4867a0e、全 suite `-x`、1 変異ごとに復元)

| ID | 変異 | 結果 | 撃墜した test |
|---|---|---|---|
| M4 | backtest `({evaluable} OR 1=1)` | 撃墜 | backtest_list_races_excludes_cancelled_when_run |
| M5 | backtest 述語行削除 | 撃墜 | every_races_query_applies_the_predicate |
| M6 | generator races 側 `OR 1=1` (前回まで 3 回生存) | 撃墜 | the_generator_race_query_excludes_cancelled_when_run |
| M6b | generator horse_rows `{cancelled} AND 1=0` | 撃墜 | the_generator_prediction_query_excludes_cancelled |
| M16b | prediction_accuracy NOT EXISTS 無効化 (前回まで 2 回生存) | 撃墜 | the_accuracy_query_excludes_cancelled_when_run |
| M17b | monitor NOT EXISTS 無効化 (前回まで 2 回生存) | 撃墜 | the_monitor_query_excludes_cancelled_when_run |
| M23 | db 分岐順序入替 | 撃墜 | a_cancelled_race_books_no_loss_through_main |
| **M25** | bdr manifest 理由内訳を excluded 総数で潰す | **生存 (3 回連続)** | — |
| M30 | am `if False and reason` | 撃墜 | each_exclusion_reason_is_counted_separately |
| M32 | am 理由をまとめて数える | 撃墜 | 同上 |
| **M54** | bdr `actual_execution_date` を保留行にも記入 | **生存 (2 回連続)** | — |
| N1 | bdr 「1 頭でも着順」に戻す | 撃墜 | a_provisional_result_is_not_final |
| X1 | db `payout_final` 判定削除 | 撃墜 | a_provisional_payout_is_not_evaluable |
| X2 | bdr `payout_final = payout_resolved` | 撃墜 | 同上 |
| X3 | bdr 確定判定を `data_div is not None` | 撃墜 | 同上 |
| X4 | db `is_final_payout` が '1' も確定 | 撃墜 | 同上 |
| X5 / X6 | bdr profit / settled から返還ゲート除去 | 撃墜 | a_refunded_horse_is_not_a_loss |
| X7 | db 返還集合に 4 (競走中止) 追加 | 撃墜 | a_race_abandonment_is_not_a_refund |
| X8 | db 非完走集合から 4 を除去 | 撃墜 | 同上 |
| X9 | bdr 返還馬も「着順が付くはず」に数える | 撃墜 | a_refunded_horse_is_not_a_loss |
| X10 | bdr 同着 1 頭目のみ | 撃墜 | a_dead_heat_winner_is_paid |
| X11 | bdr `horse_refunded = False` | 撃墜 | a_refunded_horse_is_not_a_loss |
| X14 | bdr `payout_final` 列に `payout_resolved` を書く | 撃墜 | a_provisional_payout_is_not_evaluable |
| X15a / X15b | bdr が `exclusion_reason` / `is_evaluable` に `payout_final` を渡さない (既定 True) | 撃墜 | 同上 |
| **G1** | monitor `pending_race_ids` に 1 着馬番を埋め込む | **生存** | — (キー名しか見ない) |
| **G2** | monitor top-level に `first_place_by_race` を追加 | **生存** | — (blacklist 外の語) |
| G4 | monitor 結果待ちを滞留に数える | 撃墜 | a_race_without_a_result_is_not_pending |
| G5 | monitor 中止を滞留に数える | 撃墜 | cancelled_races_are_never_pending |
| G6 | monitor 深刻度境界 `<=` → `<` | 生存 (無害) | — |
| G9 | monitor LEFT JOIN 空行スキップ削除 | 生存 (無害: 出走馬 0 のレースのみ) | — |

## 指示された 7 項目の検証 (実 9/21・9/22 データ、production `main()`)

1. **速報払戻では evaluable にならない** → **成立**。9/22 の 161 行が `payout_not_yet_final` / evaluable=False / profit 0 (payouts.data_div='1' 12 レース)。
2. **final 払戻到着後だけ evaluable へ遷移** → **成立**。同 scratch DB で `data_div='2'` に更新 → 同じ 161 行が evaluable=True / 理由空。
3. **payout 欠落を -100 にしない** → **成立**。payouts 全削除 → 161 行 `payout_not_yet_available` / profit 0 / settled 0。
4. **cancelled は永久除外** → **成立**。9/21 中山 12 レースに全馬着順 + 確定払戻 350 円を注入 → 161 行 `cancelled` / evaluable=False のまま (result/payout/final=True と記録されつつ除外)。
5. **払戻滞留が翌日以降に検出される** → **成立**。実 DB 9/23 00:30 時点 ERROR (72.5h、72 レース)。単体で 30h WARN / 49h ERROR。ただし 14 日超で自動消滅 (次アクション (4))。
6. **滞留 monitor が cancelled を誤検出しない** → **成立**。実 DB 9/21: `cancelled 12 / executed 12 / pending 12` (24 ではない)。G5 撃墜。
7. **宣言済み M 系 12 種の死亡** → **10/12**。M6 / M16b / M17b (前回 FAIL 条件候補) は実行型テストで撃墜。**M25 / M54 は生存**。

## GATE_EXEMPT の固定は十分か

不十分。`test_the_report_never_leaks_race_outcomes` は (i) dict キー名の部分一致 blacklist (order / payout_yen / odds / horse / win / profit / hit / return) と (ii) `days[0]` のキー集合完全一致のみ。**値は一切見ない** (G1: `pending_race_ids` に 1 着馬番を埋め込んでも通る)、**top-level はキー集合を固定していない** (G2: `first_place_by_race` が通る)、`main()` の text 出力は無検査 (`mon.main` を呼ぶテスト無し)。免除の根拠「件数しか出さない」を担保するには、値の形式 (レース ID 正規表現・整数のみ) と top-level キー集合の完全一致、text 出力に対する同じ検査が要る。封印ガード側 (`test_no_new_script_reads_results_without_the_gate`) はファイル名で免除しており、免除ファイルが将来 `exclusion_reason` や集計を import しても検知しない → 免除スクリプトの import 集合を固定するテストを推奨。

## 停止条件チェック

- [x] git_sha / rule_version / env_overrides — N/A (backtest JSON 生成なし)。対象 SHA `4867a0e` 開始・終了で一致
- [x] baseline paired 比較 / market_snapshot / payout 欠損 — N/A (type-B/C)
- [ ] 専門領域: 証拠を生む仕組み — **部分抵触** (宣言済み M25 / M54 生存、GATE_EXEMPT 固定がキー名のみ、滞留監視が 14 日で黙る)。金銭経路は 14 変異全滅 + 実データ 5 シナリオ成立で FAIL ではない
- [x] 他 agent との不整合 — final 判定は未提出、type-B のため統合 N/A

## 前回からの差分 / 宣言の執行

- 前回 (20260922_0600、7f5d8de): **3.4 / HOLD** → 今回 **3.9 / HOLD** (+0.5)。項目別: 設計 4→4.5、リーク 3→4、監視 3→3.5、再現性 4→3.5 (主張と実測の乖離で -0.5)、統合 3→4。-0.3 以上の低下なし
- 前回宣言「M16b または M17b が素通りなら FAIL」→ 両方撃墜、**非該当**
- 前回宣言「M6 / M25 / M54 のいずれかが素通りなら HOLD 上限」→ M6 撃墜、**M25 / M54 生存、執行 → HOLD**
- 前回宣言「N1 が残っていれば HOLD 上限」→ 部分結果としての N1 は撃墜・実データで解消。同じ行の形が **返還 ◎** 経由で残る (新規 P2、次アクション (5))
- 前回の次アクション: (1) real_query_text を実行型に → **執行済** (M16b / M17b 撃墜)。(2) generator races 側 → **執行済** (M6 撃墜)。(3) N1 → **執行済**。(4) M25 fixture → **未執行** (am 側にのみ追加、bdr manifest 側なし)。(5) 滞留監視 (N2) → **執行済**、ただし窓依存
- **今回の新宣言**: 次回この系列で **M25 または M54 が素通りなら FAIL** (3 回目 / 4 回目の持ち越しは許容しない)。G1 / G2 (値・top-level キー) のいずれかが素通り、または `--days 14` で 15 日以上前の滞留が OK になる挙動が残っていれば HOLD 上限。返還 ◎ が `analyze_misses` で不的中に数えられる状態が残っていれば HOLD 上限。上記がすべて閉じれば PASS
