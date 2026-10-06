# 研究の窓の関所 + 新しい窓の規則 レビュー (3 名) — 2026-10-06

- 対象: `docs/LOCKBOX_GOVERNANCE.md` (7e8d7a7)、`scripts/research_window.py` + `config.RESERVED_FROM` / `FRESH_FROM` + group_a / c_prime の配線 (148a9af)
- 凍結 SHA `dead4e2` で 3 名 → 反映 (`755d81e` / `f1a3484`) → CONDITIONAL の 2 名が再判定 → 残りの指摘 (`b70a237`) → FRESH_FROM 確定 (`47bf039`)

| 専門家 | 初回 | 再判定 | 主な must-fix |
|---|---|---|---|
| validation-process-auditor | 4.0 CONDITIONAL | **4.5 PASS** | reproduce_consumed の reproduces が自由記述で、A″ の 2025 の閲覧が通る → 一覧の完全一致 + 監査ログ |
| code-quality-reviewer | 3.6 CONDITIONAL | **4.0 PASS** | 期間の隙間が「許可」に化ける / 錠で固定されたファイルの編集が未記録 |
| data-pipeline-engineer | **4.2 PASS** | — | (運用) FRESH_FROM は年間の開催スケジュールで 10/10 の取り込みより前に確定 |

反映後の平均 **4.23**。

## 反映
- 期間の被覆 (development の翌日 = consumed の開始、空集合は止める)、consumed の開始は DATA_SPLIT から
- 再現の一覧は主検定を実行した A / C′ の run_index 1 だけ (停止した D の runner は 2025 を読めない)。development 以外は監査ログに追記 (書けなければ止める)
- 件数は確定 / 未確定を分離、track_type 不明は止める、中止は db.sql_evaluable_race、禁止の断片に races の発走後の列
- FRESH_FROM を schedules で決める determine_fresh_from → 2026-10-10 (確定の記録 `data/backtest/research_window_20261006/fresh_from_determination.json`)
- 規則: N の代わりの年 = 2024、件数の単位と比 r、月末の点検 = 翌月 8 日以降・確定のみ、ai-builder と目にする経路、履歴の読みは最初の事前登録より前に決める、新しい runner の命名
- 静的テスト (研究の読み込みが関所を呼ぶ、例外は凍結 runner 4 本、対象年が定数)。錠で固定されたファイルの編集を A / C′ の結果の文書に blob つきで記録
- conftest: 監査ログを session 単位で tmp へ (module fixture が本物の data/runtime に書いたのを実測して修正)
- 全テスト 1525 passed (worktree の CRLF 由来の既知 1 本を除外)、変異 38/38 KILLED

## 見送り・別件
- 本番の関所 (guard_analysis_window) へのログ: 本番・ai-builder の経路に書き込みを増やすので見送り (規則 §7)
- 監査ログを開封時に凍結物へ写す手順: primary_after_unlock の実装時の要件
- `test_model_artifacts_are_unchanged_during_the_seal` が worktree で落ちる (second_blend.json の改行で sha256 が変わる。既存、改修と無関係)
