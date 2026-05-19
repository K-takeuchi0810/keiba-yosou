# 予想ロジック分析官 採点 — Phase A1+A2+S5+S6+S7

**改修対象**: `bad4e9c..d5c76ce`
**評価日**: 2026-05-18
**評価軸**: LGBM v5 環境下での予想ロジック最善対応

## 総合: 4.35 / 5 (前回 P16 A1 4.0 → +0.35)

## 項目別

| 項目 | 前回 | 今回 | Δ |
|---|---|---|---|
| シグナル網羅性 | 4 | 4 | ±0 |
| 重み妥当性 / 過適合リスク | 4 | 4 | ±0 |
| 信頼度判定 / 確率推定 | 3.5 | **4** | **+0.5** |
| デッドコード / 設計の整合性 | 4.5 | **4.75** | **+0.25** |
| 本番運用との乖離リスク | 3 | **4** | **+1.0** |

## 主な発見

### LGBM v5 高 p 帯構造楽観の定量化

`data/backtest/20260517_124044_tan_p17_A2_records_2025_records.json` (n=48,058) の bin 集計:

| bin (raw_p) | n | raw_p_mean | **actual** | gap |
|---|---:|---:|---:|---:|
| [0.30, 0.40) | 1045 | 0.340 | **0.070** | -0.27 |
| [0.40, 0.50) | 300 | 0.442 | **0.077** | -0.37 |
| [0.50, 0.70) | 243 | 0.549 | **0.033** | -0.52 (逆転) |
| [0.70, 1.00) | 14 | 0.756 | **0.000** | 致命的 |

### Isotonic は構造楽観を正しく学習

`predictor/calibrator.json` の `y_knots` tail = 0.034, 0.039, 0.065 で `x_knots=0.908` を `y≈6.5%` までダウンマップ。**しかし `predictor/rules.py:806-809` の race 内 Σ=1 再正規化で高 p 帯馬が再浮上する**。これが S5-1 で確定した構造の核。

## Phase B1 で対処すべき項目 (LGBM 再訓練でしか直らないもの)

1. 高 p 帯構造楽観の根本治癒 (TRAIN rolling forward + listwise/softmax loss)
2. race 内 Σ=1 正規化と構造楽観の競合解消 (LGBM 側の loss 設計)

## B1 後に予想ロジック側で再評価する項目

3. `min_kelly` / `max_predicted_p` の grid 再 sweep
4. `_investment_probability` の discount A/B
5. `feature_warnings` を `predictor/filter.py:is_buy_candidate` に通す
6. `_value_score` 内 `current_track_code in {"03", "06", "10"}` のハードコード除去
7. `_RATIONALE_EXCLUDE_PREFIXES` のメタ情報化

## 関連ファイル
- `predictor/rules.py:84-90` (raw_blended_probability), `798-809` (isotonic 分岐), `806-809` (race 内再正規化), `869-904` (_investment_probability), `907-923` (_bet_metrics)
- `predictor/filter.py` (S7-α 新設、is_buy_candidate 単一関数化)
- `predictor/calibrator.json` (Isotonic, 48058 records)
- `scripts/refit_calibrator.py` (Phase A2 c2-b 新設)
- `config.py` (BUY_FILTER_DEFAULT: max_predicted_p=0.40, whitelist_tracks=[])
- `scripts/filter_sweep.py:226-234` (S6 grid 拡張)
