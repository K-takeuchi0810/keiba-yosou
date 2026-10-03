# Phase 0.5-5 事前登録の更新 — 限定再レビュー (d13c2e2、2026-10-04)

- 対象: SHA **d13c2e2** (前回 ce98a73 → HOLD 2 / 条件付き PASS 2)。外部の指示者の決定 (B / 旧 C / E の状態の細分化、C′ の登録、backfill を Group A の主検定より前に、Group A のペース補正の削除) と前回の must-fix を反映
- 担当: 4 名、範囲を限定 (validation: 探索と主検定・99% 区間・1 回・検出力 / data-pipeline: probe・backfill・PIT・被覆率 / prediction-logic: A と C′ の仕様・リーク / profitability: 返還・選択集合・金額)
- 運用: subagent CWD 限定運用。本番 DB は mode=ro (+ query_only) の集計のみ。レビュー中 worktree 不変

| 担当 | 判定 | 点 | 前回 |
|---|---|---|---|
| profitability-judge | PASS | 4.2 | 3.8 |
| validation-process-auditor | PASS (条件付き: N1〜N3) | 4.1 | 3.7 HOLD |
| prediction-logic-analyst | PASS (条件付き: MF-1〜5) | 4.0 | 3.8 |
| data-pipeline-engineer | PASS (条件付き: MF-A〜D) | 3.8 | 3.0 HOLD |

前回の must-fix は 4 名とも解消を確認 (一次テキストとコード・DB で照合)。

## 条件の must-fix (いずれも docs の追記。次のコミットで反映)

- validation N1: 価格の無い非返還馬がいるレースの扱いを一意に → レースを尤度から除き件数を記録
- validation N2: 主検定の「判定不能」の基準 → β_target と、最小検出差 > β_target なら PRIMARY_INCONCLUSIVE の規則
- validation N3 / prediction-logic MF-1: C′ の成分の期待符号と、レース内で一定の成分は条件付きロジットで識別できない → 馬ごとの成分 (style_x_pace_fit / front_competition_signed) だけを S に、レースの値は材料、style_rarity は副次
- prediction-logic MF-2: 脚質の「直近 5 走」の数え方 (平地・脚質コード 1〜4 だけ、障害と競走中止は数えない、既存の estimate_leg_code は同数の扱いが違うので流用しない)
- prediction-logic MF-3: 欠損の埋め方と標準化の順序 (平均・SD は欠損でない学習行、埋めるのは標準化の後、既知 0 頭のレース)
- prediction-logic MF-4: A の細部 (rank_in_race の分母と分位の式、trend の横軸、last の競走中止)
- prediction-logic MF-5 / data-pipeline MF-C: 当日馬場差の PIT (同じ競馬場・同じ馬場、発走時刻が対象の 15 分前以前。flush は流用しない)
- data-pipeline MF-A: 「parser の hard gate」は過大な表現 (コメントと docstring の規約で、コードでは強制されていない)
- data-pipeline MF-B: backfill の機構 (範囲を RACE の SE ファイルに限定、事前の 0 化、corner 以外の差分 0 の assert、受理の閾値、範囲は 2021-01〜2026-06 の全月、ai_builder_impact は tested)
- data-pipeline MF-D: 返還の除外をどこで行うか (eval 側。build_dataset と既存テストは変えない)

## nice-to-have (主なもの、反映したもの)

- T−10 で返還の対象を除いた後の市場の確率の再正規化 (profitability)
- 2025 の確定オッズでの回収率は買えない価格での値 → 金額の区分は T−10 の窓にだけ (profitability / validation)
- 同着のレースの扱い、再実行の規則、捨てた再抽出の上限 1% (validation)
- dry run では補正テーブルも 2022-2023 で推定し直す、学習期の重みは楽観側 (prediction-logic)
- 前走の人気で残差化した副次の記録、365 日以内の出走数・年齢と S の相関 (prediction-logic)
- 障害は過去走からも除く (prediction-logic)
- block_boot の分位の引数を検出力の固定より前に (validation)
- seed 感度の診断も CONSUMED_WINDOWS に (validation)
- 対照 1 の賭け金にも返還の規則 (profitability)
