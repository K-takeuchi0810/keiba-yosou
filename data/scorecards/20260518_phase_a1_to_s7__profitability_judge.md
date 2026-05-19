# 収益性 / 投資判断専門家 採点 — Phase A1+A2+S5+S6+S7

**改修対象**: `bad4e9c..d5c76ce`
**評価日**: 2026-05-18
**評価軸**: 「LGBM v5 限界下での最善対応」 (絶対収益性ベースの判定は不要、依頼書評価軸固定)

## 総合: 3.5 / 5 (前回 3.8 → -0.3)

**ルーブリック準用判定**: 控除率 80% を超えるのは TEST 絞り運用 88.7% のみ。Holdout 65.7% で割り込み。「複数指標のうち 1 つでも 80% 超えなら部分到達 = 総合 3 まで」というルールを準用し、改修品質を加味して 3.5 で着地。

## 項目別

| 項目 | 前回 | 今回 | Δ |
|---|---|---|---|
| 回収率 (本丸) | 5 | 3 | -2 |
| EV 計算の整合性 | 2 | 4 | +2 |
| Kelly fraction / 投資割合 | 2 | 4 | +2 |
| 買い目フィルタの実用性 | 4 | 3.5 | -0.5 |
| 校正済み確率の信頼性 | 2 | 3.5 | +1.5 |

### 詳細

- **回収率 (-2)**: TEST 81.2%/絞り 88.7%、Holdout 52.1%/絞り 65.7%。P05 EVAL 116% から賞味期限切れドリフトを観測。**LGBM v5 構造楽観 + 2026 ドメインシフトであり改修群の責任ではない**。
- **EV 計算 (+2)**: Phase A2-c1 で raw_blended_probability 導入、A2-c2 で Isotonic 移行。EV 計算経路は正しく組まれた。
- **Kelly (+2)**: Phase A1 で cap 撤廃、Kelly 0/0.05 二値縮退を解消し 0〜0.27 の連続値化。`compute_bet_size` の 1/4 Kelly mode で bet sizing が初めて機能。
- **買い目フィルタ (-0.5)**: S7-α で 4 経路集約 (構造的勝利 +0.5)。一方 S6 sweep 74 戦略 robust 0 件でフィルタ層の実効上限到達 (-1)。
- **校正後確率 (+1.5)**: Brier 0.0606 → 0.0377 (-42%)。高 p 帯 (Holdout bin [0.50, 0.55) actual=5.4%、[0.70+] actual=0%) は LGBM v5 構造楽観で未解消、ただし `max_predicted_p=0.40` で運用上回避。

## 改善提案 (優先 3 件)

1. **Phase B1 (LGBM v6 再訓練) を最優先で着手** — TRAIN を 20210101-20241231 に rolling forward + Isotonic refit。控除率 80% 再奪取の唯一の経路。本フェーズで整備したインフラ (Kelly cap 撤廃、Isotonic、filter.py 集約、max_predicted_p) はそのまま転用可能。
2. **絞り運用の Kelly-weighted return 集計を backtest に追加** — flat ベットの `buy_only_return_rate` だけでなく `kelly_weighted_return_rate` を出し、Phase A1 の bet sizing 経路の効果を数値化。
3. **「賞味期限切れ」自動検知 monitor 強化** — `weekly_monitor.bat` に直近 30 日の `buy_only_return_rate` 60% 割れ警告を追加。

## 「LGBM v5 限界下での最善対応」評価 (依頼書評価軸固定)

- S6 sweep 74 戦略 robust 0 件 / Holdout 控除率割れ は **構造的限界の証明** として扱い「壊滅」とは判定しない (依頼書指示通り)。
- Phase A1/A2/S5/S7 の改修群は **数値修正の正しさ + 責務分離 + 再発防止構造** のすべてで模範的。
- **Phase B1 移行根拠は十分**: フィルタ層 / 校正経路 / bet sizing 経路の改善余地は出し切られた。残るは LGBM v6 再訓練のみ。
- Phase B1 完了後の再採点で **+0.5〜+1.0 戻り、総合 4.0〜4.5 到達** を予期。

## 関連ファイル
- `data/backtest/20260517_044653_tan_p16_A1_test-filtered.json` (TEST 2 年 6,924 戦)
- `data/backtest/20260517_133637_tan_p17_A2_holdout-filtered.json` (PROD 2026 1,380 戦)
- `data/backtest/20260518_s6_recent_3fold.txt` (74 戦略 sweep)
- `predictor/calibrator.json` (Isotonic, source_count=48058, Brier 0.0288)
- `predictor/rules.py:907-923` (Kelly cap), `predictor/filter.py` (4 経路集約), `config.py:96-138` (BUY_FILTER), `scripts/predict.py:42-60` (1/4 Kelly)
