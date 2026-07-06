# 2026-07-06 09:00 — 11大系統外3系統追加の expert-review (7名全PASS・Opus代替採点) + 反映

## 採点モデルについて (透明性)

7名の専門家 subagent の定義は `model: fable` だが、**Fable 5 が現在システム全体で利用不可**
のため、本 review は全員 **Opus (claude-opus-4-8) で代替採点**した。過去の Fable 採点との
時系列比較には代替である旨を加味すること。各 subagent の所見冒頭にも代替採点の旨を明記済。

## 対象改修 (HEAD 407e13d → 本反映後)

`git diff 0f2ccff..HEAD` 範囲。種牡馬系統分類 (predictor/sire_lines.py) に **11大系統外の3系統**
を追加し、実 DB の unknown 上位種牡馬を「その他」でなく実系統名で表示する:

- **personon (パーソロン系)**: パーソロン/シンボリルドルフ/トウカイテイオー/メジロティターン/
  メジロアサマ/メジロマックイーン/メジロデュレン
- **stsimon (セントサイモン系)**: Ribot/His Majesty/Graustark/Tom Rolfe/Pleasant Colony/
  Princequillo/Round Table/Prince John/Prince Rose/Prince Chevalier
- **hyperion (ハイペリオン系)**: Hyperion/Aureole/Khaled/Swaps/Star Kingdom

各系統を LINE_LABEL/LINE_LABEL_SHORT/LINE_COLOR/COUNTRY_BY_LINE(全て eur 暫定)/FOUNDERS/
LINE_BY_SIRE に登録。加えて凡例のstale修正 (系統名非依存化)・tautology assert 是正・
FOUNDERS∩LINE_BY_SIRE 系統一致テスト追加。

## 採点結果 (7名並列・全員 PASS)

| 専門家 | 判定 | スコア | 主要所見 |
|---|---|---|---|
| profitability-judge | PASS | 5.0 | 収益経路への非流入を grep 実測 (predictor/features/rules/portfolio/filter/backtest で参照 0)。凡例が「期待値指標でない」明示 |
| code-quality-reviewer | PASS | 4.7 | 単一出典を構造テストで機械強制。tautology是正・overlapテストが有意。AST でリテラル重複0件実測 |
| prediction-logic-analyst | PASS | 4.6 | **血統事実24件全て正確 (誤帰属0)**。予測経路非流入を実証。Princequillo/Round Table枝のeurを将来override余地としてTODO |
| data-pipeline-engineer | PASS | 4.5 | 正規化20ケース全一致・遡上循環ガード実測・legacy DB耐性。audit を open_db_readonly 化する余地を指摘 |
| gui-ux-auditor | PASS | 4.2 | 前回HOLD(3.9)の凡例ドリフト必須指摘を**完全解消**と確認。ラベル解決を実測 |
| validation-process-auditor | PASS | 4.0 | 暫定性は3箇所で開示済・分類事実をテスト固定。OPERATION.md §10-1 突合キュー未追記をGAP指摘 |
| mobile-html-reviewer | PASS | 4.0 | ラベル併記で色近接衝突を救済(不変条件遵守)・凡例整合・狭幅予算OK。hyperion色がlight地で淡すぎと指摘 |

## 反映した指摘 (本コミット)

| 指摘 (指摘者) | 対処 |
|---|---|
| OPERATION.md §10-1 突合キューに新3系統の eur 暫定が未追記 = 暫定フラグ立てっぱなし (validation [必須]) | §10-1 に項目5を追記。personon/stsimon/hyperion の eur 暫定、Princequillo/Round Table 枝の usa 疑義を含め突合対象として明記 |
| hyperion `#4dd0e1` が light 地で dot 1.84:1 と淡すぎ (mobile) | `#26c6da` へ濃度up (northern/nearctic と距離確保しつつ light 可視性改善) |
| LINE_COLOR コメント「識別しやすい色」が14色飽和の実態と乖離 (mobile) | コメントを「色は補助・識別の唯一担保はラベル併記」に是正 (近接ペア実測値を明記) |
| test の `classify_country==eur` が暫定値を確定事実のように固定 (validation [任意]/data-pipeline) | テストに「eur は暫定・公式突合で要更新」コメント追記 |
| 凡例 stale (gui-ux [必須]・前回HOLD) | (既反映) race.html.j2:70 を系統名非依存の「系統判別不能」定義へ |
| tautology assert (code-quality) | (既反映) country_label に line_key を渡す `A or B` を分離し国キー/系統キーの区別を固定 |
| 2経路の系統割当ズレ (code-quality) | (既反映) test_founders_and_line_by_sire_agree_on_overlap を追加 |

テスト: **276 passed / 3 skipped** (test_sire_lines 32 passed)。

## 繰延 (低優先・実害小)

- audit_sire_lines.py を `open_db_readonly` で開く (診断ツールの書込みロック競合回避、data-pipeline)。
- 実機 audit で新3系統による unknown 率低下の定量測定 (本環境 DB は 0 byte で不可、コード側準備済)。
- 亀谷公式リスト突合で新3系統の eur を確定 (OPERATION.md §10-1・§10-2)。

## ユーザ実機の残作業 (継続)

1. **[最優先] cache 汚染バグ修正後の backtest 再検証**。
2. HN 産地オフセット確定 (probe_hn_offsets → parse_hn → BLOD 再取込 → フラグ True)。
3. probe_corner_offsets 緑化 → CORNER_BYTES_VERIFIED=True。
