# 研究の窓の関所の変異テストの記録 (2026-10-06)

- 対象: `scripts/research_window.py`、`scripts/group_a.py` / `scripts/c_prime.py` の `load_races` の配線、`config.py` の `RESERVED_FROM` / `FRESH_FROM_NOT_BEFORE`
- spec: `tests/mutation_specs/research_window_spec.py` (26 個)、テスト `tests/test_research_window.py`
- 実行: `git archive 148a9af` の隔離コピー (scratchpad、`.git` 無し) + `.venv64` のジャンクション (実行後に外した)
- run1 (`148a9af`): **KILLED 26 / 26** (`mutation_run1_148a9af.txt`、cp932 → UTF-8 に変換して保存)
