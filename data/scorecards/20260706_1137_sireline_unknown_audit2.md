# 採点 2026-07-06 11:37

**改修内容**: gen3 対応 `audit_sire_lines` の unknown 上位から、安全に既存 `line_key` へ接続できる高頻度種牡馬 20 件を追加
**対象ファイル**: `predictor/sire_lines.py`, `tests/test_sire_lines.py`

## 改修サマリ

- `LINE_BY_SIRE` に、JV-Data 実 DB の unknown 上位から 20 件を追加。
  - 例: ネヴアービート / ロイヤルスキー / チヤイナロツク / ミルジヨージ / lasttycoon / wildagain / lawsociety
- 既存 line_key (`northern`, `nasrullah`, `native`, `nearctic`, `stsimon`, `hyperion`) に父系事実で安全接続できるものだけ採用。
- Buckpasser / Hindostan / In Reality など、既存ラベルへ雑に押し込むと危険な枝は unknown のまま保留。
- JV-Data の大書き仮名、英字小文字、空白なし英字を `classify_sire()` 経由で固定する regression test を追加。

## audit 実測

| 指標 | 変更前 | 変更後 | 差分 |
|---|---:|---:|---:|
| dict_hit | 340,644 / 840,049 (40.6%) | 386,142 / 840,049 (46.0%) | +45,498 / +5.4pt |
| traversal_hit | 0 (0.0%) | 0 (0.0%) | ±0 |
| unknown | 499,405 (59.4%) | 453,907 (54.0%) | -45,498 / -5.4pt |
| 辞書 vs 独立遡上不一致 | 0 | 0 | ±0 |

`traversal_hit=0` のため、不一致 0 は「独立遡上で判定できた範囲に矛盾がない」という限定付きの証拠。今後は audit 出力を machine-readable に保存するか、`dict_hit` のうち独立遡上でも検証できた件数を出すと検証力が上がる。

## テスト

- `.venv64\Scripts\python.exe -m pytest tests/test_sire_lines.py tests/test_relative_race_metrics.py -q`
  - 34 passed
- `.venv64\Scripts\python.exe -m pytest tests/test_webapp.py -q`
  - 13 passed
- validation-process-auditor による再確認:
  - `.venv64\Scripts\python.exe -m pytest tests/test_sire_lines.py tests/test_relative_race_metrics.py tests/test_webapp.py -q`
  - 47 passed

## 総合スコア

| 専門家 | 今回 | 前回 | 差分 | 判定 |
|---|---:|---:|---:|---|
| GUI / UX 監査人 | 4.2 | 4.1 | +0.1 | PASS |
| モバイル HTML レビュアー | 4.8 | 4.4 | +0.4 | PASS |
| 予想ロジック分析官 | 4.3 | 4.7 | **-0.4 ⚠ 後退** | PASS |
| 収益性ジャッジ | 2.8 | 4.2 | **-1.4 ⚠ 後退** | PASS |
| データ基盤エンジニア | 4.2 | 3.9 | +0.3 | PASS |
| コード品質レビュアー | 4.1 | 4.0 | +0.1 | PASS |
| 検証プロセス監査人 | 4.0 | 4.0 | ±0.0 | PASS |
| **平均** | **4.06** | **4.19** | -0.13 | PASS |

### 後退の解釈

- 予想ロジックは 4.3 と高水準だが、前回 4.7 が「英語名 90 件 + 正規化頑健化」の強い改修だったため相対的に -0.4。今回の実装そのものは PASS。
- 収益性 2.8 は、今回の辞書追加が EV / Kelly / 買い目 / 確率校正へ直接流入しないため「回収率改善を主張できない」という評価。今回変更による収益悪化ではないが、直近 backtest が控除率未満のため投資採点は低く維持。

## 各専門家の所見

### GUI / UX 監査人

PASS 4.2。`gui/app.py` は非変更で GUI 操作への直接副作用は低い。血統系統の「その他」誤表示が減るため、ユーザが見る表示信頼性にはプラス。将来 GUI に出すなら「辞書ヒット率 / unknown 率 / 不一致 0」を短い監査結果として見せるとよい。

### モバイル HTML レビュアー

PASS 4.8。専用 role が 2 回タイムアウトしたため、同じ mobile-html 観点を default subagent で代替採点。`webapp/templates` は未変更で新規 CSS なし、既存 `line_key` のラベル/色に乗る変更のため iPhone Safari 表示リスクは低い。英字キー長テスト維持、凡例ドリフトなし、webapp 13 passed。実機/スクショ未確認のため満点ではない。

### 予想ロジック分析官

PASS 4.3。Never Say Die -> Nasrullah、Royal Ski -> Raja Baba -> Bold Ruler、Lucky Sovereign -> Nijinsky、Mogami -> Lyphard、Le Fabuleux / Law Society -> St. Simon、Chateaugay -> Swaps -> Hyperion など、既存 `line_key` への接続は概ね妥当。Buckpasser / Hindostan / In Reality を保留した点も過剰分類抑制としてよい。軽微リスクは `Kris` と `Kris S.` の同名曖昧性で、現行テストでは分離できている。

### 収益性ジャッジ

PASS 2.8。今回変更は血統表示・集計・audit 精度改善であり、予想スコア、EV、Kelly、買い目フィルタには直接流入しない。長時間 backtest は不要。投資判断上の価値は「血統集計の読み違いを減らす」「unknown 上位の次回改善候補を絞る」までで、即時の回収率改善や買い候補増加を示す証拠ではない。

### データ基盤エンジニア

PASS 4.2。JV-Data の大書き仮名 (`ネヴアービート`, `チヤイナロツク`, `シヤトーゲイ`) と英字小文字を正規化経由で固定できている。audit は父・母父・父母父・母母父を集計し、前回指摘の gen3 未カバーを解消方向。不一致 0 は強いが `traversal_hit=0` のため、独立検証の厚みは次回改善余地。

### コード品質レビュアー

PASS 4.1。追加は既存辞書運用に沿っており、literal duplicate 0、正規化衝突 0、既存 line_key 不整合なし。`LINE_BY_SIRE` が 400 件超になったため、今後同種の audit 追加が続くなら `source`, `canonical_name`, `line_key`, `reason` を持つ fixture / TSV 化を検討する段階。

### 検証プロセス監査人

PASS 4.0。before/after audit、独立遡上不一致 0、20 件 regression test、関連テスト緑化が揃っている。静的辞書追加で EV/Kelly/予想スコアへ直接流入しないため、長時間 backtest 未実行判断は妥当。減点は audit before/after が machine-readable な永続ログではない点と、前セッション由来の未追跡ファイルが残っている点。

## 横断的に見た優先課題

1. **未追跡ファイルの整理**
   - `data/backtest/20260703_053033_tan_p26-lgbm-v6-calibfit-2025-filtered.json`
   - `predictor/_v5_backup/`
   - どちらも前セッション残置。検証ログや `git status` のノイズになるため、次の本格 backtest / commit 前に採否を決める。

2. **audit 結果の永続化**
   - 今回の before/after は本 scorecard に保存したが、次からは `data/audit/` などに JSON/CSV で残すと再現性が上がる。
   - `traversal_hit=0` の理由と、独立遡上で検証できた dict_hit 件数を出せると validation score が上がる。

3. **辞書の構造化**
   - `LINE_BY_SIRE` は 400 件超。今後も unknown 上位を追加するなら、出典・追加日・audit batch を持つ TSV / fixture 化を検討。

