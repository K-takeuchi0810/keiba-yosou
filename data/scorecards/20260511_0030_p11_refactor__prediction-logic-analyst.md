# 予想ロジック分析官 採点

## 総合: 4.2 / 5 (前回 3.6 → 4.2, +0.6)

## 項目別

- **シグナル網羅性: 4/5** — シグナル本体に増減なし。ただし weights.json に 12 namespace (`track_type / distance / course / class_level / had_grade_run_bonus / condition / jockey / trainer / going / time_signal / bloodline / recent_form`) が新設され、各シグナルが「どの軸の重み」かが命名で見えるようになり実験可能性が上がった。素点据え置き。
- **重み妥当性 / 過適合リスク: 4.5/5** (前回 3 → 4.5, +1.5) — `_w()` 経由参照が **48 → 121 箇所 (× 2.5)** に拡大、`score += <定数>` 直書きは **1 件のみ** (`score -= 1000` 異常区分マーカー、コメント明示) まで圧縮。各 namespace に `_comment` キーが入り「距離 ±100m / ロングバケット」「n>=30」など適用条件まで自己文書化されている。残り課題は「既定値の根拠 (なぜ `track_type.win_per_count=5` なのか) を CHANGELOG 化」程度で、過適合リスクは外側から weights.json を差し替えるだけで A/B 比較できる構造に到達した。模範的の 5 まで届かないのは、まだ既定値そのものの妥当性 (= calibration) は backtest 一致でしか担保されていないため。
- **信頼度判定 / 確率推定: 4.5/5** — `_apply_calibrator` / `_score_probabilities` / `_confidence` 本体は無編集 (バックテスト数値が P0-3 完全一致で確認済み)。素点維持。
- **デッドコード / 設計の整合性: 4.5/5** (前回 3 → 4.5, +1.5) — **dead feature 0 件** を script で機械的に確認 (`features.py` で `feat[]=` 代入された全特徴量が `feat.get()` で参照されている)。前回繰越されていた `weight_trend / recent_avg_starters / same_day_leg_bias / same_day_leg_samples` 4 件 + 内部追加 1 件の計 5 件が完全除去。ただし `_score_one` は依然 508 行 (前回 491 行から +17 行) と肥大しており、責務分割は未着手なので 5 まで上げられない。
- **本番運用との乖離リスク: 3/5** — `same_day_leg_*` 削除で「後付けデータに依存する後段シグナル」の母数が 1 軸減ったのは加点要素だが、`leg_quality_*` のサイレント失敗・全 bin 恒等寄せの未検知ログは未着手なので前回どおり 3 維持。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **`_score_one` 508 行 → 軸別ヘルパへ分割** — 今回 namespace 化が完了したので、`_score_track_type(feat) / _score_distance(feat) / _score_class_level(feat) / _score_blood(feat) / ...` のようにドメイン軸ごとの純粋関数 (戻り値: float) に切り出せば、テストも namespace 単位で書ける。score 加算は呼び出し側で `score += _score_distance(feat)` と一括。期待効果: レビュー単位が「軸 1 つ」に閉じる / 単体テストを namespace 別に追加できる / `weights.json` の \_comment と関数 docstring が 1:1 対応。
2. **once-only 統合ログ + `min_count` 根拠コメント (前回繰越 #1, #3)** — calibrator 周りは今回の P1-1 対象外なので前回優先 1, 3 そのまま繰越。`_apply_calibrator` の `logger.warning` を `_load_calibrator` の `mtime` キャッシュキーに同期し、「有効 bin=N / 恒等寄せ bin=M / 空 bin=K / `min_count`=50 (= 2024 年 OP 平均出走頭数 14 × 3 R 程度)」を 1 行集計、ログ氾濫と全 bin 恒等寄せのサイレント失敗を同時解決。
3. **重み既定値の根拠スナップショット** — `weights.json` の各 `_comment` に「適用条件」だけでなく「初期値の出所 (= P1-1 時点でのドメイン仮説 / backtest A1 ベースライン)」を 1 行追記。次回チューニング者が「動かして良い数字 / バックテスト一致の制約で固定すべき数字」を判別できる。実装は単なるコメント追記なので 30 分以内。

## 前回からの差分

- シグナル網羅性: 4 → 4 (±0) 維持 — 軸の追加削除なしだが namespace 化で可読性向上
- 重み妥当性 / 過適合リスク: 3 → 4.5 (+1.5) 大幅改善 — magic number 直書きが 60+ → 1 件 (意図的 -1000 マーカーのみ)、`_w()` 参照 48 → 121、12 namespace 追加で外出し率が決定的に改善
- 信頼度判定 / 確率推定: 4.5 → 4.5 (±0) 維持 — 本体無編集 (backtest P0-3 と完全一致)
- デッドコード / 設計の整合性: 3 → 4.5 (+1.5) 大幅改善 — dead feature 5 件完全除去 (機械検証で 0 件確認)、ただし `_score_one` 508 行肥大は据え置きで 5 まで届かず
- 本番運用との乖離リスク: 3 → 3 (±0) 維持 — `same_day_leg_*` 系除去は微加点だが、`leg_quality_*` サイレント失敗の繰越課題が変わらないため素点据え置き

## 補足

P1-1 リファクタは「磁石となっていた magic number と dead feature を一気に整理する」改修で、5 連続繰越されていた優先課題のうち 2 件 (magic number 移管 / dead feature 削除) が同時に決着した。総合 3.6 → 4.2 の +0.6 は、項目 2 と 4 が両方 +1.5 跳ねたため (5 軸平均で +0.6)。

特筆点として、weights.json の各 namespace に `_comment` 行が入り「適用条件 (n>=30 / 距離 ±100m / OP・重賞)」が JSON 内で自己文書化された。これは新規読者が「この重みを動かしていいのか」を判定するうえで実利が大きく、項目 2 の素点を 4 ではなく 4.5 にした主因。

未消化の課題は 1 件のみ: **`_score_one` 508 行の責務分割**。namespace 化が終わった今、軸別ヘルパへの切り出しは「リネーム + ブロック移動」で済むので、次回 P1-2 系の改修で着手すれば項目 4 が 5 に届き、総合 4.4-4.5 が射程に入る。
