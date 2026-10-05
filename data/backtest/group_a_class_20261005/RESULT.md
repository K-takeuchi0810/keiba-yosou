# 競走条件コード (クラス) の probe — 結果 (2026-10-05)

- 判定: **合格**。36/36 レースで、最若年条件 (位置 635) が JRA 公式の表記から作った canonical class と一致し、最若年の年齢の欄
  (2 歳 → 623、3 歳 → 626、4 歳以上 → 629) も同じ値 (`probe_run.txt`、コード f950d6a、rc 0)
- コミットの順: 対象の固定 `7d9518a` (22:34:38) → 期待値 `1060a60` (22:37:00) → script `f950d6a` → probe の結果 `5f8976e` → 表の凍結
- 表: `class_table.csv` (sha256 `24d8bbc9…1817`)、`MANIFEST.json`。2021-2025 の JRA の 17,292 レース
  (平地 16,666 = `data_div 7` 16,651 + 中止 `9` 15、障害 626)。DB の races と双方向で差 0 (data-pipeline の確認)
- 4 名レビュー: `data/scorecards/20261005_2247_group_a_class_and_plan__review4.md`

## 正誤表

- `expected_jra_official.py` の docstring の取得時刻「22:2x〜22:36 JST」は **誤り**。正しくは **22:34〜22:36 JST** で、対象の固定の
  コミット `7d9518a` (22:34:38) の後に取った (D1 → D3 → D2 の順。D2 の取得時に内蔵ブラウザの `new Date()` で 13:36Z = 22:36 JST を
  記録)。期待値のファイルは sha256 (`121b1906…7fca6`) を保つため書き換えない
