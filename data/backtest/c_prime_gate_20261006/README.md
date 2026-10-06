# C′ の前の最終ゲートの変異テスト (2026-10-06)

- spec: `tests/mutation_specs/c_prime_gate_spec.py` (14 個)。`git archive 293eb1b` の隔離コピー (scratchpad、`.git` 無し) + `.venv64` のジャンクション (実行後に外した)
- r1 (`293eb1b`): G6 で **ABORTED** (10:15 の本番の fresh odds の健全性チェックが data/logs・data/runtime に書いた。変異の影響ではない)。それまで KILLED 5
- r2 (`293eb1b`): G14 で **ABORTED** (本番の `data/keiba.db-wal` の更新。別のプロセスの書き込み)。**G11 (market-recalibration only に S を入れる) が SURVIVED**
  → 診断の 3 集合のテストを、full と market-recalibration only の件数が分かれる例に直した (`1fcdd6c`)
- r3 (`1fcdd6c` のテスト、コードは `293eb1b` と同じ): **KILLED 14 / 14**
- 同じコピーで `tests/mutation_specs/eval_refund_spec.py` (39 個、market_term → market_feature の改名を反映) も **39 / 39 KILLED**

## 3 名レビュー (validation 4.1 PASS / prediction-logic 4.2 CONDITIONAL / code-quality 3.6 CONDITIONAL) の反映の後 (25 個)

- r4 (`9476a26`): 変異なしの基準の実行で **ABORTED** (本番の `keiba.db-wal`)
- r5 (`9476a26`): G20 で **ABORTED** (本番の fresh odds の取得)。**G16 (不収束の当てはめを通す) が SURVIVED** — 後段の有限の値の検査の文言に
  「収束しなかった」が含まれ、テストの match が通っていた → 有限の係数で不収束を返すテストを足した (`1b0cd79`)
- r6 (`1b0cd79`): **G25 (β_market = 1 の当てはめが市場のオフセットを落とす) が SURVIVED**、他 24 KILLED — 人工データの S が市場と独立だと、
  オフセットを落としても β_S が同じになる → S が市場と相関する世界のテストを足した (`1e08eaf`)
- r7 (`1e08eaf`): G19 で **ABORTED** (本番の fresh odds の健全性チェック)
- r8 (`1e08eaf`): **KILLED 25 / 25**
- 同じ版のコードで `eval_refund_spec.py` (39 個) も **39 / 39 KILLED** (`eval_refund_spec_on_9476a26.txt`、コードは 1e08eaf と同じ)
- ABORT はすべて、本番の書き手 (fresh odds の取得・健全性チェック・DB の WAL) の変化を sandbox が検出したもの。変異の実行が本番に書いたのではない
