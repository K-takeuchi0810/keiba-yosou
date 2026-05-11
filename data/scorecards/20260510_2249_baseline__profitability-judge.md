# 収益性 / 投資判断専門家 採点

## 総合: 1.8 / 5

直近 5 件の backtest はいずれも単勝控除率 80% を割り込み (50.7%〜62.4%)、一番良い 5/9 の 62.4% でも JRA 単勝控除率 (約 80%) に対して 17pt 以上のマイナス。フィルタ採用も 0〜2 件/72 戦と統計的にも実用的にも壊滅的。控除率 80% を超えていないため総合 3 以上は付けないルールを適用し、軸足を辛口に置く。

## 項目別

- **回収率 (本丸): 1/5** — 直近 5 件 (72 戦) が 50.7 / 52.2 / 62.4 / 62.4 / 62.4%。週足では 5/4〜5/6 の 3,180 戦長期検証で 73〜74% まで戻るが、それでも控除率割れ。買い目フィルタ通過分 (`buy_only_return_rate`) は全件 0.0%。資金が単調減少する状態で、現状で実弾投入したら毎週マイナス確定。
- **EV 計算の整合性: 2/5** — `_investment_probability` は (1) calibrator で校正済 model_probability を、(2) confidence 別 weight で market と blend、(3) odds 帯 discount (base 0.92 × over8/15/30) を更に掛ける三段がけ。`weights.json` で `model_blend.high=0.85`, `standard=0.78` と外側で大きく上書きされており、コード側 default (0.72/0.62) と乖離。`PRED_DISABLE_DISCOUNT=1` の比較 backtest が `data/backtest/` に見当たらず、discount の効果検証がユーザー側で追えていない。三段がけは EV を構造的に潰している疑いが濃い。
- **Kelly fraction / 投資割合: 2/5** — `_bet_metrics` で `min(kelly, 0.05)` 上限固定だが、ベット額計算には未使用 (表示のみ)。`buy_only_bets` が 1〜2 件/72 戦の状態で同 race 複数候補の分散投資ガイダンスも未実装。Kelly 値が GUI に出るだけでは「投資判断」として機能していない。
- **買い目フィルタの実用性: 1/5** — `web/generator.py` 既定値 `EV>=1.10 / Odds 2.0-8.0 / Value>=10.0`、`gui/app.py:_is_buy_candidate` も同フィルタ参照。一方で backtest の `buy_filter` は `EV>=1.05 / Odds 10-20 / Value>=0` と乖離 (生成側と検証側で別物)。それでも 72 戦中 0〜2 件しか通らず、`relaxation` ヒントも見当たらない。フィルタが「実質詰み」状態。
- **校正済み確率の信頼性: 2/5** — `predictor/calibrator.json` source_count=512、bin 0.0-0.1 は count 317/99 で安定するが、bin 0.15-0.20 は count 27 で `calibrated_probability=0.3333` と raw 0.1725 から 2 倍弱に跳ね上がり明らかに過学習。0.25 以上の高確率帯 6 サンプル全体、0.45 以上は count=0 で完全に空白。直近 backtest 内 `calibration` (count 1004) でも 0.25-0.30 bin が actual 0.6667/wins 4 と振れすぎ、reliability diagram が階段状になっていない。`shrinkage_alpha=30` だが少数 bin が raw に張り付いており shrinkage が機能していないように見える。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **生成側と検証側の buy_filter を同一定数で参照させる** — `web/generator.py:31-34` の `BET_MIN_ODDS=2.0 / MAX=8.0 / MIN_VALUE=10.0 / MIN_EV=1.10` と backtest の既定 `Odds 10-20 / Value>=0 / EV>=1.05` が完全に別運用。これでは「フィルタを掛ければ勝てるのか」を測れない。`config.py` (or `predictor/__init__.py`) に `BUY_FILTER_DEFAULT` dict を 1 か所定義し、`_is_buy_candidate` と `scripts/predict.py`/`scripts/filter_sweep.py` 双方が同じ定数を import するよう統一。期待効果: 同条件下で 72 戦 → 数百戦規模に拡張すれば、2〜3 件しか出ない死フィルタの責任所在が確定する。
2. **`_investment_probability` の三段がけを 2 段に減らす** — `predictor/rules.py:821-827` の odds 別 discount は calibrator が既に bin 化で過大確率を抑える役割を担っているのに対し重複している。`weights.json:39-45` の `discount.base=0.92` 等を一旦 1.0 に置いた `--rule-version no-discount` backtest を 5/2-5/3 と長期 (3,180 戦) の両方で取り、現行 vs 無効化の `return_rate` 差を `data/backtest/` に並べて比較。期待効果: 三段目を外して回収率が改善するなら calibrator 単段で十分という結論が出て EV が正しく出る。逆に悪化するなら calibrator の少数 bin shrinkage が壊れている証拠。
3. **calibrator の少数 bin を強制的に raw 寄せ or 統合** — `predictor/calibrator.json` の bin 0.15-0.20 は count=27 で `calibrated_probability=0.3333` と raw の倍。`min_count=20` を 50 に引き上げ、未達 bin は隣接 bin と統合 or `calibrated = avg_probability` (恒等) に固定する shrinkage 強化を `_apply_calibrator` 側に追加。期待効果: 0.15-0.20 帯の過大評価 (= 偽の高 EV 候補) を抑え、`buy_only` の的中率 0.0% が改善する見込み。

## 前回からの差分

過去 scorecard なし (baseline 初回採点)。次回はこのスコアを基準に差分を出す。
