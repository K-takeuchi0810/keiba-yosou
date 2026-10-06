# Group C′ の変異テストの記録 (2026-10-06)

- spec: `tests/mutation_specs/c_prime_spec.py` (28 個。C1〜C9 は対象レース自身の脚質コードの混入と PIT の変異)
- 実行: `git archive <sha>` の隔離コピー (scratchpad、`.git` 無し) + `.venv64` のジャンクション (実行後に外した)
- run1 (`2bc5c47`): KILLED 27 / SURVIVED 1 (C4 直近 6 走を数える — テストの例が 5 走でも 6 走でも同じ値になっていた) → 例を差し替え
- run2 (`1e15c69`): **KILLED 28 / 28**
- run3 (`de3de16`): **KILLED 28 / 28** (実行のスクリプトを足した後の再確認)

## 実行のスクリプト (`tests/mutation_specs/c_prime_run_spec.py`、24 個)

- run_spec_r1 (`c100d73`): KILLED 21 / SURVIVED 3 (R4 別の凍結物の検出力 / R8 ブートストラップの回数 / R10 錠の後の固定のファイルの変更) → テストを足した
- run_spec_r2 (`de3de16`): R11 で **ABORTED** (11:30 の本番の fresh odds の取得・健全性チェック・DB の WAL。変異の影響ではない)
- run_spec_r3 (`de3de16`): **KILLED 24 / 24**
