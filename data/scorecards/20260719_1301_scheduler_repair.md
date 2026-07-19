# 採点 2026-07-19 13:01 (定期実行バッチ修理)

**改修**: 定期タスク監査で確定した故障の修理 — ①`auto_predict_daily.bat` の未宣言引数
`fetch_full --since-last`(毎日 exit 2 で静かに失敗)除去 + 失敗の可視化(exit bit 4 +
Discord)②`weekly_monitor.bat` の安全網(monitor→coverage)を pytest より先に実行 +
pytest を PowerShell timeout で隔離 ③09:30+11:30 の 2 トリガー実登録 ④OOS タスク調査。
**bat/ps1/test のみ、rules.py/DB/ingest/fetch_fresh_odds 無変更**。
**対象**: branch `codex/scheduler-repair`、`3a8b796`(Codex 実装)+ `c224384`(HOLD 是正、Claude)

## expert-review: 該当 3 名で採点(4 名は N/A)

本改修は GUI・HTML・予想ロジック・backtest 数値に一切触れないため、ドメインが該当する
3 名を起動。gui-ux-auditor / mobile-html-reviewer / prediction-logic-analyst /
profitability-judge は **対象変更ゼロで N/A**(scorecard 記録のみ、非起動)。

| 専門家 | 判定 | スコア | 要点 |
|---|---|---:|---|
| data-pipeline-engineer | HOLD → **PASS** | 3.0 → ~4.0 | **pytest 隔離 wrapper の ExitCode-null 退行を実機再現**。HOLD 解除条件を `c224384` で充足 |
| code-quality-reviewer | PASS | 4.0 | 修正本体は正しい。検知テストに FN 3 件(次サイクル) |
| validation-process-auditor | PASS | 4.1 | red→green 独立再現。安全網は「優先順位保証≠完走保証」とスコープ要 |
| **平均(是正後)** | | **~4.03** | |

## data-pipeline HOLD の是正(commit `c224384`)

**確定バグ(実機再現済み)**: `weekly_monitor.bat` の pytest 隔離 wrapper で、
PowerShell 5.1 は `Start-Process -PassThru` の `$p.ExitCode` を **WaitForExit(ms) 成功後も
Handle 未取得だと null** で返す。結果 `exit $null` → TESTCODE=0 となり、**pytest が赤でも
bit 2 が立たず Discord に `pytest=0` と誤報**。改修が根絶しようとした「静かな失敗」を
pytest 監視チャネルに新規混入していた(旧・直接呼びより退行)。

- 独立再現: `$p.ExitCode` = `[]`(Handle 未取得)→ `[1]`(`$null=$p.Handle` 追加)。
- 是正: wrapper に `$null=$p.Handle` を挿入(理由コメント付き)+ 回帰 assert
  `assert "$null=$p.Handle" in source` を追加。修正後 wrapper が exit 非 0 を伝播することを実測。
- 全テスト 369 passed / 4 skipped、ASCII 維持。

## 良い点(3 名で裏取り済み)

- `--since-last` 除去は意味論的に正しい(既定 option=1 + fromtime=None → dataspec 単位の
  state 保存値 = 「前回以降の差分」がまさに既定挙動)。state は成功後更新でクラッシュ安全。
- 安全網の順序是正で Brier drift 監視(ルール 4)が pytest 死亡から独立(実機ログで
  monitor→coverage→pytest 順 + `exit 4`=gap のビット合成を確認)。
- timeout→124→`taskkill /T /F` 経路は実測動作。Discord は best-effort(全例外握り +
  return 0)でパイプラインを壊さない。回帰テストの AST 照合は同型バグ再発を的確にブロック。
- 09:30 + 11:30 の 2 トリガーが実タスクに登録済み(初回実走は 2026-07-20 09:30)。

## 残課題(次サイクル・いずれも非ブロッカー)

1. **検知テストの false negative 3 件**(code-quality 実証): caret 継続行 / 短オプション /
   `Start-Process -ArgumentList` スタイル(本改修が weekly で導入した書式)。加えて
   `SCHEDULED_BATS` 手動ホワイトリストが `fetch_fresh_odds.bat` を未カバー。継続行結合 +
   glob 全 bat 化で塞ぐ。
2. **fetch_full の in-band 失敗が依然 exit 0**(data-pipeline): `fetch_full.py:80` は無条件
   `return 0` で、JVOpen rc 異常(認証/-502/サーバ障害=最頻)は summaries に error を積むだけ。
   bit 4 はクラッシュしか捕まえない。**注意: `return 1 if any error` 化は外部バッチ
   (傾向収集 sync)の `if errorlevel 1 goto :run_end` を発火させ制御フローを変えるため、
   cross-project 影響を検討してから**。
3. **安全網の警告チャネルは外部 kill に部分緩和のみ**(validation): monitor は最長ステージ
   (~17 分)で、Discord 通知と exit 合成は依然 pytest 後。drift 検知後に pytest がハング→kill
   されると drift 警告が飛ばない。根治は weekly_monitor の専用 clean worktree 化。
4. **`MultipleInstances=IgnoreNew` × ExecutionTimeLimit 2h**: 09:30 実行が長引くと 11:30 が
   無音 skip される窓(日曜空対策の本命が失われる)。`-MultipleInstances Queue` 検討。
5. fetch_mining の失敗が旧式握り潰しのまま(fetch_full と非対称)。bit 8 化候補。
6. **0xC000013A の真因は未特定**(消去法で「外部中断」が有力に留まる。同時刻に並行セッションが
   同 checkout で pytest を回していた可能性)。断定しない。

## マージ時の注意

- **PR #9(output-defects)と `register_auto_predict_task.ps1` が衝突**(両者とも 11:30
  トリガー追加)。本ブランチ版が exit bit 4 コメント込みで上位互換 → **2 本目のマージ時に
  本ブランチ版を採用**。
- live タスクの Action が指す bat は**マージまで main の旧内容(`--since-last`)で実行**される。
  明朝 09:30/11:30 は旧 bat が走る(害は現状維持: fetch_full が従来どおり静かに失敗、外部
  20:00 バッチの DB で予想生成)。
- **テスト時の Discord 誤送信**: 手動 run が exit 4 で終わると末尾 notify が実 webhook へ飛ぶ。
  今後の手動検証は通知行を一時 REM アウトすること(validation/data-pipeline 両名が指摘)。
- 検収: 7/25(土)11:30 トリガー実走で日曜分が埋まること + 翌週日曜の weekly_monitor 完走。
