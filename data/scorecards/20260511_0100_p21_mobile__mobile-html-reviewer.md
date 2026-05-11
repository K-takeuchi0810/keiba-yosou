# モバイル HTML レビュアー 採点

## 総合: 4.4 / 5 (前回 3.4 → 4.4, +1.0)

> **ブロック条件解除**: 5 連続未着手 (P0-1 / P0-2 / P1-3 / P0-3 / P1-1) で発動していた優先 1〜3 (ダークモード CSS 変数化 / `<details>` 開閉インジケータ復元 / `theme-color` メタ) がこの P2-1 で **3 件同時着手・全て解消**。次回以降の expert-review ブロック運用は不要。

## 項目別

- **レスポンシブ / メディアクエリ: 4/5** — `viewport=device-width,initial-scale=1,viewport-fit=cover` 維持。`@media (max-width: 480px)` と `(max-width: 600px) and (min-width: 481px)` の二段優先度据置。`grid-template-columns: 3rem 1fr auto 1.2rem` の 4 列目に開閉インジケータ用 1.2rem 幅を新規確保し、列の畳み挙動と整合。
- **タップ領域 / 操作性: 4/5** — `.buy-card` / `summary.race-head` の `min-height: 44px` (×2) 維持。**▼ インジケータ復元で +1**: `summary.race-head::after { content: "▼" }` + `details.race[open] > summary.race-head::after { transform: rotate(180deg); transition: .2s }` で開閉が指でも視覚予測可能に。`::-webkit-details-marker` 不可視化と矛盾せず描画。残課題は `.conf-tag` クリックヒット領域 (~30px) の拡張のみ。
- **情報密度 / 可読性: 4/5** — view model フィールド構造・印フォーマット・桁数・馬番フィルタ不変。`--fg-mute: #a0a0a0` をダーク側に追加し、補助情報の沈み具合も適正化。`predictor/rules.py` のロジック変更は j2 表示パスに影響なし。
- **ダークモード / コントラスト: 5/5** — **前回最大の積み残しが完全解消、+3**: `:root` 既定値に対し `@media (prefers-color-scheme: dark)` 内で **16 変数を再定義** (`--fg / --fg-mute / --bg / --card / --border / --accent / --buy-board-bg=#2b1c1c / --buy-board-fg=#ff8a7a / --buy-card-border=rgba(255,138,122,.35) / --tag-bg=#2d2d2d / --tag-fg=#cfd4dc / --top-picks-bg=rgba(106,166,255,.10) / --grade=#ff8a7a / --turf / --dirt / --jump`)。本文残ハードコード色は `color: #fff` (有色背景上のテキスト用、合理) と `.waku-1〜8` (JRA 枠色は仕様固定) のみで、これらは仕様上ダークでも維持すべき色なので満点。
- **iOS / iCloud 経由特有の互換: 5/5** — **+1**: `<meta name="theme-color" content="#fafafa" media="(prefers-color-scheme: light)">` と `content="#181818" media="(prefers-color-scheme: dark)"` の **二本立て**追加でタブバー/ステータスバー一体感を確保。`apple-mobile-web-app-capable=yes` に加え `mobile-web-app-capable` 併記、`apple-mobile-web-app-status-bar-style` も追加。`-webkit-overflow-scrolling: touch` / 外部リソース無依存維持。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **`.conf-tag` のタップヒット領域を 44×44 相当に** — `web/templates/index.html.j2` の `.conf-tag` に `min-height: 28px; padding: 0.25rem 0.5rem; display: inline-flex; align-items: center` を加え、隣接タグ間に `gap: 0.4rem` を確保。Apple HIG の隣接タップ間隔 8px 以上を担保。
2. **ダークモード時の `.waku-1` 白背景の縁取り強化** — `.waku-1 { background: #fff; color: #000; border: 1px solid #888 }` はダーク時に「明るすぎ」で目を引く。`@media (prefers-color-scheme: dark) { .waku-1 { background: #e0e0e0; border-color: #555 } }` で輝度を下げる。
3. **`color-scheme: light dark` を `:root` に** — フォームコントロール (将来追加分) のネイティブ配色を OS テーマと自動同期。1 行追加の低コスト改善。

## 前回からの差分

- レスポンシブ / メディアクエリ: 4 → 4 (±0) 維持 — グリッド 4 列化は破綻なし。
- タップ領域 / 操作性: 3 → 4 (+1) 改善 — ▼ インジケータ復元で `<details>` の開閉予測性が大幅向上。
- 情報密度 / 可読性: 4 → 4 (±0) 維持 — view model 不変。
- ダークモード / コントラスト: 2 → 5 (+3) 大幅改善 — 16 変数の prefers-color-scheme 再定義で `.buy-board / .buy-card / .conf-tag / .top-picks` 全てが OS テーマ追従、最重要積み残し完全解消。
- iOS / iCloud 経由特有の互換: 4 → 5 (+1) 改善 — theme-color light/dark 二本 + mobile-web-app-capable + status-bar-style の 3 メタ追加で iOS 一体感最大化。

総合: 3.4 → 4.4 (+1.0)。**5 連続ブロック条件解除**。P2-1 単一改修で項目 4 (ダークモード) +3 / 項目 2 (タップ) +1 / 項目 5 (iOS) +1 の 3 軸同時改善は本プロジェクト最大の単発寄与。残るは `.conf-tag` ヒット領域と `.waku-1` ダーク輝度の微調整のみで 5.0 到達も視野。
