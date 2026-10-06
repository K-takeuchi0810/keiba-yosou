# C′ の前の最終ゲートの変異テスト (2026-10-06)

- spec: `tests/mutation_specs/c_prime_gate_spec.py` (14 個)。`git archive 293eb1b` の隔離コピー (scratchpad、`.git` 無し) + `.venv64` のジャンクション (実行後に外した)
- r1 (`293eb1b`): G6 で **ABORTED** (10:15 の本番の fresh odds の健全性チェックが data/logs・data/runtime に書いた。変異の影響ではない)。それまで KILLED 5
- r2 (`293eb1b`): G14 で **ABORTED** (本番の `data/keiba.db-wal` の更新。別のプロセスの書き込み)。**G11 (market-recalibration only に S を入れる) が SURVIVED**
  → 診断の 3 集合のテストを、full と market-recalibration only の件数が分かれる例に直した (`1fcdd6c`)
- r3 (`1fcdd6c` のテスト、コードは `293eb1b` と同じ): **KILLED 14 / 14**
- 同じコピーで `tests/mutation_specs/eval_refund_spec.py` (39 個、market_term → market_feature の改名を反映) も **39 / 39 KILLED**
