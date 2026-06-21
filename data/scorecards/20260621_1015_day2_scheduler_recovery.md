# Day2 scheduler recovery — 2026-06-21 10:15

**目的**: 2026-06-21 Day2 監視の前提である Task Scheduler が今日 (Day2) 発火しなかった事象の原因調査・復旧・証跡固定。**スコープは scheduler 復旧のみ**。予想ロジック / backtest / GUI / HTML / calibrator には触らない。

## 状態 (今日 09:56 時点で検出)

| 項目 | 発見した値 | 期待値 |
|---|---|---|
| `keiba-fresh-odds` LastRunTime | **2026/06/20 16:30:01** (= 昨日 Day1 の最後の fire) | 今日 09:00 以降の値 |
| `keiba-fresh-odds` NextRunTime | **(空)** | 今日中の次回時刻 |
| `keiba-fresh-odds` NumberOfMissedRuns | 1 | 0 |
| `keiba-fresh-odds-healthcheck` LastRunTime | **2026/06/20 16:45:01** | 今日 09:15 以降 |
| `keiba-fresh-odds-healthcheck` NextRunTime | **(空)** | 今日中 |
| `fresh_odds_health_latest.json` decision | **NOT_EVALUABLE** (昨日 16:45:02 の最後の run) | 本日の最新 |
| `keiba-oos-backtest-auto` State | Disabled | Disabled (維持) |

→ Day2 監視の前提 (scheduler 自走) が崩壊。**ユーザ判断**: 「証跡を守るための停止」ではなく「証跡を失う放置」になるため、**scheduler 限定の復旧** を許可。

## 原因 (XML dump で確定)

旧 registration script `register_fresh_odds_*_task.ps1` は `schtasks /create /sc minute /sd 2026/06/20 /st 09:00 /et 16:40` を使っていた。これが Windows Task Scheduler 内で以下のように保存されていた:

```xml
<Triggers>
  <TimeTrigger>
    <StartBoundary>2026-06-20T09:00:00</StartBoundary>
    <EndBoundary>2026-06-20T16:40:00</EndBoundary>
    <Repetition>
      <Interval>PT10M</Interval>
    </Repetition>
  </TimeTrigger>
</Triggers>
```

- `<TimeTrigger>` = **1 回限り** の時間トリガに 10 分繰り返しを足した形
- `StartBoundary` / `EndBoundary` 共に `2026-06-20` 固定 → **その日が終わった時点で trigger 完了**、翌日以降は二度と発火しない
- `/sc minute + /sd + /et` の組合せが期待していた「毎日 09:00-16:40 の間 10 分おき」にはならず、「2026-06-20 の 09:00-16:40 のみ」になる挙動

これは `/et` (end time) を 1 日の終了時刻として解釈した結果、`EndBoundary` が同日固定になる仕様。`schtasks` の癖。

参考: OOS auto (`keiba-oos-backtest-auto`) は `/sc daily` で登録されており `<CalendarTrigger><ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger>` で正しく毎日発火するため、本不具合に巻き込まれていない。

## 復旧アプローチ

`schtasks` の TimeTrigger 系から **PowerShell ScheduledTasks モジュール** に切り替え、`<CalendarTrigger>` + `<ScheduleByDay>` + `<Repetition>` で **毎日繰り返し型** に再登録。

```powershell
$dailyTrigger = New-ScheduledTaskTrigger -Daily -At $StartTime
$tmpOnceTrigger = New-ScheduledTaskTrigger -Once -At $StartTime `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Minutes $DurationMinutes)
$dailyTrigger.Repetition = $tmpOnceTrigger.Repetition
Register-ScheduledTask -TaskName ... -Action $action -Trigger $dailyTrigger -Settings $settings
```

PowerShell 5.1 では `New-ScheduledTaskTrigger -Daily` が `-RepetitionInterval` を直接受けられないため、`-Once` trigger の Repetition プロパティを借用して daily trigger に貼る形が定石。

## 修正したファイル

1. **`scripts/register_fresh_odds_healthcheck_task.ps1`** (既存修正)
   - schtasks → PowerShell cmdlet 形式
   - `/sd + /et` 依存を廃止
   - UTF-8 BOM 維持、parse OK
2. **`scripts/register_fresh_odds_task.ps1`** (新規作成)
   - 本体 `keiba-fresh-odds` の登録スクリプト
   - 前回までは user 手動 `schtasks` だった → 同じバグの再発防止のためスクリプト化
   - UTF-8 BOM、parse OK

## 復旧後の検証 (XML dump 実測)

**`keiba-fresh-odds`** — `<CalendarTrigger>` + `<Repetition Duration="PT7H40M" StopAtDurationEnd="true">` + `<ScheduleByDay DaysInterval="1">` 確認済。
**`keiba-fresh-odds-healthcheck`** — 同形式、Interval=PT15M。

| 項目 | 値 | 評価 |
|---|---|---|
| `keiba-fresh-odds` State | Ready | ✓ |
| `keiba-fresh-odds` NextRunTime | **2026/06/21 10:10:00** | ✓ 今日中に発火予定 |
| `keiba-fresh-odds-healthcheck` State | Ready | ✓ |
| `keiba-fresh-odds-healthcheck` NextRunTime | **2026/06/21 10:15:00** | ✓ 今日中 |
| `keiba-oos-backtest-auto` State | **Disabled** | ✓ 維持 |

## healthcheck 手動実行 (10:08:58)

scheduler 復旧後、すぐに状態を確認するため healthcheck を手動 1 回実行:

| 項目 | 値 |
|---|---|
| decision | **HOLD** |
| reason | "scheduler not yet fired today" (今日 10:10 の初発火待ち、正常状態) |
| scheduler.registered | **true** (昨日の誤判定 "not registered" は解消) |
| scheduler.last_task_result | 267011 (= 未実行 placeholder、登録直後で正常) |
| coverage.exists | true |
| coverage.runs_today | 0 (今日分はまだ無い) |
| coverage.contamination_detected | **false** |
| db.reachable | true |
| db.fresh_horse_rows_since_check_time | 0 |
| OOS auto State | **Disabled** |

→ **scheduler 復旧後の判定は HOLD (正しい遷移状態)**。10:10 以降に scheduler 本体が発火、coverage JSONL に行が積まれ、10:15 以降 healthcheck が自動更新するチェーンが再開する見込み。

## 禁止事項の遵守 (確認)

| 作業 | 状態 |
|---|---|
| OOS backtest 実行 | **しない** ✓ |
| OOS auto Enable | **しない** ✓ (State=Disabled 維持) |
| 予想ロジック変更 | **しない** ✓ (predictor/ 配下 0 行) |
| GUI / HTML 変更 | **しない** ✓ |
| PRED_DISABLE_BLEND 実装 | **しない** ✓ (次セッション最優先) |
| calibrator refit | **しない** ✓ |

修正対象: `scripts/register_fresh_odds_*_task.ps1` の 2 ファイルのみ。**scheduler 登録設定の修正に限定**。

## Day2 evidence の扱い

今日は **「自然稼働 Day2」ではなく「Day2 scheduler recovery」** として扱う。

- Day1 evidence (`20260620_1225_day1_evidence_lock.md`) は **無効化されていない** (= 昨日 1 日完璧に動いた実績は健全)
- Day2 は scheduler 不発で取得自体できなかったため、**本来の Day2 ではない**
- 復旧後の本日 10:10〜16:40 の稼働を観察し、別途「Day2 recovery PASS」として記録する
- Plan Step 4 完了条件「2-4 開催日で安定」の達成判定は **Day2 recovery PASS + 次開催日 (2026-06-27 土) PASS** が揃ってから

## 次セッションへの引き継ぎ

順序は変更なし:

```
[今日 残り] 10:10 以降の scheduler 自走を観察 (read-only)、16:40 終業時点で別 scorecard
[次開催日 2026-06-27 土] 通常の Day2 相当の観察
[次開催日終了後] PRED_DISABLE_BLEND 実装
[その後] C1 / C2 / C3 / C5 paired backtest
...
```

## 教訓 (運用知見)

- `schtasks /sc minute + /sd + /et` は単日 trigger になる。daily 繰り返しには使えない
- 毎日繰り返しが欲しいときは `Register-ScheduledTask` + `New-ScheduledTaskTrigger -Daily` + `Repetition` で明示登録
- trigger 種別 (`<TimeTrigger>` vs `<CalendarTrigger>`) は XML dump で確認できる。次回類似登録時は **登録直後に XML dump で trigger 種別を必ず検証する**
- 「Day1 PASS」だけで安心せず、**Day2 の発火実績を見るまで運用 OK と言わない** ことの正しさが実証された

## 関連 commit (今後)

- 本 scorecard コミット時に `scripts/register_fresh_odds_task.ps1` (新規) と `scripts/register_fresh_odds_healthcheck_task.ps1` (修正) を同梱
- OOS backtest / 予想ロジック / GUI 改修への波及なし
