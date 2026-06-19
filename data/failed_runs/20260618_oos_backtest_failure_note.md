# 失敗 run: OOS backtest (2026-06-17 起動)

| 項目 | 値 |
|---|---|
| run 種別 | OOS backtest (Plan Step 6-7) |
| 起動コマンド | `PRED_W_popularity_first=0 PRED_W_popularity_second=0 PRED_W_popularity_third=0 .venv64/Scripts/python.exe -m scripts.backtest --from 20260101 --to 20260614 --save --save-records --rule-version p25-pop-0-0-0-oos-2026` (続けて pop_7_4_2 を sequential 起動予定だった) |
| 起動時刻 | 2026-06-17T23:25:50 |
| 停止時刻 (推定) | 2026-06-18T00:00:10 (log 最終 mtime) |
| 進捗 | 1400/1620 (≈86%) で停止 — pop_0_0_0 が完了直前 |
| JSON 出力 | **なし** (atomic 保存前に死亡) |
| records JSON | **なし** |
| 子プロセス | 全消滅 (2026-06-20 確認時点で Python プロセスゼロ) |
| 検出時刻 | 2026-06-20T07:53 (ユーザ指摘で発覚、55 時間経過) |

## 推定原因

- 親 Claude セッションが long-idle で suspended
- bg shell の親プロセスが切断され、その子 Python プロセスも OS により kill
- Claude bg タスクの完了通知はランタイムが活きている間しか飛ばないため、私は死亡を検知できなかった

## 判定

| 観点 | 判定 |
|---|---|
| 検証証跡としての使用可否 | **使用不可** (rubric v3 で NOT_EVALUABLE) |
| 採用判断への投入可否 | **不可** |
| 数値の引用可否 | **不可** (途中ログ [1400/1620] も性能評価には使わない) |
| デバッグ目的の参照可否 | 可 (どの段階で何があったかの記録としてのみ) |

## 再発防止策

1. **Claude bg では長時間タスクを走らせない**
   - セッション寿命依存のため信頼できない
2. **OS 管理プロセスで起動する**
   - Windows Task Scheduler に backtest 用タスクを別途作る
   - または `Start-Process` で detach した PowerShell から起動
   - `nohup`/`disown` 相当の Windows 流儀
3. **出力は atomic に保存**
   - 既に `scripts/backtest.py` は最終一括 `json.dump` で書き出すので部分ファイルは残らない設計
   - 進捗ログは保存可、結果 JSON 未保存なら採用判断には使わない (本失敗 run の通り)
4. **再実行前に fresh odds 取得 (Plan Step 4) の安定稼働を確認**
   - `keiba-fresh-odds` Task Scheduler が 2026-06-20 09:00 に初稼働予定
   - coverage JSONL が本番データで積み上がってから OOS backtest 再実行

## 関連ファイル

- 進捗ログ: `data/failed_runs/20260618_oos_backtest_killed_at_1400_of_1620.log`
- 起動側 commit: `4268c5d`
- 関連 scorecard: なし (JSON 未保存のため expert-review を回していない)
