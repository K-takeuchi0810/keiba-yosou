# コード品質 / 保守性レビュー — F3 morning anchor（最終）

## 判定 PASS

**改修タイプ**: type-C（データ取得・運用基盤）。P25 backtest採用ゲートはN/A。  
**理由**: 最終HEAD `e5eaf34` では固定引数・実効window検査・終了コード伝播に加え、共有ロック競合を30秒間隔・総6試行で再実行し、残存時はrc=4でfail-closedとなる。登録も先行削除を廃止し `Register-ScheduledTask -Force` に置換された。待機ping数も待機秒から導出され、設定と実挙動の乖離を解消した。阻害欠陥はない。  
**根拠ファイル**: `scripts/fetch_morning_odds.bat:1`, `scripts/register_morning_odds_task.ps1:8`, `tests/test_f3_morning_anchor.py:13`, `docs/F3_morning_anchor_result.md`  
**次アクション**: lock競合継続、Python非0、marker欠落をstub実行し、rcとtemp削除を文字列検査ではなく実行テストで固定する。

## 総合: 4.5 / 5

- 前回正式スコア: **4.5 / 5**（F3 Phase 1 readiness）
- 初回レビュー: **4.3 / 5**（HEAD `6d512ba`）
- 最終: **4.5 / 5**（HEAD `e5eaf34`）
- 正式前回差分: **0.0** / 初回レビュー差分: **+0.2**
- 前回判定: **PASS** / 今回判定: **PASS**

## 項目別

- **DRY / 重複コード: 4.7 / 5** — morning wrapperは取得本体を `scripts.fetch_fresh_odds` へ一元化し、live/morningは既存の `single_run_lock()` を共有する。再試行も同じ呼出しラベルへ戻り、取得処理を複製していない（`scripts/fetch_morning_odds.bat:20-33`）。
- **dead code / 未使用シンボル: 4.8 / 5** — batの追加変数 `LOCK_RETRIES`、`LOCK_RETRY_SECONDS`、`LOCK_RETRY_PINGS`、`ATTEMPT` は全て競合経路で使用される。PowerShellのaction/trigger/settings/principal/infoも登録または観測出力へ到達し、新規dead symbolはない。
- **マジックナンバー / 設定外出し: 4.5 / 5** — 600分、min-lead=0、08:45、60分制限は要件・コメント・テストに対応し、時刻と制限はparam化済み。競合回数と待機秒は名前付き変数に集約され、ping数は `LOCK_RETRY_SECONDS+1` から導出されるため設定とログ・実待機が同期する（`fetch_morning_odds.bat:9-11,30`）。固定windowを外部上書き不可にすること自体は仕様。
- **テスト容易性 / 副作用分離: 4.0 / 5** — 共有ロックは `tmp_path` で競合とcleanupを検証し、ASCIIもdecodeで実証する。`-Force` 使用・先行削除なし・競合rc=4も回帰assertが追加された。一方、bat/PowerShellは依然ソース文字列検査中心で、6回競合、Python失敗、marker欠落、temp削除を実行していない（`tests/test_f3_morning_anchor.py:13-36`）。
- **エラー処理 / ログ / 観測可能性: 4.6 / 5** — Python rc、marker欠落rc=2、venv欠落rc=3、lock残存rc=4を区別し、各試行を専用ログへ残す。通常経路はtempを削除する。`Register-ScheduledTask -Force` により、無効な新規定義を構築中に既存タスクを先に失う経路も解消した（`register_morning_odds_task.ps1:22-45`）。

## 停止条件チェック

- [x] 固定window/min-leadが呼出し行とログmarkerで一致する。
- [x] Python終了コードをwrapper終了コードへ伝播する。
- [x] 通常経路で一時ファイルを削除する。
- [x] ASCII制約をテストで検証する。
- [x] daily 08:45、IgnoreNew、1時間制限、限定権限を登録する。
- [x] live/morningが同一の原子的single-run lockを共有する。
- [x] lock競合を有界に再試行し、残存時にrc=4でfail-closedとなる。
- [x] 先行Unregisterを廃止し、`-Force` で冪等に置換する。
- [ ] bat異常系と登録冪等性を自動実行テストで検証する。

## 反証の試み

- 「共有lockが一時競合しただけで朝アンカーを失う」に対し、競合marker検知後に30秒間隔で総6回試行する実装を確認した。全試行競合時も成功扱いせずrc=4となる。
- 「競合rc=4が後続marker欠落rc=2で上書きされる」に対し、marker欠落blockは `EXIT_CODE==0` の場合だけ2を設定するため、4は保存される（`fetch_morning_odds.bat:34-45`）。
- 「再登録失敗で既存タスクが消える」に対し、`Unregister-ScheduledTask` は削除され、全task object構築後に `Register-ScheduledTask -Force` を行うため初回経路は解消した。実機再登録後もReady、08:45、PT1H、Action一致を確認した。
- 「同時取得で二重実行する」に対し、nested lock testで2回目がFalse、解放後lock残存なし。ただし実レース時COM/DB競合は未観測で、報告書もその制約を明記している。

## 検証結果

- 対象HEAD: `e5eaf34`。`git log --stat -3`、`1163c83..e5eaf34` 差分を確認。
- PowerShell parser: **OK**。
- `pytest tests/test_f3_morning_anchor.py -q`: **4 passed**。
- 全体 `pytest -q`: **370 passed, 4 skipped**。
- `git diff --check`: エラーなし。
- 実登録: **Ready**、NextRun **2026-07-21 08:45**、Action `cmd.exe /d /c call "...fetch_morning_odds.bat"`、ExecutionTimeLimit **PT1H**。
- 初回指摘「delete-before-register」: **解消**。競合時の無音成功: **有界retry + rc=4で解消**。
- 必須簡易scan（初回実施）: `predictor/rules.py` def 20、直書き `score +=/-=` 1、既存unused feature 32件。いずれも本改修由来ではない。

## 主な改善提案

1. **競合・異常系を実行テスト化する** — `fetch_morning_odds.bat:20-48` をstub commandで起動し、競合→成功、6回競合→rc=4、Python非0、marker欠落、temp削除を確認する。
2. **テスト用の待機時間注入を用意する** — 本番既定30秒を保ちつつ、テスト時だけretry秒を短縮可能にすれば再試行回数と終了コードを高速に実行検証できる。
3. **運用ログをrotationする** — `fetch_morning_odds.log` は追記のみなので、日付またはサイズ上限を設ける。
