# 検証プロセス監査人 採点 — F3 Phase 1 readiness

**最終対象commit**: `cb56778119b3998510820116510d2fc87bad8f0d`（初回 `5ba3808`）  
**対象**: `scripts/f3_phase1_readiness.py`, `tests/test_f3_phase1_readiness.py`, `data/f3_phase1_readiness/dev_odds_coverage.json`, `docs/F3_phase1_readiness.md`

## 総合: 4.8 / 5 — **PASS（測定実装） / Phase 1 kickoff は HOLD**

- 初回readinessレビュー: 4.6 → **+0.2**。
- 直前トピック（F3 Phase 0-0b paired OOS）: 4.8 → **±0.0**。回帰警告なし。
- `cb56778` でdev開始日の固定、consistent read transaction、JRA中央/その他の母集団内訳、凍結設計SHA前後照合、一意temporary pathを追加。PIT coverage のread-only棚卸しとして再現可能で、封印・production・凍結設計不変を機械的に確認できる。一方、`drift_computable=19`、`wide_drift=0` のため、7モデル比較を始める母集団としては不足している。

## 項目別

| 採点軸 | 点 | 根拠 |
|---|---:|---|
| PIT判定・lead計算 | 5/5 | 適格判定を `predictor.pit_gate.usable_snapshots` に一本化し、`pit_cutoff` も発走時刻解釈に再利用。馬ごとの行数ではなく `fetched_at` の異なる時刻をdeduplicateし、leadは発走時刻との差で計算。T-10未満が返ればfail-fastする。 |
| 封印・read-only・不変条件 | 5/5 | `from_date`を`20260704`に固定し、`to_date >= 20261001` を拒否してから対象レースSQLへ進む。DBは `open_db_readonly`（URI `mode=ro`、fallbackでも`query_only=ON`）で、`BEGIN`後の一貫したread snapshotから全測定を取る。production 4成果物と凍結設計文書のSHAを前後照合する。 |
| 母集団・分母定義 | 5/5 | 総レース225、出馬表あり225を分離し、coverage率の分母を出馬表ありに固定。さらに中央場01-10の216件（drift 19、8.80%）とその他trackの9件（drift 0）をJSON/reportに明示し、全体19/225=8.44%との関係を追跡可能にした。 |
| 日別トレンド | 5/5 | 日別の総数・出馬表・usable・drift・wideを保存し、前後半差と暦日回帰傾きを併記。10 race dates中、実際にusableがあるのは7/18・7/19だけという事実がJSONから追えるため、「improving」は記述統計と明記した範囲では妥当。 |
| 外挿・readiness解釈 | 4/5 | `+76/4週` は「週2日×active day平均9.5」の参考値と明記し、判定に使わない。基礎がactive 2日だけで区間推定・欠測率調整がなく、収集停止や開催差を反映しないため、計画値としての使用は禁止が妥当。これが唯一の減点軸。 |

## 実測整合性

- 窓: `20260704`–`20260719`、T-10。225/225レースに出馬表、usable 71（31.56%）、異時刻2点あり19（8.44%）、wide drift 0。中央場は216件、drift 19（8.80%）、その他は9件、drift 0。
- earliest lead中央値は全体19.95分、午前19.95分、午後19.96分。post-cutoff違反は0。
- 19レースはすべて2時点で、各時点のhorse snapshot行数が当該レースの出馬頭数と一致した。ただしコードはsnapshot completenessを明示的な条件・出力にはしていないため、将来の部分スナップ混入防止は残課題。
- 日別drift率は7/18=25.0%、7/19=27.78%、それ以前8日=0%。前半0.0%→後半10.56%、傾き+0.108 rate/weekは計算どおりだが、収集開始の段差を一般的な上昇トレンドとは解釈しない。
- JSONの`git_sha`は最終commit `cb56778` と一致。凍結設計SHAはbefore/after/currentすべて `8ad55711...18a8`、production 4成果物も前後一致。focused testsは **10 passed**、親実行の全体テストは **371 passed, 4 skipped**。

## 最終安全性確認

- `_validate_window` は開始日が`20260704`以外なら拒否し、封印開始日以降も拒否する。
- read-only接続で`PRAGMA query_only=1`を確認後、`BEGIN`して対象レース・スナップを同一DB snapshotから読む。
- JSON/reportはUUID付き同一directory temporary fileからatomic replaceし、競合する固定`.tmp`を使わない。
- JSONは`consistent_read_transaction=true`、`frozen_design_unchanged=true`、`production_artifacts_unchanged=true`、`sealed_holdout_accessed=false`を記録し、独立contract照合も通過。

## 残課題

1. 各時点の出馬頭数カバレッジを機械可読で記録し、2つの完全または事前定義coverage以上のsnapshotだけをdrift-computableとする。今回の19レースは独立照合で全時点が完全だったため非HOLD。
2. 外挿は少なくとも複数週のactive dayを蓄積後に更新し、観測日bootstrapまたはPoisson区間と欠測日シナリオを併記する。
3. Phase 1判断をJRA中央に限定するなら、日別トレンドも`jra_central`だけで並列出力し、全DB母集団との混同を完全に避ける。

## 判定

**最終測定実装はPASS**。実運用PITゲート、固定dev窓、封印ガード、consistent read transaction、母集団内訳、production/凍結設計不変、provenanceは堅い。  
**Phase 1の7モデル比較着手はHOLD**。現時点の異時刻2点母集団は19レース、60分以上のwide driftは0であり、モデル比較・walk-forward・特徴選抜を支える規模に達していない。朝アンカー要否は「広窓が現状ゼロ」という材料までは確立したが、タスク登録判断はhuman-in-loopに残す。
