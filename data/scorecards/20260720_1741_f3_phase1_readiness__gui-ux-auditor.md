# GUI / UX 監査人 採点

## 判定: HOLD

**理由**: F3 Phase 1 readiness は type-B（診断・readiness 計測）で `gui/app.py` に変更がなく、今回改修による GUI 回帰はない。一方、既存 GUI は全長時間ステージでの確実なキャンセルと基本 ARIA がプロ承認水準に未達。
**根拠ファイル**: `gui/app.py:197`, `gui/app.py:275`, `gui/app.py:1000`, `gui/app.py:1936`, `gui/app.py:2413`
**次アクション**: `ingest_all` / `publish_to_icloud` 内部へ協調キャンセルを通し、進捗要素へ `role="progressbar"` と `aria-valuenow` を付与する。

**改修タイプ**: type-B（`scripts/f3_phase1_readiness.py` による診断・成果物生成。GUI 差分なし）
**採点対象**: `gui/app.py` の Api / CONTROL_HTML と、最終 HEAD `cb56778` による GUI 影響
**スコープ外**: readiness 指標の統計的妥当性、Phase 1 の開始判定そのもの
**GUI 非影響確認**: `git diff 068efb0 cb56778 -- gui/app.py` と `git status --short -- gui/app.py` はともに空。現行 `gui/app.py` の blob は `dee91197622c62a19b17e1226626d65446a7629d`。
**JS 検証**: PASS — Python 解釈後の CONTROL_HTML から 22,086 bytes を抽出し `node --check` 成功。onclick 8 種の呼出先はすべて関数定義あり（missing=[]）。

## 総合: 3.6 / 5（参考スコア、項目平均）

| 項目 | 今回 | 前回 | 差分 |
|---|---:|---:|---:|
| ボタン発見性 / フロー明示性 | 4 | 4 | 0 |
| エラー人間化 / 復旧支援 | 4 | 4 | 0 |
| 進捗表示 / ETA / キャンセル | 3 | 3 | 0 |
| 二重実行防止 / ボタン状態管理 | 4 | 4 | 0 |
| レイアウト / タップ領域 / アクセシビリティ | 3 | 3 | 0 |
| **総合（項目平均）** | **3.6** | **3.6** | **0.0** |

## 項目別

- **ボタン発見性 / フロー明示性: 4/5** — 主要 CTA に「取得 → 予想 → 公開」、個別操作に Ⅰ→Ⅱ→Ⅲ→Ⅳ と依存順序が明示され、主要 action に具体的な `title` がある（`gui/app.py:1943-1964`）。ただし `<details id="helpBox">` はなく、初回操作をまとめたヘルプは未実装（`gui/app.py:1967-1979`）。
- **エラー人間化 / 復旧支援: 4/5** — `_safe` は型名・メッセージ・hint・trace を分離し（`gui/app.py:215-242`）、JS はサマリ + hint と JSON 詳細を折り畳み表示する（`gui/app.py:2470-2475`）。一方、`_error_hint` は主要系統に限られ（`gui/app.py:197-212`）、一部 Promise 失敗は raw `e` 表示（`gui/app.py:2378-2383`, `gui/app.py:2440-2445`）。
- **進捗表示 / ETA / キャンセル: 3/5** — progress bar、百分率、ETA、実行中のみ見える中止ボタン、1秒ポーリングがある（`gui/app.py:1936-1940`, `gui/app.py:2413-2469`）。ただし `ingest_all` と `publish_to_icloud` 内部には `_check_cancel` が伝播せず、押下直後に止まらない区間が残る（`gui/app.py:1000-1009`, `gui/app.py:1100-1127`）。
- **二重実行防止 / ボタン状態管理: 4/5** — status に応じ全 `data-action` を disable し（`gui/app.py:2108-2111`, `gui/app.py:2414-2438`）、Python 側 `_begin_run` が lock 内で running を原子的に check-and-set するため JV-Link COM の二重 Open は防ぐ（`gui/app.py:275-286`）。`inFlight` は未採用で、通信失敗時にボタンを再有効化し得る余地は残る（`gui/app.py:2440-2445`, `gui/app.py:2489-2493`）。
- **レイアウト / タップ領域 / アクセシビリティ: 3/5** — sidebar / dashboard は `overflow-y:auto`（`gui/app.py:1249-1258`, `gui/app.py:1322-1326`）、`focus-visible` もある（`gui/app.py:1810-1814`）。反面、tab の `aria-selected`、日付 label の input 関連付け、progress bar の ARIA role/value、通常ボタンの44px相当タップ高が不足（`gui/app.py:1908-1940`, `gui/app.py:1984-1987`）。

## 停止条件チェック

- [x] JS パース成功、onclick 呼出先欠落なし
- [x] 最終 HEAD `cb56778` まで `gui/app.py` 差分なし
- [x] Ⅰ→Ⅱ→Ⅲ→Ⅳ の操作順序と主要 action title あり
- [x] Python 側原子ガードにより JV-Link COM 二重 Open 防止
- [ ] 専門領域のプロ承認条件: 全長時間ステージの確実なキャンセルと基本 ARIA が未達
- P25 固有の paired baseline / market snapshot / payout ゲート: N/A（type-B readiness の GUI 影響監査）

## 反証の試み

- 改修の主張「GUI 非影響」に対し、readiness スクリプト追加が共通 import やテンプレートを間接変更した可能性を確認。対象コミット間の `gui/app.py` 差分と同ファイル status は空で、さらに実際に Python が生成した JS の構文と onclick target を再検査したため、今回改修による GUI 回帰は不成立。

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
