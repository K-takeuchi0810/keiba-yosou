# Group D 凍結前レビュー (4 名) — 2026-10-06

- 対象: branch `group-d-pit-20261006`、§8-4d (`31a7dfc`) → 探索台帳 (`b189ffa`) → 実装・変異 36/36 (`3278479`〜`f546da9`) → E1 (`87d9c88`) → E2 (`b7bbbc4`)
- 実施時刻: E2 の記録の直後 (このファイルは停止の後、族の総括の時点で事後に書いた。点数と要旨は当時の報告から転記)

| 専門家 | 点 | 要旨 |
|---|---|---|
| data-pipeline-engineer | 4.5 PASS | 件数を本番 DB (mode=ro) で独立に再現。全馬欠損で除いた年 301〜302 レース = 新馬戦の数と一致 |
| validation-process-auditor | 4.3 | E2 を独立に再計算してビット一致。構造の事実 (S_std ↔ 前走の評価値 レース内相関 0.94、R² 0.93) を実測。解釈の制約を凍結前に台帳へ固定することを must-fix |
| code-quality-reviewer | 4.0 | 主検定の副次の記録が探索スクリプトを import して来歴から漏れる / テスト冒頭 docstring の過大な主張 (小さな must-fix) |
| prediction-logic-analyst | 3.8 | 前走の評価値は Group A の last 成分と同じ関数、A とのレース内情報の重なり約 93%。§2 D の仮説は交互作用にしか現れない |

**平均 4.15**。

## その後の扱い

- 4 名とも「E1/E2 を見た後に仕様を変えるのは forking path」で一致。外部の指示者の判断で、仕様は変えず **主検定を実行しない** (`BLOCKED_BY_IDENTIFIABILITY` / `PRIMARY_NOT_RUN`、`3b3c209`)。2025 は未閲覧
- code-quality の must-fix は停止の記録の前に反映 (gap_equivalence を `scripts/group_d.py` へ移動等、`3b3c209`)
- 当初の「交互作用は MDE ≈ 0.3 で検定不能」は 0/1 の取り方だけの値で撤回 (S × class_move では ≈ 0.107)。`docs/PHASE05_5_GROUP_D_RESULT.md` §2
