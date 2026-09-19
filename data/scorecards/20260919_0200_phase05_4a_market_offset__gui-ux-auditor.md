# GUI / UX 監査人 採点 — efe611c Phase 0.5-4A 市場オフセットモデル

## 判定: HOLD (前回維持 — 本改修由来の減点・停止条件抵触なし)

**理由**: type-B (分析スクリプト + 学習成果物追加)。`gui/` `web/` `predictor/rules.py` `features.py` `ml_model.py` `config.py` に差分ゼロ。GUI への間接影響は前回と同じ 6 経路で不在を実測。判定は直近 GUI 採点 (3.2 / HOLD) を維持。
**根拠ファイル**: `predictor/ml_model.py:25,47,67` / `config.py:201-208,240-248` / `predictor/rules.py:1035` / `scripts/market_offset_model.py:42-54,156,173` / `scripts/market_offset_eval.py:43-47,323`
**次アクション**: 0.5-4A 不合格により R1-R8 (前回提示の表示要件) の GUI 実装は着手不要。

**改修タイプ宣言**: type-B。`git show efe611c --stat` = 9 files / +1,736 / -3。P25 固有ゲートは N/A。

## 総合: 3.2 / 5 (前回 3.2 維持)

## 依頼: GUI / 既存予想経路への影響 — なし (6 経路実測)

1. **逆依存なし**: `grep -rn market_offset gui/ predictor/*.py web/ config.py` → 0 件。依存は一方向のみ。
2. **features.py / rules.py への作用なし**: 新規 2 script に monkeypatch / `_CACHE` 書換なし。`predictor/` 配下への書込は `save_model` と `META_PATH.write_text` の 2 箇所で、パスは固定。
3. **誤ロードなし**: `ml_model.py:25` は固定名 `lgbm_model.txt`。venv32 実測で確認。`predictor/` に `.txt` が 3 本並ぶが、ディレクトリ走査によるロードは `predictor/*.py` に存在しない。
4. **封印指紋に影響なし**: `SEALED_ARTIFACTS` は固定 6 key。venv32 実測 `len=6`、`market_offset_*` は含まれず。
5. **互換テーブル失効トリガに影響なし**: `rules.py:1035` の glob は `*-filtered.json` で新規 JSON は非該当。
6. **実行確認 (venv32 = GUI 実行環境)**: `gui.app` import OK、`sys.modules` に `market_offset` / `fundamental_eval` 不在。CONTROL_HTML JS 22,428 文字 `node --check` PASS。venv64: 13 passed / 40 passed・1 skipped。

**反証の試み**: 「venv32 で `tests/test_feature_manifest.py` が 3 件 FAIL する」→ 原因は `scripts/fundamental_eval.py` の `import numpy` で venv32 に numpy 不在。うち 1 件は前 commit でも落ちる。GUI 実行経路は numpy を要求しない。**本改修由来の回帰ではない**。ただしテスト実行環境を venv64 と明記することを推奨。

## 項目別 (前回維持、本改修による変動なし)

- タスクフロー / 発見性: 3/5
- エラーの人間化 / 回復支援: 3/5
- システム状態の可視性: 3/5 (鮮度表示は現在時刻基準の単一値のまま)
- 状態整合性 / 誤読防止: 3/5
- レイアウト / 入力効率 / a11y: 4/5

## 参考所見 (将来 GUI 露出時の留意点)

- 0.5-4A の結論 (β₂ 区間が 0 をまたぐ / 購入条件該当 0 頭 / 補正平均 0.31pt) は「補正が存在しない」に近い。将来 GUI に載せる場合、補正列が常に ±0.3pt だとユーザは「AI が仕事をしている」と誤読しやすい。**不合格モデルの出力は DOM に生成しない**のが正解。
- `predictor/` に実験モデルが蓄積 (`fundamental_model.txt` / `market_offset_model.txt`)。現在はロード経路が固定名のため安全だが、**将来誰かが `glob("*.txt")` を書いた瞬間に誤ロードが成立する構造**。`predictor/experiments/` 等への分離を提案。

## 停止条件チェック

- [x] GUI / HTML 差分なし
- [x] 6 経路で間接影響なし (実測)
- [x] JS `node --check` PASS / gui.app import OK (venv32)
- [x] 対象テスト 13 + 40 passed (venv64)
- [x] 専門領域別 Hard Fail 不抵触

## 過去提案の消化追跡

- **0913 持ち越し (2 回目)**: 「同日 3 回の重複 Discord 通知」の差分化 — `scripts/auto_predict.py` に該当なし。未消化。次回 (3 回目) で放置なら「システム状態の可視性」を 3 → 2.5 に降格する。
- 0918 提案 1-2 — 0.5-4A 不合格により実装契機が消えたため追跡対象から外す。

## 前回からの差分

- 全 5 項目変動なし。総合 3.2 → 3.2。判定 HOLD 維持。
- 新たに検出: venv32 の numpy 不在でテストが部分 FAIL (環境差、非回帰)。
