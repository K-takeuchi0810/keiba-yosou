# コード品質 / 保守性レビュー — auto predict watchdog

## 判定: PASS

**理由**: type-C（JV-Link取得・Windows日次運用）として、watchdogの有界終了、取得直後のingest、破損raw／取得／ingest失敗の非0伝播に加え、option=1のRACE no-dataをoption=2・前週月曜起点で回復する経路が実装・試験・実データで確認された。`rc=-1`近接コード、祝日月曜の取得窓、catch-up後も空のRACEを成功扱いする経路は最終HEAD `0f90945` で解消し、停止条件に抵触しない。

**根拠ファイル**: `scripts/run_auto_predict_daily.ps1:5-80`、`scripts/fetch_full.py:28-179`、`jvlink_client/client.py:70-96,265-269`、`tests/test_auto_predict_task_runner.py:15-335`

**次アクション**: 採用を妨げない最優先改善として、JV-Link return codeを例外文字列ではなく構造化値でclient summaryへ渡し、`fetch_full`のregex依存を除く。

## 改修タイプとスコープ

- **type-C（データ取得／日次スケジューラ運用）**。対象コミットは `cb970a0`、`903b74b`、`a3b13a4`、`99681dd`、`05d68a9`、`c04b1d5`、`5f1a5f9`、`e685c19`、`986598b`、`0f90945`。
- 対象はwatchdog、Task Scheduler登録、日次batch、`fetch_full --ingest`、RACE当週fallback、no-data正規化、および回帰テスト。
- P25 backtest、確率品質、収益性、`market_snapshot`、`meta.env_overrides` は **N/A（対象外）**。
- worktreeには本改修外の `scripts/fetch_fresh_odds.bat` 変更と未追跡成果物がある。採点は上記8コミット、対象テスト、read-only DB確認に限定した。

## 総合: 4.2 / 5（参考スコア）

## 項目別

- **DRY / 単一出典: 4/5** — watchdogは専用runnerへ、RACE catch-up時刻・no-data判定・空summary生成も小さな関数へ分離される（`scripts/run_auto_predict_daily.ps1:1-80`、`scripts/fetch_full.py:28-49`）。留保は、JV-Linkのreturn codeがclientから構造化されず、`fetch_full`が例外文字列をregex解析する層間契約である点（`jvlink_client/client.py:265-269,426-430`、`scripts/fetch_full.py:35-37`）。
- **dead code / 未使用シンボル: 5/5** — 新規helper、fallback、`no_data` markerはいずれも本番経路から到達し、回帰テストも直接使用する（`scripts/fetch_full.py:28-49,98-131,155-162`、`tests/test_auto_predict_task_runner.py:250-335`）。
- **マジックナンバー / 設定外出し: 4/5** — option=1/2、前週月曜起点、`rc=-1`には役割コメントと回帰テストがある（`scripts/fetch_full.py:28-38`、`tests/test_auto_predict_task_runner.py:296-310`）。土日固定規則は除去された。watchdogの通知30秒・kill確認10秒は名前付き定数ではない（`scripts/run_auto_predict_daily.ps1:41,67`）。
- **テスト容易性 / 変更失敗モード: 4/5** — focused **14 passed**、全suite **423 passed / 4 skipped**。option=1 no-data→option=2、土曜／祝日月曜の前週月曜起点、catch-up後も空のRACEの非0、bad raw、fetch/ingest非0をfake clientで固定する（`tests/test_auto_predict_task_runner.py:144-330`）。`rc=-1`の部分一致という実際に発見した失敗モードも、-10/-101/-111/-116の境界testで即検出可能（同`:303-310`）。減点はkill失敗125と通知有効経路が動的試験されない点。
- **エラー処理 / 観測可能性: 4/5** — watchdogは124/125を分離し、fetchはdataspec error／bad rawを1、ingest errorを2で返す（`scripts/run_auto_predict_daily.ps1:54-80`、`scripts/fetch_full.py:148-178`）。RACE incremental no-dataは前週月曜起点fallbackをflush付きで記録し（`scripts/fetch_full.py:99-120`）、catch-up後も空なら曜日を問わずerrorを保持して1を返す（同`:123-139,171-173`）。留保は、rcが構造化値ではなく文字列regexである点（同`:40-42`）。

## 停止条件チェック

- [x] watchdogの有界timeoutとprocess-tree killを動的試験。
- [x] fetch dataspec error / ingest error / bad rawの非0伝播テストあり。
- [x] option=1 RACE no-dataからoption=2前週月曜起点fallback・ingestまでの試験あり。
- [x] `rc=-1`と-10/-101/-111/-116を厳密に区別する回帰テストあり。
- [x] 実DBの2026-08-08をread-only再計測し、races **36** / horse_races **462** を確認。
- [x] 土曜と祝日月曜で前週月曜起点になる回帰テストあり。
- [x] catch-up後もRACE no-dataなら曜日を問わず非0となる回帰テストあり。
- [x] 全回帰テスト成功 — **423 passed / 4 skipped**。
- [x] 最終差分 `git diff 986598b..0f90945 --check -- <対象2ファイル>` は終了0。
- [x] P25固有停止条件 — **N/A（type-C）**。

## 実測・運用状態

- `.venv64\Scripts\python.exe -m pytest -q tests/test_auto_predict_task_runner.py`: **14 passed（5.82秒）**。
- `.venv64\Scripts\python.exe -m pytest -q`: **423 passed / 4 skipped（19.44秒）**。
- `_is_no_data`境界を直接再実行: -1=True、-10/-101/-111/-116=False。
- SQLite read-only query: 2026-08-08は races=**36**、horse_races=**462**。
- 予想72R生成、MAIBuilder API／公開UIの36R表示は親タスクから実運用証跡として提示された。今回はコード品質担当のため、そのUI操作自体は再実行していない。

## 反証の試み

- 主張「no-data判定はrc=-1だけ」に対し、最初の `5f1a5f9` を-101/-111/-116で実行すると全てTrueとなり **反証成立**。`e685c19` のexact-match regexと境界test後に再実行し、-1のみTrueへ修正された（`scripts/fetch_full.py:35-37`、`tests/test_auto_predict_task_runner.py:303-310`）。
- 主張「option=1でRACEを取り逃しても祝日月曜を含め自動復旧できる」に対し、fake clientの2呼出しと起点計算を再実行。土曜2026-08-08は2026-07-27、祝日想定月曜2026-08-10は2026-08-03を返し、2回目はoption=2・dataspecs=[RACE]・取得ファイルのみingestとなり **反証不成立**（同`:250-301`）。
- 主張「fallback後もRACEが空なら無音成功しない」に対し、2回ともRACE `rc=-1`を返すfake clientを再実行し戻り値1を確認したため **反証不成立**（同`:312-330`）。
- 主張「実DBへ当日カードが到達した」に対し、read-only SQLite queryを再実行し36R/462頭を確認したため **反証不成立**。

## 主な改善提案

1. **JV-Link error codeを構造化する** — `jvlink_client/client.py:120-121,265-269,426-430` の`JVLinkError`に`rc`を保持させ、summaryへ`error_code`を出す。`scripts/fetch_full.py:40-42`の文字列regex契約を除く。
2. **Task更新を非破壊化する** — `scripts/register_auto_predict_task.ps1:21-24,39-41` の先行Unregisterをやめ、object構築後に`Register-ScheduledTask -Force`で置換する。
3. **通知を完全なbest-effortにする** — `scripts/run_auto_predict_daily.ps1:29-47` の通知process起動を`try/catch`で囲み、通知起動障害が元の124/125を上書きしない回帰テストを追加する。

## 前回からの差分

- 前回（HEAD `986598b`）: **PASS / 4.2** → 今回（HEAD `0f90945`）: **PASS / 4.2**。
- テスト容易性は4を維持。RACE catch-up後も空なら非0となる回帰が追加され全suite成功だが、125と通知有効経路は未実行。
- エラー処理は4を維持。曜日固定なしでRACE空をfail-closed、非RACE no-dataのみ正常化するため前回残存は解消。文字列rc契約が残るため5には上げない。
