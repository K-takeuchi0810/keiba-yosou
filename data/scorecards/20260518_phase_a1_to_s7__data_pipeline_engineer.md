# データパイプライン技術者 採点 — Phase A1+A2+S5+S6+S7

**改修対象**: `bad4e9c..d5c76ce`
**評価日**: 2026-05-18

## 総合: 4.4 / 5 (前回 4.0 → +0.4)

## 項目別

| 項目 | 前回 | 今回 | Δ |
|---|---|---|---|
| エラー回復 (`_snapshot_meta` try/except) | 5 | 5 | ±0 |
| idempotency (`refit_calibrator` `--dry-run` + `.bak`) | 4 | 4 | ±0 |
| データ鮮度管理 (meta snapshot) | 3 | 5 | +2 |
| スキーマ整合 (records JSON) | 4 | 4 | ±0 |
| リトライ / 失敗時の records 保全 | 3 | 4 | +1 |

## 主な発見

1. **3 世代追跡が確立**: `predictor/calibrator.json.source_records_meta.git_sha=d3e0dd124b...` で「現 calibrator → records 採取時 → 採取時の calibrator/lgbm」の連鎖が完全追跡可能。
2. **担当範囲のコア (`jvlink_client/` / `db.py` / `data/schema.sql`) は 9 連続改修ゼロ継続** — Phase A1-S7 は backtest 検証インフラが主スコープのため担当範囲外の改修。
3. **4.7 MB records JSON を git に乗せている判断は妥当** — diff が human-readable、revert/cherry-pick が容易、gzip / LFS は過剰。
4. **`meta.git_sha` 仕様**: commit 17d3f56 以降の backtest JSON にのみ付与 (pre-A2 c0 は未付与、後追い fill は不要)。

## 主な改善提案 (優先 3 件)

1. **records JSON に `schema_version` 必須化** — refit_calibrator で機械検査して c1 前 records 誤投入を防止
2. **CLAUDE.md ルール 1-quater (bg 出力永続 path)** — `feedback_tmp_volatile.md` 想定に基づく文書化
3. **`data/calibrator_history/` 世代管理** — `.bak` 1 世代では不足、ML モデル相当の独立 history が必要

## 関連ファイル
- `scripts/backtest.py:34-78` (`_snapshot_meta()`), `:704-720` (`--save-records`)
- `scripts/refit_calibrator.py:90-115`
- `scripts/filter_sweep.py:213-233` (S6 追加), `:466-520` (recent-3fold)
- `predictor/calibrator.json` (現 Isotonic, source_records_meta 同梱)
- `predictor/calibrator.json.bak` (旧 bin, 3294B)
- `predictor/calibration.py:88-134` (`fit_isotonic_calibrator`)
- `data/backtest/20260517_124044_tan_p17_A2_records_2025-filtered.json` (meta 12 フィールド完全)
- `data/backtest/20260517_124044_tan_p17_A2_records_2025_records.json` (4.7 MB / 48,058 records / 4 keys)
- `data/backtest/20260518_s6_recent_3fold.txt` (74 戦略 × 3 fold)
