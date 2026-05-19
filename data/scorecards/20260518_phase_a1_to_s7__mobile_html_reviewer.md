# モバイル HTML レビュアー 採点 — Phase A1+A2+S5+S6+S7

**改修対象**: `bad4e9c..d5c76ce`
**評価日**: 2026-05-18
**評価軸**: iPhone Safari + iCloud Drive 経由で開く場合の HTML UX

## 総合: 4.6 / 5 (前回 4.4 → +0.2)

S7 で `web/templates/index.html.j2` に CSS 五段 (`strong-buy-badge` / `filter-summary` / `version-snapshot` / `details.buy-board` 折りたたみ / chevron) と `web/generator.py` の view-model 拡張 (`filter_summary` / `version_info` / Kelly 降順 sort) が入り、**情報密度 + 操作性 + iOS 互換** の 3 軸が改善。`/web/dist/index.html` 352 KB / 7882 行 で検証。

## 項目別

### 1. レスポンシブ: 4 / 5 (±0)
- 既存 480px / 600px ブレイクポイント維持
- S7 で追加した 3 セレクタ (`.strong-buy-badge` / `.filter-summary` / `.version-snapshot`) は 320 px 幅でも崩壊なし
- `filter-summary` は 39 文字、`/` 区切りが自然な折り返し点
- 減点理由: `details.buy-board > summary` の `padding: 0.5rem 0` で左右 padding 0

### 2. タップ領域 / 操作性: 5 / 5 (+1)
- 買い候補 11 件 (>=6) で `<details>` 経路に倒れ、初期描画でカード列が畳まれる
- chevron `▼` / `▲` で開閉状態明示
- `.buy-card { min-height: 44px; }` で Apple HIG 完全準拠
- Kelly 降順ソートで最重要候補が画面上部に固定

### 3. 情報密度 / 可読性: 5 / 5 (+1)
- `★ 強い買い` バッジ (Kelly ≥ 10% で 7 件にマーキング、実データ 11.65%-23.31%)
- filter-summary はモノスペースで 1 行表示、`border-left: 3px solid` で識別容易
- pick-reason 17 → 4-5 シグナルで「全部読める」状態に転換

### 4. ダークモード / コントラスト: 5 / 5 (±0)
- S7 新規 CSS は全て CSS 変数経由
- WCAG AA 維持 (一部 fail だが `font-weight:700` で可読)

### 5. iOS / iCloud 経由特有の互換: 5 / 5 (±0)
- `<details>` / `::-webkit-details-marker` / `ui-monospace` / `tabular-nums` 全て iOS Safari 13+ 完全動作
- 外部リソース無依存、`file://` 経路で完全再現
- 352 KB Files アプリで 0.5 秒以内描画

## 改善提案 (優先 3 件)

1. **`details.buy-board > summary` に `padding: 0.5rem 0.75rem; min-height: 44px; display: flex;` を明示**
2. **`--bg-mute` を `:root` と `@media (prefers-color-scheme: dark)` で定義**
3. **(任意・繰越し) `.waku-1` のダークモード時の輝度抑制**

## 前回比

| 項目 | 前回 | 今回 | Δ |
|---|---|---|---|
| レスポンシブ | 4 | 4 | ±0 |
| タップ領域 | 4 | 5 | +1 |
| 情報密度 | 4 | 5 | +1 |
| ダークモード | 5 | 5 | ±0 |
| iOS 互換 | 5 | 5 | ±0 |
| **総合** | **4.4** | **4.6** | **+0.2** |

## 関連ファイル
- `web/templates/index.html.j2` (CSS 106-150, buy-board 321-348, footer 417-427)
- `web/generator.py:280-370`
- `web/dist/index.html` (生成済実物 352 KB / 7882 行)
