# Validation Process Auditor 採点 — Phase A1+A2+S5+S6+S7

**改修対象**: `bad4e9c..d5c76ce`
**評価日**: 2026-05-18

## 総合: 4.55 / 5 (前回 4.22 → +0.33)

| 軸 | 今回 | 前回 | 増分 |
|---|---:|---:|---:|
| 1. バックテスト設計 | 4.7 | 4.5 | +0.2 |
| 2. リーク防止 | 4.7 | 4.5 | +0.2 |
| 3. calibration 計測 | 4.4 | 3.8 | +0.6 |
| 4. A/B 比較 / バージョン管理 | 4.7 | 4.5 | +0.2 |
| 5. 過適合監視 | 4.4 | 3.8 | +0.6 |

## 主要な前進 (検証プロセス観点)

1. **meta snapshot 制度** (`scripts/backtest.py:_snapshot_meta` at c0): 直近 4 件の backtest JSON すべてに calibrator/LGBM/git_sha が同梱。前回宿題 #2 完全対応。
2. **Isotonic 化 + fit 窓 disjoint**: calibrator が TEST 期 (2025) fit → PRODUCTION 2026 で out-of-sample。aggregate Brier -37.6% 改善。前回宿題 #1 完全対応。
3. **CLAUDE.md ルール 1-ter の checklist 化サイクル**: S3 事故 → ルール制定 → S4 で 2 回違反 → checkbox 形式に書き換え → S6/S7 違反ゼロ という稀有なメタ品質改善サイクル。
4. **S6 sweep の陰性証明** (74 戦略 × 3 fold で robust 0 件): 「filter 層では救えない、Phase B1 (LGBM v6) こそが唯一の経路」という意思決定根拠を 222 データポイントで支持。
5. **S7-α `predictor/filter.py` 集約 + 二重防御**: 4 経路で重複していた is_buy_candidate を単一関数に集約 + 表示層に冗長 kelly guard。同種バグ 2 回発生に対する構造的予防。

## 主要な残課題

1. `scripts/backtest_diff.py` (前回宿題 #3) 未着手 — B1 前に着手推奨。
2. `p16_A1_test` は Step 0 前のため `meta=False`。
3. records JSON 自体には `meta` 未付与。
4. `weekly_monitor.bat` の Task Scheduler 登録の自動検証経路なし。
5. rolling Isotonic refit 未実装 (B1 後の運用で必要)。

## 関連ファイル
- `data/scorecards/20260517_0010_p16_A1_kelly_uncap__validation_process_auditor.md` (前回 4.22)
- `scripts/backtest.py:34-75` (`_snapshot_meta`), `:449` (meta 埋込), `:668` (`--save-records`)
- `scripts/refit_calibrator.py` (c2-b 新設)
- `predictor/filter.py` (S7-α-2 集約)
- `predictor/calibrator.json` (Isotonic, `trained_from=20250101`, `source_records_meta` 同梱)
- `data/backtest/20260517_133637_tan_p17_A2_holdout-filtered.json` (PROD holdout, meta carry)
- `data/backtest/20260518_s6_recent_3fold.txt` (74 戦略 × 3 fold, robust 0/74)
- `CLAUDE.md` (ルール 1-bis subagent CWD / ルール 1-ter 3-checkbox pre-flight)
- `weekly_monitor.bat` (Brier drift +20% 監視)
