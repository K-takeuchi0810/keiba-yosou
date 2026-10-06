# 収益性 / 投資判断専門家 採点 — 中止レース final2: 最終ゲート HOLD 是正 (内訳 / 実施日 / 監視窓 / 返還◎ / 失格 / fail-open) — SHA `3cd1871`

## 判定: PASS

**subagent CWD 限定運用での評価 (worktree 絶対パス指定)**。対象 `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\data-div-cancelled`、
`git -C` 形式のみ。開始・終了時に `rev-parse HEAD` = `3cd18716f5852850dac55d4731e2bde845ea7126`、`status --short` = 0 行を確認。
変異・状態注入はすべて `git archive 3cd1871` の隔離木 (`scratchpad/gate2_profit/iso`、変異ごとに `git checkout -- .` + porcelain 空を assert) と
scratch DB (`scratch.db` = 実 DB を `mode=ro` で ATTACH し 9/19-9/22 の races / horse_races / payouts を複製) で行った。実 DB は SELECT のみ。
HTML は本番 `data/results/2026-09-21|22/predictions_source_*_110117|110124_*.html` を読むだけ (bet-tag 注入は scratch コピー `inj_*.html`)。
封印データ (2026-10-01 以降) は見ていない。

**改修タイプ**: type-B (答え合わせ CSV の状態モデル / 監視ツール) + type-C (`db.py` 判定関数)。`config.BUY_FILTER_DEFAULT` (suspended=True) /
calibrator / weights / Kelly は不変 (`git -C <wt> diff --stat 50fc046...3cd1871` に config.py / predictor/ 無し)。
P25 固有ゲート (2026 holdout ROI 180% / `buy_only_return_rate_ci95` / bonus_candidate / paired baseline) は **N/A (対象外)**。

**理由**: 前回最終ゲート (validation-process-auditor 3.9 / HOLD) の解除条件のうち金銭経路と N に関わるもの — 返還 ◎ の miss 混入、
失格による永久結果待ち、`payout_final` の fail-open 既定、manifest 内訳 (M25)、保留行の実施日 (M54)、監視の 14 日窓 — を
**独立変異 19 種 (18 撃墜 / 1 生存) と実 9/21・9/22 データ (再導出 481 行 一致 / 不変量違反 0) の両方**で閉じていることを確認した。
生存 1 件 (Q10 = 前回 M3、`tan_payout1>0` ガード無検査) は実 DB 該当 0 行で、production では状態注入 (d) で機能を確認済 (fixture 欠落のみ)。
停止条件に抵触するものは無い。買い候補は両日 0 件 (suspended) で収益主張は無く、段階は **観察用** のまま。

**根拠ファイル**: `db.py:128-198`、`scripts/build_daily_results.py:681-731,753-818,863-876,904-918`、`scripts/analyze_misses.py:177-195`、
`scripts/payout_finality_monitor.py:82-83,179-202,241-250`、`tests/test_build_daily_results.py:36-167,395-780`、
`tests/test_analyze_misses_exclusion.py:62-201`、`tests/test_cancelled_races.py:604-670,815-857`、
scratch `gate2_profit/real/0921|0922/`、`gate2_profit/scn/*`、`gate2_profit/mut.py` / `mut_result.json`

**次アクション (マージ阻害ではない)**: (1) Q10/M3: `_run_main` に「payouts 行あり・`tan_payout1=0`」の fixture を足し
`payout_resolved=="False"` / `settled=="0"` を assert (3 回目の持ち越し、次回は HOLD 条件に格上げ)。
(2) `would_be_candidate` を `write_csv` の列に出す (計算だけして捨てている `:620,:792` vs `:863-876`。suspended 期間の反実仮想 N が CSV から復元不能)。
(3) 回収率 helper を 1 箇所に置き `sum(profit)/sum(settled)` を signature で固定 (planned を受けない)。実データで planned 分母だと 28.7% / settled 分母だと 57.5% と 2 倍ずれる (下表 g)。

## 総合: 4.2 / 5 (参考スコア。前回 4.2、項目別は 回収率 4→4.5 / 開示 4→4.5 で上振れ、他 3 項目不変)

## 実測 (このセッション、すべて自分で実行)

| 項目 | 実測値 |
|---|---|
| pytest 4 ファイル (worktree / 隔離木) | **120 passed / 120 passed** (隔離木は `git init` 後。非 git だと `git_provenance()` で 23 件落ちる = 環境要因) |
| pytest 全 suite (隔離木) | **767 passed / 11 skipped / 1 failed**。失敗は `test_f3_phase0_0_eval::test_saved_pair_reproduces_frozen_validation_auc` = worktree に untracked `data/f3_phase0_0/metrics.json` が無いだけ (main `50fc046` で同テスト pass、本シリーズは predictor/ 不変) |
| 実 DB 9/25 21 時台 | payouts 9/19-9/22 は全 72 行 `data_div='2'` (確定)。9/21 中山 12R `races.data_div='9'`。9/21 阪神 4R 7番 abnormal **3** (除外=返還)、6R 15番 abnormal **4** (競走中止、印 ☆) |
| 9/21 production 出力 (実 DB, `--output-dir` scratch) | 320 行 = evaluable **159** / cancelled **161**、reasons `{cancelled: 161}`。◎ 24 のうち evaluable 12 (阪神)、的中 3 (280+270+140=690) |
| 9/22 production 出力 | 161 行 = evaluable 161 / excluded 0。◎ 12、的中 2 (180+140=320)。`prediction_issued` と evaluable は別キーで保持 (同数だが理由は「全確定」で正当) |
| 金額 3 列 + 状態列の独立再導出 (DB から自前 SQL) | **481 行 全一致 / 不変量違反 0** (settled<=planned、非 evaluable なら profit=settled=0、refunded なら profit=settled=0、evaluable と reason 空が同値、exec_date と evaluable が同値) |
| 返還馬 (阪神 4R 7番) の行 | `horse_refunded=True` / evaluable=True / order 0 / profit 0 / settled 0 |
| 競走中止 (阪神 6R 15番) の行 | `horse_refunded=False` / evaluable=True / order 0 (返還にしない: 正) |
| bet_candidate (production HTML) | 両日 **0 件** (suspended=True)。planned=settled=profit 合計 0 |
| manifest | `schema: 3` (前回指摘の版未更新は解消)、`evaluation_exclusion_reasons` が理由別 dict |
| 滞留監視 (実 DB ro, `--days 7`) | status **OK** / pending 0 / `pending_scan_from=20200101`。9/21 は cancelled 12 / executed 12 / payout_final 12 (中止を滞留に数えない) |
| ◎ 的中率 (evaluable 24 戦, 5 的中) | Wilson 95% CI **[9.2%, 40.5%]**。仮に ◎ ベタ買いなら 1,010/2,400 = 42.1% だが **n=24 << 100 で判断不能** (この数字で戦略を語ってはいけない) |

### 状態注入 (scratch DB、production `main()` 経由、HTML は本番そのまま)

| # | 注入 | 期待 | 結果 |
|---|---|---|---|
| a | 9/22 payouts を `data_div='1'` (速報) | 全行 `payout_not_yet_final`、evaluable 0、実施日空 | **161 / 0 / exec_date 0** OK |
| b | 9/22 payouts 削除 | `payout_not_yet_available` | **161** OK |
| c | 9/22 1R 3番の着順を 0 | 1R 14 頭だけ `result_not_yet_available` | **14 / evaluable 147** OK |
| d | 9/22 1R `tan_payout1=0` (行は残す) | `payout_not_yet_available` 14 | **14** OK (ガードは production で機能。fixture が無い = Q10) |
| e | 9/21 中山 12R に全馬着順 + 確定払戻 350 円を注入 | cancelled のまま永久除外 | **cancelled 161 / evaluable 159** OK |
| f | 9/21 阪神に 速報 2R / 払戻なし 1R / 部分着順 1R を混在 | 4 理由が潰れない | `{cancelled:161, payout_not_yet_available:13, payout_not_yet_final:18, result_not_yet_available:10}` OK |

### 金銭経路 (◎ pick-line に `<span class="bet-tag">` を注入した scratch HTML コピー。本番 HTML は不変)

| # | 条件 | planned | settled | return | profit | ROI (settled) | ROI (planned = 誤) |
|---|---|---|---|---|---|---|---|
| g | 9/21 実 DB (中止 12 + 阪神 12) | 2,400 | **1,200** | 690 | -510 | **57.5%** | 28.7% |
| h | 9/22 実 DB | 1,200 | 1,200 | 320 | -880 | 26.7% | 26.7% |
| i | 9/21 + 注入 f (evaluable ◎ 8 戦のみ決済) | 2,400 | **800** | 690 | -110 | 86.2% | 28.7% |
| j2 | 9/21 + 4R ◎ 2番を取消 (abn 1) + 1R ◎ 3番を競走中止 (abn 4) | 2,400 | **1,100** | 690 | -410 | 62.7% | 28.7% |

j2 の行単位: 4R ◎ は `refunded=True / profit 0 / settled 0 / planned 100`、1R ◎ は `refunded=False / profit -100 / settled 100` (返還と中止の取り違え無し)。
`analyze_misses.build()` (scratch results dir) は races **11** / hits 3 / skipped `{excluded_cancelled: 12, excluded_pick_refunded: 1}`、
4R は分析外・1R は `hit=0, pick_abnormal=4` で miss として残る。
g の 中止 12 ◎ は planned 1,200 / settled 0 で分母に入らない (指示の「中山 12R は N / 的中率 / stake / profit / ROI すべて対象外」を満たす)。

## 変異テスト (独立設計 19 種、隔離木 3cd1871、4 テストファイル `-x`、1 変異ごとに復元 + porcelain 空 assert)

| ID | 変異 | 結果 | 撃墜した test |
|---|---|---|---|
| Q1 | profit の返還ゲート除去 (返還馬が -100) | 撃墜 | a_refunded_horse_is_not_a_loss:645 |
| Q2 | settled の返還ゲート除去 (分母だけ混入) | 撃墜 | 同:647 |
| Q3 | settled を `not_cancelled` でゲート (保留を分母に) | 撃墜 | a_race_without_results_is_pending_not_a_loss:566 |
| Q4 | 外れを 0 円に (`else -100` を `else 0` に) | 撃墜 | a_disqualified_pick_is_a_loss:714 |
| Q5 | 返還集合から 2 (発走除外) を落とす | 撃墜 | test_cancelled_races:819 (NOT_A_START 同値) |
| Q6 | 返還集合に 5 (失格) を足す = 負けを隠す | 撃墜 | a_disqualified_pick_is_a_loss:713 |
| Q7 | 非完走集合から 5 を落とす (失格レースが永久に結果待ち) | 撃墜 | 同:710 |
| Q8 | `exclusion_reason` の `payout_final=True` 既定を復活 (fail-open) | 撃墜 | payout_final_has_no_fail_open_default (DID NOT RAISE) |
| Q9 | bdr が `is_evaluable(..., payout_final=True)` 固定 | 撃墜 | manifest_keeps_every_exclusion_reason_apart:525 |
| **Q10** | `races_with_payout` の `tan_payout1>0` ガード除去 (**前回 M3**) | **生存 (3 回目)** | — (行あり・金額 0 の fixture が無い) |
| Q11 | 同着 2 頭目に `tan_payout1` を払う | 撃墜 | a_dead_heat_winner_is_paid:732 |
| Q12 | manifest `evaluation_rows_evaluable = len(eval_rows)` (N 水増し) | 撃墜 | manifest_counts_split_evaluable_from_issued:459 |
| Q13 | 実施日を `result_resolved` で埋める (M54) | 撃墜 | only_an_evaluable_race_gets_an_execution_date:539 |
| Q14 | analyze_misses の返還 ◎ skip を削除 | 撃墜 | only_evaluable_races_reach_the_analysis:134 |
| Q15 | analyze_misses が `confirmed_order==0` の ◎ を全部 skip (競走中止の miss を隠す) | 撃墜 | 同:134 |
| Q16 | `horse_refunded` を pred 側から取る (常に False) | 撃墜 | a_refunded_horse_is_not_a_loss:644 |
| Q17 | `is_final_payout` が 1 も確定扱い | 撃墜 | the_fixture_really_holds_five_states:499 |
| Q18 | 払戻 lookup のキーを lstrip しない (勝馬が -100) | 撃墜 | a_dead_heat_winner_is_paid:732 |
| Q19 | 監視の検出範囲を `--days` 窓に戻す | 撃墜 | 「窓を過ぎた滞留が黙っている」assert |

撃墜率 **18 / 19 = 94.7%**。-100 復活 (Q1, Q4, Q6, Q18)、分母混入 (Q2, Q3, Q12)、返還/中止の取り違え (Q5, Q6, Q7, Q14, Q15, Q16)、
速報確定 (Q8, Q9, Q17) はすべて撃墜。生存は Q10 のみで、実 DB 全年で「payout 行あり・`tan_payout1` 0/空」は 0 行 (前回確認) かつ production では注入 d で機能。

## 項目別

- **回収率 (損益会計の正しさ): 4.5/5** — 実データ 481 行を DB から独立再導出して完全一致。返還 (0 / 分母外)・競走中止 (-100)・失格 (-100)・
  同着 2 頭目・速報払戻 (未決済) がすべて実データまたは注入で期待どおり。ROI 分母は settled で、planned を分母にすると 2 倍ずれることを
  実数で示した (g: 57.5% vs 28.7%)。減点: Q10 の 3 回目生存 (fixture 欠落)、settled 分母の規約が helper で強制されていない (消費者 0 件のため実害 0)。
- **EV 計算の整合性: 4/5** — 不変 (本改修は EV 経路に触れない)。
- **Kelly / 資金管理: 4/5** — 不変 (suspended=True、100 円固定の観察会計)。
- **買い目フィルタの実用性 / 検証集合=表示集合: 4/5** — 不変。`would_be_candidate` は計算後に CSV へ出ない dead field のまま (P2 持ち越し)。
- **不確実性開示 / N の健全性 / 3 段階区別: 4.5/5** — manifest が total / evaluable / excluded / 理由別を値まで分離し `schema: 3`。
  `prediction_issued` と evaluable が別キー。analyze_misses の分母から返還 ◎ を外し中止 ◎ は残す (対照つき)。監視は表示窓と検出範囲を分離し
  実 DB で OK / 中止非計上。減点: 反実仮想 N (would_be) が復元不能、n が小さいことを CSV 側は明示しない (読み手責任のまま)。

## 停止条件チェック

- [x] git_sha / rule_version / env_overrides — N/A (backtest JSON なし)。manifest は builder_git_sha / dirty を記録 (scratch 実行では隔離木の sha が入る、本番では 3cd1871 になる)
- [x] baseline paired 比較 / market_snapshot / bonus_candidate — N/A (type-B/C、収益主張なし)
- [x] payout 欠損 race の扱い — 中止 = cancelled (永久)、着順あり払戻なし = `payout_not_yet_available`、速報 = `payout_not_yet_final`、いずれも金額 0・分母外・実施日空
- [x] 専門領域 (単勝/複勝混同、1 件依存、180% 混同、CI 下限 100% 未満を利益扱い) — 収益主張がなく不抵触。本書の ROI 数値はすべて「注入した仮想ベット」の会計検証であり戦略成績ではない
- [x] 前回 validation-auditor の HOLD 条件のうち本 agent 領域 — 返還 ◎ (Q14 + j2)、失格 (Q6/Q7)、fail-open (Q8)、M25 (Q12 + f)、M54 (Q13)、窓 (Q19) を撃墜。G1/G2 (監視の値・キー固定) は validation-auditor 領域で本書では未検証

## 反証の試み

- 「返還馬を -100 に数えない」: 実データ (阪神 4R 7番) + 注入 j2 + Q1/Q2/Q16 で **成立**
- 「競走中止・失格を返還にしない」: 実データ (阪神 6R 15番) + j2 (1R ◎ -100) + Q5/Q6/Q7/Q15 で **成立**
- 「速報払戻で evaluable にならない・渡し忘れで fail-open しない」: 注入 a + Q8/Q9/Q17 で **成立**
- 「manifest の N 内訳が潰れない・issued と evaluable が別」: 注入 f (4 理由同居) + Q12 で **成立**
- 「ROI 分母に中止・保留・返還が入らない」: g/i/j2 で settled が evaluable かつ非返還のぶんだけ (1,200 / 800 / 1,100) で **成立**
- 「payout 行あり・金額 0 を決済扱いしない」: production は注入 d で正しいが、**テストは Q10 を通す** = 成立するが未固定

## 前回からの差分

- 前回 (7f5d8de、20260922_0600) **4.2 / PASS** から今回 (3cd1871) **4.2 / PASS**。項目別: 回収率 4 から 4.5 / EV 4 / Kelly 4 / フィルタ 4 / 開示 4 から 4.5。-0.3 以上の低下なし
- 前回提案 (1) M3 fixture: **未執行** (Q10 生存)。(2) 決済状態の透明化: `payout_final` 列と `schema: 3` で **実質執行**。(3) 馬単位返還を refunded に: **執行済** (`horse_refunded`、analyze_misses も除外)
- 前回留保「速報払戻を決済扱い」: **解消** (`payout_not_yet_final`)。「schema 版未更新」: **解消**。`would_be_candidate` dead field: **継続**
- 今回の新宣言: 次回この系列で **Q10 が素通りなら HOLD 上限** (4 回目の持ち越しは許容しない)
- 戦略段階: **観察用** で不変。買い候補 0 件・収益主張なし・CI 下限 100% 超の証拠なし = 紙運用・実弾候補のどちらでもない。
  本書に出る ROI (57.5% / 26.7% / 42.1%) は会計経路の検証用の仮想ベットで n=24、**戦略成績として引用してはならない**
