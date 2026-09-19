# モバイル HTML レビュアー 採点

## 判定: PASS

**理由**: 最終 HEAD `cb56778` の変更は `scripts/f3_phase1_readiness.py` とテストだけで、分岐元 `068efb0` から `web/templates/index.html.j2`・`web/generator.py` へのコミット差分はない。F3 Phase 1 readiness監査によるモバイルHTML回帰は認めない。  
**採点対象**: `web/templates/index.html.j2`、`web/generator.py`、既存 `web/dist/index.html`。readiness判定・統計品質は専門外で採点しない。  
**根拠**: `git log --stat -3`、`git diff 068efb0..cb56778 -- web`（出力0件）、`git status --short -- web`（出力0件）、テンプレート／view model／生成物先頭200行。  
**次アクション**: readiness監査はモバイルHTML観点で次段階へ進めてよい。別改修で枠番4/6/7/8のAA適合と生成HTMLの1.5MB予算超過を解消する。

## 総合: 4.0 / 5

前回 4.0 → 今回 4.0（±0）。HTML/CSS/view modelに変更がないため全項目据え置き。

## 項目別

- **レスポンシブ / メディアクエリ: 4/5** — `viewport` は `device-width, initial-scale=1, viewport-fit=cover`。本文は `max-width:720px`、480px以下で調教師・性齢・斤量、481–600pxで調教師を畳む。320/375/414pxは横スクロール表で破綻を回避する（`index.html.j2:5,138,438,464-487`）。
- **タップ領域 / 操作性: 5/5** — 日付ナビ、買い候補カード、レース`summary`は44px以上。開閉矢印とopen時回転で状態を示す（`index.html.j2:106-122,313-337,380-402,473-475`）。
- **情報密度 / 可読性: 4/5** — 基本文字16px / line-height 1.5。印・馬番・馬名・オッズを一覧表示し、`horse_num`の`00`／空値はview modelで除外する（`index.html.j2:68-74,406-416,720-724`; `generator.py:314-383`）。0.72–0.78remの補助文字が多い点は留保。
- **ダークモード / コントラスト: 3/5** — 主配色はAA相当だが、白文字の枠番4/6/7/8は通常文字4.5:1未達（前回実測: 4枠4.06、6枠2.50、7枠2.92、8枠2.91）。CSS差分なし（`index.html.j2:37-65,523-530`）。
- **iOS / iCloud互換: 4/5** — Apple web-app meta、light/dark theme-color、sticky header、`overflow-x:auto`、`-webkit-overflow-scrolling:touch`を実装し外部リソース依存なし。safe-area padding未実装に加え、既存生成物1,755,415 bytesは1.5MB予算を超える（`index.html.j2:5-10,75-105,436-438`; `generator.py:672-679`）。

## 停止条件チェック

- [x] 最終HEAD `cb56778` と直近3コミットを確認。readiness改修2コミットはscript/testのみ。
- [x] `068efb0..cb56778`の`web/`差分、および作業ツリーの`web/`差分は0件。
- [x] viewport、320/375/414/600/720+px、44pxタップ領域、dark、iOS／オフライン互換を確認。
- [x] 専門領域の停止条件に抵触なし。

## 反証の試み・制約

- 「readiness改修はHTMLに影響しない」に対し、コミット差分と作業ツリー差分の両方を確認し、いずれも0件だった。
- 指定の`.venv32/Scripts/python.exe`で`render()`を約4分実行したが完了出力前だったため停止した。新規生成成功は証拠にせず、既存 `web/dist/index.html`（2026-07-20 12:16:25生成、先頭200行確認）と現行テンプレート／view modelの静的確認に限定した。

## 主な改善提案

1. 枠番4/6/7/8の背景または文字色を調整し、通常文字として4.5:1以上を確保する。特に6枠を優先する。
2. `env(safe-area-inset-left/right)`を考慮した余白を追加する。
3. file://初回パース負荷を抑えるため、生成範囲の短縮または古い開催の間引きで1.5MB以下へ戻す。

## 前回からの差分

- レスポンシブ: 4 → 4（±0）
- タップ領域: 5 → 5（±0）
- 情報密度: 4 → 4（±0）
- ダークモード: 3 → 3（±0）
- iOS互換: 4 → 4（±0）
- 前回判定 PASS → 今回 **PASS**。既存の留保はあるが、今回改修による回帰はない。
