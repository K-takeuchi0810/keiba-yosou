# コード品質 / 保守性レビュー — hidden scheduled tasks

## 判定: PASS

**理由**: 初回停止理由だった未存在ターゲットの偽成功は、起動前 `FileExists` 検査により解消した。正常・子プロセス非0・未存在・引数付きcmd・ps1・無効modeの各境界で終了コードを実測し、8件の現タスクにも意図外設定差分がない。
**根拠ファイル**: `C:\Users\kizun\AppData\Local\ScheduledTaskRunner\run-scheduled-task-hidden.vbs:6-35`、`scripts/fetch_fresh_odds.bat:1-6`、`C:\Users\kizun\Documents\Codex\2026-08-02\new-chat\outputs\scheduled-task-backup_20260802_214740\manifest.json:1-115`
**次アクション**: 採用を妨げない改善として、runnerと副作用のない境界fixtureを管理対象へ移し、再配置手順を残す。

## 改修タイプとスコープ

- **type-C（取得ジョブのWindows運用）**。対象は `scripts/fetch_fresh_odds.bat` のASCII/CRLF化、外部VBS runner、8件のユーザータスク登録、および `keiba-fresh-odds` の既定実行上限への復帰。
- P25 backtest、`market_snapshot`、`meta.env_overrides`、収益性・確率品質は **N/A（対象外）**。
- 対象外の既存・未追跡ファイルは評価・編集していない。

## 総合: 4.2 / 5（参考スコア）

## 項目別

- **DRY / 単一出典: 4/5** — 非表示起動を48行のrunnerに集約し、8タスクが同一実装を参照する。反面、runnerはリポジトリ外の `AppData\Local` にあり、タスク定義もリポジトリ内の宣言的構成から生成されないため、再構築手順の単一出典は弱い。退避XML 8件とmanifestは存在する（manifest `:1-115`、このセッションで8件を実測）。
- **dead code / 未使用シンボル: 5/5** — `cmd` は7件、`ps1` は1件で現登録から到達する。`fileSystem`、`BuildArguments`、`Quote` も実行経路から使用され、未到達分岐は確認されなかった（runner `:6-47`）。
- **マジックナンバー / 設定外出し: 4/5** — hidden=`0` とwait=`True` は名前付き定数で、PowerShellはSystemRoot展開・NoProfile・NonInteractiveを明示する（runner `:3-4,26-29`）。`2` と `87` はWindows終了コードとして妥当だが、意味を示す定数名はない（runner `:9-10,18-19,30-31`）。fresh-oddsは現在Settings API上 `PT72H`、Export XMLでは既定値のため要素なしで、変更前と同じ。
- **テスト容易性 / 変更失敗モード: 4/5** — 副作用のないfixtureで正常バッチ0、引数付きcmd7、ps1 9、未存在2、無効mode/引数不足87を実測した。スペースを含む引数もcmd fixtureが期待値を検査して7を返した。減点はこれらが永続的な自動テストとして管理されていない点。
- **エラー処理 / 観測可能性: 4/5** — 起動前 `FileExists` が未存在を2でfail-fastし（runner `:16-20`）、`Shell.Run(..., 0, True)` の子終了コードをTask Schedulerへ返す（runner `:34-35`）。初回に0だった同一の未存在ケースを再実行し2を確認した。runner固有ログがないため、終了コードだけでは原因の詳細を残せない点を減点した。

## 停止条件チェック

- [x] 改修前タスクXML 8件とmanifestを確認。
- [x] 現在の8タスクがすべて `wscript.exe //B //NoLogo` と同一runnerを参照することを実測。
- [x] 8件のターゲットがすべて現在存在することを実測。
- [x] 退避XMLとの全leaf比較で8件すべてActionだけが差分。トリガー、Principal、WorkingDirectory、Settingsに意図外差分なし。fresh-oddsのExport XMLにも `ExecutionTimeLimit` 要素はなく、変更前と一致。
- [x] `scripts/fetch_fresh_odds.bat` はASCIIのみ、UTF-8 BOMなし、CRLF 6件、bare LF 0件。`git diff --check` は終了0。
- [x] runnerの未存在ターゲットが非0でfail-fastすること — 終了2を実測。
- [x] P25固有停止条件 — N/A（type-C）。

## 反証の試み

- 主張「wrapperは元処理の終了コードと引数を維持し、起動不能を成功扱いしない」に対し、正常バッチ、引数付きcmd fixture、ps1 fixture、未存在ターゲット、無効mode、引数不足を試験。順に0、7、9、2、87、87となり成立した。
- 主張「タスク変更は起動方法だけ」に対し、退避XMLと現行Export-ScheduledTaskの全leaf要素を比較。8件すべてでAction以外の差分0件だったため成立した。

## 主な改善提案

1. **runnerを復元可能な単一出典に置く** — リポジトリ内の管理対象scriptとインストール手順から `AppData\Local` へ配置し、SHA-256または内容照合を行う。8タスク同時停止時の復旧性を上げる。
2. **wrapper境界の回帰試験を残す** — 今回実測した正常0、子プロセス非0、未存在、スペース引数、ps1、無効modeを自動fixtureとして保持する。
3. **終了コードを名前付き定数化する** — runner `:9-20,30-31` の `2` と `87` を `ERROR_FILE_NOT_FOUND` / `ERROR_INVALID_PARAMETER` として宣言し、運用時の意味を明示する。

## 前回からの差分

- **テスト容易性 / 変更失敗モード: 3 → 4 (+1)** — 未存在ターゲット検査を追加し、cmdのスペース引数とps1を含む境界を再実測。
- **エラー処理 / 観測可能性: 2 → 4 (+2)** — 未存在ターゲットの終了コードが0から2へ変わり、偽成功を解消。
- **総合: 3.6 → 4.2 (+0.6)**。
- **前回判定: FAIL → 今回判定: PASS** — 唯一の停止理由だった観測不能な起動失敗が解消した。
