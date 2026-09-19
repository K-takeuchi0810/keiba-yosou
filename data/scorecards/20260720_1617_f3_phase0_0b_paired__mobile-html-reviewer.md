# モバイル HTML レビュアー 採点

## 判定: PASS

**理由**: 今回は type-B（paired OOS 評価スクリプト／結果文書）で、`web/templates/index.html.j2`・`web/generator.py`・`web/dist/index.html` にコミット差分はない。F3 Phase 0-0b によるモバイル HTML 回帰は認めない。
**採点対象**: `web/templates/index.html.j2`、`web/generator.py` と既存生成物。F3 の統計・予測品質は専門外で採点しない。
**根拠ファイル**: `web/templates/index.html.j2:5-10,37-65,94-138,380-487,523-530`、`web/generator.py:314-383,648-670`、`git log --stat -3`（最終 HEAD `fa1d491`）、`git diff 068efb0..fa1d491 -- web`（出力 0 件）。
**次アクション**: F3 Phase 0-0b はモバイル HTML 観点で次段階へ進めてよい。別改修で枠番 4/6/7/8 の文字色を WCAG AA 相当へ修正する。

## 総合: 4.0 / 5（参考スコア）

前回 4.0 → 今回 4.0（±0）。HTML/CSS/view model の変更がないため全項目据え置き。

## 項目別

- **レスポンシブ / メディアクエリ: 4/5** — `viewport` は `device-width, initial-scale=1, viewport-fit=cover`。本文は `max-width:720px`、480px 以下で調教師・性齢・斤量、481–600px で調教師を畳む。320/375/414px は横スクロール表で破綻を回避する (`index.html.j2:5,138,438,464-487`)。
- **タップ領域 / 操作性: 5/5** — 日付ナビ、買い候補、レース `summary` は `min-height:44px`。`summary::after` の矢印と open 時回転で状態を示す (`index.html.j2:106-122,313-337,380-402,473-475`)。
- **情報密度 / 可読性: 4/5** — 基本文字 16px / line-height 1.5。印・馬番・馬名・オッズを一覧表示し、`horse_num` の `00` / 空値は view model で除外する (`index.html.j2:68-74,406-416,720-724`; `generator.py:314-383`)。補助文字に 0.72–0.78rem が多い点は留保。
- **ダークモード / コントラスト: 3/5** — 主配色は前回実測で AA 相当だが、白文字の枠番 4/6/7/8 は小さい馬番表示で 4.5:1 未達（4枠 4.06、6枠 2.50、7枠 2.92、8枠 2.91）。CSS差分なし (`index.html.j2:37-65,523-530`)。
- **iOS / iCloud 経由特有の互換: 4/5** — Apple web-app meta、light/dark theme-color、sticky header、`overflow-x:auto` と `-webkit-overflow-scrolling:touch` を実装。外部リソース依存なし。`viewport-fit=cover` に対する safe-area padding は未実装 (`index.html.j2:5-10,75-105,436-438`)。

## 停止条件チェック

- [x] 改修タイプは type-B。P25 固有の backtest / market snapshot / payout ゲートはモバイル HTML 採点では N/A。
- [x] `git status --short` と `git log --stat -3` を最終 HEAD `fa1d491` で確認。直近3コミットは `scripts/f3_phase0_0_eval.py` と tests のみ。
- [x] F3 分岐元 `068efb0` から最終 HEAD `fa1d491` までの `web/` 差分は 0 件。表示経路に非影響。
- [x] viewport、320/375/414/600/720+px の CSS、44px タップ領域、dark、iOS/オフライン互換をテンプレートとview modelで確認。
- [x] 専門領域の停止条件に抵触なし。

## 反証の試み

- 主張「F3 Phase 0-0b は HTML に影響しない」に対し、`git diff 068efb0..fa1d491 -- web` と `git status --short -- web` を確認 → ともに出力 0 件で成立。
- 指定の `render()` は起動したがレビュー時間内に完了しなかったため停止。生成成功を新規証拠とはせず、コミット差分 0 件と現行テンプレート／view modelの静的確認に限定した。

## 主な改善提案

1. **枠番 4/6/7/8 の AA 適合** — `web/templates/index.html.j2:526-530` の背景または文字色を調整し、通常文字として 4.5:1 以上を確保する。特に6枠を優先する。
2. **safe-area padding の追加** — `web/templates/index.html.j2:75-81,138` に `env(safe-area-inset-left/right)` を考慮した余白を追加する。

## 前回からの差分

- レスポンシブ: 4 → 4（±0）
- タップ領域: 5 → 5（±0）
- 情報密度: 4 → 4（±0）
- ダークモード: 3 → 3（±0）
- iOS 互換: 4 → 4（±0）
- 前回判定: PASS → 今回: **PASS**。`web/` 差分がなく、既存の軽微な留保にも変化なし。
