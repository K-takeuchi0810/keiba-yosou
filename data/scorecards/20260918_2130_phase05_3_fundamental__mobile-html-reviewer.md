# モバイル HTML レビュアー 採点 — 2fb703a Phase 0.5-3 Fundamental Model

## 判定: PASS (前回維持)

**理由**: 改修タイプ **type-B** (分析/診断ツール + 研究用モデル成果物)。`git show 2fb703a --stat` で 12 files / +18,362 行、`web/` 変更 0 件・`predictor/__init__.py` `rules.py` `features.py` `ml_model.py` 変更 0 件。HTML 生成経路への影響なしを **直接証明** したので前回スコア維持。P25 固有ゲート・`web/dist` 再生成必須は N/A だが、回帰有無の確認のため再生成・実測は実施した。
**根拠ファイル**: `predictor/feature_manifest.py`、`predictor/ml_model.py:25-27`、`config.py:204-205`、`web/dist/index.html` (本セッション再生成)
**次アクション**: 0.5-4 で「市場 vs AI vs 差」を HTML に出すとき (type-D) に下記「表示要件」を受入条件にする。それまで web 側の作業なし。

## 総合: 4.2 / 5 (前回 4.2、±0)

## 依頼 1 — HTML 生成経路への影響なしの証明 (本セッション実測)

| 確認 | 結果 |
|---|---|
| `git diff 2fb703a~1 2fb703a --stat -- web/ predictor/__init__.py predictor/rules.py predictor/features.py` | **空** (差分なし) |
| `import web.generator; from predictor import predict_race` 後の `sys.modules` | `feature_manifest` / `fundamental*` **未ロード** ([]) |
| `feature_manifest` の import 元 | `scripts/fundamental_eval.py:41` `scripts/fundamental_model.py:46` の 2 箇所のみ。web/・gui/・predictor 本体からの参照なし |
| 新規 `predictor/fundamental_model.txt` の誤ロード経路 | なし。`ml_model.py:25,27` は固定パス、`config.py:204-205` で hash 凍結。`predictor/*.txt` を glob するコードは 0 件 |
| `rules.py:1035` の `data/backtest/*-filtered.json` glob | 新規 JSON は `-filtered.json` に **不一致** → 最新 snapshot キャッシュに混入しない |
| テスト | `test_publish_safety` + `test_webapp*`: 32 passed / `test_template_render` + `test_feature_manifest`: 28 passed |
| 再生成 (`--from 20260913 --to 20260913 --no-publish --json`) | rc=0、**352,889 bytes** (09/13 生成物 352,989 bytes と 100 bytes 差 = 生成時刻・git_sha 分)。DOM 約 5,227 要素、外部リソース 0、viewport あり、theme-color ×2、observation-notice あり、「サスペンド中」2 箇所 |

結論: **回帰なし**。予想 HTML の出力は改修前と同一内容。

## 項目別 (web 無変更のため前回値を維持、所見のみ更新)

- **レスポンシブ: 4/5** — 変更なし。`index.html.j2:507-528` の列畳みは健在
- **タップ領域: 5/5** — 変更なし
- **情報密度/誤読防止: 5/5 (維持、ただし留保 2 件を次回 type-D で減点対象に予告)** — (a) 09/13 ページで `top-p` タグ **9/24 レース (37.5%)** = ◎ ≠ 最高P の二重ランカーが依然常態 (`web/generator.py:86-99` は表示パッチであり構造是正ではない)。(b) `index.html.j2:745` `:692` で EV が P と **同じ `conf-tag` スタイル**で並ぶ。凡例で「EV は的中回収と結びつかない」と書きつつ同格表示 = 過去指摘「EV>1 印付き表示」の残滓。web 無変更なので今回は据え置き
- **ダークモード/コントラスト: 3/5** — 再計算: `.top-p` 6.29:1 (dark 6.80:1)、`.conf-tag` 8.66 / 9.25、`.pick-reason` 5.50 / 6.79、`.mark` 6.02 / 7.20、`.bet-tag` 5.44 → 全て AA PASS。waku 4/6/7/8 白文字未達は **未再計測・4 回目の持ち越し**。`.top-p` は 0.68rem = **10.9px** で HIG 最小 11pt 未満
- **iOS/file:// + 予算: 4/5** — 352,889 bytes (< 1MB)、外部依存 0。CLI 引数なし既定は `generator.py:312-313` の **±14 日**で 300 秒超。auto_predict は明示日付なので公開物は無傷だが、08-22 提案 2 が未処置 (持ち越し)

## 停止条件チェック

- [x] git_sha / rule_version — type-B、HTML footer `version_info` は不変。N/A
- [x] baseline paired 比較 / market_snapshot counts / payout 欠損 — N/A (type-B)
- [x] 専門領域 Hard Fail: fresh/stale 表示、観察専用 notice、サイズ < 1.5MB、AA 未達の重要テキストなし → **不抵触**

## 反証の試み

- 主張「predictor/ 追加は HTML に影響しない」に対し「LGBM ローダやキャッシュが glob で新ファイルを拾う」シナリオを検証 → **不成立** (固定パス + hash 凍結 + glob パターン不一致、sys.modules 空、再生成物サイズ差 100 bytes)

## 依頼 2 — 「市場確率 vs AI確率 vs 差」の iPhone 表示要件 (0.5-4 type-D の受入条件案)

出典: `docs/PHASE05_RESULTS.md` (Fundamental は 0-5% 帯 −0.51pt、5-10% −1.11pt、10-20% **+2.26pt [+1.28, +3.33]** の系統ずれ; 20-30% は [−0.96, +5.39] で 0 をまたぐ)。市場含意確率は `rules.py:1143-1151` `_market_probabilities` に既存。

1. **単一ランカー原則 (42% 問題の構造是正)** — 行の並び・強調・印は **差 (logit 残差) 1 本**から派生させる。P や EV で別順位を作らない。◎ を残す場合は「差 1 位 = ◎」と定義し `_top_probability_horse_num` のパッチを削除。守れないなら印列を廃止し凡例から「総合本命度」を消す。
2. **3 値は 1 行・同一フォント・`font-variant-numeric: tabular-nums`・横スクロール禁止** — 例 `市場 14.0% ／ AI 14-16% ／ 差 —`。375px で `.col-odds` を「市場%+オッズ+人気」に、新列「AI%/差」を追加し、≤480 で隠す列は 性齢/斤量/調教師 まで。差の列を折りたたみ (`<details>`) に入れるのは **Hard Fail**。
3. **較正ずれは「数値」でなく「幅」と「表示ゲート」で伝える** — `+2.26pt` を各行に出してもユーザは足し算できない。(a) AI% は帯別ずれを織り込んだ **区間表示** `AI 14-16%` (幅がそのまま信用度になり、20-30% 帯の幅 6.4pt は見た目で「当てにならない」と伝わる)。(b) **差は |AI − 市場| が帯の較正ずれ CI 上限 (10-20% 帯なら 3.33pt) を超えたときだけ数値表示**、以下は `—`。閾値未満を数値で見せない = 物理的に誤読不能。帯値は成果物 JSON の `band_calibration_fundamental` を生成時に読み、footer に artifact 名を刻む。
4. **凡例 1 行を model-legend に追加** — 「AI% は検証 (2024-25) で 10-20% 帯が実績より約 2pt 低め。差はこの誤差を超えた分だけ表示」。折りたたみ禁止。
5. **観察 / 購入の 3 軸区別 (色+形+ラベル)** — 差の符号だけで緑/赤に塗るのは禁止 (色だけ = Hard Fail)。閾値超えは **枠線ピル + ラベル「割安候補 (観察)」**。封印判定が通るまでラベルに「観察」を必ず含め、`bet-tag` と別形状にする。
6. **EV の同格表示を撤去** — `EV` conf-tag を削除し、必要なら `<details>` 「診断値」へ降格。
7. **鮮度は市場% に内包して可視化** — 現状の取得時刻は `title=` / `aria-label` のみで **iOS のタップでは表示されない**。`市場 14.0% (09:41)` と本文に出し、stale/unknown の行は **差を計算しない**。
8. **文字サイズ・予算** — 差/AI% は 0.85rem (13.6px) 以上、`.top-p` 0.68rem は 0.75rem 以上へ。追加セル ≈ +140KB 見込み → 約 490KB で 1MB 予算内。

## 主な改善提案

1. **要件 1+6 を先に** — 二重ランカー解消と EV 同格表示撤去は現行テンプレでも着手可能
2. **要件 7** — `title` 依存の鮮度表示を本文化
3. **`generator.py:312-313` 既定 ±14 日を単日既定に** — 08-22 提案 2 の 2 度目の持ち越し

## 前回からの差分

- 全 5 項目 ±0 (前回 4.2、09/13・09/14 集約でも 4.2 維持)
- 前回判定 PASS → 今回 PASS。web 無変更・回帰なしを実測で確認。ただし「情報密度 5」は EV 同格表示と `title` 依存鮮度の 2 点で次回 type-D 時に 4 へ下げる予告付き
