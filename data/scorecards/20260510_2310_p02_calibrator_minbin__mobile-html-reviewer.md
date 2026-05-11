# モバイル HTML レビュアー 採点

## 総合: 3.4 / 5 (前回 3.4 → 3.4, ±0)

## 項目別

- **レスポンシブ / メディアクエリ: 4/5** — `web/templates/index.html.j2` と `web/generator.py` に今回の改修 (P0-2 calibrator min-bin / P0-1 延長) は到達していない。viewport / `@media (max-width: 480px)` / 481–600px の二段優先度・`max-width: 720px` 中央寄せはそのままで、レイアウト挙動は前回と完全に同一。
- **タップ領域 / 操作性: 3/5** — `.buy-card` / `summary.race-head` の `min-height: 44px` 維持。`::-webkit-details-marker { display: none }` で開閉インジケータが見えない問題、`<details>` 間 `margin-bottom: 0.5rem` のみで誤タップしやすい問題はいずれも未着手 (前回優先 2 がそのまま残置)。
- **情報密度 / 可読性: 4/5** — 買い候補カードのフィールド構成 (馬番 / 印 / 馬名 / オッズ / 人気 / P / EV / K) は不変。calibrator 側の変更で各馬の P (= キャリブ後確率) の値域は若干変わる可能性があるが、表示テンプレ・桁数フォーマットは変わらないため、モバイル単体の視認性スコアには影響しない。`buy_count` の表示も既存どおり。
- **ダークモード / コントラスト: 2/5** — `.buy-board { background: #fff8f7 }`、`.conf-tag` の固定灰背景、`prefers-color-scheme: dark` 配下での上書き欠如はそのまま残存。前回最重要積み残しの「ハードコード色 → CSS 変数化」は未着手。
- **iOS / iCloud 経由特有の互換: 4/5** — `apple-mobile-web-app-capable=yes` / `-webkit-overflow-scrolling: touch` / 外部リソース無依存は維持。`mobile-web-app-capable` 併記、`theme-color`、`apple-mobile-web-app-status-bar-style` の欠如も依然解消されず。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **ダークモード時のハードコード色を CSS 変数化** (前回優先 1 から継続) — `index.html.j2:59` `.buy-board { background: #fff8f7 }`、`:73 .buy-card`、`:190 .conf-tag` の固定色を `--buy-bg / --buy-card-bg / --tag-bg` に置換し、`@media (prefers-color-scheme: dark)` 内で再定義。2 改修連続で据え置きなのでそろそろ着手したい。
2. **`<details>` の開閉インジケータを CSS で復元** (前回優先 2 から継続) — `summary.race-head::after { content: '▼' }` + `details[open] summary::after { transform: rotate(180deg) }` を追加してタップ可能性を視覚化。
3. **`<meta name="theme-color">` light/dark 二本追加** (前回優先 3 から継続) — `index.html.j2:7` 付近で iOS タブ識別性 / ステータスバー一体感を低コストで向上。

## 前回からの差分 (前回スコアがあれば)

- レスポンシブ / メディアクエリ: 4 → 4 (±0) 維持 — テンプレ未変更。
- タップ領域 / 操作性: 3 → 3 (±0) 維持 — テンプレ未変更。
- 情報密度 / 可読性: 4 → 4 (±0) 維持 — calibrator の改善は P 値域に影響し得るが HTML 表示形式は不変。
- ダークモード / コントラスト: 2 → 2 (±0) 維持 — CSS 未変更。前回優先 1 が 2 改修連続で未着手。
- iOS / iCloud 経由特有の互換: 4 → 4 (±0) 維持 — 外部依存追加なし、メタ未追加。

総合: 3.4 → 3.4 (±0)。今回の P0-2 (calibrator 過学習対策: min_bin_size / cap) + P0-1 延長は `predictor/` 層だけの変更で、モバイル HTML 出力には到達していないため全 5 軸を据え置いた。次回スコアを上げるには、前回・今回と 2 連続で据え置きになっている優先 1 (ダークモード変数化) への着手が必須。
