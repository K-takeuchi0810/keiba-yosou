# F3 Phase 0-0 発走後リーク定量化結果

- 実行日時: 2026-07-20T10:37:50
- コードcommit: `068efb0cce3d2b369942cced2d4601d04135f264`
- 評価スクリプトSHA-256: `48b158bd754a1a457885a4a7bdae31bae8ccd9d80e49d747d08c3c9e058ae491`
- train/val: 20210101〜20231231、時系列末尾20%をval
- 固定seed: 20260720、boosting rounds: 781
- 遮断対象: `same_day_bias_score`, `leg_quality_available`, `same_day_bias_available` の3件のみ

## Validation

| model | AUC | Brier | LogLoss | race top-1 |
|---|---:|---:|---:|---:|
| M0_public_v6 | 0.791409 | 0.061494 | 0.222437 | 0.282064 |
| M1_zero_fill | 0.789435 | 0.061589 | 0.223021 | 0.281581 |
| M2_control | 0.791320 | 0.061522 | 0.222510 | 0.281099 |
| M2_treatment | 0.788781 | 0.061670 | 0.223299 | 0.281099 |

差分は左辺−右辺の直接差。AUC/top-1は正が左辺優位、Brier/LogLossは負が左辺優位。

- live skew（M0−M1）: `{"auc": 0.0019743931752551624, "brier": -9.546076892837096e-05, "logloss": -0.0005838435437252321, "top1_hit_rate": 0.00048216007714563247}`
- 事前登録3チャネル差（M2-control−M2-treatment）: `{"auc": 0.0025388106527592935, "brier": -0.00014721837779155256, "logloss": -0.0007887821435402786, "top1_hit_rate": 0.0}`

## 固定pre-2026-07 OOS

- 期間: 20260101〜20260614（封印開始 20261001 より前）
- M2-treatment: 425 bets / 65 hits / 回収率 62.0941%
- 開催日block bootstrap 95% CI: [48.9680%, 76.2769%] (B=10000, seed=20260720)
- 旧参照: 199 bets / 回収率 70.7035% / CI [0.4658, 0.9673]
- 母集団差: 現行 1578 races / 425 bets、旧参照 1620 races / 199 bets
- 比較上の注意: Window, buy filter, popularity overrides and historical calibrator match the 70.7% reference, but predictor/rules.py uses the reviewed commit rather than the historical git SHA. Race and bet counts also differ, so the OOS percentage-point difference is not a paired estimate of leak contribution.
- OOS処理時間: 82.9分。再実行は30分超pre-flight対象。

## 結論

同一split/seedで事前登録3チャネルだけを除外したときのAUC差は +0.002539。3チャネル除外validationはAUC≈0.788781 / OOS≈62.09%（旧70.7%との差は非pairedで、全stackのリーク除去効果とはみなさない）。

production artifactはSHA-256前後一致。封印期間、DB書込み、Discord、production更新は実施していない。

## 対象外の追加観察

- treatmentにも `same_day_gate_bias_score`、rule側のsame-day/`leg_quality_code` 経路などは残る。事前登録どおり遮断対象を3チャネルから拡張せず、本結果を全リーク除去baselineとは呼ばない。
- G-MINおよびPIT-UNPROVEN特徴は今回の対象外で、変更していない。
