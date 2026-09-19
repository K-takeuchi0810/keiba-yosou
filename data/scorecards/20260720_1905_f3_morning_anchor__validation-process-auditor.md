# 検証プロセス監査人 採点 — F3 朝オッズアンカー

**対象HEAD**: `e5eaf34f0865fd99ce16a8561972815da26b54f1`（基盤 `3ce4810`、ログ値保持修正 `6d512ba`、競合fail-closed修正 `1163c83`、retry timing整理 `e5eaf34`）  
**対象**: `scripts/fetch_morning_odds.bat`、`scripts/register_morning_odds_task.ps1`、`tests/test_f3_morning_anchor.py`、`docs/F3_morning_anchor_result.md`、実ログ、Task Scheduler 状態  
**実測時点**: 2026-07-20 19:03 JST

## 総合: 3.4 / 5 — **HOLD（基盤PASS、数値受入未完）**

- 前回（F3 Phase 1 readiness）: **4.8 / 5**
- 差分: **-1.4**（回帰警告）
- この差は既存readiness計測基盤のコード回帰ではなく、今回の受入標本が0レースで、事前指定された実地ゲート4件が未充足であることによる。
- 朝アンカーを有効化したdev窓・Phase 1へ進む判定は、最初のJRA開催日の非ゼロ受入まで停止する。

## 項目別

| 検証軸 | 点 | 根拠 |
|---|---:|---|
| 実効引数・no-op検出・再現性 | 5/5 | 32bit Python、`--window 600 --min-lead 0`固定、`window=0-600min`厳密検査、専用ログ、rc記録を確認。実ログでも3回マーカー一致・rc=0。`%*`を渡さず上書きを防ぐ。 |
| 60分前PITカバレッジ | 2/5 | 合格条件は「当日全レースに `fetched_at` lead >=60分が1点以上」と明記されているが、DB対象0件のため分母・分子とも未測定。08:45は最初の09:50発走まで65分しかなく、起動遅延・複数場を順次取得する時間で実測leadが60分未満になるリスクが残る。 |
| `wide_drift` / readiness再評価 | 2/5 | 次回にT-10後再計算し `wide_drift > 0`を要求する手順はあるが、今回未実行で既知値は0のまま。さらに現branchには `scripts/f3_phase1_readiness.py` がなく、別branchの統合が前提。 |
| 競合・障害観測 | 4/5 | 共通のatomic lock、`busy_timeout=5000`、nested-lockテストを確認。最終HEADでは共有lock検出時に30秒間隔・最大6試行し、残存時はrc=4でfail-closedするため、従来の無音rc=0を解消した。Task Scheduler同時起動は対象0件でCOM/ingestへ入らず、実競合証明だけが残る。 |
| 取得量・欠落パターン | 4/5 | 行数/タイムスタンプから479行/日、raw約33.9KiB/日という参考推計と、次回のDB行・raw byte実増分測定手順がある。実増分は0、朝配信欠落の時刻帯・競走種別分布は未測定なので運用受入には使えない。 |

## 実証済み

- `keiba-morning-odds`: Ready、daily 08:45、NextRun 2026-07-21 08:45、Actionは専用bat、制限1時間、`IgnoreNew`、直近結果0。
- `keiba-fresh-odds`: Ready、09:00、同時スモーク直近結果0。両ログは同じ19:03:51秒に実行されたが、両方 `total_races=0`。
- focused test: **4 passed**、全体 **370 passed / 4 skipped**。ASCII、固定引数、登録設定、競合時rc=4、最大6試行、同一プロセス内の二重lock拒否を検査。
- task登録は既存taskを先に削除せず、`Register-ScheduledTask -Force`で更新するため、更新途中の登録消失リスクを縮小した。
- `scripts/fetch_fresh_odds.bat`、凍結設計、モデル等は対象diffに含まれない。
- 過去backtestとrule_version付き成果物は残っており、既存の検証履歴基盤を消してはいない。

## 次回JRA開催日の受入手順（全項目必須）

1. 事前に朝アンカーbranchとreadiness branchをmainへ統合し、08:40までにTask Actionのbat実在、Task Ready、当日レース分母を記録する。統合前の登録だけではAction先が存在せず稼働しない。
2. 08:45実行について、ログ/coverage JSONLで `window=600`、`eligible_races>0`、`fetched_races>0`、`lock_skipped=false`、COM/SQLite error=0を確認する。
3. `odds_snapshots.fetched_at` と発走日時からレース単位の最大leadを算出し、**当日全JRA中央レースの100%で lead >=60分**を要求する。未達は時刻帯・場・R・競走条件別に列挙し、特に各場1Rを独立確認する。
4. 08:45開始の実測余裕が5分未満、または1件でも60分未達なら、遅延を許容せず開始時刻を前倒しして再受入する。`StartWhenAvailable`による遅延実行も当該日の60分ゲートを免除しない。
5. T-10点の収集後に同一日を含めたreadinessを再計算し、2時点PIT成立レース数と `wide_drift > 0` を確認する。0なら「朝点欠落」と「価格変化なし」を分離して報告する。
6. morning処理中にlive取得を実際に発火し、30秒間隔の再試行ログ、両Task結果、COM rc、DB lock、最終rcを記録する。lock解放後の成功、または6試行後rc=4のどちらかを要求し、無音成功を競合PASSにしない。
7. 実行前後の `odds_snapshots` 行数、distinct race/timestamp、raw 0B31ファイル数・bytes、DB bytes、所要時間を差分保存し、推計479行/日・33.9KiB/日との乖離と欠落分布を評価する。

## 判定

専用batと登録基盤は **PASS**。ただし、事前指定された数値合格（全レース60分前点、`wide_drift > 0`）、実COM/DB競合、実取得量、朝オッズ欠落分布はすべて未完である。したがって **データgo-live、dev窓開始日の確定、Phase 1開始はいずれもHOLD** とする。
