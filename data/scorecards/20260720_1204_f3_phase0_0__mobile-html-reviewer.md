# モバイル HTML レビュアー 採点

## 判定: PASS

**理由**: 今回は type-B（固定 split/seed の診断・検証）であり、`web/templates/index.html.j2` / `web/generator.py` に差分はない。最新 HTML の再生成も成功し、F3 Phase 0.0 によるモバイル表示回帰は認めない。
**採点対象**: `web/templates/index.html.j2`、`web/generator.py`、再生成した `web/dist/index.html` の先頭 200 行。F3 のリーク定量値・予測品質は専門外で採点しない。
**根拠ファイル**: `web/templates/index.html.j2:5-10,37-65,94-138,380-487,523-530`、`web/generator.py:314-383,648-670`、`web/dist/index.html:1-200`
**次アクション**: F3 Phase 0.0 はモバイル HTML 観点で次段階へ進めてよい。別改修で枠番 4/6/7/8 の文字色を AA 適合へ修正する。

## 総合: 4.0 / 5（参考スコア）

前回 4.4 → 今回 4.0（-0.4）。これは今回の非 HTML 改修による回帰ではなく、現行枠番色をコントラスト比で再測定した評価補正。HTML/CSS の今回差分は ±0。

## 項目別

- **レスポンシブ / メディアクエリ: 4/5** — `viewport` は `device-width, initial-scale=1, viewport-fit=cover`。本文は `max-width:720px`、480px 以下で調教師→性齢→斤量を同時に畳み、481–600px は調教師のみを畳む (`index.html.j2:5,138,464-487`)。320/375/414px は固定幅が小さい race-head grid と横スクロール表で破綻を回避する。優先列を段階的に 1 列ずつ畳まない点は留保。
- **タップ領域 / 操作性: 5/5** — 日付ナビ、買い候補カード、`summary` はモバイルで `min-height:44px` (`index.html.j2:106-122,473-475`)。`summary::after` の ▼ と open 時 180° 回転で開閉状態を明示する (`index.html.j2:380-402`)。主要操作要素は Apple HIG 相当を満たす。
- **情報密度 / 可読性: 4/5** — 基本文字 16px / line-height 1.5、閉じたレースにも印・馬番・馬名・オッズを表示 (`index.html.j2:68-74,406-416,658-662`)。`horse_num` の `00` / 空値は view model 前に除外され、生成物に `waku-0`、`単勝 0番`、`>0</td>` は実測 0 件 (`generator.py:314-383`)。0.72–0.78rem の補助文字が多い点は留保。
- **ダークモード / コントラスト: 3/5** — 主配色は実測で `fg/bg` 14.76:1、`fg-mute/card` 6.01:1、`accent/bg` 7.20:1、`buy-board-fg/buy-board-bg` 7.13:1、`tag-fg/tag-bg` 9.25:1、白/grade 5.44:1 と AA 適合 (`index.html.j2:13-65`)。ただし枠番は白文字/4枠 4.06:1、6枠 2.50:1、7枠 2.92:1、8枠 2.91:1 で、小さい太字馬番の AA 4.5:1 に未達 (`index.html.j2:516-530`)。
- **iOS / iCloud 経由特有の互換: 4/5** — Apple/mobile web-app meta、light/dark theme-color、sticky header、`overflow-x:auto` + `-webkit-overflow-scrolling:touch` を実装 (`index.html.j2:5-10,75-81,94-105,436-438`)。テンプレートと生成物を検索し、外部 `script/link/img/url/http` 依存は 0 件。`viewport-fit=cover` に対する `env(safe-area-inset-*)` がなく、横向きノッチ端末は未保証。

## 停止条件チェック

- [x] 今回変更は type-B。P25 固有の backtest / market snapshot / payout ゲートは N/A（モバイル HTML 採用判断ではない）。
- [x] `git status --short` と `git log --stat -3` を確認。今回対象は未追跡の診断 script/test/doc で、`web/` 差分は 0 件。
- [x] 指定の `.venv32/Scripts/python.exe` で `render()` を実行し、`web/dist/index.html`（470,358 bytes）を再生成。
- [x] viewport / 320・375・414・600・720+px の CSS / タップ領域 / dark / iOS / オフライン依存を確認。
- [x] 専門領域の停止条件に抵触なし。既存 WCAG 未達は今回差分でなく、F3 の次段階進行を止めない。

## 反証の試み

- 主張「F3 Phase 0.0 は HTML に影響しない」に対し、`git diff -- web/templates/index.html.j2 web/generator.py web/dist/index.html` と再生成後の `git status --short` を確認 → `web/` 差分 0 件で成立。
- オフライン Files 閲覧を崩す外部依存の混入を検索 → `script/link/img/url/http` 参照 0 件で反証不成立。

## 主な改善提案

1. **枠番 4/6/7/8 の AA 適合** — `web/templates/index.html.j2:526-530` の背景または文字色を調整し、12.8px 相当の馬番で 4.5:1 以上を確保する。特に 6枠 2.50:1 が最優先。
2. **safe-area padding の追加** — `web/templates/index.html.j2:75-81,138` に `padding-left/right: max(..., env(safe-area-inset-*)))` を追加し、`viewport-fit=cover` と整合させる。

## 前回からの差分

- レスポンシブ: 4 → 4（±0）
- タップ領域: 4 → 5（+1）— 現行 HTML の日付ナビを含む全主要操作要素で 44px を再確認。
- 情報密度: 4 → 4（±0）
- ダークモード: 5 → 3（-2）— 現行枠番色のコントラスト実測による評価補正。今回改修の回帰ではない。
- iOS 互換: 5 → 4（-1）— safe-area inset 未実装を絶対基準で補正。今回改修の回帰ではない。
- 前回判定: v3 判定記載なし。今回: **PASS**（F3 の HTML 非影響を再生成と diff で確認）。
