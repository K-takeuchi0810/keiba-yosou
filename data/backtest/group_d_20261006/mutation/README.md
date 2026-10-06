# Group D の変異テストの記録 (2026-10-06)

- spec: `tests/mutation_specs/group_d_spec.py` (36 個: group_d.py 14 / group_d_run.py 14 / prereg_runner.py 8)
- 実行: `git archive <sha>` の隔離コピー (scratchpad、`.git` 無し) + `.venv64` のジャンクション (実行後に外した)
- run1 (`3278479`): D1〜R6 のうち KILLED 17 / SURVIVED 3 (D5 要求水準を平均に — 例の値で平均と中央値が同じ / D12 class_move の欠損を 0 で — 例の平均が 0 /
  R5 主検定の結果の上書き — テストなし)、R7 で ABORTED (本番の `keiba.db-wal` の更新)
- テストを直して (`54080fb`)、R7 以降と生存した 3 個だけの一時の spec (`partial_specs/_rest_gd_r1b.py`) で run1b: KILLED 18 / SURVIVED 1
  (P3 SE の小さい方 — テストの 2 つの SE が同じ値だった)
- テストを直して (`8dc209f`)、P3 だけの spec で run1c: **KILLED** → **36 / 36**
- 一時の spec の変異の 4 タプルは、コミット済みの spec の同名のエントリを `runpy` で読んで抜き出したもの
