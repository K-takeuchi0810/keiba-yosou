# モバイル HTML レビュアー 採点

## 総合: 4.4 / 5 (前回 4.4 → 4.4, ±0)

> 本改修は `config.BUY_FILTER_DEFAULT` の値変更 (8-20 オッズ / popularity 制約解除 / exclude_confidence=[]) と、`web/generator.py:152-158` の None 対応 (`None → min_pop=1 / max_pop=99 / exclude_conf=[]`) のみ。`web/templates/index.html.j2` / CSS 変数 / メタタグ / view model フィールド shape は全て不変。`bet_candidate` の真偽集合が変わるだけで HTML 構造には到達しない。よって CSS 5 軸は全項目維持が正当。

## 項目別

- **レスポンシブ / メディアクエリ: 4/5** — `viewport=device-width,initial-scale=1,viewport-fit=cover` 据置。`@media (max-width:480px)` / `(max-width:600px) and (min-width:481px)` 二段優先度、`.buy-card { padding: 0.85rem 0.75rem; min-height: 44px }` 維持。8-20 オッズ帯への絞り込みで `.buy-card` 件数自体は減るが、各カード内の `buy-meta` テキスト長は `%.1f倍` で 1 桁→2 桁化しても 1 文字差 (例 `5.2倍 1人気` → `12.4倍 5人気`)。320px でも改行しない範囲。
- **タップ領域 / 操作性: 4/5** — `.buy-card min-height:44px` / `summary.race-head` 据置。中穴帯に絞り込んだことで「人気馬の本命カード」「混戦警告カード」が消え、ボード長が縮む → 親指で全候補をスクロール走査しやすくなる副次効果あり (CSS 直接改善ではないので加点せず)。繰越し残課題は `.conf-tag` ~30px ヒット領域のみ。
- **情報密度 / 可読性: 4/5** — `buy-meta` の `{{ popularity }}人気` 部分が None 制約解除で 1-18 人気のレンジを取りうるようになり、稀に「14人気」等 2 桁表示が出る可能性。ただし `.buy-meta` 内の `/` 区切り構造で改行は誘発しない。**情報の質的変化**: 表示馬が「人気裏付けあり (1-4 人気)」から「中穴中心 (推定 5-12 人気主体)」にシフトするため、ユーザーが `.buy-card` を見た瞬間の「これは挑戦的買い」判断が必要になる — が HTML 表示観点では popularity を出している以上、可読性は維持。今データセットでは `buy_candidates=0` で `no-buy` 文言表示されるが、これも前回同様で structure 不変。
- **ダークモード / コントラスト: 5/5** — 16 変数の `prefers-color-scheme: dark` 再定義 (`--buy-board-bg=#2b1c1c` / `--buy-card-border=rgba(255,138,122,.35)`) 完全維持。中穴カードが増減しても色設計は満点継続。
- **iOS / iCloud 経由特有の互換: 5/5** — `theme-color` light/dark 二本 + `mobile-web-app-capable` + `apple-mobile-web-app-status-bar-style` + `-webkit-overflow-scrolling: touch` 全て不変。外部リソース無依存維持、Files アプリ経由オフライン閲覧で崩れない。

## 中穴カード (8-20 倍) のモバイル見え方への影響

- `.buy-meta` の `%.1f倍` フォーマットは 8.0〜20.0 倍帯で「1桁.1桁」または「2桁.1桁」、最大 5 文字 (`20.0倍`)。320px 幅で 1 行に収まる範囲、改行誘発なし。
- popularity 解除で 2 桁人気 (`10人気`〜`18人気`) が `.buy-meta` 末尾に乗りうる。`/` 区切りで折り返しても `.buy-card` の `padding` が吸収。
- `.buy-metrics` の `EV {{ "%.2f"|format }}` は中穴帯で値が大きくなる傾向 (例 `EV 1.85`)。桁あふれ無し。
- 「買い」表示自体が「人気裏付けあり」から「中穴狙い」に意味的変化するが、HTML 上は `mark` / `num` / `name` / `odds` / `popularity` の同フィールドを同レイアウトで出すのみ。モバイル UI 上の見え方は前回と等価。
- 今回データセットでは buy_count=0 で `<section class="no-buy">` 経路に倒れる。文言「EV/信頼度条件を満たすレースは見送り判定です。」が表示され、レイアウト崩れ無し。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **`.conf-tag` のタップヒット領域を 44×44 相当に** — `web/templates/index.html.j2:226` の `.conf-tag` セレクタに `min-height:28px; padding:0.25rem 0.5rem; display:inline-flex; align-items:center` と隣接 `gap:0.4rem` を追加。Apple HIG 隣接 8px 担保。前々回からの繰越し優先 1。
2. **`.buy-meta` の 2 桁人気で右端折返し時の視認性確保** — `web/templates/index.html.j2:278` 付近の `.buy-meta` に `white-space: normal; word-break: keep-all;` 明示、`/` 区切りで「12.4倍 14人気」が 320px で改行する想定の余白確保。中穴帯シフトで 2 桁人気が増えるため。
3. **`.buy-card` の中穴カード差別化バッジ (任意)** — 8-20 倍帯のカードに `<span class="badge mid-odds">中穴</span>` を generator 側で付与し、CSS で `background: rgba(255,138,122,.15)` をオプションで色付け。ユーザーが「これは挑戦的買い」と一目で認識できる。j2 変更を伴うので慎重採用。

## 前回からの差分

- レスポンシブ: 4 → 4 (±0) 維持 — CSS / メディアクエリ無改修。
- タップ領域: 4 → 4 (±0) 維持 — `min-height:44px` 不変、カード件数減は副次効果のみ。
- 情報密度: 4 → 4 (±0) 維持 — view model shape 不変、popularity 2 桁化の可能性のみで構造維持。
- ダークモード: 5 → 5 (±0) 維持 — 変数定義不変。
- iOS 互換: 5 → 5 (±0) 維持 — メタタグ不変。

総合: 4.4 → 4.4 (±0)。担当範囲 (CSS / j2 / メタ) は本改修の影響範囲外。`config` と `generator.py` の None 対応のみで HTML 出力 byte 列構造は同一。中穴帯シフトはユーザー体験 (買い目戦略) には影響するが、モバイル HTML レビュー観点では前回スコア維持が適切。次回 5.0 到達には繰越し優先 1 (`.conf-tag` ヒット領域) の単発着手で十分。
