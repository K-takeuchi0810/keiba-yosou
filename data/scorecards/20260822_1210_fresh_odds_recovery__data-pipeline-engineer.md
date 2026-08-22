# データパイプライン技術者 — 20260822_1210 fresh_odds_recovery

**判定**: HOLD (2 事由。1 件は是正済み、1 件はユーザ実行待ち)
**総合**: 3.6 / 5 (前回 4.0、-0.4 ⚠ 後退)

| 項目 | 今回 | 前回 |
|---|---|---|
| JV-Link エラー回復 | 4 | 4 |
| ingest 冪等性 / クラッシュ一貫性 | 4 | 4 |
| データ鮮度管理 (SLO) | 4 | 4 |
| スキーマ進化 / 復旧 | 2 | 4 |
| fresh odds 取得運用 | 4 | 4 |

**HOLD 事由 1 (是正済み)**: commit が自己完結していなかった。committed `db.py` が未コミットの
`jvlink_client.parser` の JockeyChange / CourseChange を import しており、clean checkout では
`import db` が ImportError → ingest / fetch / backtest / auto_predict の全経路が起動不能。
「深夜に壊れて git checkout . で復旧を試みると全タスクが死ぬ」状態。
→ 履歴を作り直し db.py を自分の変更のみに分離。別 worktree で `import db` 成功を実測。

**HOLD 事由 2 (未実行)**: `repair_odds_stamps --apply` 未実行。7,444 行 / 544 レースの汚染が残存
(件数は判定者が dry-run で独立再導出し一致)。

**独立検証された事実**: 6 日間停止の実在を coverage JSONL の日次件数で確認 (62→45→1×5 日→10)。
外部 ai-builder の毎分 ingest も本リポの `ingest_all` を import しているため post-start ガードが
効くことを確認。TC 速報で races.start_time が更新されるため発走時刻変更にも追従。

**改善提案**: (1) JC/CC 側の即コミット → 分離により解消 (JC/CC は別セッションの管轄に戻した)。
(2) repair --apply と適用後の適格数再計測 (未実行)。(3) watchdog の lock 所有確認 → 是正済み
(unlink 前に PID 照合)。start_watchdog の単体テストは未追加 (残課題)。
