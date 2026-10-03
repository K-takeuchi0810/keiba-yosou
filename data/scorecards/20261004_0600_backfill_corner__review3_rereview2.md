# 通過順位の backfill の専用処理と Scratch A / B — 3 名レビュー + 限定再レビュー (2026-10-04)

## 3 名レビュー (96f75e7)

| 担当 | 判定 | 点 |
|---|---|---|
| data-pipeline-engineer | PASS | 4.4 |
| validation-process-auditor | PASS (本番 --apply 前に must-fix 2) | 4.3 |
| code-quality-reviewer | PASS | 4.1 |

- validation must-fix: (1) 対象外の行・ほかのテーブルの不変を本番の手順で機械的に示す → backfill に対象外の行のチェックサムと
  接続の総変更件数の検査を入れた (本番のレポートの outside_before / outside_after)。(2) 変異の記録をリポジトリに → mutation/ に移した
- validation の訂正: Scratch A の v2 を「初版より厳しい」と書いたのは不正確 (混合の変更で、反転させたのは頭数の定義を広げた側)。
  根拠は事前登録の返還の規則と starter_count との一致 → RESULT_SCRATCH_A.md を訂正
- data-pipeline: 前の状態の assert、計画の読み取りを書き込みトランザクションの中へ、OperationalError の捕捉、ROLLBACK の例外、
  wal_checkpoint、raw 0 件のエラー、開催日の判定の限界、本番の手順 5 段、ai_builder_impact は requires_followup (ai-builder の
  行列キャッシュの鍵に DB の中身が無い) → すべて反映
- code-quality: テストの穴 3 件 (閾値の大きさ・全月の存在・1 角の食い違い)、失敗時のレポート、SET / WHERE の生成、定数化 → 反映

## 限定再レビュー (a2dd389、v2)

| 担当 | 判定 | 点 | 前回 |
|---|---|---|---|
| data-pipeline-engineer | PASS | 4.5 | 4.4 |
| code-quality-reviewer | PASS | 4.3 | 4.1 |

- data-pipeline: 本番 (20 GB、WAL、horse_races 754,416 行) での書き込みトランザクションの保持は 1〜3 分、WAL のピークは
  200〜250 MB 以下の見込み。読み手はブロックされない。書き手の機械検出を手順に回した判断は是 (正しさは BEGIN IMMEDIATE 等で機械化済み)。
  clone で取り消し SQL → 再適用が同じ digest に収束することを確認。TRUNCATE の checkpoint の戻り値は成功時 (0,0,0) なので
  合否は busy 0 と WAL 0 B で見る。shm の mtime が WAL より鋭い (10/04 05:44 に動いていた)
- code-quality: 自作の変異で v2 のガードのテストの穴 5 件 (前の状態の向き・1 角の行・適用後の読み直し・sqlite3.Error・result)
- → v3 (275650f / 040ce12) で反映: テスト 6 件と変異 K22〜K26、dry-run は mode=ro、-shm、COMMIT 直後の状態、BaseException、
  main の想定外の例外、手順の補強 (shm・db_rows・checkpoint の基準・取り消しの条件・常駐プロセスの再起動)
- 変異 26/26 KILLED (mutation/run5_result.txt)。v3 の差分 (テストと堅牢化) は再レビューにかけていない
