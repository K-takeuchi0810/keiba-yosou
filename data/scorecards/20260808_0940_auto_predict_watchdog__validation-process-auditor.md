# 検証プロセス監査人 採点 — auto predict watchdog

## 判定: PASS

**理由**: 現HEAD `0f90945` は当日E2E復旧と前週月曜からのcatch-up境界に加え、option=2後もRACEがrc=-1ならexit 1へ伝播するfail-closed契約を復元した。対象テスト16件と全423件が独立再実行で緑、実DB・Task・MAIBuilderの当日データ供給も確認済みで、採用を止める欠陥は残っていない。
**根拠ファイル**: `scripts/run_auto_predict_daily.ps1:4-81`、`scripts/fetch_full.py:28-181`、`data/logs/auto_predict_daily_20260808.log:32-68`、`data/logs/fetch_fresh_odds.log`、`data/runtime/fresh_odds_health_20260808_103003.json:1-44`
**次アクション**: 自動fallbackの開始・取得結果・ingest・最終exitを単一の構造化ログへ残し、通知起動失敗と通知timeoutの動的テストを追加する（非阻害）。

## 改修タイプとスコープ

- **type-C（JV-Link取得・SQLite取り込み・Windows日次運用）**。watchdogの一部はtype-B的だが、主要成果は当日RACE供給の復旧なのでtype-Cを主分類とする。
- 対象コミット: `cb970a0`、`903b74b`、`a3b13a4`、`99681dd`、追補 `05d68a9`、`c04b1d5`、復旧実装 `5f1a5f9`、rc厳密化 `e685c19`、catch-up境界修正 `986598b`、RACE fail-closed復元 `0f90945`。公開成果物 `558dfc5` はE2E証跡としてのみ確認した。
- スコープ外: 予測重み、calibrator、収益性、買いフィルタ、GUIレイアウト。P25 paired backtest / factorial / market_snapshotゲートは **N/A（対象外）**。
- worktreeには本改修外の `scripts/fetch_fresh_odds.bat` 変更と未追跡成果物がある。コード採点は上記コミット・対象ファイル、運用採点は時刻付きログ・Task・read-only DB/API実測へ限定した。

## 総合: 4.0 / 5（参考スコア）

## 項目別

- **watchdog検証設計: 4/5** — 正常子exit 7、1秒timeout=124、孫PowerShellのPID消滅を動的検査する（`tests/test_auto_predict_task_runner.py:15-115`）。本番Taskも10:26:59開始、watchdogが10:29:17にexit 0を記録した（`data/logs/auto_predict_watchdog.log`）。125分岐と通知起動障害は動的注入試験がなく5点にはしない。
- **時間境界・鮮度検証: 4/5** — 08:00/09:00 trigger、1200秒上限、前週月曜00:00からのoption=2 catch-upをコード化し、土曜2026-08-08→2026-07-27、祝日月曜想定2026-08-10→2026-08-03をテストする（`scripts/fetch_full.py:28-40,108-137`、`tests/test_auto_predict_task_runner.py:296-329`）。catch-up後もRACEがrc=-1ならerrorを保持してexit 1とする回帰試験があり、HOSE等の通常no-dataだけを成功へ正規化する。
- **ingest／失敗分類: 4/5** — `--ingest` はdataspec別filenamesだけを再取込し、dataspec error=1、ingest error=2、破損raw=1でfail-closed（`scripts/fetch_full.py:148-179`）。実DBをread-only再集計し、20260808は36 races / 462 horse_races、20260809は36 racesを確認。日次ログもRACE files=5、errors=0、RA=38、SE=492を記録する（`data/logs/auto_predict_daily_20260808.log:39-45`）。
- **バージョン管理・再現性: 4/5** — 機能、tree kill、通知、ingest、破損raw、週次復旧、rc厳密化、前週境界を独立コミットへ分けた。rc=-1だけをno-dataとし、-10/-101/-111/-116を除外する（`scripts/fetch_full.py:42-43`、`tests/test_auto_predict_task_runner.py:298-304`）。対象差分の`git diff --check`は0。手動option=2 runの完了全文が専用ログに残らず、DB/後続ログから再構成が必要な点は留保。
- **監視・運用受入: 4/5** — 日次ログは36 races取得後に20260808〜09の72 racesを生成し`push_ok=True`、終了0（`data/logs/auto_predict_daily_20260808.log:46-68`）。fresh oddsは10:29:26に2 racesを取得し、DB再集計で0B31の28 snapshotsを確認。health artifactはscheduler/coverage/DBを全PASSとする（`data/runtime/fresh_odds_health_20260808_103003.json:5-44`）。MAIBuilder healthはdate=20260808、live_updated_at=2026-08-08T10:38:53+09:00、daily cacheは36 racesだった。

## 自分で再実行・再導出した証拠

- 現HEAD `0f90945` のfocused（watchdog/fetch/ingest/mining）: **16 passed in 5.22s**。
- 現HEADの全suite: **423 passed / 4 skipped in 16.46s**。
- 対象コード範囲 `git diff --check`: exit 0。runner/Task登録PowerShell parser: error 0 / 0。
- JVLinkAgent: PID 18416、CreationDate 2026-08-08 10:00:42。復旧ログは09:58:57再起動開始、09:59:03 running（`data/logs/jvlink_recovery_20260808.log:1-3`）。
- SQLite read-only集計: 20260808=36 races / 462 horses、20260809=36 races。10:29:26の0B31=2 races / 28 snapshots。
- Task read-only実測: `keiba-auto-predict` LastResult=0、`keiba-fresh-odds` LastResult=0。双方Ready。
- MAIBuilder: `/api/health` HTTP 200、date=20260808、live更新継続。daily cache `daily_v4_20260808_*.json` は36 races。

## 停止条件チェック

- [x] 改修タイプをtype-Cと分類し、P25固有ゲートをN/Aとして分離
- [x] 正常終了コード、timeout=124、孫process消滅の動的試験あり
- [x] kill失敗/残存=125、timeout通知、通知30秒上限をコード確認
- [x] 取得filenames限定ingest、dataspec/ingest/bad_files非0伝播を試験・コード確認
- [x] option=1 no-data時の前週月曜からのoption=2復旧試験あり
- [x] option=2後もRACEがno-dataだった場合のfail-closed試験・実装
- [x] rc=-1と近接エラーコードの誤分類防止試験あり
- [x] 実JV-Link後の実SQLite当日件数、予想公開、fresh odds、MAIBuilder当日データを確認
- [x] 現HEADの全回帰が緑
- [x] P25再現性meta / paired baseline / market snapshot / payout欠損 — **N/A（type-C）**

## 反証の試み

- 主張「timeout時に孫processが残らない」に対し、CMDがPowerShell孫をspawnしてhangするfixtureを実行。runner=124、記録PID不在で **反証不成立**（`tests/test_auto_predict_task_runner.py:69-115`）。
- 主張「rc=-1復旧で他の負エラーもno-data扱いする」に対し、-10/-101/-111/-116を注入。すべてfalseで **反証不成立**（同`:302-308`）。
- 主張「コード試験だけ成功し、実データは依然0件」に対し、Task、日次ログ、DB、fresh odds、MAIBuilderを突合。36 races / 462 horses、72 races生成、2 races / 28 snapshots、MAIBuilder 36 racesを再導出し **反証不成立**。
- 主張「option=1/2がともにRACE rc=-1でも成功扱いされる」に対し、両fetchがrc=-1を返すfixtureを実行。RACE errorを保持して`main()==1`となり **反証不成立**（`scripts/fetch_full.py:123-137,156-179`、`tests/test_auto_predict_task_runner.py:312-329`）。

## 他専門家判定との整合（type-Cのため参考）

- code-quality: PASS / 4.2、data-pipeline: PASS / 4.0、prediction-logic / profitability / mobile-html: PASS。gui-uxは改修前証跡に基づくHOLDのまま。
- type-Aではないため6 agent統合ゲートは必須ではない。本監査では、全回帰、当日E2E成功、RACE欠落時のfail-closed契約を独立に確認した。

## 主な改善提案

1. **自動fallbackの本番証跡を固定する** — `option=1 rc=-1 → option=2` の開始・open/read/download・ingest summary・最終exitを同じdaily logへ残し、今回のように手動runと後続runをDBから再構成しなくて済むようにする。
2. **通知分岐を動的試験する** — `scripts/run_auto_predict_daily.ps1:29-48` のnotifierをfixture差替え可能にし、通知起動失敗・通知timeoutでも元の124/125を保持することを固定する。
3. **開催カレンダーとの照合を補助監視に加える** — 現状はRACE catch-upが空なら曜日を問わず安全側に失敗する。YSCH等を単一出典として照合すれば、長期非開催時の誤警報を抑えつつ期待開催日の説明可能性を高められる。

## 前回からの差分

- 直前版: NOT_EVALUABLE / 3.6（実JV-Link→実SQLite→MAIBuilderの証拠欠如）。
- `e685c19` 再監査版: PASS / 4.0。実DB 36 races / 462 horses、日次Task exit 0、72 races公開、fresh odds、MAIBuilder当日表示を確認。
- `986598b` 再監査版: **HOLD / 3.8**。前週月曜境界は改善したが、catch-up後のRACE欠落を成功扱いしていたため保留。
- 今回 `0f90945`: **PASS / 4.0**。RACEだけはcatch-up後のrc=-1をerrorとして保持しexit 1へ伝播する実装と回帰試験を追加。focused 16件、全423件、差分整合性がすべて緑。
