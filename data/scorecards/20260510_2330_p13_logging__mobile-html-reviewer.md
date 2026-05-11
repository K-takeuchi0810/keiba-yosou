# モバイル HTML レビュアー 採点

## 総合: 3.4 / 5 (前回 3.4 → 3.4, ±0)

> **警告: モバイル HTML 改修が 3 連続未着手** (P0-1 延長 → P0-2 calibrator min-bin → P1-3 logging)。前回優先 1〜3 (ダークモード変数化 / details インジケータ / theme-color) が 3 改修連続で据え置き。次回も `web/` 圏外なら、品質追跡として警告ではなくブロック扱いにすべき水準。

## 項目別

- **レスポンシブ / メディアクエリ: 4/5** — 今回の P1-3 改修は logging 導入 (おそらく `predictor/` か `jvlink_client/` 圏内)。`web/templates/index.html.j2` `web/generator.py` ともに変更なし。viewport / `@media (max-width: 480px)` / 481–600px 二段優先度・`max-width: 720px` 中央寄せはそのまま。
- **タップ領域 / 操作性: 3/5** — `.buy-card` / `summary.race-head` の `min-height: 44px` 維持。`::-webkit-details-marker { display: none }` で開閉インジケータ不可視・`<details>` 間 `margin-bottom: 0.5rem` のみで誤タップ懸念は前回優先 2 のまま 3 連続据え置き。
- **情報密度 / 可読性: 4/5** — テンプレ未変更。logging 改修は HTML 出力フィールドに到達しないため、表示密度・桁数・印フォーマットは完全に同一。
- **ダークモード / コントラスト: 2/5** — `.buy-board { background: #fff8f7 }`、`.conf-tag` の固定灰背景、`prefers-color-scheme: dark` 未上書きが残存。前回最重要積み残し (ハードコード色 → CSS 変数化) は 3 改修連続で着手なし。
- **iOS / iCloud 経由特有の互換: 4/5** — `apple-mobile-web-app-capable=yes` / `-webkit-overflow-scrolling: touch` / 外部リソース無依存は維持。`mobile-web-app-capable` 併記、`theme-color`、`apple-mobile-web-app-status-bar-style` は依然欠如。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **ダークモード時のハードコード色を CSS 変数化** (前回優先 1 から **3 連続**継続) — `index.html.j2:59` `.buy-board { background: #fff8f7 }`、`:73 .buy-card`、`:190 .conf-tag` の固定色を `--buy-bg / --buy-card-bg / --tag-bg` に置換し、`@media (prefers-color-scheme: dark)` 内で再定義。これ以上の据え置きは品質追跡上の機能不全。
2. **`<details>` の開閉インジケータを CSS で復元** (前回優先 2 から **3 連続**継続) — `summary.race-head::after { content: '▼' }` + `details[open] summary::after { transform: rotate(180deg) }` を追加。
3. **`<meta name="theme-color">` light/dark 二本追加** (前回優先 3 から **3 連続**継続) — `index.html.j2:7` 付近で iOS タブ識別性 / ステータスバー一体感を低コストで向上。

## 前回からの差分 (前回スコアがあれば)

- レスポンシブ / メディアクエリ: 4 → 4 (±0) 維持 — テンプレ未変更。
- タップ領域 / 操作性: 3 → 3 (±0) 維持 — テンプレ未変更。
- 情報密度 / 可読性: 4 → 4 (±0) 維持 — logging は出力 HTML に到達しない。
- ダークモード / コントラスト: 2 → 2 (±0) 維持 — CSS 未変更、優先 1 が 3 連続未着手。
- iOS / iCloud 経由特有の互換: 4 → 4 (±0) 維持 — メタ未追加。

総合: 3.4 → 3.4 (±0)。今回の P1-3 logging 導入は `web/` 担当範囲外のため全 5 軸据え置き。**直近 3 改修 (P0-1 / P0-2 / P1-3) すべてでモバイル改善が積み残し**となっており、次回スコアアップには優先 1 (ダークモード CSS 変数化) への着手が事実上必須。
