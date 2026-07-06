# 2026-07-06 03:00 — テン・上がり・先行力パネル (SmartRC 部分実装) の expert-review 反映

## 対象改修

ユーザが SmartRC の「テン・上がり・先行力」パネル (スクリーンショット) を提示し
「この情報が無い」と指摘。検証済みデータで作れる部分を実装 (ユーザ承認)。
前コミット 457fc69 (baseline) + 本コミット (7 名レビュー指摘の反映)。

## 採点結果 (7 名並列、全員 HOLD → 全指摘対処)

| 専門家 | 判定 | スコア | 主要所見 |
|---|---|---|---|
| mobile-html-reviewer | HOLD | 4.2 | 凡例不整合 + 非対応注記の分離 |
| code-quality-reviewer | HOLD | 4.1 | 凡例不整合 + コメント重複 + テスト欠如 |
| profitability-judge | HOLD | 4.0 | 凡例「その時の」= best-of-best 合成の過大表示 |
| data-pipeline-engineer | HOLD | 3.9 | 凡例不整合 + **cache 汚染バグ検出** |
| validation-process-auditor | HOLD | 3.9 | **cache key 汚染バグ (予測層に波及)** + probe 単一情報源 |
| gui-ux-auditor | HOLD | 3.5 | 凡例不整合 + 用語二重化 + ジャーゴン |
| prediction-logic-analyst | HOLD | 3.4 | 凡例不整合 + **「テン」は用語誤り (テン≠4角)** |

## 最重要: cross-horse cache 汚染バグ (validation/data-pipeline 検出、確認済み実バグ)

`predictor/features.py` の `relative_race_metrics` は past_run の**馬番に固有**の値
(タイム差・上がり順位) を返すが、cache key (旧 1221 行) がレース識別子のみで馬番を
含まず、レース内共有 feature_cache 経由で**同一過去レースを走った 2 頭目以降が
1 頭目の値に汚染**されていた。波及先は `rules.py:643` の上がり順位スコア (+4/+2) と
LGBM 特徴 `best_final_3f_rank`/`best_relative_time_diff`。
→ **cache key に `horse_num` を追加**して解消 (馬番はレース内一意なので (レース識別
+馬番) で past_run を一意決定)。`tests/test_relative_race_metrics.py` で汚染の実証
(旧キーでは 2 頭目が 1 頭目の値を引く) と修正後の馬固有性を固定。

**⚠ backtest 再検証が必要**: この修正は feature 値を変える (汚染除去)。scoring/LGBM を
使う backtest 数値が (共有 cache で走っていれば) 動く。ユーザ実機で
`scripts.backtest` の再実行と data/backtest/ の rule_version 付き再保存を推奨
(汚染除去は品質向上方向だが、数値影響の測定が必要)。

## 表示指摘の対処 (全 7 名共通のブロッカー + 個別)

| 指摘 | 対処 |
|---|---|
| 凡例「(上N位)=その時の」が実装 (独立 min=別レース合成) と不整合 (全 7 名) | 表示を「(近走最高N位)」に、凡例を「近走で記録した最良のレース内上がり順位(最速タイムと別レースの場合あり)」に。views コメントも是正 |
| 「テン」は用語誤り (prediction-logic: テン=序盤/4角=終盤) | 「テン」→「先行力」に改称。凡例に「SmartRC のテン(序盤)とは別概念・4角位置取りで代替」。features.py docstring「テンP相当」も是正 |
| probe 状態と (暫定) ラベルの単一情報源なし (validation) | config.CORNER_BYTES_VERIFIED フラグ新設。False の間だけ「(暫定)」付与、probe 緑化で True 反転 → 外し忘れ防止 |
| コメント重複 (code-quality F-2, data-pipeline) | views.py の旧コメント削除、新文言に一本化 |
| 新分岐のテスト欠如 (code-quality F-3, validation #6) | test_horse_detail_line_agari_rank_and_pace_provisional (4 分岐: 順位併記/時間のみ/先行力暫定/データ無) |
| 凡例ドリフト防止 assert の新トークン未適用 (gui-ux #4, mobile #2) | test_webapp に「近走で記録した最良…」「テン1F・CR・シェア」の固定 assert 追加 |
| 非対応注記のジャーゴン/未分離 (gui-ux #3, mobile #3) | probe/バイト位置 の内部語をユーザ向け文言に。SmartRC 差異を別 <p> に分離 |
| シェア記述の矛盾 (validation (b)) | views の父×馬場「Share 相当」コメントを「シェアとは別物 (未対応)」に是正 |
| 「上T…(上N位)」の「上」重複 (gui-ux) | 「(近走最高N位)」で解消 |

テスト: **265 passed / 3 skipped** (+ cache 汚染 regression 3 本 + detail 分岐 4 分岐 + 凡例固定)。

## SmartRC パネルの対応状況 (ユーザ回答)

- ✅ 上がり3F (時計 + 近走最高順位): 検証済みバイト位置 (final_3f=391)
- ⏳ 先行力 (4角位置取り): 実装済・corner バイト位置 probe 緑化まで「(暫定)」。緑化で自動確定
- ❌ テン1F / CR / シェア: JV-Data に該当値が無く再現不可 (凡例明記)

## ユーザ実機の残作業 (次回セッション)

1. **[最優先] cache 汚染バグ修正後の backtest 再検証** — scoring/LGBM 数値の変化測定。
2. verify_pedigree (父母父/母母父確定) / unknown 一覧 (その他削減) / audit_sire_lines /
   probe_corner_offsets 緑化 → CORNER_BYTES_VERIFIED=True。
3. 亀谷公式リスト突合 (国別血統、OPERATION.md §10)。
