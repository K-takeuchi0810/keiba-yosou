# 予想ロジック分析官 採点

## 総合: 4.2 / 5 (前回 4.2 → 4.2, ±0)

## 項目別

- **シグナル網羅性: 4/5** — P2-1 はモバイル CSS のみで `predictor/` 無編集。前回確認の 12 namespace 構成 (track_type / distance / course / class_level / had_grade_run_bonus / condition / jockey / trainer / going / time_signal / bloodline / recent_form) を維持。素点据え置き。
- **重み妥当性 / 過適合リスク: 4.5/5** — `_w()` 参照 121 箇所・`score += <定数>` 直書き 1 件 (異常区分 -1000 マーカーのみ) の状態を維持。weights.json / calibrator.json も差分なし。
- **信頼度判定 / 確率推定: 4.5/5** — `_apply_calibrator` / `_score_probabilities` / `_confidence` 無編集。バックテスト数値も不変想定。
- **デッドコード / 設計の整合性: 4.5/5** — dead feature 0 件状態を維持。`_score_one` 508 行肥大の責務分割は今回スコープ外につき未着手で、5 まで届かない点も据え置き。
- **本番運用との乖離リスク: 3/5** — `leg_quality_*` のサイレント失敗・全 bin 恒等寄せ未検知ログは前回繰越のまま未着手。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **`_score_one` 508 行 → 軸別ヘルパへ分割 (前回繰越 #1)** — namespace 化が完了しているので `_score_track_type / _score_distance / _score_class_level / _score_blood / ...` の純粋関数 (戻り値: float) に切り出し、namespace 単位でテスト可能化。次回 P1-2 系で着手すれば項目 4 が 5 に届き総合 4.4-4.5 が射程。
2. **once-only 統合ログ + `min_count` 根拠コメント (前回繰越 #2)** — `_apply_calibrator` の `logger.warning` を `_load_calibrator` の `mtime` キャッシュキーに同期し「有効 bin=N / 恒等寄せ bin=M / 空 bin=K / `min_count`=50」を 1 行集計、項目 5 を +1 改善。
3. **重み既定値の根拠スナップショット (前回繰越 #3)** — `weights.json` の各 `_comment` に「初期値の出所 (P1-1 ベースライン / backtest A1)」を 1 行追記。30 分以内で項目 2 を 5 に押し上げ可能。

## 前回からの差分

- シグナル網羅性: 4 → 4 (±0) 維持 — 担当範囲未変更
- 重み妥当性 / 過適合リスク: 4.5 → 4.5 (±0) 維持 — weights.json 差分なし
- 信頼度判定 / 確率推定: 4.5 → 4.5 (±0) 維持 — 本体無編集
- デッドコード / 設計の整合性: 4.5 → 4.5 (±0) 維持 — `_score_one` 分割未着手
- 本番運用との乖離リスク: 3 → 3 (±0) 維持 — `leg_quality_*` 課題未着手

## 補足

P2-1 はモバイル CSS 専用改修で `predictor/` 配下に差分なし。担当範囲未変更のため前回スコア 4.2 をそのまま維持。次の予想ロジック改修時には繰越 3 件 (うち優先 1 件は `_score_one` 分割) を消化したい。
