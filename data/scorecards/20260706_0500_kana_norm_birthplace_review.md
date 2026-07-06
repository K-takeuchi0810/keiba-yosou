# 2026-07-06 05:00 — 仮名正規化 (その他削減) + 産地抑制 + 父母父確定 の expert-review

## 対象改修 (実 DB 検証の往復を含む)

ユーザ実機での確認出力を受けた 3 件の確定作業:
1. **父母父・母母父 = 確定** (ディープ産駒 父母父=Alzao、充填 89-94%)。parser docstring を確定へ格上げ。
2. **「その他」の主因 = 仮名大小差** (JV-Data 大書き ヤ/ヨ/ツ vs 辞書小書き ャ/ョ/ッ)。
   _normalize に小書き→大書き変換 + 正規化済み照合表で構造的に解消。unknown 上位から 9 頭追加。
3. **産地 (HN 205-229) = オフセット誤り判明** → config.HN_BIRTHPLACE_VERIFIED=False で表示抑制、
   probe_hn_offsets.py で正しい位置特定の道筋。

## 採点結果 (7 名並列)

| 専門家 | 判定 | スコア | 主要所見 |
|---|---|---|---|
| prediction-logic-analyst | PASS | 4.4 | 追加 9 頭全件正確・仮名正規化の衝突ゼロ実証。フォーティナイナーズサン要確認 |
| profitability-judge | PASS | 4.3 | 収益経路非流入・セル再編の統計ガード維持を実証 |
| data-pipeline-engineer | PASS | 4.3 | 産地抑制の門番規律・probe 分割を合成3形式で実証。繁殖番号シフト連動を要確認 |
| code-quality-reviewer | PASS | 4.1 | 正規化照合表は模範。audit_sire_lines の照合乖離 (P1) を検出 |
| validation-process-auditor | PASS | 4.1 | 検出→抑制→probe の house standard 準拠。doc 同期 (R-1/R-2) 要 |
| gui-ux-auditor | HOLD | 3.8 | 凡例「取込後に表示」が実態(非表示)と不一致 = 凡例ドリフト 3 回目 |
| mobile-html-reviewer | HOLD | 4.2 | 同上 (凡例不整合) + 375px nowrap 溢れ (既存条件) |

## HOLD 2 件 + 全指摘の対処

| 指摘 | 対処 |
|---|---|
| **凡例ドリフト 3 回目 (gui-ux/mobile HOLD)**: 産地凡例「取込後に表示」が実態(フラグで非表示)と不一致、しかも固定 assert が stale 文言を保護 | **構造的根絶**: render_race に show_origin (=HN_BIRTHPLACE_VERIFIED) を渡し、凡例の産地記述をフラグ連動の Jinja 分岐に。False では「検証未完了のため非表示」、True で産地説明を表示。両分岐の固定 assert を更新 (表示=実表示の単一情報源) |
| **audit_sire_lines 照合乖離 (code-quality P1)**: _normalize 大書き化で生 FOUNDERS/LINE_BY_SIRE の小書きキーに当たらず診断数値が歪む | 公開 lookup_line() 追加 + audit を正規化済み照合 (_FOUNDERS_N ローカル / lookup_line) へ |
| doc 同期 (validation R-1/R-2) | OPERATION.md §9-2 を「UM=確定 / HN=誤り判明+probe 手順」に、parse_hn docstring を「205-229 誤り判明・抑制中・probe で確定」に更新 |
| 正規化キー衝突ガード (code-quality P2 / prediction-logic / profitability / validation R-3) | test_normalized_lookup_no_key_collision (len parity 3 辞書) |
| ヵ/ヶ 欠け (prediction-logic / code-quality / data-pipeline / profitability) | _KANA_SMALL_TO_LARGE に ヵヶ→カケ 追加 |
| フォーティナイナーズサン 父名疑義 (prediction-logic) | 投機的追加だったため除去 (unknown 一覧外・確度不足) |
| turnto コメント (prediction-logic) | Sir Gaylord 枝 (Hail to Reason 非経由) も内包する旨を FOUNDERS コメントに追記 |
| 繁殖番号シフト連動 (data-pipeline MED-1) | probe に父繁殖/母繁殖の現行 vs 候補行を追加。parse_hn docstring に「230-249 も同方向ずれ疑い」明記 |
| probe nit (code-quality P3 / data-pipeline) | dead step 削除 (CRLF 分割へ書換で解消)、ファイル検出を read(64)+"HN" in head に、_split_records (ingest 共通) で分割 |

テスト: **269 passed / 3 skipped**。

## 実 DB 検証で確定した事実

- **父母父/母母父**: UM idx8=父母父/idx12=母母父 のバイト位置正当性を実証 (Alzao × 6 頭)。
- **「その他」主因**: 仮名大小差。正規化で リアルシヤダイ/アンバーシヤダイ/トウシヨウボーイ 等が回復。
- **産地**: HN 205-229 は誤り (先頭欠け+"11"混入)。表示抑制済み、要 probe 確定。

## ユーザ実機の残作業 (繰延・次回セッション、validation R-5)

1. **[最優先] cache 汚染バグ修正後の backtest 再検証** (20260706_0300 から継続)。
2. **HN 産地オフセット確定**: `probe_hn_offsets` 実行 → parse_hn 修正 → BLOD force 再取込 →
   HN_BIRTHPLACE_VERIFIED=True。繁殖番号 230-249 のシフト連動も同時確認 (無音誤りに注意)。
3. **亀谷公式リスト突合** (国別血統、OPERATION.md §10)。
4. **audit_sire_lines / probe_corner_offsets 緑化** → CORNER_BYTES_VERIFIED=True。
5. verify_pedigree の第2アンカー (キズナ産駒 父母父=ストームキャット) 突合記録 (validation R-4)。
