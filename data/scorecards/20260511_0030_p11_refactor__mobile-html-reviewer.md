# モバイル HTML レビュアー 採点

## 総合: 3.4 / 5 (前回 3.4 → 3.4, ±0)

> **ブロック条件到達: モバイル HTML 改修が 5 連続未着手** (P0-1 / P0-2 / P1-3 / P0-3 / P1-1)。今回 P1-1 は `predictor/` 内部リファクタで `web/templates/` `web/generator.py` には変更なし。前回優先 1〜3 (ダークモード CSS 変数化 / `<details>` 開閉インジケータ / `theme-color` メタ) は **5 改修連続据え置き**。次回改修で `web/` 圏外なら品質追跡上の機能不全とみなし、expert-review 通過をブロックする運用に切替を提案する。

## 項目別

- **レスポンシブ / メディアクエリ: 4/5** — テンプレ完全不変。viewport / `@media (max-width: 480px)` / 481-600px 二段優先度・`max-width: 720px` 中央寄せはそのまま。
- **タップ領域 / 操作性: 3/5** — `.buy-card` / `summary.race-head` の `min-height: 44px` 維持。`::-webkit-details-marker { display: none }` の不可視化が **5 連続据え置き**で開閉が指で予測しづらい状態継続。
- **情報密度 / 可読性: 4/5** — `predictor/rules.py` リファクタは出力 dict キー不変想定のため、build_view_model 経由で j2 に流れるフィールド構造・桁数・印フォーマットは同一。密度維持。
- **ダークモード / コントラスト: 2/5** — `.buy-board { background: #fff8f7 }`、`.conf-tag` 固定灰背景、`prefers-color-scheme: dark` 未上書きが残存。**5 改修連続未着手** — 最重要積み残し。
- **iOS / iCloud 経由特有の互換: 4/5** — `apple-mobile-web-app-capable=yes` / `-webkit-overflow-scrolling: touch` / 外部リソース無依存は維持。`mobile-web-app-capable` 併記、`theme-color`、`apple-mobile-web-app-status-bar-style` 依然欠如。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **ダークモード時のハードコード色を CSS 変数化** (前回優先 1 から **5 連続**継続) — `web/templates/index.html.j2:59` `.buy-board { background: #fff8f7 }`、`:73 .buy-card`、`:190 .conf-tag` の固定色を `--buy-bg / --buy-card-bg / --tag-bg` に置換し、`@media (prefers-color-scheme: dark)` 内で再定義。**ブロック条件発動** — 次回改修ではこの 1 件着手を必須化提案。
2. **`<details>` の開閉インジケータを CSS で復元** (前回優先 2 から **5 連続**継続) — `summary.race-head::after { content: '▼' }` + `details[open] summary::after { transform: rotate(180deg) }`。
3. **`<meta name="theme-color">` light/dark 二本追加** (前回優先 3 から **5 連続**継続) — `index.html.j2:7` 付近で iOS タブ識別性 / ステータスバー一体感を低コスト改善。

## 前回からの差分 (前回スコアがあれば)

- レスポンシブ / メディアクエリ: 4 → 4 (±0) 維持 — テンプレ未変更。
- タップ領域 / 操作性: 3 → 3 (±0) 維持 — テンプレ未変更。
- 情報密度 / 可読性: 4 → 4 (±0) 維持 — predictor 内部リファクタは view model フィールド構造に影響せず。
- ダークモード / コントラスト: 2 → 2 (±0) 維持 — CSS 未変更、優先 1 が **5 連続**未着手。
- iOS / iCloud 経由特有の互換: 4 → 4 (±0) 維持 — メタ未追加。

総合: 3.4 → 3.4 (±0)。P1-1 は `predictor/rules.py` の関数分割等の内部リファクタで `web/` 圏完全不変につき全 5 軸据え置き。**5 改修連続 (P0-1 / P0-2 / P1-3 / P0-3 / P1-1) でモバイル改善積み残し** — ブロック条件到達。次回スコアアップには優先 1 (ダークモード CSS 変数化) 着手が必須。
