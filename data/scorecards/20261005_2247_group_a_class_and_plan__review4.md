# 2026-10-05 22:47 — Group A のクラスの抽出 + §8-4b-2 + 探索台帳の事前固定 (4 名レビュー)

- 対象: worktree `group-a-class` (branch group-a-class-20261005)、8447a35..2ae320f。**subagent CWD 限定運用での評価** (main には未反映)
- 対象の変更: scripts/group_a_class_table.py・tests/test_group_a_class_table.py (新規)、data/backtest/group_a_class_20261005/
  (対象の事前固定 → JRA 公式の期待値 → probe 36/36 → 2021-2025 の表 17,292 レース)、docs/PHASE05_5_CLASS_EXTRACTION.md、
  docs/PHASE05_5_PREREG.md §8-4b-2 (追補)、docs/PHASE05_5_EXPLORATION.md (新規、探索の前の固定)
- ai_builder_impact: none (DB・schema・共有の parser は不変。data-pipeline が確認)

| 担当 | 判定 | 総合 | must-fix |
|---|---|---|---|
| validation-process-auditor | CONDITIONAL | 4.3 | 同点の規則の全順序 (軸をまたぐ・連鎖) / §8-4b の当日の馬場差の段落 (613-617、テストの要求を含む) を置き換えることの明記 |
| prediction-logic-analyst | CONDITIONAL | 3.6 | W1 の識別の保護 (ハンデ戦を推定から除く、w ≤ 0 なら W1 無効) / 馬場差に当該レース自身を含めるかの固定 |
| data-pipeline-engineer | PASS | 4.4 | なし (probe と build を自分で再実行してバイト一致、DB と双方向で差 0) |
| code-quality-reviewer | CONDITIONAL | 4.0 | MANIFEST に git_dirty と読んだ / 捨てた件数 / 表が data_div 9 と障害を含む超集合であることの明記 |

平均 4.08。

## should-fix (要旨)

- validation: 交差 (1 年推定) と最終 (3 年推定) で疎なセルの率が 5〜8 倍違うことを A-3 に記載 (1 年: セル 20 未満のレース 7.2% / 9.4%、
  評価値なし 2.9% / 2.8%。3 年: 1.1% / 0.6%) / V1・V2 の自レースの包含の偏りの明記 / 探索の loader に year ≤ 2024 のコード強制 + テスト /
  2022⇄2023 の選択結果をコミットしてから 2024 の dry run / 障害の定義の統一 (§8-4b「52〜57」と A-0「51 以上」)
- prediction-logic (学習期 2022-2024 のデータで実測): 標準タイムの模型を秒 / km で推定 (g・c と V の単位をそろえる) / 年齢の制限の区分
  (class_table の c2〜c5 から導出) を局外の補正に追加 (999 の 2〜3 歳限定 248 戦が +0.484 s/km) / 大差負けの裾を固定の上限で winsorize /
  診断に「過去走の頭数と S の相関」(残差 / km と頭数の相関 −0.139、≤ 8 頭 +0.17 s/km vs 15〜18 頭 −0.07 s/km) /
  W1 は同じ馬の中でも斤量が時間とともに増える (相関 +0.354) ので逆符号に推定されやすい / `rank_in_race` と `last` は市場と相関が高く、
  市場の外の情報が残りうるのは `best3_365` と `trend_365`
- data-pipeline: 空の raw で黙って成功 / 書き込みの途中の失敗で半端な csv / `expected_jra_official.py` の改行 (新規 clone で sha が変わる) /
  build_run.txt の来歴 / docs の `probe_class.py` の誤記・data_div 9 の明記 / 重複ファイルの distance・track_type_code の食い違いも停止条件に
- code-quality: 原子的な書き込み / 短いレコード / `race_id()`・`is_jra` の重複 / private な `_split_fixed` の依存の明記 / `.py` の eol /
  テストの追加 (短いレコード・data_div 9・probe の「raw に無い」・`_git_sha` の unknown・失敗時に csv が残らない)

## 自分で見つけた誤記

- `expected_jra_official.py` の docstring の取得時刻「22:2x〜22:36」は誤り。実際は対象のコミット (7d9518a、22:34:38) の後の 22:34〜22:36
  (内蔵ブラウザの `new Date()` で D2 の取得時に 13:36Z = 22:36 JST を記録)。validation の指摘「取得の開始が対象のコミットより前」は
  この誤記から生じたもので、期待値は対象の固定の後に取った。sha を保つため本体は書き換えず、正誤表で訂正する

## 次

指摘を反映 (コードと文書) → 仕様に関わる提案 (秒 / km の模型・年齢の制限の区分・裾の上限・W1 の保護) は外部の指示者に諮る →
探索の開始は確認の後。
