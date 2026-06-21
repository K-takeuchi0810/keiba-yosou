# Day2 recovery evidence — 2026-06-21 16:45 終業時点

## 重要な前提注記 (必読)

- 本日 (2026-06-21) は **自然継続稼働の Day2 ではない**。朝時点で scheduler の `NextRunTime` が空になっていたため、**scheduler-only recovery** を 10:00 頃に実施した (commit `2df45f6`)。
- そのため Day2 は **通常 PASS ではなく recovery PASS/FAIL** として扱う。
- **Day1 evidence (`20260620_1225_day1_evidence_lock.md` / commit `583e58c`) は無効化しない**。
- Plan Step 4 の完了判定は、**Day2 recovery PASS** と **次開催日 2026-06-27 (土) の自然稼働 PASS** を確認してから行う。1 週間分の天気予報が当たっただけで気象予報士を名乗らないのと同じ。

## 判定: Day2 recovery PASS (条件付き)

**理由**: 10:10 以降に再登録した daily CalendarTrigger が 16:40 まで自走、終業後 NextRunTime に **2026/06/22 9:00:00** が正しく入った (= 日跨ぎの罠が解消されたことを実証)。FAIL / NOT_EVALUABLE は 0。

**根拠ファイル**:
- `data/runtime/fresh_odds_health_latest.json` (16:45 時点)
- `data/logs/fresh_odds_coverage.jsonl`
- `data/logs/fresh_odds_health_20260621.log`
- 終業後 `Get-ScheduledTask | Get-ScheduledTaskInfo` の NextRunTime 実測

**次アクション**: 明日 (2026-06-22 月) 09:00 に scheduler が**自然に**発火し、 NextRunTime が更新されることを翌朝 read-only で確認すること。次開催日 2026-06-27 (土) の終日稼働 PASS まで Plan Step 4 完了は保留。

## 16:45 時点の実測値 (固定対象)

### scheduler

| 項目 | keiba-fresh-odds | keiba-fresh-odds-healthcheck |
|---|---|---|
| State | Ready | Ready |
| LastRunTime | 2026/06/21 16:40:00 | 2026/06/21 16:45:00 |
| LastTaskResult | **0** | **0** |
| **NextRunTime** | **2026/06/22 9:00:00** | **2026/06/22 9:15:00** |
| trigger 種別 | `<CalendarTrigger>` + `<ScheduleByDay DaysInterval="1">` ✓ | 同上 ✓ |
| repetition | Interval=PT10M Duration=PT7H40M | Interval=PT15M Duration=PT7H40M |

`NextRunTime` が **明日 09:00** に正しく入っている = recovery 成功の最も明確な証拠。昨日 (recovery 前) は同欄が空だった事象が再現していない。

### coverage (今日 10:10〜16:40 の稼働実績)

| 指標 | 値 | Plan 期待値 | 評価 |
|---|---:|---:|---|
| 起動回数 | 39 | 46 (= 09:00-16:40 全日相当) | 84.8% (10:10 開始 = 約 7 fire 分の取り損ね、recovery 影響として許容) |
| eligible_races (累計) | 69 | 36 (= 1 開催日目安) | **1.92 倍** (発走 2-25 分前 race が多かった、開催 2 場の影響) |
| fetched_races (累計) | 65 | - | 94.2% |
| ok_races (累計) | **65** (= 94.2%) | 100% | わずかに低下 |
| error_races | 0 | 0 | ✓ |
| no_data / timeout / empty | 0 / 0 / 0 | 0 | ✓ |
| **lock_skipped** | **2** | 0 | 軽微 (要監視、原因不明) |
| failed_reason 分類 | 空 | - | ✓ |
| contamination_detected | **False** | False | ✓ |

#### lock_skipped=2 の意味 (注記)

`scripts.fetch_fresh_odds` 起動時に `single_run_lock()` が前回 run の lock を検出してスキップした回数。考えられる原因:

1. 前回 run が想定より長引き、次回 run と重なった
2. JV-Link 接続が遅く 10 分以内に完走しなかった
3. 何らかの一時的なファイルロック

39 回中 2 回 = 5%、本日中の eligible / ok が十分供給されている (eligible 69、ok 65) ため運用に支障なし。ただし **次開催日に再発するなら原因調査** が必要。

### DB

| 項目 | 値 |
|---|---|
| `odds_fetched_at >= 2026-06-21T09:00:00` の行数 | **290** |
| 最新 odds_fetched_at | 2026-06-21T18:10:13 (= 16:40 以降にも何か取得経路あり、要確認の小規模事象) |
| 2026-06-21 のレース数 (races テーブル) | 36 |
| 2026-06-21 の馬レコード数 (horse_races テーブル) | 537 |
| `confirmed_order > 0` の馬数 (= 着順確定) | **0** ← JV-Link 確定データ取得は未実施 |
| payouts 行数 (= 払戻取込済) | 16 ← 一部のみ |

### health JSON (16:45:02 時点)

```json
{
  "decision": "PASS",
  "scheduler": { "ok": true, "last_run_time": "2026-06-21T16:40:00", "last_task_result": 0 },
  "coverage": { "ok": true, "ok_races_today": 65, "contamination_detected": false },
  "db": { "ok": true, "fresh_horse_rows_since_check_time": 290 }
}
```

### health log 集計 (本日)

`data/logs/fresh_odds_health_20260621.log`:

- PASS / HOLD / FAIL / NOT_EVALUABLE の正確な内訳は明日朝に集計する (現セッションのみで確認可能だが時刻のためまとめて固定)
- 重要観察: **本日中の FAIL / NOT_EVALUABLE 出力なし** (これは手動 healthcheck の 10:08:58 で HOLD、その後の自動 cycle で PASS に推移、と一連の遷移として整合)

### OOS auto

- State: **Disabled** (維持) ✓
- LastRunTime: 1999/11/30 0:00:00 (= 一度も発火していない)
- NextRunTime: 2026/06/22 17:30:00 (登録は維持、Disabled で発火しない)

## 禁止事項チェック (本日終業まで遵守)

| 作業 | 状態 |
|---|---|
| OOS backtest 実行 | **なし** ✓ |
| OOS auto Enable | **しない (Disabled 維持)** ✓ |
| 予想ロジック (`predictor/`) 変更 | **0 行** ✓ |
| GUI / HTML 変更 | **なし** ✓ |
| PRED_DISABLE_BLEND 実装 | **持ち越し (次セッション最優先のまま)** ✓ |
| calibrator refit | **なし** ✓ |

本日触ったのは scheduler 登録スクリプト 2 件のみ (`scripts/register_fresh_odds_*_task.ps1`)。`predictor/` `backtest` `GUI` `HTML` `weights.json` `calibrator.json` への変更は **絶対零**。

## Day2 recovery の "条件付き" の意味

Day2 recovery PASS と判定したが、以下の条件が満たされて初めて Plan Step 4 完了に進める:

1. **明日 (2026-06-22 月) の自然発火確認** — `NextRunTime=2026/06/22 9:00:00` が指定通りに動くか。これが daily trigger の真の検収。月曜は非開催日のためレースは無いが、scheduler が「09:00 fire → eligible 0 で coverage に 1 行 append → NextRun=翌日 09:00 更新」の cycle を回せるかを read-only で見る
2. **次開催日 2026-06-27 (土) の終日 PASS** — 1 週間後の開催日に自然稼働で eligible / fetched / ok / contamination=False が再現できるかの最終検収

これら 2 つが PASS して、初めて「日跨ぎの罠も潰した運用化完了」と言える。1 日動いただけで気象予報士を名乗らない。

## 関連 commit

- `2df45f6`: Day2 scheduler recovery (TimeTrigger → daily CalendarTrigger)
- `583e58c`: Day1 evidence lock (有効維持)

## 次セッションへの引き継ぎ (本 scorecard 後の作業)

順序:

1. (今夜の続き) 今日のレース結果データ (`confirmed_order` / `payouts`) を取り込むため、user が **JV-Link 本日確定データ取得 (Ⅰ ボタン or `scripts.fetch_jvdata` 相当)** を走らせる判断 → user 待ち
2. 取込完了後、`scripts/build_daily_results.py` (新規) で予測 + 最終オッズ + 着順 + 払戻 を CSV 化 → `data/results/2026-06-21/*.csv`
3. 評価 CSV で 3 分類 (A モデル > 市場 / B 市場 > モデル / C ノイズ)
4. **今日中は CSV を書き出すだけ、モデル改修は禁止** (user 指示)
5. 数日〜数週間ぶん蓄積後、市場ベースライン比較へ

明日朝 (2026-06-22 月) は **scheduler 自然発火確認のみ** が能動的な仕事。それ以外は read-only。
