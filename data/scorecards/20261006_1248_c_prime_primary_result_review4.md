# 2026-10-06 12:48 — Group C′ 主検定の実行と記録 (4 名レビュー、マージの前)

- 対象: worktree `c-prime`、レビュー SHA 58dd91e (base main 7a92b9d)。**subagent CWD 限定運用での評価**。主検定は再実行していない
- ai_builder_impact: none (config.py の CONSUMED_WINDOWS の追記だけ)

| 担当 | 判定 | 総合 | must-fix |
|---|---|---|---|
| validation-process-auditor | PASS | 4.5 | なし (順序・sha256・pinned blob・MDE を一次データで再計算、事前登録からの逸脱 0) |
| profitability-judge | CONDITIONAL | 4.2 | 結果の文書に「段階: 観察用のまま」 |
| prediction-logic-analyst | CONDITIONAL | 4.1 | 通過順位版の Group C を事前登録するための学習期の条件 (κ・反証の条件・主検定の年と多重比較) |
| code-quality-reviewer | CONDITIONAL | 4.1 | 2025 の履歴の digest の感度のテスト / 錠の前の照合も 2025 の結果を NULL にして読むことのテスト (独自の追加変異 X1'・X2'・X11' が生存) |

平均 4.23。prediction-logic は区間の幅から逆算した SE 0.0195 が結果を読まない Fisher の SE 0.0194 と一致することを確認 (検出力の手順の信頼性)。

## 反映

- テスト (`5a58261`、固定のファイルは変えない): digest の感度 (脚質・返還で変わり、着順・オッズで変わらない) / arm の照合の spy / Z_DIRECTION。変異 R35〜R37・C32 を KILLED
- 文書: 段階 / 通過順位版の Group C の学習期の条件 / 140% 級との距離 / 件数の見込み 2,349 と 0 頭の橋渡し / β_market の学習期との整合 / 同着 5 と 6 /
  1 − r² ≈ 0.15 / 同時の当てはめの準共線 / 4 分類の較正の痕跡 (新しい仮説の候補としてだけ) / 判定日は決めないまま不要に / 名前の表記 / 最初の凍結の主張の性質

## 持ち越し

- C′ と Group A の runner の共通化は、次の runner (通過順位版の Group C か Group D) のブランチの最初のコミットで、その runner の凍結より前に
  (Group A の `_check_pinned` は fail-open の写しのまま。両 runner は歴史的な記録として凍結)
- mutation_sandbox に `--only` と spec の sha256 の印字 / 来歴の own_output を複数のパスに (開始の印の除外) / 2025 のブートストラップの SE の保存 (次の群から)
- profitability: 族の総括の文書を Group D の結果が出た時点で書く (§4-3)。次の優先は A の標準化を直した再事前登録・通過順位版の Group C・D の順という意見
