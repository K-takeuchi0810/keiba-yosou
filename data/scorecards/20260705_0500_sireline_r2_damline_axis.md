# 2026-07-05 05:00 — 系統辞書第2次拡充 + ターントゥ系新設 + 傾向集計の母父系統軸 (edb7b72 + 追補)

## 対象改修 (rubric v4: type-B/D)

実機での「まだ『その他』が残る」指摘 + SmartRC パリティ再点検への対処:

1. LINE_BY_SIRE 第 2 次拡充 **121 件** (母父世代 1990-2000 年代 + 現役) — 実追加数は
   prediction-logic の実測。コミットメッセージの「約 95 件」は過少申告だった。
2. **turnto (ターントゥ系) バケツ新設** — Halo 非サンデー枝 (タイキシャトル等) の受け皿。
   FOUNDERS のヘイルトゥリーズン/ターントゥを roberto 便宜寄せから是正 + ヘイロー追加。
3. /trends に **母父系統 (dam_sire_line) 軸** — 前回 profitability 指摘の
   「母父系統は表示のみで集計軸なし」の解消 (SmartRC パリティ残ギャップの充足)。

## 採点結果 (7 名並列)

| 専門家 | 判定 | スコア | 主要所見 |
|---|---|---|---|
| prediction-logic-analyst | PASS | 4.7 | **121/121 全件正確 (2 回連続誤り 0)**。turnto 停止順序を動的検証で成立確認 |
| mobile-html-reviewer | PASS | 4.4 | turnto #7986cb は 6 地色中 5 で 3:1 超。前回 M1/M2/S 全消化を確認 |
| profitability-judge | PASS | 4.2 | 誤読防御 5 点 (min_n/Wilson/bootstrap/緑=CI下限>100/n_values) の新軸への自動適用を構造確認 |
| code-quality-reviewer | PASS | 4.2 | 3 辞書 parity を mutation 注入 3 種で実証 (全て fail-fast) |
| validation-process-auditor | PASS* | 4.1 | 条件 = prediction-logic 非 FAIL → 4.7 PASS で**充足済み** |
| gui-ux-auditor | HOLD | 4.1 | 解除条件 = race 凡例の矛盾 1 行 → **対処済 (下記 1)** |
| data-pipeline-engineer | HOLD | - | 解除条件 R1 = init_db migration 順序の実バグ → **対処済 (下記 2)** |

## HOLD 2 件の解除 (本コミットで対処)

1. **[gui-ux/profitability 必須] race.html.j2 凡例の矛盾** — 「傾向集計の系統軸は父系のみ
   対応」が母父系統軸新設と矛盾 → 「父系統・母父系統の両軸に対応」へ更新。あわせて
   「その他=11大系統外（パーソロン系等）または系統判別不能」を追記 (gui-ux 推奨 2)。
2. **[data-pipeline R1] init_db の migration 順序バグ (実バグ)** — schema.sql の
   idx_horse_masters_dam_sire が dam_sire_breeding_num を参照するため、「テーブルは
   あるが列が無い」旧 DB では executescript が index 作成で落ち、後置の _ensure_column
   は**到達不能な dead code** だった (前回 scorecard の「対処済」記載は虚偽状態)。
   → 列補修を executescript の**前**に移動 (`_ensure_column_if_exists`、テーブル無し時
   skip)。regression 3 本 (`tests/test_db_migration.py`: 旧 DB 補修成功 / 新規 DB /
   冪等) で固定。

## 推奨指摘 → 追補反映

| # | 指摘 (指摘者) | 対処 |
|---|---|---|
| 3 | 旧 DB では waku 集計でも縮退 warning が毎回発火・文言もミスリード (data-pipeline R2, code-quality) | `_rows_with_key` に need_dam_bn を導入 — dam_sire_line 以外は最初から NULL を選び例外経路を通らない。warning は実縮退時のみ + 例外文字列付き。接続毎判定は維持 (writer 修復後に自動復帰) |
| 4 | classify_sire のリクエスト内メモ化 (data-pipeline R3) | aggregate_course / today_trends にユニーク (名前, 繁殖番号) 単位のメモ化を追加 |
| 5 | 縮退が UI 非開示 (profitability 3) | result に dam_bn_degraded を追加し、trends に「簡易分類」チップ + 「その他が多めに出ます」を表示 + テスト |
| 6 | 新スキーマ側 (非縮退遡上) テスト欠如 (validation 2) | `test_aggregate_dam_sire_line_new_schema_traversal` 追加 |
| 7 | _normalize 表記ゆれ非対応の明文化 (validation 3) | docstring に明記 + audit_sire_lines が検出器である旨 |
| 8 | /today の軸 3 つ絞りが暗黙 (validation 4, mobile S3) | today_trends docstring に意図 (セル枯れ防止) を明記 |
| 9 | line-dot の色単独識別禁止の不変条件 (mobile S2) | base.html.j2 の .line-dot に不変条件コメント (turnto/storm/roberto は輝度比 ~1.03:1) |
| 10 | logger 配置 / docstring ファクター列挙 (code-quality, profitability 2) | import 整理 + 「母父系統」追記 |
| 11 | 「10 大系統」コメント stale (gui-ux 3) | 「11 大系統」へ是正 |
| 12 | 縮退 helper 同型 3 箇所の一元化 (code-quality 提案 1) | **次回 webapp 改修時の課題として繰延** (各所テスト保護済・実害なしのため) |

テスト: **247 passed / 3 skipped** (追補後フル実行)。

## SmartRC パリティ再点検の結論 (2026-07-05、サイト再取得は proxy 403 のため前回解析記録と照合)

- ✅ 同等以上: 出馬表 (系統 2 段=父/母父・色分け・印)・傾向集計 (今回母父系統軸を追加、
  CI/min_n/多重比較開示付きで本家を上回る)・当日速報・補助指標行 (近3走/上T/脚質/斤量/
  馬体重/間隔/距離変更/父×馬場)
- ⏳ 実機 gate 待ち (実装済): テンP 相当 (コーナー順位×テン 3F の先行力指標。probe 緑化
  → backfill 後に自動有効化)
- ❌ 対応しない (方針): IPAT 連携 (規約)・NAR 地方 (別契約)・合成オッズ/フル馬柱 (要望次第)

## ユーザ実機の残作業 (次回セッション冒頭タスク、validation 監査で「必達」指定)

1. **`python -m scripts.audit_sire_lines` を本コミット以降の HEAD で実行** (BLOD 未取込なら
   先に取込)。旧 FOUNDERS では「ロベルト」表記ゆれが隠蔽されていたため、turnto 化後の
   実行のみが有効な証拠。dict=roberto vs traversal=turnto の不一致が出たら breeding_horses
   の表記を確認。unknown 率の定量も同時に取得。
2. 従来からの hard gate: probe_corner_offsets --expect/--ra 緑化 → corner backfill →
   実 DB bias_scan → 先行力 ablation。
