# データパイプライン技術者 採点 — F3 Phase 0-0b paired OOS

## 総合: 4.3 / 5（前回 4.2 → 今回 4.3、差分 +0.1）— **PASS**

対象は最終HEAD `fa1d491` と、`scripts/f3_phase0_0_eval.py`、
`tests/test_f3_phase0_0_eval.py`、`data/f3_phase0_0/paired_oos.json`、
`docs/F3_phase0_0b_result.md`。指定の `.Codex/agents/_rubric.md` は今回も存在しないため、
直前の同担当 `20260720_1204_f3_phase0_0__data-pipeline-engineer.md` の形式を踏襲した。
JV-Link/raw ingest/schema 本体に変更はない。

同一 OOS harness/race ledger/day-block resample、file単位atomic write、evaluator commit、
production/cache/Phase 0成果物/OOS reference/historical calibratorとの衝突guardに加え、
JSONを `data/f3_phase0_0/paired_oos.json`、reportを固定pathへ限定した。DB/source/configを含む
任意の別pathは長時間処理前に拒否され、破壊的出力リスクが閉じたため **PASS** とする。

## 項目別

- **DB read-only / sealed 境界: 5.0/5**
  - OOS は既存 `_evaluate_oos` を再利用し、`open_db_readonly()`、固定窓
    `20260101..20260614`、`require_confirmed=True` を維持する。
  - 実 DB で `PRAGMA query_only=1`、書込みは
    `attempt to write a readonly database` で拒否された。DBへの変更なし。
  - `_guard_unsealed` は開始・終了の双方で `>=20261001` を拒否し、テストあり。
    paired 経路も開始時と各 OOS 評価時に検査する。

- **paired 標本整合 / 決定性: 4.7/5**
  - treatment を先に実行し、凍結済み `425 bets / 65 hits / 62.0941%` の完全再現を
    control 実行の前提にする fail-closed 構造。
  - control/treatment の race-id 集合一致を検査し、1回生成した day index 標本を
    両系列に適用して ROI 差を計算する。B=10,000、seed=20260720 は固定。
  - artifact の validation AUC も control/treatment とも期待値に一致し、hashを保存。
  - ただし dict 化前の race-id 重複と、同一 race-id の day 一致は明示検査しない。
    divergent ledger で shared resample の期待差を固定する単体テストも未追加。
  - `bootstrap_samples<=0` は `run_paired_oos` 入口、DB/model読込前に即時拒否される。

- **artifact / provenance: 4.4/5**
  - evaluator commit `af13474` のgit blob SHA-256は保存済み `ecabaa...40ad` と一致し、
    paired成果物を実際に生成したコードを復元可能。rules SHA、モデル・特徴定義hash、
    production before/after hash、OOS窓、blocked 3特徴、bootstrap条件も保存する。
  - production 4成果物は artifact 記録値=before=after=現在値で全件一致した。
  - 一方、paired JSON は入力 `metrics.json`、cache、OOS reference、historical calibrator
    の hashを継承しない。元 metrics には cache/calibrator hash があるが、結果単体では
    完全な provenance chain にならない。git dirty状態も未保存。
  - evaluator hash は run 終了時だけ取得するため、長時間実行中のコード変更を検知しない。

- **idempotency / atomicity / 出力安全性: 4.2/5**
  - 既定の JSON と Markdown は主要数値・結論が一致し、再bootstrapはseed固定で再現可能。
  - `_atomic_write_text` で各ファイルはtemp→replace、JSON/report相互同一とproduction 4件、
    cache、Phase 0成果物、OOS reference、historical calibratorとの衝突を事前拒否する。
  - JSONは必ず `data/f3_phase0_0/paired_oos.json`、reportは必ず
    `docs/F3_phase0_0b_result.md`。DB/evaluator/config指定はJSON/report双方で実測拒否。
    任意 `data/other/paired_oos.json` も拒否し、custom output_dir による迂回はない。
  - JSONとreportは2回のreplaceでありpair transactionではない。固定 `.tmp` 名のため
    並行実行時も競合する。相互hash manifest/fsyncもない。
  - `paired_oos.json` は `.gitignore` の `data/*` 対象、結果 Markdown も未追跡で、
    commit `af13474` には evaluator/test のみが含まれ、確定結果は含まれていない。

- **回復性 / 性能 / observability: 3.3/5**
  - 既存 feature cache を使い、DB reader は WAL writer を阻害しない。ledger は約1,578 race
    規模でメモリ上処理しており、今回の規模では妥当。
  - 既存 treatment OOS は約4,972秒。paired は同じ OOS を2回走らせるが、checkpoint、
    resume、timeout、cancel がなく、失敗時は最初から再計算となる。
  - paired JSON は各モデルの `elapsed_sec` を落としており、総実行時間も保存しない。
    custom outputの親存在・書込み可能性は長時間処理前にpreflightしない。

## 成果物・実測

- `git log --stat -3`: 最終HEAD=`fa1d491`。
  `paired_oos.json` と `F3_phase0_0b_result.md` は commit 対象外。
- `.venv64/Scripts/python.exe -m pytest -q tests/test_f3_phase0_0_eval.py`:
  **11 passed in 3.12s**。全体は **377 passed / 4 skipped**。
- paired artifact: 50 day blocks、self-selected union 471 races、missing payout 0、
  bootstrap valid 10,000/10,000。
- control `424/65/63.1132%`、treatment `425/65/62.0941%`、
  paired差 `+1.0191% [−4.6737%, +6.4106%]`。JSON と report は一致。
- cross-selected bases は双方のROI・CIが一致し、差 `0`。同一 race/day ledger の
  shared resample 実装と整合する。
- raw 先頭10種とサイズ、`fetch_state.json`、read-only DB のテーブル/indexを確認。
  大容量 raw `.jvd` 本体は読んでいない。

## 優先課題

1. **P1: transactional publish** — 一時ディレクトリへ JSON/report を生成し、相互hashと
   schema検証後に atomic replace。途中失敗時に正式成果物が不変なテストを追加する。
2. **P1: provenance chain 完結** — evaluator commit/dirty、run開始時hash、metrics/cache/
   reference/calibrator SHA-256、入力モデル定義hashを paired manifest に固定し、終了時再検査。
3. **P1: ledger invariant テスト** — race-id重複なし、両ledgerのday一致、payout presence、
   divergent selectionでも1つのday index標本を共有することを統合テストで固定する。
4. **P2: 長時間run回復性** — model別/day別 checkpoint、resume、定期進捗、cancel/timeout、
   model別および総 `elapsed_sec` を追加する。
