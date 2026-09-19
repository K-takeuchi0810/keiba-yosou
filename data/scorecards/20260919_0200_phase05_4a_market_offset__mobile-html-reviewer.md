# モバイル HTML レビュアー 採点 — efe611c Phase 0.5-4A 市場オフセットモデル

## 判定: PASS (前回維持)

**理由**: 改修タイプ **type-B**。`git show efe611c --stat` で 9 files / +1,736 行、`web/` 変更 **0 行**、`predictor/*.py` `gui/` `config.py` `weights.json` `calibrator.json` 変更 **0 行**。新規 `predictor/market_offset_model.txt` (191,369 bytes) が HTML 生成経路に干渉しないことを 7 項目で実測し、すべて不在を確認。
**根拠ファイル**: `predictor/ml_model.py:25` / `web/generator.py:224,873-880,948-949` / `predictor/rules.py:1035` / `scripts/market_offset_model.py:52-54` / `web/dist/index.html` (本セッション再生成)
**次アクション**: web 側の作業なし。0.5-4A 不合格により「市場 vs AI vs 差」の HTML 化は着手条件未達のまま保留。

## 総合: 4.2 / 5 (前回 4.2、±0)

## 依頼 — HTML 生成経路への影響なしの証明 (7 項目、本セッション実測)

| # | 確認 | 結果 |
|---|---|---|
| 1 | `git diff efe611c~1 efe611c --stat -- web/ 'predictor/*.py' gui/ config.py weights.json calibrator.json` | **空** (0 行)。predictor/ 配下の差分は `.txt` `.meta.json` の 2 データファイルのみ |
| 2 | `import web.generator; from predictor import predict_race, ml_model` 後の `sys.modules` | **[]** 未ロード |
| 3 | `market_offset` / `feature_manifest` の import 元 | `scripts/` と `tests/` のみ。web・gui・predictor 本体・config から **0 件** |
| 4 | 新規 `.txt` の誤ロード経路 | なし。`ml_model.py:25` は固定パス、`SEALED_ARTIFACTS` 6 点で hash 凍結。offset 側の `MODEL_PATH` は別定数 |
| 5 | glob | `predictor/*.txt` を glob するコード **0 件**。`rules.py:1035` の `*-filtered.json` に新規 JSON は不一致。publish 複製対象は `index.html` + `static/` `assets/` のみ → `.txt` が iCloud に漏れる経路なし |
| 6 | テスト | `test_publish_safety` + `test_template_render` + `test_feature_manifest`: **47 passed** / `test_webapp` 系: **18 passed** |
| 7 | 再生成 (`--from 20260919 --to 20260919 --no-publish --json`) | rc=0、**328,995 bytes**。改修前コード生成の同日 HTML 329,011 bytes と **−16 bytes**。タグ単位 diff 384 断片を分類すると、更新時刻 / オッズ時刻 / 倍率 / 人気順 / P / EV / pick-reason のみ = **全て 08:45→09:52 のオッズ再取得に起因**。構造・文言・CSS の差分 **0** |

再生成物の健全性: DOM 約 4,926 要素、外部 `<link>/<script>` **0**、viewport あり、`theme-color` ×2、観察専用 notice / 「サスペンド中」7 参照。

結論: **回帰なし**。

## 項目別 (web 無変更のため前回値維持)

- レスポンシブ: 4/5
- タップ領域: 5/5
- 情報密度/誤読防止: 5/5 (留保 2 件据え置き: EV が P と同格表示 / 鮮度の分単位が `title` 依存で iOS タップで見えない。次回 type-D で 4 へ下げる予告を継続)
- ダークモード/コントラスト: 3/5 (waku 4/6/7/8 白文字の未達は **5 回目の持ち越し**)
- iOS/file:// + 予算: 4/5 (328,995 bytes、外部依存 0。`generator.py` 既定 ±14 日は未処置)

## 停止条件チェック

- [x] git_sha / rule_version — N/A (type-B、HTML の出所刻印は不変)
- [x] baseline paired / market_snapshot counts / payout 欠損 — N/A
- [x] 専門領域 Hard Fail: fresh/stale 表示・観察専用 notice・サイズ < 1.5MB・AA 未達の重要テキストなし → **不抵触**

## 反証の試み

- 「HTML 生成が新モデル `.txt` を拾う」→ 固定パス + hash 凍結 + glob 不一致 + sys.modules 空で **不成立**
- 「同日 HTML の差分にコード由来の変化が隠れている」→ 384 断片を全分類、残余 36 件も全て人気順の変動 = オッズ由来。**不成立**

## 参考所見

0.5-4A は β₂ 区間が 0 をまたぎ不合格、補正は平均 0.31pt / 最大 3.75pt。仮に表示するなら前回要件 3 (差は帯別較正ずれ CI 上限超のみ数値表示) に照らして **全頭が `—` になる規模** = HTML に出す価値なし。表示に乗せない判断を推奨。

## 前回からの差分

- 全 5 項目 ±0 (4.2 → 4.2)。判定 PASS 維持。
- 持ち越し 3 件 (EV 同格表示 / `title` 依存鮮度 / waku 色 dark 未再計測) は件数変わらず。
