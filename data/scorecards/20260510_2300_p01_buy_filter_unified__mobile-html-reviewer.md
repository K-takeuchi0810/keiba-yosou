# モバイル HTML レビュアー 採点

## 総合: 3.4 / 5 (前回 3.4 → 3.4, ±0)

## 項目別

- **レスポンシブ / メディアクエリ: 4/5** — `web/templates/index.html.j2` の viewport / `@media (max-width: 480px)` / 481–600px の二段優先度・`max-width: 720px` 中央寄せはそのまま。HTML 出力ロジックに今回の変更は到達していないため、レイアウト面の挙動は前回と同一。320px 級で馬名 ellipsis が多発しがちな点も未解消。
- **タップ領域 / 操作性: 3/5** — `.buy-card` / `summary.race-head` の `min-height: 44px` (`index.html.j2:172` 付近) は維持。`::-webkit-details-marker { display: none }` で開閉インジケータが見えない問題、`<details>` 間 `margin-bottom: 0.5rem` のみで誤タップしやすい問題はいずれも未着手。今回の改修対象外。
- **情報密度 / 可読性: 4/5** — `index.html.j2:233` の `全 {{ race_count }} レース / 買い候補 {{ buy_count }} 件` 表記、`:236-244` の買い候補カードのフィールド構成 (馬番 / 印 / 馬名 / オッズ / 人気 / P / EV / K) は変更なし。`web/generator.py:14,32-35` で `BUY_FILTER_DEFAULT` 経由になったが、しきい値 (min_odds=1.05 / min_ev=0 / min_kelly=10 / min_confidence=20) は前回値と同一なので、HTML 上で出る件数・密度の体感はほぼ変わらない見込み。`buy_count` と GUI dashboard の件数が一致するようになったのは閲覧側の納得感に効くが、表示そのものの可読性は不変。
- **ダークモード / コントラスト: 2/5** — `.buy-board { background: #fff8f7 }` (`:59`)、`.buy-board h2` の固定白背景、`.conf-tag` の固定灰背景はそのまま残存。`prefers-color-scheme: dark` 配下で上書きが入っていない既知の AA 不通過は未修正。今回の P0-1 はロジック層のみで CSS は触っていないため、本軸は前回と同点。
- **iOS / iCloud 経由特有の互換: 4/5** — `apple-mobile-web-app-capable=yes` / `-webkit-overflow-scrolling: touch` / 外部リソース無依存は維持。`mobile-web-app-capable` 併記、`theme-color`、`apple-mobile-web-app-status-bar-style` の欠如も未解消。`web/generator.py` 頭 35 行を見る限り CDN 等の外部参照が新たに混入していないことは確認できる (import が `config.BUY_FILTER_DEFAULT` 追加のみ)。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **ダークモード時のハードコード色を CSS 変数化** — `index.html.j2:59` `.buy-board { background: #fff8f7 }`、`:73 .buy-card`、`:190 .conf-tag` の固定色を `--buy-bg / --buy-card-bg / --tag-bg` に置換し、`@media (prefers-color-scheme: dark)` 内で再定義。前回からの最重要積み残し。
2. **`<details>` の開閉インジケータを CSS で復元** — `index.html.j2:119` の `::-webkit-details-marker { display: none }` の上に、`summary.race-head::after { content: '▼' }` + `details[open] summary::after { transform: rotate(180deg) }` を追加。タップ可能であることを視覚化。
3. **`<title>` の timestamp 排除 or 短縮 + theme-color 追加** — `<title>` から毎回変動する更新時刻を外し、`<meta name="theme-color">` light/dark 二本を `index.html.j2:7` 付近に追加。iOS タブ識別性 / ステータスバー一体感が低コストで向上。

## 前回からの差分 (前回スコアがあれば)

- レスポンシブ / メディアクエリ: 4 → 4 (±0) 維持 — テンプレ未変更。
- タップ領域 / 操作性: 3 → 3 (±0) 維持 — テンプレ未変更。
- 情報密度 / 可読性: 4 → 4 (±0) 維持 — フィルタしきい値が同一値 (1.05 / 0 / 10 / 20) のため `buy_count` の見え方は不変。GUI と完全一致するようになった点はモバイル単体採点ではスコアに反映しない (一貫性の効果はモバイル側では感じづらい)。
- ダークモード / コントラスト: 2 → 2 (±0) 維持 — CSS 未変更。
- iOS / iCloud 経由特有の互換: 4 → 4 (±0) 維持 — 外部依存追加なし。`web/generator.py` の import 追加 (`BUY_FILTER_DEFAULT`) は実行時 HTML には影響しない。

総合: 3.4 → 3.4 (±0)。今回の改修はモバイル HTML 出力に対しては実質「リファクタ」であり、見え方が変わらないため評価軸 5 本いずれも前回スコアを据え置いた。次回スコアを上げるには上記の優先 1 (ダークモード変数化) に着手する必要がある。
