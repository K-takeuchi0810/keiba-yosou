# 採点 2026-06-30 02:04

**改修内容**: 参照系・速報系レコード RC/CS/YS/BT/HY/WE/AV/TC の取り込み (commit 0a37ae1)。data-pipeline HOLD 指摘の record_master PK バグを是正 (commit 69b55d1)。
**対象ファイル**: jvlink_client/parser.py, jvlink_client/ingest.py, db.py, data/schema.sql, tests/test_reference_records.py

## 総合スコア (項目平均) の推移

| 専門家 | 今回 | 前回 | 差分 | 判定 |
|---|---|---|---|---|
| GUI / UX 監査人 | 3.6 | 3.6 | ±0 | PASS (スコープ外・再実行せず継承) |
| モバイル HTML レビュアー | 4.6 | 4.6 | ±0 | PASS (スコープ外・再実行せず継承) |
| 予想ロジック分析官 | 4.0 | 4.0 | ±0 | PASS |
| 収益性ジャッジ | 4.0 | 4.0 | ±0 | PASS (スコープ外・継承) |
| データ基盤エンジニア | 3.6 | 4.4 | **⚠ 後退 -0.8** | HOLD → **是正済** |
| コード品質レビュアー | 4.3 | 4.2 | +0.1 | PASS |
| 検証プロセス監査人 (最終ゲート) | 4.3 | 4.1 | +0.2 | **GATE PASS** |

平均 (substantive 4) ≈ 4.05。最終ゲート PASS。
**⚠ データ基盤 -0.8 後退**: record_master PK の silent data loss バグ (下記)。HOLD 判定だったが
同セッションで是正済 (commit 69b55d1) → 後退要因は解消。

## ⚠ 後退の内容と是正 (data-pipeline HOLD)

**実 raw で検出された correctness バグ**: record_master の旧 PK
`(record_id_kubun, track_code, track_type_code, distance, grade_code)` は記録区分と
レース日付を含まず、RC raw 2165 件中 **1691 件(78%) を INSERT OR REPLACE が黙って破棄**。
残る 1 行も最速でも最新でもなく「ファイル順最後」(例: 2021年 56.8s の記録があるのに
1995年 101.3s の phantom を保持)。F5 速度指数の基準として使えない状態だった。

**是正 (69b55d1)**: PK に `record_div, race_year, race_month_day, race_num` を追加し記録の
履歴を全保持 (2165→2129 行, loss 1691→36)。live DB は DROP+再作成+RC 再 ingest で
474→2129 行に修復。例コースの最速 56.8s が保持されることを確認。

## 各専門家の所見 (要約)

### 検証プロセス監査人 (4.3, GATE PASS) ★最終ゲート
production 全パスから新 8 テーブル参照ゼロを grep 実証。WE/AV/TC の PIT 規律を schema
コメントで具体化 (announced_time アンカー)。前回降格宣言 (1)`_split_fixed` トラップは
新 8 種で parse_*_file を付けず再発なし → **クローズ**。byte 位置は実 raw 回帰で第三者再現可。
**降格宣言 (2) 継続**: features.py がこれら 8 表を参照した瞬間、PIT ゲートのコード実装が
無ければ即 FAIL (スコープ外免除なし)。RC 行数乖離 (474 vs 2165) を 1 行明記要求 → 本是正で解消。

### データ基盤エンジニア (3.6, HOLD → 是正済)
production 完全分離・冪等性 OK。WE の announced_time in PK は PIT 保全として正しい。
**record_master PK の silent data loss を実 raw で実測検出** (上記、-0.8 の根拠付き)。
提案: (1) record_master PK 是正 [済]、(2) ingest summary に「処理レコード数 vs PK dedup 後
行数」の乖離を出す (silent collapse 検出)、(3) 致命例外の種別集計 (継続課題)。

### コード品質レビュアー (4.3, PASS ⬆+0.1)
dead code 3→5: 前回後退要因の `parse_*_file`/`_split_fixed` トラップを、新 8 種で
parse_*_file を付けない明示判断で根絶。`_upsert_race_keyed` 汎用化と `_upsert_master` の
2 系統は key 構造の違いに対応した妥当な分割。BT byte 補正の根拠コメント・_fit ガード継承を評価。
提案: _upsert_race_keyed の year 限定 docstring [済]、致命例外種別集計 (継続)。

### 予想ロジック分析官 (4.0, PASS)
features.py 未参照 (土台整備)。エッジ期待 **BT系統(F9, 市場外情報で最有望) > WE(馬場ドリフト)
>> RC(速度基準) ≈ AV(頭数衛生)**。水準スナップショットは市場既織り込みで alpha≈0、価値は
時系列ドリフトと系統×コース交互作用。AV/WE は既存 F1(compute_race_relative)/F2(_gate_zone)
の分母 (starter_count) 補正・馬場層別にも効く。**CS/YS/HY/TC は純参照=死蔵候補** (特に HY 176k)。

### GUI/UX (3.6) / モバイル (4.6) / 収益性 (4.0) — 継承 PASS
gui/web/predictor/config の diff ゼロ (前回 20260630_0131 と同一スコープ)。再実行せず継承。

## 横断的に見た優先課題 (是正後に残るもの・優先順)

1. **特徴量化前の PIT ゲートをコード強制** (validation 降格宣言 (2)) — features.py が exotic_odds/
   vote_counts/weather_going 等を参照する瞬間、発走前 announced_time 限定 or PK data_div 化を
   実装と同時に。怠れば次回 FAIL。
2. **ingest 観測性: 処理数 vs dedup後行数の乖離出力** (data-pipeline #2) + 致命例外の種別集計 (継続)。
3. **純参照テーブル (CS/YS/HY/TC) の死蔵明示** (予想ロジック) — F 番号に紐づかないものは
   schema に「網羅目的・予測非接続」を注記、または ingest 対象から外す検討。
