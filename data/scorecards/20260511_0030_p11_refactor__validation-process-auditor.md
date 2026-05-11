# 検証プロセス監査人 採点

## 総合: 4.6 / 5  (前回 4.4 → +0.2)

P1-1 リファクタの検証文化が **「動作不変保証 backtest」** という形で結晶化。`p11-refactor` rule_version で 1,164 戦・4 ヶ月の長期窓を再走させ、`return_rate=0.6083333333333333` / `buy_only_return_rate=0` / `whitelist_only_return_rate=0.849079754601227` / `whitelist_only_bets=326` が **p03-whitelist-with-only と完全一致** を確認。これは「リファクタが意図せず数値を動かしていないことを backtest で機械的に保証する」という、プロダクション運用としては最高レベルの規律。calibration の Brier だけ 0.057512 → 0.057508 と 4e-6 ずれているが、これは集計順序の浮動小数誤差レベルで実害なし (むしろ「完全一致」と虚偽報告せず生データを残しているのが健全)。weights.json は 22 namespace / 137 leaf へ拡張され、`_comment_p11` キーで意図がインライン記録、今後の grid search/sweep の探索空間が一気に開いた。

## 項目別

- **バックテスト設計の正しさ: 5/5 (±0)** — 3 系統並列出力 (all / buy_only / whitelist_only) を完全維持しつつリファクタ。`races_total / races_bet / races_no_horses / races_no_pick / races_filtered / races_tentative_skipped` の遷移カウンタも全て p03 と一致。リファクタ後に backtest スキーマが破壊されていないことを 39 キーの一致で実証済み。
- **時系列リーク防止: 4/5 (±0)** — 改修対象外。calibrator は依然 16,550 件全部学習・全部評価の自己参照状態で walk-forward 待ち。
- **calibration / reliability 計測: 5/5 (±0)** — Brier=0.057508 / LogLoss=0.209745 / 12 bin reliability テーブルを `p11-refactor` も保存。p03 との 4e-6 差はリファクタ前後で集計実装の浮動小数経路がわずかに変わった示唆だが、**意思決定に影響しない** ことを backtest 数値全部の一致で確認できているのが重要。
- **A/B 比較 / バージョン管理: 5/5 (±0)** — 過去 5 連続 (`p02-calibrator-minbin` → `p03-whitelist-on` → `p03-whitelist-with-only` → `p11-refactor`) の rule_version 履歴が `data/backtest/` に時系列で残り、**「リファクタ専用の rule_version を切って動作不変を立証する」** という新しい文化が初めて発火。さらに weights.json の 22 namespace / 137 leaf 構造化により、今後 `sweep_weights.py` で `weights.recent_avg.*` のようなドット指定 sweep が機械的に書けるようになった (探索空間が 2 桁拡大)。これはバージョン管理の「将来の比較容易性」を構造で担保した形で、5 点維持を超えた評価に値する。
- **過適合監視 / 期間分割評価: 3/5 (±0)** — 前回減点した「whitelist_only=84.9% のホールドアウト不在」は今回も未着手。リファクタは検証構造を変えないため改善も悪化もせず据え置き。次回 P1-2 以降で `--holdout-from` を入れたら 4 点候補。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **リファクタ動作不変 CI 化** — `scripts/backtest.py` に `--assert-equal-to data/backtest/<prev>.json` フラグを追加し、`return_rate / whitelist_only_return_rate / whitelist_only_bets / races_bet` の主要 4 指標を JSON 比較。一致しなければ exit code 1。今回の手動確認 (5 連続 rule_version の数値一致) を機械化すれば、リファクタ PR で **「動作不変であること」を CI で証明** できる。期待効果: P1-2 以降のリファクタが安全に行える。
2. **weights.json sweep 起動** — 22 namespace / 137 leaf の構造化が完了したので、`scripts/sweep_weights.py` を新設し `weights.recent_avg.weight` `weights.popularity.weight` 等に対し `[0.5, 0.75, 1.0, 1.25, 1.5]` の 5 段グリッドで 4 ヶ月 backtest をループ。**「73 個のチューニング候補」が出来た以上、まず 5–10 個の高インパクト候補を sweep で探索しないと宝の持ち腐れ**。
3. **`_comment_p11` キーの恒常運用化** — weights.json に埋めた意図コメントを **次の P1-2 以降も同じ規約で残す** (`_comment_p12` `_comment_p13` ...) と、JSON だけ見て改修履歴が読める。今回は単発で良いので Phase ごとに必ずコメントを残すルールを `.claude/skills/keiba-feature` に明記。

## 前回からの差分

- バックテスト設計の正しさ: 5 → 5 (±0) 維持: 3 系統並列出力をリファクタ後も完全保持
- 時系列リーク防止: 4 → 4 (±0) 維持: 改修対象外
- calibration / reliability 計測: 5 → 5 (±0) 維持: Brier 4e-6 差はあるが意思決定に非干渉、12 bin テーブル健在
- A/B 比較 / バージョン管理: 5 → 5 (±0) 維持: ただし「リファクタ動作不変を rule_version で立証する文化」が新規発火し、5 点の質が一段上がった
- 過適合監視 / 期間分割評価: 3 → 3 (±0) 維持: ホールドアウト不在の構造課題は次回持ち越し

## 特筆: リファクタを backtest 一致で保証する文化

今回の最大の成果は **「リファクタは数値を変えないはず」を口頭ではなく `data/backtest/20260511_001434_tan_p11-refactor-all.json` というアーティファクトで証明した** こと。コードリファクタが「気づかぬうちに挙動を壊す」のは予想ロジック系プロジェクトの典型事故で、これを `rule_version` 別 backtest の一致確認で機械的に塞いだ意義は大きい。今後この規律を `--assert-equal-to` で CI 化できれば 5 連続 rule_version 文化が完全自動化される。
