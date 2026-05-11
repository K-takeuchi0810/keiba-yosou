# モバイル HTML レビュアー 採点

## 総合: 4.4 / 5 (前回 4.4 → 4.4, ±0)

> 本改修 (a: walk-forward / e: sweep + config 更新) は **`predictor/rules.py` と `web/generator.py:165` の `bet_candidate` 判定ロジック**に閉じ、`web/templates/index.html.j2` / CSS 変数 / メタタグは無改修。view model の **フィールド shape も不変** (`bet_candidate` の真偽が変わるのみ)。よって CSS 5 軸は全て前回維持で正当。

## 項目別

- **レスポンシブ / メディアクエリ: 4/5** — `viewport=device-width,initial-scale=1,viewport-fit=cover` 維持。`@media (max-width:480px)` / `(max-width:600px) and (min-width:481px)` 二段優先度維持。グリッド `3rem 1fr auto 1.2rem` 4 列構成も変更なし。
- **タップ領域 / 操作性: 4/5** — `.buy-card` / `summary.race-head` の `min-height:44px` 据置。▼ インジケータ + `rotate(180deg)` 健在。**副次的改善**: 月平均 26 戦の本物に絞り込んだことで `.buy-board` 内カード数が減り、隣接タップ干渉リスクが構造的に低下 (ただし CSS 直接改善ではないので加点せず)。残課題は `.conf-tag` ~30px ヒット領域のみ。
- **情報密度 / 可読性: 4/5** — `bet_candidate=True` の馬が `exclude_confidence` (暫定/混戦/接戦) で削られる結果、`.buy-board` には信頼度の高いカードのみ表示。馬名・オッズ・印・人気の桁数フォーマット不変。`--fg-mute` の沈み具合も適正。
- **ダークモード / コントラスト: 5/5** — 16 変数の `prefers-color-scheme: dark` 再定義 (`--buy-board-bg=#2b1c1c` / `--buy-card-border=rgba(255,138,122,.35)` 等) 完全維持。表示カード数の増減と無関係に色設計は満点継続。
- **iOS / iCloud 経由特有の互換: 5/5** — `theme-color` light/dark 二本 + `mobile-web-app-capable` + `apple-mobile-web-app-status-bar-style` 維持。外部リソース無依存、`-webkit-overflow-scrolling: touch` も健在。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **`.conf-tag` のタップヒット領域を 44×44 相当に** — `web/templates/index.html.j2` の `.conf-tag` セレクタに `min-height:28px; padding:0.25rem 0.5rem; display:inline-flex; align-items:center` と隣接 `gap:0.4rem` を追加。Apple HIG 隣接 8px 担保。前回から繰越し優先 1。
2. **ダークモード時の `.waku-1` 白背景輝度を抑える** — `@media (prefers-color-scheme: dark) { .waku-1 { background:#e0e0e0; border-color:#555 } }` でダーク時のみ #fff→#e0e0e0 に。
3. **`color-scheme: light dark` を `:root` に 1 行追加** — 将来のフォームコントロール用、ネイティブ配色を OS テーマ自動同期。

## 前回からの差分

- レスポンシブ: 4 → 4 (±0) 維持 — CSS 無改修。
- タップ領域: 4 → 4 (±0) 維持 — カード数減は構造的副次効果のみ、CSS 直接改善なし。
- 情報密度: 4 → 4 (±0) 維持 — view model shape 不変、絞り込みは表示量変化のみ。
- ダークモード: 5 → 5 (±0) 維持 — 変数定義不変。
- iOS 互換: 5 → 5 (±0) 維持 — メタタグ不変。

総合: 4.4 → 4.4 (±0)。担当範囲 (CSS / j2 / メタ) は本改修の影響範囲外であり、維持判定が適切。次回 5.0 到達には繰越し優先 1 (`.conf-tag` ヒット領域) の単発着手で十分。
