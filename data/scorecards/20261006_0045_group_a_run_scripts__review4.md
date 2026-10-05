# 2026-10-06 00:45 — Group A の実行の script (freeze / power / primary) と配列版の推定 (4 名レビュー)

- 対象: worktree `group-a-class`、c9688b5..46d474a。**subagent CWD 限定運用での評価**。2025 は誰も読んでいない
  (prediction-logic は 2021-2024 で freeze を worktree の外に試走、BOOT_N 200)
- ai_builder_impact: none

| 担当 | 判定 | 総合 | must-fix |
|---|---|---|---|
| validation-process-auditor | CONDITIONAL | 4.2 | M1「1 回だけ」の錠が `--out` 単位 / M2 主検定の前提の sha を照合しない (git_dirty・依存ファイル) / M3 2 段の書き出し |
| prediction-logic-analyst | CONDITIONAL | 4.0 | 結果を副次記録の後に 1 回だけ書く構造 (副次記録で落ちると β・区間が未記録のまま再実行になる) |
| data-pipeline-engineer | CONDITIONAL | 4.0 | `_target_ages` で年齢の欠損が 0 になる |
| code-quality-reviewer | CONDITIONAL | 4.1 | M1 錠が完走に依存 (結果は末尾でしか書かれない、`--out` 単位) / M2 本番の経路の `assert` |

平均 4.08。

## 確かめられたこと

- prediction-logic: `clogit_packed` は `conditional_logit` と数学的に同じ (標準化・勾配・ヘッセ・上限・収束、詰め物の行の扱い、再抽出の
  重複レースの扱い)。凍結物に S の再現に要る物が揃う。2021-2024 の試走 (BOOT_N 200): 学習 9,974 レース、β_S 0.043 (ヘッセ SE 0.022、
  boot SE 0.023)、合成の重み best3 0.055 / trend 0.018 / rank 0.015 / last 0、leave-one-year-out の符号 −, +, −、ρ 0.54。
  **見通し**: SE の換算 ≈ 0.023 × √(9,974 / 約 3,330) ≈ 0.039 → MDE ≈ 0.134 > β_target 0.112 (検出力の段で判定不能がほぼ確定する見込み)
- data-pipeline: power.json に 2025 の結果に依存する数は無い。全工程の見積もり 10 分未満 (ルール 1-ter の対象外)。接続はすべて mode=ro
- code-quality: **S4 (勝ち馬のいないレースを SD に入れる) は等価でない** と反例で示した (seed 1・15 レース・b 6.0 で原本は収束、S4 は不収束)。
  私の「アフィン不変」の主張は、許容誤差と 1 歩の上限が標準化の単位なので成り立たない。既存のテスト (seed 0) は両方 NaN で空振りだった

## should-fix (要旨)

- validation: 2025 のブートストラップの SE を診断として / N_power − N_primary を結果に / 同着と勝ち馬なしの分割 / 残差化の欠損件数と complete-case 版 /
  主検定の後の `config.CONSUMED_WINDOWS` と台帳への記録の段取り
- prediction-logic: 2021-2024 の履歴の一致の照合 / leave-one-year-out の fold の失敗を記録に落とす / 人気の定義 (同値は平均) の明記 /
  残差化は pooled であることの明記
- data-pipeline: NaN を null に / primary で凍結の MANIFEST の sha も照合 / 錠を凍結物の側に
- code-quality: `_within_corr` と `within_race_corr`・`_rel` と `_rel_to_root` の重複 / dead code `year_rows` / マジックナンバー /
  `pack` の副作用 (Packed と行の対応が暗黙)
