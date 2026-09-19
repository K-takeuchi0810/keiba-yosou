# 予想ロジック分析官 採点

## 総合: 4.2 / 5（前回 4.0 → 今回 4.2、+0.2）

**判定: PASS**

> 評価対象: 最終HEAD `fa1d491` の F3 Phase 0-0/0-0b paired OOS evaluator、test、`paired_oos.json`、結果報告。初回評価後のcanonical出力allowlist・atomic write・入力保護・samples fail-fast・provenance差分を含む。`.Codex/agents/_rubric.md` は現 CWD に存在しないため、前回 `20260720_1204_f3_phase0_0__prediction-logic-analyst.md` の5軸を継承した。

## 今回 / 前回 / 差分

| 採点軸 | 今回 | 前回 | 差分 | 根拠 |
|---|---:|---:|---:|---|
| シグナル網羅性 | 4.5 | 4.5 | ±0.0 | control 112列、treatment 109列。除外は登録3列だけで追加0・順序維持。ただし `same_day_gate_bias_score` 等は対象外のまま残る。 |
| 重み妥当性 / 過適合リスク | 4.0 | 4.0 | ±0.0 | 重み変更なし。固定済みモデルと同一OOSを使い、結果を見て特徴・閾値・期間を動かしていない。単一seedで学習されたM2 pairという留保は前回同様。 |
| 信頼度判定 / 確率推定 | 4.0 | 4.0 | ±0.0 | val AUCを再現し、実運用stackのtop選択・filterを通してROIを比較。CIが0を含むことを「寄与しない」と断定する結論は、非有意と同等性を混同している。 |
| デッドコード / 設計整合性 | 4.9 | 4.5 | +0.4 | 既存 `_evaluate_oos` を再利用し、同じday indexを両系列で共有。exact-3、AUC再現、treatment OOS再現、production hash不変をfail-closed化。さらに入力/出力衝突防止、canonical出力固定、原子的書込み、samples正値検証を追加。top/filter差の帰属情報は不足。 |
| 本番運用との乖離リスク | 3.6 | 3.0 | +0.6 | 同一窓・filter・calibrator・rulesでcontrol/treatmentを比較でき、旧70.7%との非paired比較問題は解消。成果物の書込先をcanonical pathへ厳密固定しprovenanceも強化。ただしrule側のPOST-HIGH/PIT-UNPROVEN経路は残り、全stackのde-leaked baselineではない。 |

## 必須観点の検査

- **exact-3 artifact: PASS** — `m2_control_features.json` 112列に対し treatment は109列。差分は `same_day_bias_score` / `leg_quality_available` / `same_day_bias_available` のみ、追加列なし、残存順序も一致。model/feature SHA-256 と evaluator SHA-256 は `paired_oos.json` と実ファイルで一致した。
- **決定性AUC: PASS（軽微な留保）** — control `0.7913195088860858`、treatment `0.7887806982333265` を再現。test は固定値を `abs=1e-10` で確認する。ただし実行時 gate 自体の許容差は `1e-5` で、比較対象はAUCだけ。Brier/LogLoss/top-1や「元の保存時model hash」との一致はgateしない。
- **paired bootstrap: PASS** — 反復ごとに1個の `indices` を作り、control/treatmentの賭金・払戻を同じ開催日block標本で集計してからROI差を算出。B=10,000、seed固定。basis (a) の `d=+1.0191pt`、95%CI `[-4.6737pt,+6.4106pt]` は実装とartifactで整合する。
- **安全差分: PASS** — paired JSON/reportの同一パスとproduction/参照/cache/学習成果物への衝突を拒否し、JSONは `data/f3_phase0_0/paired_oos.json`、reportは `docs/F3_phase0_0b_result.md` へ厳密固定。両出力を同一ディレクトリ内の一時ファイルから原子的に置換し、`samples <= 0` はOOS前に停止する。artifactの `evaluator_commit=af13474...` と `evaluator_sha256` は長時間評価を実際に実行したcommit内容と一致する。
- **top選択とfilter差: PARTIAL** — basis (a) のunionは471 races、control 424 bets、treatment 425 betsなので、集合算術上はintersection 378、control-only 46、treatment-only 47。basis (b-1)/(b-2) は各共通レース集合で両モデルのROI日次系列が完全一致し、差はともに0。ただしartifactは `horse_num` 一致数、top変更数、filter判定の2×2表、反転理由を保存しないため、「top差が0で93件はfilterだけが反転」とは証明できない。
- **basis (b) の解釈: 要明記** — treatment-selectedまたはcontrol-selectedのレース集合を固定し、相手モデルも自身のtop馬を強制的に1点購入した反実仮想感度分析である。相手側の `is_buy_candidate` は無視するため運用policy ROIではなく、選択モデルに条件付けられた非対称なtop結果比較。両方向を出す設計は妥当だが、表のラベルだけではこの意味が伝わりにくい。
- **結論の強さ: FAIL寄りのPARTIAL** — CIが0を含むので言えるのは「この50開催日OOSと自己選択policyではROI差を統計的に検出できなかった」。同等性マージン/TOSTや事前に許容した最大寄与幅がないため「3チャネルはROIに有意寄与しない」「correctness章を閉じる」は強い。さらに `de-leaked baseline=M2-treatment` は3 ML列だけのablationで、共通rule blendの `same_day_bias_score`、`same_day_gate_bias_score`、raw `leg_quality_code` 等を除去していない。

## 構造的評価

- シグナル自体の網羅性は前回から不変。今回の価値は新しい予想シグナルではなく、同一OOSでの比較可能性を回復した点にある。
- `rules.py` の直書き `score +=/-=` は `score -= 1000` の異常馬マーカー1件。`weights.json` は24 top-level keysで、今回の変更によるmagic number/dead featureの新規回帰はない。
- `_evaluate_oos(..., include_ledger=True)` で同一race ledgerを作り、race ID集合不一致を停止する設計は良い。treatmentを先に再実行して 425 bets / 65 hits / 62.0941% を再現できなければcontrolを走らせない点もfail-closed。
- 最終安全差分はprediction出力やROI値を変更せず、誤った書込先、部分書込み、無効なbootstrap件数を評価開始前に止める。`evaluator_commit` が最終HEADでなく `af13474` なのは不整合ではなく、約3時間のOOSを実行したコードを指す正しいprovenanceである。
- self-selected basis は各policyの現実的なROI差を推定する。一方、filter閾値近傍で予測値が動くと賭け集合が大きく変わるため、AUC/top-1差が小さくてもROI policy差が小さいとは限らない。今回も純粋な件数差は1件だが、集合差は93件である。
- `paired_oos.json` は `.gitignore` の `data/*` 対象、`F3_phase0_0b_result.md` は未追跡。evaluator SHAは再現性を補うが、確定baselineとして引き継ぐならartifact/reportの保存・参照方法を明文化する必要がある。

## 優先課題

1. **結論を非有意の範囲へ弱める** — 「有意寄与しない」ではなく「有意なROI差を検出できなかった」。correctnessを閉じるなら、実務上の同等性マージンを事前定義してTOSTまたはCI全体がその範囲内かで判定する。
2. **top差とfilter差をartifact化** — `top_same/top_changed`、`both_bet/control_only/treatment_only/neither`、同一top時のfilter反転、反転理由（odds/value/confidence等）、日別差分を保存する。basis (b) が0になった理由を集計値ではなく機構で説明する。
3. **baseline名称を限定する** — `de-leaked baseline` を `exact-3 ML-feature ablation baseline` へ変更し、rule側残存経路と `same_day_gate_bias_score` を明記する。
4. **決定性gateを強化する** — 保存元のexpected model/feature SHA、AUC/Brier/LogLoss/top-1、LightGBM versionを固定し、bootstrapの非ゼロ差・basis (b)・filter反転ケースもunit testへ追加する。

## 検証メモ

- 最終HEAD `fa1d491`: JSONをcanonical pathへ固定し、任意 `output_dir` の留保を解消。先行差分 `d4a4dcc` / `5b4d43d` / `655d5d0` と合わせ、予想シグナル・重みの変更なし。
- 必須weights確認: 24 top-level keys。magic-number検出: `predictor/rules.py:580 score -= 1000` の1件。
- `pytest tests/test_f3_phase0_0_eval.py -q`: **11 passed in 3.08s**。全体suiteは親実行で **377 passed**。
- production artifact前後SHA一致、sealed holdout未アクセス、今回のレビューでは指定scorecard以外を変更していない。
- 前回比は **+0.2**。-0.3以上の回帰警告は該当なし。
