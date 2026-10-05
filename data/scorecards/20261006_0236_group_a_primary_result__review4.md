# 2026-10-06 02:36 — Group A 主検定の実行と記録 (4 名レビュー、マージの前)

- 対象: worktree `group-a-class`、HEAD ce9a4cb (main 8447a35 から)。**subagent CWD 限定運用での評価**
- ai_builder_impact: none (共有のファイルの変更は config.py の CONSUMED_WINDOWS の追記と .gitattributes だけ。code-quality が確認)

| 担当 | 判定 | 総合 | must-fix |
|---|---|---|---|
| validation-process-auditor | PASS | 4.4 | なし (手順・順序・sha・MDE を一次データで再計算、マージ可) |
| code-quality-reviewer | PASS | 4.4 | なし (arm / primary の分離、テスト 110 本、変異 R16〜R20、共有のファイル) |
| prediction-logic-analyst | CONDITIONAL | 4.1 | 判別できなかった主因の書き方の訂正 (レース内の分散 0.26 が主、市場との相関は従で約 2 割) |
| profitability-judge | CONDITIONAL | 3.7 | 収益の 1 行 (β̂ では比 1.25 の購入集合ほぼ 0、140% 級 β ≈ 0.28 は 99% 区間の外、観察用) / 残差化版の診断の注記 |

平均 4.15。must-fix はすべて文書の修正で、反映した (docs/PHASE05_5_GROUP_A_RESULT.md の「意味」と「補足」、docs/PHASE05_5_EXPLORATION.md の
「C′ に引き継ぐ記録」)。

## 自己訂正

- 結果の文書とユーザーへの報告で「S と市場の相関が約 0.5 で、使える情報が事前の見込みの半分以下」と書いたのは主因の取り違え。
  power.json の情報行列で、市場の確率で重み付けたレース内の分散は 1 レースあたり 0.26 (866.5 / 3,335)、市場との相関で失うのは約 2 割
  (シューア補元 0.26 → 0.21)。主因は、S を全体で標準化して分散がレース間に回ったこと

## should-fix (反映したもの / 持ち越し)

- 反映: 同着の件数の突合 (事前登録の 6 は障害 1 を含む、平地 5) / sha256 は CRLF の作業ツリーの値 / §8-8 の判定日は保留と明記 /
  β_market 0.867 と P_new の定義 / primary の dirty の理由
- 持ち越し (code-quality): 開始の印を来歴の own_output に含める / git が無いときの例外を RunError に / 複合の理由の構造化
