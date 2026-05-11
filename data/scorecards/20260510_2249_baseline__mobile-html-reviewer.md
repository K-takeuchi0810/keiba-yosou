# モバイル HTML レビュアー 採点

## 総合: 3.4 / 5

## 項目別

- **レスポンシブ / メディアクエリ: 4/5** — viewport は `width=device-width, initial-scale=1, viewport-fit=cover` で正しく、`@media (max-width: 480px)` で調教師/性齢/斤量を畳み、481–600px で調教師のみ畳むという二段優先度も妥当。`max-width: 720px` の中央寄せもあり、iPhone 縦持ちで破綻しない。ただし 320px 級では「印 / 馬 / 馬名(7rem) / オッズ / 騎手」5 列でなお狭く、馬名 ellipsis 多発が懸念 (実機 320px で確認余地)。
- **タップ領域 / 操作性: 3/5** — 480px 以下で `summary.race-head` と `.buy-card` に `min-height: 44px` を付けており Apple HIG 基準は満たす。一方 `<a class="buy-card">` 内アンカー以外、`<details>` 開閉インジケータ (▶/▼) を非表示 (`::-webkit-details-marker { display: none }`) にしており、開閉できることが視覚的に分からない。隣接タップ領域 (連続する details) の隙間も `margin-bottom: 0.5rem` のみで指サイズで隣を誤タップしやすい。
- **情報密度 / 可読性: 4/5** — 16px ベース / line-height 1.5 で標準、表は 0.85rem (480px 以下 0.8rem) と妥当。馬番 "0"/"00" 行は generator.py:101-104 で除外済みで HTML に "0" が残らない実装は良い。ただし `td.horse-name { max-width: 7rem }` で馬名が ellipsis されるとカタカナ 4-5 文字で切れる。`<title>` に絶えず変わる timestamp が入り iOS Safari の履歴/タブ判別性が悪い。
- **ダークモード / コントラスト: 2/5** — `.buy-board` の `background: #fff8f7`、`.no-buy` 経由でなく `.buy-board h2` の `background: #c0392b; color: #fff` 等 ダークモードでも上書きされない**固定白背景**が複数存在 (`.buy-board { background: #fff8f7 }`、`.conf-tag { background: #eef2f7; color: var(--fg-mute) }`)。ダークモードで「白い箱に灰文字」になり WCAG AA 不通過。`waku-1 { background: #fff; color: #000 }` も周囲が `--card: #232323` の中で浮く (これは枠番の伝統色なので妥当ではあるが、隣接コントラストはレビューしておきたい)。
- **iOS / iCloud 経由特有の互換: 4/5** — `apple-mobile-web-app-capable=yes`、`-webkit-overflow-scrolling: touch`、`position: sticky` ヘッダ、外部 CSS/JS/フォント依存ゼロで `file://` でも完全動作。ただし iOS では `apple-mobile-web-app-capable` は非推奨で `mobile-web-app-capable` 併記が推奨。`apple-mobile-web-app-status-bar-style` も無し。`<meta name="theme-color">` 不在で iOS 15+ Safari 上部の色がデフォルトのまま。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **ダークモード時のハードコード色を CSS 変数化** — `index.html.j2:60` `.buy-board { background: #fff8f7 }`、`:73 .buy-card`、`:190 .conf-tag { background: #eef2f7 }` などダークモード分岐の外で固定色を使っている箇所を、`--buy-bg`, `--tag-bg` 等の変数に置換し `@media (prefers-color-scheme: dark)` 内で再定義。これだけでダーク時の白浮き/灰文字 AA 不通過が一掃され、夜の iPhone 閲覧で実用性が大きく改善する。
2. **`<details>` の開閉インジケータを CSS で復元** — `index.html.j2:119` で `::-webkit-details-marker { display: none }` した上、代わりの ▼/▶ を `summary.race-head::after { content: '▼'; transition: transform .2s }` `details[open] summary::after { transform: rotate(180deg) }` で grid 3 列目に追加。今は「タップして開ける」ことが視覚的に伝わらず、初見ユーザーが情報を取りこぼす。
3. **iOS テーマカラー / ステータスバー色を追加** — `index.html.j2:7` 付近に `<meta name="theme-color" content="#fafafa" media="(prefers-color-scheme: light)">` と `<meta name="theme-color" content="#181818" media="(prefers-color-scheme: dark)">`、加えて `<meta name="apple-mobile-web-app-status-bar-style" content="default">` を追加。iCloud Files から開いた際 (= Safari エンジン) のステータスバーが本文と一体化してアプリ感が出る。低コストで体験向上。

## 前回からの差分 (前回スコアがあれば)

- 初回採点のため差分なし (baseline)。
