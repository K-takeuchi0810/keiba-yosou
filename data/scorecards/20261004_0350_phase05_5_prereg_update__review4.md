# Phase 0.5-5 事前登録の更新 (§8) — 4 名レビュー (2026-10-04)

- 対象: branch `phase05-5-prereg-update-20261004`、SHA **ce98a73** (base main 3f5e868)。docs のみ (PHASE05_5_PREREG.md §8 新設、PHASE05_RESULTS.md 1 段落)
- 担当: validation / prediction-logic / data-pipeline / profitability
- 運用: subagent CWD 限定運用。本番 DB は mode=ro (+ query_only) の軽いクエリのみ。レビュー中 worktree 不変

| 担当 | 判定 | 点 |
|---|---|---|
| validation-process-auditor | HOLD (M1-M5 を直せば PASS) | 3.7 |
| prediction-logic-analyst | PASS (条件付き: M1-M4 を Group A の仕様固定より前に) | 3.8 |
| profitability-judge | PASS (M1-M2 を Group A 実装前に) | 3.8 |
| data-pipeline-engineer | HOLD (MF-1〜3 を直せば PASS 見込み) | 3.0 |

## must-fix (担当横断で統合)

1. **§8-3 の通過順位の事実と原因の誤り (4 名中 3 名)**。数値 (2021-2025 0.0%、2026 32.6%) は正しいが:
   - 2026 は 1〜6 月 0%、**7 月以降 ~99%** (「5 月以降」は誤り)。parser の offset 修正 2aa1263 (2026-07-05) 以降の取込分だけ
   - 欠落の原因は元データではない。**raw `data/raw/RACE/SEVM2021..2025*.jvd` に 97.5% 入っていて現行 parser で読める** (data-pipeline が 2 ファイルで確認、脚質コードと整合)。列は 2026-07-04 の migration で後付けされ backfill されていない。さらに `config.CORNER_BYTES_VERIFIED = False` (バイト位置は未検証の暫定、parser の hard gate)
   - `leg_quality_code` (脚質) は 2021-2025 で 100% (C / E の脚質の元データとして存在する)
   - `races.lap_times` は 2021-2025 で 0% (Group B の前半ペースは通過順位と独立に塞がっている)
   - 「蓄積を待つ」は誤った選択肢 (待っても 2022-2024 は埋まらない)。解除の道は「probe 緑化 → raw からの再取込 (backfill)」
2. **§8-6 の尤度の選択集合が主検定の市場と両立しない (profitability / data-pipeline)**: 2022-2025 の異常コード 3 は全頭 win_odds=0 (2 は 4 年とも 0 頭)。確定市場の主検定では 2/3 は価格が無いので選択集合に残せない。期間 (市場) ごとに集合を定義し直す。感度分析は T−10 側だけで意味を持つ
3. **§8-6 の既存の欠陥の記述が経路の半分だけ (profitability / validation / data-pipeline)**: 2/3 を「払戻 0 の外れ」に数える経路に加え、価格の無い 2/3 がいるレースは `runner_set_mismatch` で**レースごと黙って落ちる** (発走後の情報による選択)。修正は「落とす」でなく「返還」に。4 (競走中止、2025 で 218 頭) / 5 / 7 は返還しない = 損失、を表に。出典は `db.REFUNDED_ABNORMAL_CODES`
4. **主検定の区間の水準・方式・n_boot・seed が未固定 (validation / prediction-logic)**: §4-2 の「95% 区間の下限が Bonferroni 補正後も 0 超」は内部矛盾 (95% は α=0.05)。`block_boot` は 2.5/97.5 分位しか返さず、N_BOOT_PRIMARY=300 では 99% 端点が成立しない。「99% パーセンタイル区間、n_boot ≥ 2000 (推奨 5000)、seed の値」を今書く
5. **§6 と §8-4 の優先関係、§4-1 の市場の注記 (validation)**: 複数回の試行が許されるのは学習期の探索だけ。§4-1 の `logit(P_T10)` の式は移植確認用
6. **Group A の時間の代理の再発の穴 (prediction-logic)**: `perf_rating_best3` / `trend` のような生涯 best 型は左打ち切りで年とともに変わる。有界の遡及窓 (直近 365 日 or 直近 k 走) で定義し、生涯 best / 平均を作らない
7. **Group A のペース補正項 (validation)**: 2021-2025 に通過順位もラップも無い。(a) 項を落とす / (b) 時計だけの代理を学習期で決めて記録、のどちらかを宣言
8. **PIT の具体化 (prediction-logic)**: 補正テーブル (距離・競馬場・クラス・斤量) は 2022-2024 だけで推定して凍結 / 当日の馬場差は発走時刻のブロック順に T−10 までに確定したレースだけ (build_dataset の flush と同じ構造、テストで固定) / `finish_time` は MSSt 形式 (分×600 + 秒×10 + 1/10 秒に復号。`predictor/features.py:228` の生の減算は分境界で誤る潜在バグ) / 競走中止の finish_time=0 は NaN
9. **凍結物の列挙と 2025 の対象集合 (validation)**: S_A の合成重み・標準化の平均/SD (2022-2024)・補正テーブル。2025 の集合 (JRA 01-10 / data_div≠9 / 勝ち馬あり / 1 を除く / 全頭 win_odds>0) と、落ちる件数の事前の記録

## 決定が要る事項 (結果を見る前に固定しないと forking path になる)

- B / C / E の扱い: 状態の名前 (BLOCKED_BY_INGEST_STATE 等) と解除の手順 (probe 緑化 → 2021-2025 + 2026-05/06 の再取込)。再取込は本番 DB への書き込み (CLAUDE.md ルール 5、ai_builder_impact、開催日を避ける)
- 脚質コード (`leg_quality_code`) で作る C′ / E′ を登録するか。登録するなら C の枠を使う (5 群のまま) か 6 群目 (0.05/6) か
- 通過順位の backfill を Group A の結果を見る前にやるか後か
- Group A のペース補正項 (落とす / 時計の代理)

## nice-to-have (主なもの)

- 主検定が MDE 付近で通った場合、金額試験は構造的に判定不能 (比 ≥1.25 は 2025 で約 10〜360 頭) を先に予想として書き、結果の記録区分を 4 つに固定 (PRIMARY_FAIL / PRIMARY_PASS × MONEY_UNTESTABLE / × MONEY_UNDERPOWERED / × MONEY_PASS) (profitability)
- 現行の金額試験は絶対 5pt (BUY_EDGE_PT) のままで §4-5 の比 ≥1.25 が未実装 → 返還の修正と同じ段で実装 (profitability)
- 検出力: β_market と同時推定なので実効情報は Schur 補元。2025 の実測 1 − Σp² は 0.795。S_A を全体で標準化すると between-race 成分で v は 0.4 を割りうる → 見込みは上限寄り (validation)。exp(2β) は正規化前のオッズ比で β≈0.28 は楽観側 (profitability)
- S_A の合成: 期待符号を事前に書き、学習期で逆符号の成分は重み 0 / 重みの安定性を bootstrap で / 2022-2023 → 2024 で符号確認 / 等重み z 平均の代替 (prediction-logic)。2022-2023 → 2024 の dry run を探索の中に (validation)
- 副次: S_A を着順で残差化した版 (「負けたが内容は良かった」の直接の検定) (prediction-logic)
- 2025 は「LGBM 系の早期停止・選択に対して OOS でない」と限定して書く (prediction-logic)
- final_3f は障害レースでは 3F タイムでない (129-152) → 障害を除外 (data-pipeline)
- 探索台帳のファイル名、leave-one-year-out の符号、Group A の購入率の見込みと封印窓の判定日を先に (validation / profitability)
- 特払いは馬番 00 が捨てられて全頭外れになる → 修正のテストで件数 0 を assert (profitability)
