# A″ の変異テストの記録 (2026-10-06)

- spec: `tests/mutation_specs/group_a2_spec.py` (24 個: group_a2.py 15 / group_a2_explore.py 9)
- 実行: `git archive <sha>` の隔離コピー (scratchpad、`.git` 無し) + `.venv64` のジャンクション (実行後に外した)
- 最初の実行 (`c9002d6`) は変異の名前の「σ₁」が cp932 で表示できず出力で止まった (結果なし) → 名前を直して (`6966063`)
- run1 (`6966063`): KILLED 23 / SURVIVED 1 (X6 レース内の分散の門の境界 — 0.50 ちょうどのテストが無かった)
- テストを足して (`3aa1391`) run2: **KILLED 24 / 24**
