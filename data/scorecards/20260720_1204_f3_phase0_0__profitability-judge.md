# 収益性 / 投資判断専門家 採点 — F3 Phase 0-0

## 総合: 2.0 / 5（前回 3.8、差分 -1.8）

固定 pre-2026-07 OOS は **425 bets / 65 hits / 回収率 62.09% / 収支 -16,110円**。開催日 block bootstrap 95% CI は **[48.97%, 76.28%]** で、上限さえ JRA 単勝控除率の目安 80% を超えない。ルーブリックの「全体回収率 75% 未満は 1〜2点候補」「80%を超えない限り総合3以上不可」に該当する。Phase 0-0 は production を変えた改修ではなく、従来の 116.1%/3.8 点と異なる窓・戦略を測って不採算性を可視化したものなので、-1.8 は改修による悪化ではなく **より強い OOS 証拠への評価更新**である。

## 項目別

- **回収率（本丸）: 1/5（前回 5、-4）** — 425件とサンプルは十分だが 62.09%。100円均等なら投資42,500円、払戻26,390円、損失16,110円。日ブロック CI 上限76.28%も80%未満で、偶然の下振れだけでは説明しにくい。直近の意味ある OOS backtest も p25-v5 buy_only 194件/54.1%、p26-v6 123件/56.3%で同方向。最新 p26 calibration-fit成果物は buy_only 0件で投資判断には使えない。
- **EV計算の整合性: 2/5（前回 2、±0）** — OOS は `min_ev=None` / `min_value=None` だが、共通フィルタの `kelly_fraction > 0` により投資確率×オッズの正エッジ判定は残る。historical p21 isotonic calibrator と linear blend/discount を使う一方、`predictor/rules.py` は旧参照 SHA ではなく現行 p26。確率分布不一致を warning のまま適用するため、199→425件という候補数変化をリーク除去だけに帰属できない。`PRED_DISABLE_DISCOUNT=1` 対照も本成果物にはない。
- **Kelly fraction / 投資割合: 2/5（前回 2、±0）** — Kelly は候補の正エッジ判定にだけ使われ、賭け金は全件100円。5% cap の資金配分効果、最大ドローダウン、同日・同開催への相関集中は未評価。今回は各race top-1のみなのでrace内複数候補問題はない。
- **買い目フィルタの実用性: 1/5（前回 4、-3）** — 425件で詰みパターンではないが、回収率62.09%で実弾候補として不合格。旧199件から+113.6%増えており、同一窓・同一filter表記でも実際の選択集合は一致しない。新metricsには confidence別採用率・回収率、relaxation、bet ledgerがなく、どの層が37.91%の毀損を作ったか追えない。
- **校正済み確率の信頼性: 2/5（前回 2、±0）** — production calibrator は p26一致の isotonic、47,884件、118 knots、単調性あり。一方、今回OOSは旧参照と揃えるため p21 isotonic（48,058件）を M2-treatment/p26 rules に適用。比較条件としての意図は理解できるが、投資確率としては version mismatch。isotonic成果物にはbinごとの count / avg_probability / actual_win_rate がなく、高確率帯の標本数や reliability diagram を監査できない。

## 固定 OOS・CI・旧70.7%の検査

- split/seed: train 8,294 races / val 2,074 races、時系列末尾20%、seed 20260720、781 rounds。M2-control 112特徴、M2-treatment 109特徴で、差分は事前登録3件だけ。
- F3 OOS: 2026-01-01〜06-14、1,578 races、50 betting days、425 bets、65 hits、62.09%。日単位を復元抽出する10,000回 percentile bootstrap、seed 20260720。日内相関を保つ実装は妥当。
- 旧参照: 同じ表記窓で1,620 races、199 bets、29 hits、70.70%。今回との差は **-8.61pt** だが、race数 -42、bet数 +226、rules SHA相違のため非paired。旧CI [46.58%, 96.73%] は賭け単位bootstrap、新CIは開催日blockで、CI同士も同一手法ではない。
- 結論: **70.7%はM2-treatmentで再現したとは言えず、純リーク寄与のROI推定にも使えない**。言えるのは、現在の測定stackでは62.09%で、80%を統計的にも超えていないこと。

## 不変性・封印・再現性

- production 4 artifact は metrics の前後 SHA が一致し、現時点の再計算 SHA も after と全件一致。`production_artifacts_unchanged=true` を確認。
- OOS終端は20260614、封印開始20261001。日付guardは開始・終了のどちらかが封印域なら拒否し、対象テストも通過。
- `data/f3_phase0_0` のcontrol/treatment feature定義を比較し、除外は `same_day_bias_score` / `leg_quality_available` / `same_day_bias_available` の3件のみ。
- 検証: `.venv64/Scripts/python.exe -m pytest tests/test_f3_phase0_0_eval.py -q` → **5 passed**。`.venv32` は numpy 未導入でcollection不可（本スクリプトはlightgbmを使うため設計どおり64bit経路）。
- CIを第三者が軽量再計算できる日別集約/匿名bet ledgerが保存されておらず、完全再現には約83分のOOS再走が必要。

## 優先課題

1. **旧70.7%とのpaired比較を作る** — 旧SHAの rules/filter/list_races と同一race universeを固定し、control/treatment双方を同じ現行DB snapshot・同じ日block bootstrapへ通す。候補race/bet IDの差分も保存する。
2. **M2-treatment専用calibratorをTRAIN内だけでfit** — 現行の旧p21 mapping流用版と並べ、校正差で候補数・ROIがどれだけ動くか分離する。OOSでの再fitは禁止。
3. **監査可能な投資台帳を保存** — 日付、race key、候補、オッズ、校正前後確率、EV、Kelly、払戻、confidenceの日別集約を実験配下へ保存し、CI・confidence別ROI・flat対Kellyを短時間で再計算可能にする。

## 前回からの差分

- 総合 **3.8 → 2.0 (-1.8)**。回収率116.1%（41件、旧EVAL）から62.09%（425件、固定OOS）へ評価証拠が更新されたことが主因。
- EV/Kelly/校正の構造課題は 2点据置。今回の価値は、利益改善ではなくリークを含む見かけ性能を固定条件で測り、実弾投入不可を明確にした点。
- production挙動は不変なので、この採点低下をPhase 0-0のリリース回帰とは扱わない。
