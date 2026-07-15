# PR #5 最終 expert-review scorecard — 血統辞書 4 コミット (sireline)

- **日時**: 2026-07-16 03:00 JST
- **PR**: https://github.com/K-takeuchi0810/keiba-yosou/pull/5
- **対象**: `claude/feature-bias-validation-yl5key` @ f454003 (現時点; 本 scorecard 追加後は次コミット)
- **base**: `origin/main` @ 1094160 (Merge PR #3)
- **コミット (4 本)**:
  - 91f16c0 audit: --since-year フィルタ追加
  - 37c49b2 audit: --since-year の 4 桁バリデーション追加 (data-pipeline 監査 D3)
  - c24008d 辞書拡充: Sunday Silence 英名バグ修正 + 現代主要母父15種 (--since-year 2023 洗い出し反映)
  - f454003 系統国是正: Medicean / Lycius → 欧州型 (prediction-logic 監査 (a) 反映)
- **改修タイプ**: type-B (webapp 表示専用、predictor 非流入)
- **代替採点**: Fable 5 利用不可のため 7 名すべて Opus (`.claude/agents/_rubric.md` v4 準拠)

## 総括

**7 名全員 PASS、平均 4.69 / 5.0**。予測経路 (rules.py / features.py / ml_model.py) への sire_lines 流入ゼロを全レビュアーが grep で独立確認。P25 固有ゲートは type-B のため N/A。

| # | Agent | 判定 | スコア | 主要指摘 |
|---|---|---|---|---|
| 1 | prediction-logic-analyst | PASS | 5.0 | 血統事実 18 件全て正確、predictor 完全非流入 (grep 全 0)、Zafonic 対称性 GOOD |
| 2 | code-quality-reviewer | PASS | 4.4 | **SS-176 型再発防止 (英名 alias class-wide)** の点対応→構造対応化を推奨 |
| 3 | data-pipeline-engineer | PASS | 4.2 | **D1: `--since-year` コメント文言と実挙動のズレ** (実測で "全期間扱いに倒れる" は誤り、silent 0-hit/絞りすぎ/中途カットが正) |
| 4 | validation-process-auditor | PASS | 4.7 | 予測非流入完全、血統は unchanging property でリーク構造的に不能。持ち越し宿題 4 件は nit |
| 5 | profitability-judge | PASS | 5.0 | 収益経路全 9 モジュールで系統辞書非依存を静的+実行時二重実証。マージ推奨明示 |
| 6 | gui-ux-auditor | PASS | 4.5 | GUI/HTML 変更なし、audit CLI UX は Nielsen 1/2/5/9 で診断ツール標準以上 |
| 7 | mobile-html-reviewer | PASS | 5.0 | web/templates 完全無変更、webapp 側は情報密度改善方向・誤読リスク減 |

## 監査指摘への対応

### (対応済) code-quality: SS-176 型再発防止 (点対応 → 構造対応)

**指摘の実測**: Sunday Silence が英名エントリ欠落で 176 産駒 unknown 化していたのと同型のリスクが、日本主要 sire (Deep Impact / Stay Gold / King Kamehameha / Manhattan Cafe / Agnes Tachyon 等 32 種) に構造的に残存。海外重賞馬の UM 3 代血統に英名格納された際に silent unknown 化する可能性あり。

**対応**: 主要日本 founder クラス sire 32 種に英名 alias を LINE_BY_SIRE へ一括収載 (predictor/sire_lines.py 末尾ブロック)。国別は全て line 既定に合致するため COUNTRY_OVERRIDE 追加不要。汎用ガード `test_founder_class_bilingual_aliases_2026_07_16` を tests/test_sire_lines.py に追加し、22 主要ペアの kana/英名双方が unknown でないこと + 同一 line に解決することを構造的に守る。SS-176 型の再発が今後 fail-fast で検出される。

### (対応済) data-pipeline: D1 `--since-year` コメント文言修正

**指摘の実測**: コメント「3 桁以下だと '23' >= '2023' が字句上 True になり黙って全期間扱いに倒れる」は SQL の比較方向 `race_year >= ?` を逆に読んでいた誤記。実挙動は:
- `--since-year 23` → 0 件 (silent)
- `--since-year 202` → 2024+ のみ (silent 中途カット)
- `--since-year 2` → 20xx 系すべて (silent 絞りすぎ)

いずれも silent という結論 (バリデーションの必要性) は正しいが、失敗モード記述が factually wrong だった。コメントを実測ベースの記述に是正 (scripts/audit_sire_lines.py L81-86)。4 桁バリデーション自体は不変。

### (対応済) prediction-logic: Zafonic 対称・Deputy Minister 対称の一貫性

前コミット `f454003` の Medicean/Lycius eur override 修正でクリア (再確認)。

### (未対応、blocking なし) 持ち越し宿題

- validation-auditor: 英名主経路の明示コメント、Medaglia d'Oro アポストロフィ variant の個別 regression、race_year TEXT 前提の in-code コメント、絞り込み後の集計対象数の 1 行 stderr — いずれも nit
- data-pipeline D2 (index range SEARCH 化、頻度が上がるまで対処不要), D3 (`--since-year` unit test、既存の合成 DB スモークで代替), D4 (n_recent=0 の早期案内、副作用なし)
- gui-ux-auditor: help epilog 例、下限 1900 warning、意図が主用途文言に明示

## 検証

- **全 293 passed / 3 skipped** (pytest -q、`test_founder_class_bilingual_aliases_2026_07_16` 追加分 +1)
- predictor 非流入の grep 実測: `predictor/rules.py` / `features.py` / `ml_model.py` / `portfolio.py` / `risk.py` / `filter.py` / `candidates.py` / `tickets.py` / `calibration.py` / `stats.py` / `backtest.py` / `monitor.py` — 全モジュールで `sire_lines|classify_sire|LINE_BY_SIRE` 一致ゼロ (profitability-judge が別実測)
- 実行時検証 (prediction-logic):
  ```
  Sunday Silence     → sunday / jpn         (バグ修復)
  Frankel            → northern / eur
  Medaglia d'Oro     → northern / usa       (COUNTRY_OVERRIDE)
  Medicean / Lycius  → mrprospector / eur   (Zafonic 対称)
  Mark of Esteem     → neverbend / eur
  ```
- csv.writer + utf-8-sig BOM 付きで Excel 直開き対応 (--dump-unknown)
- 4 桁バリデーション fail-fast は rc=2 で argparse 慣習に整合

## 判定: **マージ可能**

7 名全員 PASS、平均 4.69。指摘のうち対応価値の高い 2 件 (SS-176 型再発防止・data-pipeline D1 コメント誤記) は本 scorecard 追加コミットで解消。type-B の非侵食基準を完全クリア。予測ロジック・買い候補フィルタ・EV/Kelly・backtest 集計いずれにも一切流入せず。

## 関連ファイル

- `/home/user/keiba-yosou/predictor/sire_lines.py` (L112 SS 英名, L657-702 第 3 バッチ, L682-711 主要日本 sire 英名 alias, L849-875 COUNTRY_OVERRIDE)
- `/home/user/keiba-yosou/scripts/audit_sire_lines.py` (L76-91 --since-year + バリデーション + 是正済コメント)
- `/home/user/keiba-yosou/tests/test_sire_lines.py` (L664-750 3 regression: sunday_silence_english_alias / batch_unknown_csv_recent / founder_class_bilingual_aliases)
