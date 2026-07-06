# 2026-07-06 07:00 — 英語名辞書 + 正規化頑健化の expert-review (7 名全 PASS) + 反映

## 対象改修

「父母父/母母父の系統が『その他』」「その他が残る」への構造的対処:
1. UM 3代血統は海外祖先を英語名格納 → LINE_BY_SIRE に国際種牡馬 **実数 90 件**を英語で追加。
2. _normalize を NFKC + 小書き仮名→大書き + 英字小文字化 + 記号/空白畳み込みに強化
   (Mr.Prospector↔Mr. Prospector、A.P.Indy、Sadler's Wells の ' 字種、全角ローマ字を吸収)。

## 採点結果 (7 名並列・全員 PASS)

| 専門家 | 判定 | スコア | 主要所見 |
|---|---|---|---|
| prediction-logic-analyst | PASS | 4.7 | **英語名 90 件全件正確 (誤り 0)**。綴り変種/英語 COUNTRY_OVERRIDE を留保 |
| mobile-html-reviewer | PASS | 4.4 | 英語名 peditem 最悪 230px<予算。凡例ドリフト構造根絶を確認 |
| profitability-judge | PASS | 4.2 | 収益経路非流入を grep 実証。英語国別 override 不在を指摘 |
| gui-ux-auditor | PASS | 4.1 | 誤「その他」の実解消。英語原表記主義は誠実 |
| code-quality-reviewer | PASS | 4.0 | 正規化単一経路・衝突 0。literal 重複盲点・件数記載ズレ |
| validation-process-auditor | PASS | 4.0 | 検証プロセス準拠。audit gen3 未カバー・綴り未突合 |
| data-pipeline-engineer | PASS | 3.9 | .lower() 副作用なし。綴り変種脆弱性・audit gen3 未カバー |

## 全指摘の反映 (本コミット)

| 指摘 (指摘者) | 対処 |
|---|---|
| 綴り変種脆弱性 (prediction-logic/validation R-4/data-pipeline P2): Mr.Prospector/A.P.Indy/全角/アポストロフィ字種で unknown 劣化 | **_normalize に NFKC + 記号/空白畳み込み**追加。全角ローマ字・ピリオド有無・スペース差・' 字種を吸収。regression テスト |
| audit が gen3 列未カバー (validation R-1/data-pipeline P1) | audit_sire_lines を父/母父/**父母父/母母父**の 4 世代集計に拡張 (英語名の効果測定可能に) |
| 英語 COUNTRY_OVERRIDE 不在 (profitability/prediction-logic) | Mill Reef→eur、Deputy Minister/Vice Regent→usa を英語で併記 (カナ子孫と国別一致) |
| literal 重複キー盲点 (code-quality #1) | ast で全 dict リテラルの重複キーを検査するテスト追加 |
| 英↔カナ整合ガード欠如 (code-quality #2/profitability #2) | 主要 10 ペアの系統+国別一致テスト |
| 英語名長予算 (mobile #3) | 英語キー ≤20 字の parity テスト |
| 狭幅 nowrap 溢れ (mobile #1、既存条件) | ≤400px で .ctag を display:block・pedline に max-width |
| 暫定性の開示 (validation R-3) | 英語ブロックに「観測済み数件・残り暫定・安全側劣化」コメント |
| 残作業明文化 (validation R-2/R-5) | OPERATION.md §9-3「その他削減の効果測定」新設 (audit 実行・残存英語名クエリ・11大系統外は正しくその他) |
| 件数記載 (code-quality/data-pipeline) | 本 scorecard に実数 90 件で記載 |

テスト: **274 passed / 3 skipped**。

## 「その他」の完全解消可能性についての正直な整理

- **構造的に潰した**: 仮名大小差 + 英語名 + 綴り変種 (NFKC/記号) + traversal。11 大系統に
  血統が繋がる種牡馬は名前表記が想定内なら分類される。
- **残る「その他」の 2 種**: (a) **11 大系統外** (パーソロン系メジロマックイーン、In Reality 系
  ダノンレジェンド 等) = **正しい「その他」**。(b) 辞書未収載かつ想定外表記の海外祖先 =
  実 DB の unknown 上位を見て随時追記。(b) の網羅は実機 audit 出力が一次資料。

## ユーザ実機の残作業 (次回・繰延一覧)

1. **[最優先] cache 汚染バグ修正後の backtest 再検証** (20260706_0300 から継続)。
2. **「その他」残存の実測**: `python -m scripts.audit_sire_lines` (gen3 対応済) で unknown 上位を確認 →
   想定外表記の海外祖先を辞書追記。11 大系統外は正しくその他のまま。
3. HN 産地オフセット確定 (probe_hn_offsets → parse_hn 修正 → BLOD 再取込 → フラグ True)。
4. 亀谷公式リスト突合 (国別、OPERATION.md §10)。probe_corner_offsets 緑化 → CORNER_BYTES_VERIFIED=True。
