# Codex 作業指示: F3-a 朝オッズアンカー 立ち上げ(データ取得基盤・完走型)

## 0. これは何か / なぜ即時か

Phase 1 readiness で **ドリフト計算は事実上 0%**(earliest_lead が全レース ~20分に張り付き=`fetch_fresh_odds`
の window=25 が発走直前帯しか取らないため、wide_drift=0)と確定。F3 のドリフト特徴 x_i(§4.2)には
「朝の基準点 + T-10 直前点」の2点が要る。**朝アンカー収集は F3 のハード前提**で、これが無いと Phase 1 は
着手不可。封印開始 **2026-10-01 は凍結済(D2)**で、ドリフトを封印判定で使うには**それ以前に朝アンカーが
稼働している必要**があり、1日遅れるごとに dev/封印の drift カバレッジが不可逆に減る=**即時立ち上げ**。

正本 §1-6 は `fetch_fresh_odds.bat --window 600` と書くが、**その bat は引数を引き渡さない**
(`%*` 無し)ので黙って window=25 で走る(`fetch_full --since-last` と同型の "静かな no-op")。
本タスクは専用 bat で回避し、**no-op を検出する仕組みごと**作る。

これは事前登録の凍結対象(モデル/特徴定義/判定基準)には触れない**データ取得基盤の整備**であり、
正本 §1-6 の計画の執行。

## 1. ガードレール(最上位・逸脱禁止)

- 凍結決定(D1 T-10 / D2 封印 / §4)・production 予想挙動・model/calibrator artifact を**変えない**。
- **`scripts/fetch_fresh_odds.bat`(live 10分タスクが使用中)を触らない**。その `%*` 欠落は
  「別チケット」として最終報告に記録するのみ(今回は修正しない)。
- 着手前 `git status --short`。tracked 未コミットは停止報告(untracked のみ続行)。
  `git checkout -b codex/f3-morning-anchor main`。**push しない**。作業後 `git checkout main` へ戻す。
- **触らない**: `C:\Users\kizun\dev\傾向収集\` / `.claude/skills/html-ui-ux-review/` / 他 codex/* branch /
  封印(2026-10-01 以降)。JV-Link は **32bit `.venv32`**。ASCII スクリプトのみ。Discord 送信禁止。
- **`docs/F3_MARKET_RESIDUAL_DESIGN.md` を編集しない**(§1-6 の修正・データ体制追記・dev窓制限の事前登録は
  Claude が go-live 日確定後に rev1.2 で実施)。

## 2. 作業

### 2-1. 専用 `scripts/fetch_morning_odds.bat`(新規)
- `.venv32\Scripts\python.exe -u -m scripts.fetch_fresh_odds --window 600`(min_lead は全域取得のため 0 相当に)
  を**引数固定**で呼ぶ。専用ログ `data/logs/fetch_morning_odds.log` へ。
- **条件1(no-op 根絶)**: モジュール起動時に**実効 window をログ出力**すること(既存 line ~156 が
  `window=...` を print しているはず。無ければ1行追加)。スモークで「ログ上 **window=600**」を合格条件にする。
- **競合対策**: SQLite `busy_timeout`(数秒)を morning プロセスで設定 + mkdir-lock(傾向収集
  `sync_jvlink_then_collect.bat` の lock パターン踏襲)を取得し、live 10分タスクと DB/JV-Link を直列化。

### 2-2. `scripts/register_morning_odds_task.ps1`(新規)+ 登録
- `keiba-morning-odds` を **daily 09:30**(または §2-4a の競合確認で衝突すれば回避時刻/lock 前提)で登録。
  `scheduler-repair` の `Register-ScheduledTask` パターン踏襲、ASCII、`Get-ScheduledTask | Get-ScheduledTaskInfo`
  で NextRun を実機確認。ExecutionTimeLimit は広窓取得に足る値(例 1h)。
- **★merge 結合の明記**: 登録タスクの Action が指す bat は **main の内容で実行**される。本ブランチが
  main へマージされるまで bat は main に無く、09:30 のタスクは失敗する。→ **スモーク(§2-3)は
  タスク経由でなく bat を直接呼んで**行い、タスクの機能発火は「マージ後」である旨を報告に明記。

### 2-3. スモーク検証(条件2・数値合格)
bat を**直接**1回実行し(タスク経由でなく)、以下を**すべて**満たすか:
- ログ上 **実効 window=600**(条件1)
- その日の**全レース**について、発走 **60分以上前**の `fetched_at` 点が **1点以上**入ったか(レース単位で報告)
- **翌日 readiness 再計算**(`scripts/f3_phase1_readiness.py` を当日含む窓で再実行)で **wide_drift > 0** になるか
- **欠落パターンの報告**: 朝時点で単勝オッズが配信されない時間帯・レース種別があれば、その分布を報告
  (JV-Link が朝に win odds を配信しているかの実証。配信されないパターンがあればそれ自体が設計制約)

### 2-4. 運用確認(条件4)
- **(a) 競合**: live 10分タスクと**同時刻に1回**走らせ、JV-Link COM rc・DB ロックの挙動を実機観察。
  競合(rc 異常 / "database is locked" / どちらか無音失敗)があれば、lock/busy_timeout で直列化されるか、
  または回避時刻(例: 09:00 の 10分タスク開始前)に寄せるかを判断し、採った対処を報告。
- **(b) 取得量**: window=600 で JVOpen 読取件数・`odds_snapshots` 行増加・ディスク増分を1回分実測し、
  日次増加率の見積もりを報告(テーブル肥大の予兆監視のため)。

## 3. 生成物

- `scripts/fetch_morning_odds.bat`(新規・ASCII)、`scripts/register_morning_odds_task.ps1`(新規・ASCII)
- 必要なら `scripts/fetch_fresh_odds.py` に実効 window ログ1行追加(条件1、既存 print があれば不要)
- `docs/F3_morning_anchor_result.md`: スモーク結果(実効window / 全レース≥60分カバレッジ / wide_drift>0 確認 /
  欠落パターン / 競合挙動と対処 / 取得量見積もり / **go-live 日** / merge 結合注意 / fetch_fresh_odds.bat %* の別チケット記録)
- (readiness 再計算の出力は `data/f3_phase1_readiness/` に別名で)

## 4. やらないこと(再掲)
- `fetch_fresh_odds.bat`(live)を変更しない。凍結決定・production・封印に触れない。
- `F3_MARKET_RESIDUAL_DESIGN.md` を編集しない(Claude が rev1.2 で反映)。push しない。

## 5. 最終報告(12 行以内)
1. fetch_morning_odds.bat のスモーク: 実効 window=600 か / 全レース≥60分前点の充足率 / wide_drift 新値
2. 朝オッズ欠落パターン(時間帯・レース種別)の有無
3. keiba-morning-odds 登録: NextRun、および「マージ後に機能発火」注意
4. 競合確認(a)の観察結果と採った対処 / 取得量(b)の日次増加率見積もり
5. fetch_fresh_odds.bat %* 欠落の別チケット記録
6. 凍結設計・production・封印 無変更 / 傾向収集・skill・他branch 無変更 / checkout=main / push なし

---

## (Claude Code 側メモ — Codex には渡さない)

- 受領後 Claude 検証: (a) bat が module を window=600 で呼びログに実効値が出るか、(b) スモークの
  「全レース≥60分前点 + wide_drift>0」の生成物確認、(c) 競合対処が実際に直列化しているか、
  (d) live fetch_fresh_odds.bat が無変更か。
- その後 Claude が **rev1.2 で `F3_MARKET_RESIDUAL_DESIGN.md` を編集**:
  1. §1-6 の「`fetch_fresh_odds.bat --window 600`」→「`fetch_morning_odds.bat`(専用)」へ修正(文書↔実体の乖離解消)
  2. データ体制の変化点1行: 「YYYY-MM-DD 以降 朝アンカー(window=600, 09:30 daily)稼働。drift 系特徴の
     available_at はこの日以降のみ充足」(go-live 実日を Codex 報告から採る)
  3. **事前登録追加**: drift 特徴を使うモデルの **dev 窓は anchor 稼働日以降に限定**。稼働前期間との混合は禁止
     (混合すると drift が「計算不能→0埋め」で静かに歪むため)。tag `f3-design-rev1.2`。
- scripts(bat)変更 + タスク登録につき、完了後 **expert-review はデータ基盤中心**(+ 必要なら code-quality)。
  Codex 自作 scorecard は D1 無効。
- 別チケット: fetch_fresh_odds.bat の `%*` 欠落(live 使用中のため別途、no-op 検出の一般化)。
