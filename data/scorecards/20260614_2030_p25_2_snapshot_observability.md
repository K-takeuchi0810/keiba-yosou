# 採点 2026-06-14 20:30 — P25-2: backtest market_snapshot 観測性 + post-start guard + 年間目標180%

**改修内容**: P25 検証設計書作成 + backtest に market_snapshot 観測性追加 (fresh/stale/unknown/post_start counts, age分布, bonus候補数) + predictor/rules.py に post-start guard + docs/OPERATION.md 年間目標180%化
**対象ファイル**: `scripts/backtest.py`, `predictor/rules.py`, `tests/test_backtest_market_snapshot.py`, `tests/test_market_popularity_scoring.py`, `docs/P25_MARKET_POP_VALIDATION_PLAN.md`, `docs/OPERATION.md`

## 総合スコア (項目平均) の推移

| 専門家 | 今回 | 前回 (P25) | 差分 |
|---|--:|--:|---:|
| GUI / UX 監査人 | 3.8 | 3.8 | +0.0 |
| モバイル HTML レビュアー | 4.0 | 4.2 | -0.2 |
| 予想ロジック分析官 | 3.6 | 3.5 | +0.1 |
| 収益性 / 投資判断 | 2.5 | 2.0 | +0.5 |
| データパイプライン技術者 | 3.8 | 3.6 | +0.2 |
| コード品質 / 保守性 | 4.1 | 4.0 | +0.1 |
| 検証プロセス監査人 | 3.6 | 3.3 | +0.3 |
| **平均** | **3.63** | **3.49** | **+0.14** |

## 後退警告

- **モバイル HTML -0.2**: タップ領域の実測再計算で `.day-nav a` 33.1px (HIG 44pt 未達) を新たに検出。P25-2 は web ファイル無変更のため、前回の採点粒度不足が今回で補正された形。-0.3 未満のため GATE_FAILED には該当しない。

## 各専門家の所見

### GUI / UX 監査人 (3.8)

- P25-2 は `gui/app.py` を変更していない。前回の指摘 (II→III 依存可視化、market_snapshot_age_min 表示) は未是正のまま。
- JS パース PASS、状態整合性 (lock/cache_gen/cancel) に退行なし。
- 改善提案: II→III 依存を title 属性 + 動的ラベルで可視化、dashboard warnings に market_snapshot 統計を追加。

### モバイル HTML レビュアー (4.0)

- web ファイルへの変更ゼロ。HTML 出力への影響なし。
- 新規検出: `.day-nav a` タップ高さ 33.1px (HIG 44pt 未達)、waku-6/7/8 コントラスト 3:1 fail 継続。
- 改善提案: waku 色の AA 準拠化、`.day-nav a` に min-height:44px、市場人気 rationale の iOS Safari 向け可視化。

### 予想ロジック分析官 (3.6)

- post-start guard は機能的に正しい (両経路で fresh=False)。ただし rules.py は `None` 返し、backtest.py は負値返しでセマンティクスが非対称。
- 7/4/2 重みの ablation 証拠は依然なし (項目1・2 の上限を 3 に制約)。
- 改善提案: `_market_snapshot_age_min` の post-start/unknown 分離、popularity weights ablation 実施、`compute_features` の fallback 仕様テスト追加。

### 収益性 / 投資判断 (2.5)

- buy_only CI95=[0.0, 1.13]。ランダム購入と区別不能。実弾投入不可。
- post-start guard 追加で EV 計算整合性が改善 (+1)。ただし calibrator mismatch 継続。
- 既存 smoke JSON には `market_snapshot` キーが未存在 (P25-2 コード反映前の生成物)。
- 改善提案: market_snapshot 入り JSON の再生成、`_snapshot_age_min` 共有化、年間目標180%の根拠明記。

### データパイプライン技術者 (3.8)

- market_snapshot ブロックはインメモリ集計のみで DB 非汚染。クラッシュ一貫性は良好。
- post-start guard の非対称セマンティクス (rules: None, backtest: 負値) は意図的だが命名が紛らわしい。
- p90 分位数の floor-integer 近似は大規模 n では無視可能だが小規模テストで混乱源。
- 改善提案: 分位数関数の線形補間化、2実装の対応コメント、scope フィールドの意味をテストで固定。

### コード品質 / 保守性 (4.1)

- 新規5関数はすべて消費確認済み、dead code なし。
- `_popularity_config` の fallback 不一致は今回で解消。
- `_snapshot_age_min` (backtest) と `_market_snapshot_age_min` (rules) の二重実装が DRY 観点の上限を制約。
- テスト8件全 PASS (pytest 実行確認)、境界値カバレッジ良好。
- 改善提案: 2関数の共通モジュール化、post-start bonus 不適格の直接アサート追加。

### 検証プロセス監査人 (3.6)

- market_snapshot コード実装は具体的で追跡可能。ただし既存 smoke JSON にはキー未出力。
- calibrator fit/評価期間の非重複を JSON で実測確認。post-start guard は機能的に正しい。
- 設計書の 4-fold 定義と bootstrap サンプリング単位が未記載。
- 改善提案: market_snapshot 入り smoke run 再実行、fold 境界と bootstrap 単位の明記、calibrator refit 着手。

## 横断的に見た優先課題

1. **`_snapshot_age_min` 二重実装の統一** (担当: code-quality + prediction-logic + data-pipeline)
   - rules.py と backtest.py に同等ロジックが平行存在。post-start の返り値セマンティクスが異なる (None vs 負値)。
   - 共通モジュール化するか、最低限コメントで対応関係を明示する。

2. **market_snapshot 入り JSON の生成** (担当: validation-process + profitability)
   - 既存 smoke JSON (P25-2 コード前) には `market_snapshot` キーが存在しない。
   - P25-2 コードでの再実行が Step 1 完了の要件。

3. **設計書の fold 定義・bootstrap 単位の固定** (担当: validation-process)
   - 合格条件に「4-fold MIN」があるが fold 期間境界が未記載。実行前に固定しないと結果を見てから fold を選べる状態になる。
