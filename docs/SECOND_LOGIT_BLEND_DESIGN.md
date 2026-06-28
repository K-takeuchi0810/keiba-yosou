# 二段ロジット再ブレンド 設計書 (Benter 補正)

作成: 2026-06-28 / 根拠: deep-research (`memory/project_roi_research_2026_06_28`) + コード精読

---
## ⚠️ 結果 (2026-06-28): OOS で反証 — 採用せず

本設計を実装し OOS 検証した結果、**この 2025-fit 係数・この適用形態の logit 再ブレンドは
EV を改善しなかった**。production は既定の linear のまま維持する。

- fit (2025通年, 32,677サンプル): b1=0.151 / b2=0.560 → 実効モデル重み **21%**。
  現行の手設定 0.78-0.85 は、勝敗 fit 上はモデルを過大に信用していた。
- OOS EV帯別 (2026-01-01〜2026-06-14, ◎1,578件):
  - linear: AUC(EV,的中)=0.3637 / Spearman(EV,払戻倍率)=-0.1593
  - linear(discount無し): AUC=0.3595 / Spearman=-0.1651
  - logit: AUC=0.2889 / Spearman=-0.2463
  - race-clustered bootstrap ΔAUC(logit - linear_no_discount) 95%CI = **[-0.0891, -0.0506]**
- **確定した結論**: discount を対称化しても、この logit 形態は EV の anti-predictivity を解消せず、
  AUC では linear(discount無し)より明確に悪い。→ 採用せず。
- **断定しないこと**: 「レバーは Blend#2 ではない」「モデルにエッジがない」までは本実験単独では未証明。
  今回否定できたのは、単一2025窓・C=10000・β=1・sigmoid適用の logit 置換案。
  複数窓安定性、fractional(β×0.5)、B-only ablation、上流モデル刷新は別検証が必要。
- logit mode (`PRED_BLEND_MODE=logit`) は既定off の opt-in 配管として残置。production は linear 不変。
- scorecard: data/scorecards/20260628_1710_second_logit_blend_refuted.md (平均3.67)。
- 再検証 JSON: `data/backtest/20260628_191122_ev_bucket_oos_20260101_20260614.json`

以下は反証前の設計記録 (再現性・経緯のため保持)。

---

## 1. 問題と根本原因

EV/Kelly 信号が **anti-predictive**（高EVほど実回収が低い、`project_p24_pred_accuracy`）。
deep-research が文献的根本原因を特定:

> Benter (1994): 生のモデルが「価値あり」と判定する馬（model_prob > market_prob）は、
> 実際の勝率が**公開オッズ側へ regress（回帰）する**。だからモデル単独の優位性は構造的に
> 過大評価される。補正は model_prob と market_prob を**第二のロジットで再ブレンド**してから
> advantage を計算すること。公開オッズはほぼ情報完備で、モデルの増分は微小だが正（dR²=.0178）。

## 2. 現状のブレンド経路 (2段ある)

`predictor/rules.py predict_race()`:

1. **Blend#1** rule × LGBM: `_blend(raw_rule_prob, raw_lgbm_prob, w_rule=0.5)` (`PRED_BLEND_W_RULE`)
2. calibrator (isotonic): `_apply_calibrator(blended)` → **model_prob** (`rules.py:1333`)
3. market_prob: `_market_probabilities()` = 単勝オッズ implied をレース内正規化 (overround 除去, `rules.py:1136`)
4. **Blend#2** model × market: `_investment_probability()` (`rules.py:1147`)
   - **線形凸結合**: `blended = model_prob * w + market_prob * (1-w)`
   - `w` は信頼度別**手設定**: weights.json 実値 = 高信頼 **0.85** / 標準 **0.78** / 接戦 0.70 / 混戦 0.62 / 暫定 0.30
   - 後段で odds 帯別 discount (base .92, >8 ×.90, >15 ×.82, >30 ×.72)

**Blend#2 が Benter の指す箇所**。現状は (a) 線形空間、(b) モデル過重 (0.78–0.85)、(c) outcome 非fit の
手設定。研究の「公開ほぼ完備・増分微小」と真逆にモデルを信用しており、これが anti-predictivity の機構。

## 3. 提案: Blend#2 をロジット再ブレンドに置換

### 3.1 数式
```
z = β0 + β1 * log(model_prob) + β2 * log(market_prob)
p_raw = sigmoid(z)
investment_prob = p_raw / Σ_race(p_raw)     # レース内再正規化 (Σ=1 制約)
```
β は **OOS の actual win outcome に conditional logit / ロジスティック回帰で fit**。
手設定 `model_weight` を捨て、データが決めた β1/β2 に置換する。
研究の予測: β1（モデル係数）は手設定の 0.78–0.85 相当より**大幅に小さく**出るはず
（= モデルを今より遥かに低く信用する）。そうなれば改善の傍証。

### 3.2 実装方針 (calibrator.json の運用を踏襲)
- **fit スクリプト**: `scripts/fit_second_blend.py`（`--from --to` で OOS 窓、calibrator と同じ
  trained_from/to/source_count/generated_at の provenance を記録）。出力 `predictor/second_blend.json`。
- **適用**: `_investment_probability` に mode 分岐を追加。
  - `PRED_BLEND_MODE=linear`（既定・現状維持）/ `=logit`（新）。後方互換を壊さない。
  - logit 係数が無い/壊れている時は linear に安全フォールバック（calibrator 不在時と同じ思想）。
- **discount の扱い**: logit fit が odds 依存の過大評価も吸収するため、logit mode では
  既存 odds discount は**既定 OFF**（`PRED_DISABLE_DISCOUNT` 相当を内包）。二重補正回避。
- 既存 `PRED_DISABLE_BLEND=1`（本セッションで実装済）はそのまま B 層 ablation 用に残す。

### 3.3 検証 (ゲート)
- factorial: 線形(現状) vs logit を OOS 窓で **paired** に走らせ、buy_only ROI と
  **paired CI** を比較（`PRED_DISABLE_BLEND` 実装で C3/C6 セルが可能になった）。
- walk-forward 必須: β を 1 窓で fit→別窓で評価（in-sample β で ROI を語らない。研究の
  「test-set tuning は楽観バイアス」教訓 = Silverman 36.73% の罠）。
- 採用条件: paired CI 下限が現状線形を上回る **かつ** calibration_in_sample=false。
  超えても 100%(控除率) 未満なら従来どおり観察専用継続（near-term 目標は価値破壊停止）。

## 4. リスク
- β fit のサンプル不足/過適合 → fractional 適用（β を 0.5 倍して保守化）も検討。研究の
  「fractional Kelly が正解・full は推定誤差に致命的」と同じ精神。
- レジーム shift（P12 失敗） → 四半期 re-fit を calibrator と同期運用。
- market_prob=0（オッズ無し/取消）時の log(0) → 現状の `market_prob<=0 → model のみ` 分岐を維持。

## 5. 工程順序
1. (実行中) OOS backtest 再実行 = 層 A ablation の足場 + 真の baseline ROI/CI 確定
2. `scripts/fit_second_blend.py` 実装 + 1 窓 fit
3. `_investment_probability` に logit mode 追加 (env 分岐・安全フォールバック)
4. factorial paired OOS (linear vs logit) + walk-forward
5. expert-review (profitability-judge / validation-process-auditor / prediction-logic-analyst 重点)
