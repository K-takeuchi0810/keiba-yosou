# モバイル HTML レビュアー 採点 — 99eec68 Phase 0.5-4B 基盤修復

## 判定: PASS (前回維持)

**改修タイプ: type-B** (`git show 99eec68 --stat`: 20 files、`web/` `webapp/` `gui/` 変更 **0 行**。`predictor/` 差分はモデル 4 データファイルのみ、`predictor/*.py` は不変)。
**理由**: config 変更 (DATA_SPLIT / warmup / SPLIT_DIVERGENCE) と置換モデル `.txt` が HTML 生成経路に到達しないことを 7 項目で実測。同日 HTML を旧コード版と再生成版で突き合わせ、コード由来の差分 0。
**根拠ファイル**: `config.py:118-129,175` / `web/generator.py:21-30,312-313` / `webapp/server.py:34,45` / `predictor/ml_model.py:25` / `web/dist/index.html`

## 総合: 4.2 / 5 (前回 4.2、±0)

## 依頼 — config 変更 + モデル置換が HTML に影響しないことの証明 (7 項目、実測)

| # | 確認 | 結果 |
|---|---|---|
| 1 | `git show 99eec68 --stat -- web/ webapp/ predictor/` | web/webapp **0 行**。predictor は `.txt` `.meta.json` ×4 のみ |
| 2 | `import web.generator; from predictor import predict_race, ml_model` 後の `sys.modules` | **[]** 未ロード |
| 3 | config import 元 | `web/generator.py` は 6 点のみ。`DATA_SPLIT` `SPLIT_DIVERGENCE` `data_split` `DATA_PERIODS` は `dir()` に **0 件**。`webapp/server.py` は旧 `DATA_PERIODS["test"]["to"]` のみ参照 → 既定窓 `('20210101','20251231')` で **不変** (DATA_SPLIT と混ざる経路なし) |
| 4 | 誤ロード経路 | `ml_model.py:25` 固定パス (1,492,446 bytes、Jul 12 不変)。新特徴名 `j_rides_365` `t_runs_365` `h_history_truncated` を含む json はモデル meta 2 件のみ、web 用 feature list には **0 件** |
| 5 | glob | `predictor/*.txt` を glob するコードは web/webapp に **0 件** |
| 6 | テスト | `test_data_split` + `test_publish_safety` + `test_template_render`: **45 passed** / `-k webapp`: **19 passed** |
| 7 | 同日再生成のバイト比較 | 旧コード版 **329,011 bytes** → 新コード版 **329,092 bytes** (+81)。DOM タグ **4,926 → 4,926**、`<tr>` 311 → 311、`<style>` 完全一致。タグ単位 diff 811 断片を分類: 時刻 288 / オッズ・P・EV・人気 496 / その他 27。その他 27 は全て pick-reason の馬体重到着・`conf-tag` の付け替え・`version-snapshot` の `git: e93e3f9 → 99eec68`。**構造・文言・CSS の差分 0** |

結論: **回帰なし**。◎ の入替はオッズ (13.3→9.2 倍) と馬体重の到着によるデータ由来で、モデル (`lgbm_model.txt`) は不変。

## 項目別 (web 無変更のため前回値維持)

- レスポンシブ: 4/5
- タップ領域: 5/5
- 情報密度/誤読防止: 5/5 (留保据え置き: EV が P と同格 `conf-tag` 表示 / 鮮度の分単位が `title` 依存で iOS タップで見えない。次回 type-D で 4 へ下げる予告を継続)
- ダークモード/コントラスト: 3/5 (waku 4/6/7/8 白文字の AA 未達は **6 回目の持ち越し**)
- iOS/file:// + 予算: 4/5 (同日版 329,092 bytes、外部依存 0)

## 停止条件チェック

- [x] git_sha 刻印: `git: 99eec68` に更新されている
- [x] baseline paired / market_snapshot counts / payout 欠損 — N/A (type-B)
- [x] 専門領域 Hard Fail: fresh/stale 表示・観察専用 notice・AA 未達重要テキスト → **不抵触**
- [!] **参考 (改修に起因しない既知事項)**: 引数なし既定 (±14 日) で再生成すると **2,049,974 bytes** (> 1.5MB 閾値)。本番経路は同日指定で 329KB なので Hard Fail には当てない。ただし前回「未処置」と記した項目が実測で閾値超えに達したため、次回 type-D で既定レンジを日別に揃えることを推奨

## 反証の試み

- 「DATA_SPLIT の train 変更で webapp の傾向集計期間が動く」→ `server.py` は `DATA_PERIODS["test"]` を読み DATA_SPLIT を参照しない。**不成立**
- 「置換された `.txt` を予想経路が拾う」→ 固定パス + sys.modules 空 + 新特徴名が web 用 feature list に不在。**不成立**
- 「同日 HTML の +81 bytes にコード由来の変化が隠れている」→ 811 断片を全分類、非数値 27 件も全てデータ到着と sha 刻印。**不成立**

## 参考所見 (将来スマホ HTML に出す際)

`h_history_truncated` フラグや `*_365` 特徴を pick-reason に出す場合、「通算」と「直近 365 日」の区別を語で明示しないと ◎ 根拠の誤読を招く (「騎手勝率 13%」の分母が何かがスマホでは読めない)。現時点では HTML に未到達のため採点対象外。

## 前回からの差分

- 全 5 項目 ±0 (4.2 → 4.2)。判定 PASS 維持。
- 持ち越し 3 件 (EV 同格表示 / `title` 依存鮮度 / waku 色 dark) は件数変わらず。既定レンジ 2.05MB を新たに数値付きで記録。
