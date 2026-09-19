# Codex 作業指示: 朝アンカー 開催日受入(deferred smoke・完走型・07-25 以降に実行)

## 0. これは何か

朝アンカー取得基盤(branch `codex/f3-morning-anchor`、task `keiba-morning-odds` 08:45 daily)は完成したが、
07-20 が 0 レースだったため効力(60分前充足・wide_drift>0・欠落パターン・実競合)が **HOLD**。
本指示は**マージ後の最初の JRA 開催日(今週末 07-25 土 / 07-26 日)以降**にその受入を閉じる。

## 1. 実行前提(満たさなければ停止して報告)

- **branch `codex/f3-morning-anchor` が main へマージ済**(Action 先 `fetch_morning_odds.bat` が main に存在)。
- **JRA 開催日を1日以上経過**し、その日 08:45 に `keiba-morning-odds` が発火済み。
  未マージ or 未開催なら「まだ実行不可」と報告して終了(何も測らない)。

## 2. 全体ルール

- 測定のみ。DB read-only。production/凍結設計(D1/D2/§4)不変。封印非接触(`to_date < 20261001`)。
- `git checkout -b codex/f3-morning-raceday main`。push しない。作業後 main へ戻す。
- 触らない: `傾向収集` / `.claude/skills/html-ui-ux-review/` / 他 codex/* branch / 封印。ASCII。Discord 禁止。
- `F3_MARKET_RESIDUAL_DESIGN.md` を編集しない(rev1.2 は Claude が go-live 日確定後に実施)。

## 3. 測定(対象=マージ後最初の開催日)

### 3-1. 朝タスクが実際に走ったか
- `Get-ScheduledTask keiba-morning-odds | Get-ScheduledTaskInfo` の LastRunTime = 当該開催日 08:45、
  LastTaskResult = 0。`data/logs/fetch_morning_odds.log` に **`CHECK: effective window=600 confirmed`** が
  当該 run で出ているか(no-op でないことの実証)。`odds_snapshots` に朝の行が増えたか。

### 3-2. readiness 再計算(当該開催日を含む窓)
`scripts/f3_phase1_readiness.py` を当該開催日を含む窓(`to_date < 20261001` は維持)で再実行し:
- **60分前充足**: 当該開催日の**全レース**で発走 60 分以上前の `fetched_at` 点が 1 点以上。**レース単位の充足率**を報告。
- **wide_drift > 0**(本命の成否)。当該開催日の drift_computable 率(旧 baseline 8.4% との対比)。
- earliest_lead_min 分布が朝側(≥60分)へ実際に伸びたか。

### 3-3. 欠落パターン(条件2 の JV-Link 朝配信の実証)
朝時点で単勝オッズが **60分前に配信されなかった**レース/時間帯/レース種別があれば、その分布を報告。
配信されないパターンがあれば**それ自体が設計制約**(該当レースは drift 特徴の母集団から除外する材料)。
**★1〜2開催日では確定しない**: wide_drift>0・朝配信の実証(§3-1〜3-4)は今回で判定してよいが、
欠落パターンと drift_computable 率の**安定値は複数開催の蓄積が要る**。rev1.2 に凍結するのは
「go-live 日」と「drift dev 窓を anchor 稼働日以降に限定」までとし、**欠落パターンに基づく母集団除外規則は
複数開催確認後に別途確定**(本開催日の結果は暫定値として報告するのみ、除外規則を今回凍結しない)。

### 3-4. 実競合(条件4a の未完分)
当該開催日、08:45 の morning run(window=600、09:00 を跨ぐ可能性)と 09:00 開始の 10 分タスクの
**実 COM/DB 競合**を観察: `fetch_morning_odds.log` / `fetch_fresh_odds.log` に共有ロックのリトライ痕
(`shared lock busy; retry`)や `database is locked` が出たか、両者 rc=0 で完了したか。**共有ロックが実際に
直列化したか**を結論。

### 3-5. 取得量(条件4b の実測分)
当該開催日の `odds_snapshots` 実行増分行数 + ディスク増分を実測し、参考見積り(~479 行 / 33.9KiB / 36 レース日)
との乖離を報告。

## 4. 生成物 / 5. 報告(10 行以内)

- `docs/F3_morning_anchor_raceday_result.md`: §3-1〜3-5 の数値 + **go-live 日(朝アンカーが実捕捉した最初の開催日)**。
- 報告: (1) 朝タスク発火 + effective window=600 confirmed、(2) 60分前充足率 / wide_drift 新値、
  (3) 欠落パターン、(4) 実競合の直列化可否、(5) 取得量実測、(6) 封印非接触 / DB read-only / production 不変 /
  傾向収集・skill・他branch 不変 / checkout=main / push なし。

---

## (Claude Code 側メモ — Codex には渡さない)

- 実行前に **branch がマージ済 + 開催日経過** の2前提を要確認(未達なら Codex は停止報告する設計)。
- 受領後 Claude 検証: readiness 再計算が `usable_snapshots` 経由 / 封印ガード / wide_drift の定義一致。
- go-live 日が確定 → Claude が **rev1.2** で `F3_MARKET_RESIDUAL_DESIGN.md` 編集:
  §1-6 の「bat --window 600」→「fetch_morning_odds.bat(専用)」/ データ体制1行(go-live 実日)/
  drift モデルの dev 窓を anchor 稼働日以降に限定する事前登録。tag `f3-design-rev1.2`。
- その後 **データ基盤中心の expert-review**(効力が実データで確認された完成パッケージに対して。
  Codex 自作 scorecard は D1 無効)。
- 欠落パターンが広ければ、朝アンカーの取得時刻/窓の再調整 or 対象レース種別の限定を次サイクルで検討。
