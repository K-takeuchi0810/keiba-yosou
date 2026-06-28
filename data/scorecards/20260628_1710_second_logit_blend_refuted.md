# 採点 2026-06-28 17:10

**改修内容**: 二段ロジット再ブレンド(Benter補正)を実装→OOSでEV悪化を確認し採用せず(production linear不変)。PRED_DISABLE_BLEND/PRED_BLEND_MODE=logit env + fit_second_blend.py / analyze_ev_buckets.py 新規 + test3件(8/8 pass)
**対象ファイル**: predictor/rules.py, scripts/fit_second_blend.py, scripts/analyze_ev_buckets.py, predictor/second_blend.json, tests/test_market_popularity_scoring.py

## 総合スコア (項目平均) の推移

| 専門家 | 今回 | 前回 | 差分 | 判定 |
|---|---|---|---|---|
| GUI / UX 監査人 | 3.6 | 3.6 | ±0 | PASS |
| モバイル HTML レビュアー | 4.4 | 4.4 | ±0 | PASS |
| 予想ロジック分析官 | 3.7 | 3.9 | -0.2 | HOLD |
| 収益性ジャッジ | 3.4 | ~3.5 | ±0 | HOLD |
| データ基盤エンジニア | 3.6 | 4.0 | **-0.4 ⚠ 後退** | HOLD |
| コード品質レビュアー | 3.7 | 3.9 | -0.2 | HOLD |
| 検証プロセス監査人 (最終ゲート) | 3.3 | 4.6(p05/性質別) | -1.3※ | **CONDITIONAL** |

平均 **3.67**。※validation の前回比は採用改修(p05)が基準で性質が異なる。

## 最終ゲート判定: CONDITIONAL

「採用せず・production linear 不変」という**意思決定は健全で全員が支持**(保守側・誤運用リスク無し)。
ただし**負の結論の提示強度が一次データの範囲を超える over-claim**があり、確定知見として固定する前に是正条件あり。

## 各専門家の所見 (要約)

### GUI / UX 監査人 (3.6, PASS)
GUI 直接変更なし・JS パース PASS。誤読動線増なし。新規負債: `PRED_BLEND_MODE=logit` の実発火が GUI 非表示(係数完備なので env セットで実発火しうる)。提案: generator footer に blend_mode 表示。

### モバイル HTML レビュアー (4.4, PASS)
web/ 無変更・HTML サイズ 399KB(予算内)・production linear 不変を確認。リグレッション無し。継続課題: .conf-tag タップ領域 / ◎根拠の出所表示。

### 予想ロジック分析官 (3.7, HOLD)
train-serve skew 最小化設計は堅実。**B-only ablation (PRED_DISABLE_BLEND=1 単独 run) が無く、「logit悪化の根因=B経路の市場寄りすぎ」の因果は断定不能**。C=10000(near-unregularized)で b2 過大の可能性、OOS logloss 未記録。fit時 odds の provenance 欠落。

### 収益性ジャッジ (3.4, HOLD) ★最重要監査
- EV帯別の数値再導出: 依頼の値と JSON 一致。logit 高EV帯壊滅は事実。
- **非対称比較(linear=discount込/logit=discount無)は bucket 差分量を歪める**。
- **ただし AUC/Spearman は単調変換不変** → 「両モード anti-predictive」「logit が AUC で劣る(0.289<0.364)」は**非対称の影響を受けず頑健**。最終決定(不採用)の向きは覆らない。
- 高EV帯 CI は重なる(logit[1.5,∞) hit Wilson95 [0,6.1%], n=59)→ bucket 大小の断定は弱い。全体方向(n=1578)は頑健。
- pop1-3 ROI 68.5%(CI上限<100%)=利益エッジ無し は妥当。logit を OOS 評価して見送り=winner's curse 回避の模範。

### データ基盤エンジニア (3.6, HOLD ⚠-0.4)
second_blend.json provenance は calibrator と概ね一貫。`_load_second_blend` の mtime キャッシュ/破損フォールバック堅牢。減点: (1) backtest JSON `meta.rule_version=None`(既存バグ)、(2) `_load_second_blend` が rule_version 照合せず(calibrator と非対称)、(3) JSON 非アトミック書き込み、(4) post_start snapshot 257race 放置(スコープ外)。

### コード品質レビュアー (3.7, HOLD)
env 3種は実装済(未実装env前提なし)。減点: (1) **env 3種が backtest meta.env_overrides 未記録**→ablation 事後検証不能(最優先2行修正)、(2) **fit と analyze の race ループほぼ重複**(DRY、共通イテレータ抽出推奨)、(3) `apply_note`「race内Σ=1再正規化」記述がコード(再正規化せず)と乖離、(4) sigmoid clamp ±60 が2箇所直書き。test 3件は質が高い。

### 検証プロセス監査人 (3.3, CONDITIONAL) ★最終ゲート
- 時系列分離(2025fit/2026eval) PASS、リーク無し PASS、paired 設計妥当。
- **(最大欠陥) discount 非対称**: 公平比較には両者 discount OFF で揃える再検証が必要。
- **CI 欠落**: paired なら paired 検定(race-clustered bootstrap)で AUC 差・bucket return の CI を出すべき。点推定見出し(0% vs 27%)は n=59 で過剰。
- **over-claim**: 「レバーはモデルのエッジ不足」は本実験の範囲超。係数は単一窓 fit(CV無)、fractional(β×0.5)未試行。「本係数・本適用形態では改善せず」へ表現緩和すべき。
- meta(git_sha/env)欠落。renormalization の doc↔code 食い違い。

## 横断的に見た優先課題 (優先順)

1. **記録の over-claim を是正する** (validation #5 + prediction-logic + profitability)
   - memory / design doc の「レバーは Blend#2 でなくモデルのエッジ不足」を
     「この 2025-fit logit 係数・本適用形態(discount無/単一窓/β=1)では anti-predictivity を解消せず、
     AUC/Spearman(単調変換不変=頑健)で両モード<0.5。ただしモデルのエッジ全否定は本実験では未証明」へ緩和。
2. **discount 対称の再検証 + CI** (validation #1/#2 + profitability #1)
   - linear も `PRED_DISABLE_DISCOUNT=1` 相当で EV 再計算し同一空間で paired 比較。
   - race-clustered bootstrap で AUC 差・bucket return の CI を出力 JSON に追加。
   - ※AUC/Spearman は不変なので結論の向きは変わらない見込みだが、説得力・厳密性のため。
3. **証跡規律** (code-quality #1 + data-pipeline #1)
   - backtest の env_keys に PRED_BLEND_MODE / PRED_DISABLE_BLEND / PRED_DISABLE_SECOND_BLEND を追加。
   - 分析 JSON に meta(git_sha/git_dirty/env_overrides)を追加。second_blend.json アトミック書き込み。
4. **(中期) DRY + doc整合** — race ループ共通イテレータ抽出、apply_note の再正規化記述を実装に合わせる、_load_second_blend に rule_version 照合追加。

---

## 2026-06-28 19:11 CONDITIONAL 是正結果

上記 CONDITIONAL のうち、短時間で閉じられる証跡・検証面を追加実施した。

- `scripts/analyze_ev_buckets.py` に discount 対称比較 (`linear_ev_no_discount`) を追加。
- 同スクリプトに race-clustered bootstrap CI を追加。
- 分析 JSON に `meta.git_sha` / `git_dirty` / `git_status_short` / `env_overrides` / `second_blend_sha256` を追加。
- `scripts/backtest.py` の env snapshot に `PRED_BLEND_MODE` / `PRED_DISABLE_BLEND` / `PRED_DISABLE_SECOND_BLEND` を追加。
- `_load_second_blend()` に `RULES_VERSION` 照合を追加し、不一致時は linear fallback。
- `predictor/second_blend.json` の `apply_note` を現実装に合わせて修正。

再検証 JSON: `data/backtest/20260628_191122_ev_bucket_oos_20260101_20260614.json`

主要結果:

| 指標 | linear | linear(discount無し) | logit |
|---|---:|---:|---:|
| AUC(EV,的中) | 0.3637 | 0.3595 | 0.2889 |
| Spearman(EV,払戻倍率) | -0.1593 | -0.1651 | -0.2463 |

race-clustered bootstrap:

- ΔAUC(logit - linear): 95%CI `[-0.0935, -0.0546]`, median `-0.0742`
- ΔAUC(logit - linear_no_discount): 95%CI `[-0.0891, -0.0506]`, median `-0.0700`

是正後の判断:

- discount 非対称を外しても、logit はこの適用形態では linear を上回らない。
- 「採用せず / production linear 不変」の意思決定は維持。
- ただし断定範囲は「2025単一窓 fit・C=10000・β=1・sigmoid直接適用の logit 置換案は不採用」に限定する。
- 「Blend#2 以外が主因」「モデルにエッジがない」までは未確定。B-only ablation、複数窓 fit、fractional 係数、上流 LGBM refresh は別検証。
