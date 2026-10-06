# Group C′ の変異テストの記録 (2026-10-06)

- spec: `tests/mutation_specs/c_prime_spec.py` (28 個。C1〜C9 は対象レース自身の脚質コードの混入と PIT の変異)
- 実行: `git archive <sha>` の隔離コピー (scratchpad、`.git` 無し) + `.venv64` のジャンクション (実行後に外した)
- run1 (`2bc5c47`): KILLED 27 / SURVIVED 1 (C4 直近 6 走を数える — テストの例が 5 走でも 6 走でも同じ値になっていた) → 例を差し替え
- run2 (`1e15c69`): **KILLED 28 / 28**
