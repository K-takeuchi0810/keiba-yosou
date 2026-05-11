# 予想ロジック分析官 採点

## 総合: 4.2 / 5 (前回 4.2 → 4.2, ±0)

## 項目別

- **シグナル網羅性: 4/5** — 改修 a/e は walk-forward (`scripts/`) と sweep のみで `predictor/` 配下は無編集。12 namespace 構成 (track_type / distance / course / class_level / had_grade_run_bonus / condition / jockey / trainer / going / time_signal / bloodline / recent_form) を維持。素点据え置き。
- **重み妥当性 / 過適合リスク: 4.5/5** — weights.json / calibrator.json に差分なし。今回 sweep (e) は読み出し専用で重み未更新、`_w()` 121 参照・直書き定数 -1000 (異常マーカー) のみの状態を継続。むしろ walk-forward (a) で「whitelist + 人気 1-4 + 信頼度除外」フィルタの汎化性能が時系列分割で検証されたことは過適合監視としてプラス材料。
- **信頼度判定 / 確率推定: 4.5/5** — `_apply_calibrator` / `_score_probabilities` / `_confidence` の本体は無編集。後段の「信頼度除外」フィルタが walk-forward で実用範囲を数値定義した形で、閾値運用の根拠が強化された。
- **デッドコード / 設計の整合性: 4.5/5** — dead feature 0 件を維持。`_score_one` 508 行の責務分割は今回スコープ外で未着手のため 5 まで届かない点も据え置き (継続課題)。
- **本番運用との乖離リスク: 3/5** — `leg_quality_*` のサイレント失敗・全 bin 恒等寄せ未検知ログは前回繰越のまま未着手。ただし sweep スクリプトは walk-forward 評価に組み込み可能な形なので、本番との乖離検出フックの土台にはなる。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **`_score_one` 508 行 → 軸別ヘルパへ分割 (前回繰越 #1)** — namespace 完了済なので `_score_track_type / _score_distance / _score_class_level / _score_blood / ...` の純粋関数 (戻り値 float) に切り出し、namespace 単位でテスト可能化。次回 P1-2 系で着手すれば項目 4 が 5 に届き総合 4.4-4.5 が射程。
2. **once-only 統合ログ + `min_count` 根拠コメント (前回繰越 #2)** — `_apply_calibrator` の `logger.warning` を `_load_calibrator` の `mtime` キャッシュキーに同期し「有効 bin=N / 恒等寄せ bin=M / 空 bin=K / `min_count`=50」を 1 行集計、項目 5 を +1 改善。
3. **sweep 結果の `weights.json._comment` への根拠スナップショット追記 (前回繰越 #3 強化)** — e の sweep 出力 (top 重み候補) を `weights.json` の各 `_comment` に「初期値の出所 (P1-1 ベースライン / sweep yyyy-mm-dd)」として 1 行追記。30 分以内で項目 2 を 5 に押し上げ可能。

## 前回からの差分

- シグナル網羅性: 4 → 4 (±0) 維持 — `predictor/` 無編集
- 重み妥当性 / 過適合リスク: 4.5 → 4.5 (±0) 維持 — weights 差分なし、walk-forward 検証は加点要素だが既に 4.5 上限近く
- 信頼度判定 / 確率推定: 4.5 → 4.5 (±0) 維持 — 本体無編集、フィルタ実用範囲の数値化は加点材料
- デッドコード / 設計の整合性: 4.5 → 4.5 (±0) 維持 — `_score_one` 分割未着手
- 本番運用との乖離リスク: 3 → 3 (±0) 維持 — `leg_quality_*` 課題未着手

## 補足

改修 a (walk-forward) + e (sweep) は `predictor/` 配下に差分なし。後段フィルタ「whitelist + 人気帯 1-4 + 信頼度除外」が時系列分割で検証され、ロジックの実用範囲が数値化された点は構造的妥当性に対する間接的な裏付け。担当範囲未変更のためスコア 4.2 維持。次回予想ロジック改修時に繰越 3 件 (優先 1 件は `_score_one` 分割) を消化したい。
