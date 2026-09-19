# GUI / UX 監査人 採点

## 判定: HOLD

**理由**: F3 morning anchor の最終 HEAD `e5eaf34` と直前3コミットは batch / PowerShell / tests の運用改修で `gui/app.py` に差分がなく、今回改修による GUI 回帰はない。一方、既存 GUI は全長時間ステージでの確実なキャンセルと基本 ARIA がプロ承認水準に未達。
**根拠ファイル**: `gui/app.py:197`, `gui/app.py:275`, `gui/app.py:1000`, `gui/app.py:1100`, `gui/app.py:1936`, `gui/app.py:2413`
**次アクション**: `ingest_all` / `publish_to_icloud` 内部へ協調キャンセルを通し、進捗要素へ `role="progressbar"` と `aria-valuenow` を付与する。

**改修タイプ**: type-B/C 境界の運用・データ取得自動化（morning odds anchor の batch / scheduler / tests。GUI 差分なし）
**採点対象**: `gui/app.py` の Api / CONTROL_HTML と、最終 HEAD `e5eaf34` による GUI 影響
**スコープ外**: morning anchor の取得時刻、再試行・ロック設計、Task Scheduler 登録、保存データの妥当性
**GUI 非影響確認**: `git log --stat -3` の変更先は `scripts/fetch_morning_odds.bat`, `scripts/register_morning_odds_task.ps1`, `tests/test_f3_morning_anchor.py` の3ファイルのみ。`git diff 3ce4810 e5eaf34 -- gui/app.py` と `git status --short -- gui/app.py` はともに空で、現行 `gui/app.py` の blob は `dee91197622c62a19b17e1226626d65446a7629d`。
**HTML / CSS / JS 検証**: PASS — Python 解釈後の CONTROL_HTML は HTML parser を通過し、style 1 block の波括弧は 126 / 126。script は22,086文字を抽出して `node --check` 成功。onclick 8種（`cancelRun`, `forceRefresh`, `presetLatest`, `presetToday`, `presetWeekend`, `resetFilters`, `runAction`, `showTab`）の呼出先はすべて関数定義あり（missing=[]）。現行 `gui/app.py` に独立した `PREVIEW_HTML` 定数はなく、プレビューは CONTROL_HTML 内の pane / iframe で実装される（`gui/app.py:1982-2031`）。

## 総合: 3.6 / 5（参考スコア、項目平均）

## 項目別

- **ボタン発見性 / フロー明示性: 4/5** — 主要 CTA に「取得 → 予想 → 公開」、個別操作に Ⅰ→Ⅱ→Ⅲ→Ⅳ と依存順序が明示され、主要 action に具体的な `title` がある（`gui/app.py:1943-1964`）。ただし `<details id="helpBox">` はなく、初回フローと復旧手順をまとめた操作ヘルプは未実装（`gui/app.py:1967-1979`）。
- **エラー人間化 / 復旧支援: 4/5** — `_safe` はエラー型・メッセージ・hint・trace を分離し（`gui/app.py:215-242`）、JS は1行サマリ + hint と JSON 詳細を折り畳み表示する（`gui/app.py:2470-2475`）。一方、`_error_hint` は主要6系統に限られ（`gui/app.py:197-212`）、ダッシュボード・進捗・API Promise の一部失敗は raw `e` 表示のまま（`gui/app.py:2378-2383`, `gui/app.py:2440-2445`, `gui/app.py:2486-2487`）。
- **進捗表示 / ETA / キャンセル: 3/5** — progress bar、百分率、ETA、実行中のみ表示される中止ボタン、1秒ポーリングがある（`gui/app.py:1936-1940`, `gui/app.py:2413-2469`）。ただし `ingest_all` と `publish_to_icloud` の内部には `_check_cancel` が伝播せず、押下直後に停止できない区間が残る（`gui/app.py:1000-1009`, `gui/app.py:1100-1127`）。
- **二重実行防止 / ボタン状態管理: 4/5** — status に応じ全 `data-action` を disable し（`gui/app.py:2108-2111`, `gui/app.py:2414-2438`）、Python 側 `_begin_run` が lock 内で running を原子的に check-and-set するため JV-Link COM の二重 Open は防ぐ（`gui/app.py:275-286`）。`inFlight` は未採用で、進捗取得失敗が `false` を返すため API 本体の返却後にボタンを再有効化し得る余地は残る（`gui/app.py:2440-2445`, `gui/app.py:2489-2493`）。
- **レイアウト / タップ領域 / アクセシビリティ: 3/5** — sidebar / dashboard は `overflow-y:auto`（`gui/app.py:1249-1258`, `gui/app.py:1322-1326`）、`focus-visible` もある（`gui/app.py:1810-1814`）。`display:none` は中止・プレビュー等の状態切替用途で恒久的な死にゾーンではない。反面、tab の `aria-selected`、日付 label の input 関連付け、progress bar の ARIA role/value、通常ボタンの44px相当タップ高が不足する（`gui/app.py:1777-1793`, `gui/app.py:1908-1940`, `gui/app.py:1984-1987`）。

## 停止条件チェック

- [x] JS パース成功、onclick 呼出先欠落なし
- [x] 最終 HEAD `e5eaf34` まで `gui/app.py` 差分なし
- [x] Ⅰ→Ⅱ→Ⅲ→Ⅳ の操作順序と主要 action title あり
- [x] Python 側原子ガードにより JV-Link COM 二重 Open 防止
- [ ] 専門領域のプロ承認条件: 全長時間ステージの確実なキャンセルと基本 ARIA が未達
- P25 固有の git_sha / paired baseline / market_snapshot / payout ゲート: N/A（morning anchor 運用改修の GUI 影響監査）

## 反証の試み

- 改修の主張「GUI 非影響」に対し、morning anchor の運用改修が共通 import や埋め込みテンプレートを間接変更した可能性を確認。対象コミット間の `gui/app.py` diff と同ファイル status は空で、blob も前回監査と同一。さらに Python が生成した HTML / CSS / JS と onclick target を再検査したため、今回改修による GUI 回帰は不成立。

## 主な改善提案（優先1件、最大3件）

1. **キャンセルを ingest / publish 内部まで伝播** — `ingest_all(..., cancel_check=self._check_cancel)` 相当と、公開コピー前後の `_check_cancel()` を追加する（`gui/app.py:1000-1009`, `gui/app.py:1100-1127`）。
2. **進捗とフォームの ARIA を補完** — `#progressWrap` に `role="progressbar"`、JS に `aria-valuenow/min/max` 更新、日付 label に `for`、tab に `aria-selected` を追加する（`gui/app.py:1908-1940`, `gui/app.py:1984-1987`）。
3. **操作ヘルプを追加** — sidebar に `<details id="helpBox">` を置き、初回フロー、検証モード禁止事項、エラー時の復旧順を記載する（`gui/app.py:1967-1979`）。

## 前回からの差分

- ボタン発見性: 4 → 4（GUI 差分なし）
- エラー人間化: 4 → 4（GUI 差分なし）
- 進捗 / ETA / キャンセル: 3 → 3（既存の中止保証不足が残る）
- 二重実行防止: 4 → 4（Python 原子ガードを維持）
- レイアウト / アクセシビリティ: 3 → 3（既存 ARIA 課題が残る）
- 前回判定: HOLD。今回も HOLD。総合 3.6 → 3.6（差分 0.0）。
- 時系列確認: 2026-05 baseline 3.2 から改善後、直近2回は 3.6 / HOLD。今回も同水準で回帰なし。
