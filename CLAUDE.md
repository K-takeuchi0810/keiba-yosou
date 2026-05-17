# keiba-yosou — Claude Code 運用規約

このリポジトリで Claude Code が改修するときの全プロジェクト共通ルール。

## 必須ルール

### 0. セッション開始時は `git status` を必ず確認

新しいセッションを開いたら **まず `git status`** を確認する。

- 未コミットの変更や未追跡ファイルがあれば、**新規改修に着手する前に整理する** (コミット or 退避 or 削除)。
- 過去にここを怠った結果、本体ファイル (`config.py`, `CLAUDE.md`, `scripts/filter_sweep.py` 等) が長期間 untracked のまま放置され、`master` と worktree branch でファイル構成が乖離して優先課題リスト (`project-state`) と現実が噛み合わない事故が起きた。
- スパースな worktree (`condescending-ellis-a242c5` 等) に居ても、`master` 側に未コミットの主要ファイルが居る可能性があるので、迷ったら親リポも見る。

### 1. 改修ごとに `expert-review` を必ず実行 (D1 モード)

`gui/` `predictor/` `jvlink_client/` `web/` `scripts/` 配下、または `weights.json` `calibrator.json` `schema.sql` のいずれかを編集して **タスク完了を宣言する直前** に、`expert-review` メタスキルを必ず通す。

詳細: `.claude/skills/expert-review/SKILL.md`

- 7 名の専門家 subagent を **並列** 起動
- `data/scorecards/<yyyymmdd>_<hhmm>_<topic>.md` に結果を保存
- 総合スコアが前回比 -0.3 以上下がった項目があれば警告
- ユーザの確認を待たない (D1 = auto-trigger)

ドキュメントだけの修正 (`*.md`) はスキップしてよい。

#### 1-bis. worktree 改修について expert-review を呼ぶ前の前提条件

worktree branch (例: `.claude/worktrees/<name>/`) で改修して expert-review を呼ぶ場合、subagent の CWD は **親リポ (`C:\Users\kizun\dev\keiba-yosou`)** を向くため、worktree 上の未反映改修は subagent から **不可視** となる。validation-process-auditor / code-quality-reviewer 等が `git log` `git diff` を実行する系の判定は CWD 仕様の影響を強く受け、未反映だと「改修が存在しない」と誤評価する (2026-05-16 P16 A1 で validation-auditor が 1.6 を出して GATE_FAILED 推奨した実例あり)。

そのため expert-review 実行前に、以下のいずれかを必ず完了させる:

- **(a) worktree commit + 親リポへの cherry-pick / merge を完了** (最も安全、推奨)
- **(b) subagent prompt に worktree 絶対パスを明示** し、すべての `git` 操作を `git -C "<worktree-path>" <subcommand>` 形式で行うよう指示。Read / Bash / Grep もすべて worktree 絶対パスで指定

(a) と (b) のどちらを選ぶかは「親リポ反映を本セッションでやるか / 次セッションへ持ち越すか」で決める。時間制約 (重い backtest と並走中など) で (a) が間に合わない場合のみ (b) を採るが、その場合は scorecard に「subagent CWD 限定運用での評価」と明記する。

#### 1-ter. 重い計算 (30 分以上の bg 実行) を起動する前の前提条件

`scripts.backtest` の TEST 全期 (3-4 時間) や Isotonic 再 fit など、**bg 実行 30 分以上の重い計算** を起動する前に、必ず以下を確認する:

1. **実行 cwd の整合性**: 親リポ (`/c/Users/kizun/dev/keiba-yosou`) で `.venv64/Scripts/python.exe -m scripts.backtest ...` を呼ぶ場合、worktree branch の最新 commit が親リポ master に **ff merge 済み** であること。`git -C /c/Users/kizun/dev/keiba-yosou log -3 --oneline master` で worktree の最新 commit hash が含まれているかを確認。
2. **コード反映の事前検証**: 改修した dataclass フィールド / 関数 / フラグが、実行直前に 1 行スクリプトで確認可能。例: `python -c "from predictor.rules import Prediction; import dataclasses; print([f.name for f in dataclasses.fields(Prediction)])"` で新フィールドの存在を確認。
3. **コミット境界の明示**: 重い計算の結果を baseline JSON として保存する場合、その時点の `git rev-parse HEAD` を `--rule-version` に込めるか、`meta.git_sha` (P17 A2 c0 で追加済) として記録。

**理由**: 2026-05-17 P17 A2 Step 1 で、worktree commit `0e30621` (c1) を親リポ master に ff merge しないまま親リポで TEST 全期 backtest を起動した結果、c1 適用前のコードで 3.6 時間動き、生成された `p17_A2_pos_fix` baseline が p16_A1_test と完全一致する重複データになった事故あり (3.6 時間の計算時間ロス、コードや計画への影響はゼロ)。subagent CWD 問題 (ルール 1-bis) と同質の「親リポ↔worktree 同期の見落とし」事故。

これを防ぐため、重い計算前のチェックリスト 3 項目を必須化する。短時間 backtest (< 30 分) や local テストはこの対象外。

### 2. `gui/app.py` の HTML/JS を編集したら必ず `python-embedded-js` 検証

詳細: `.claude/skills/python-embedded-js/SKILL.md`

`CONTROL_HTML` / `PREVIEW_HTML` を触ったら **node で JS パース確認** が必須。Python の triple-quoted 文字列で `\n` が改行に展開される罠で過去 4 回以上ボタンが死んでいる。

### 3. 32bit Python 必須経路の遵守

JV-Link COM は 32bit。`.venv32/Scripts/python.exe` を使う。詳細は `.claude/skills/jvlink-com/SKILL.md`。

### 4. 戦略採用後の月次 rolling 監視義務 (2026-05-15 P12 失敗からの学び)

`config.BUY_FILTER_DEFAULT` に新戦略を採用したら **必ず** 以下を運用化:

1. **`weekly_monitor.bat` を Windows Task Scheduler に登録** (毎週日曜実行)
   - 内部で `scripts.monitor --days 30 --threshold 0.20` 実行
   - 直近 30 日 Brier が baseline 比 +20% 劣化で警告 (exit 1)

2. **Brier 警告発火時の対応**
   - 即サスペンド (`whitelist_tracks=[]` で買い候補ゼロにする)
   - `scripts.filter_sweep --recent-3fold` で robust 戦略再選定
   - 必要なら `scripts.train_lgbm` で LGBM 再訓練 (TRAIN 期間 rolling forward)

3. **採用戦略の "賞味期限" = 3 ヶ月**
   - 3 ヶ月経過時に必ず `--recent-3fold` を再実行
   - 結果が依然 robust なら継続、崩壊していたら退避

**理由**: P12 で `wl5_pop_1_2` を TEST 通年 184% (CI [116%, 266%]) で採用したが、
PRODUCTION 2026 hold-out で **45% に大暴落** (収支 -6,310 円)。
原因は「採用判断 (通年集約) と実運用期間 (春のみ) の季節 / 開催ミスマッチ」と
「馬場特性が 2026 春で大規模 shift」。
**「TEST robust = PRODUCTION robust」は成立しないことを実証**。月次監視 +
四半期再選定でしか継続運用は不可能。

## 専門家 7 名

| ID | 担当 |
|---|---|
| `gui-ux-auditor` | pywebview コントロールパネル UX |
| `mobile-html-reviewer` | iPhone Safari + iCloud 経由の HTML |
| `prediction-logic-analyst` | rules.py / features.py / weights.json の構造 |
| `profitability-judge` | backtest 数値・EV・買い目フィルタ |
| `data-pipeline-engineer` | JV-Link → SQLite |
| `code-quality-reviewer` | DRY / dead code / 設定外出し |
| `validation-process-auditor` | backtest 設計・calibration |

## 関連スキル

- `.claude/skills/project-state/` ← **新セッション開始時に最初に読む** (現状サマリ + 次の優先課題)
- `.claude/skills/expert-review/` ← **改修の最後に必ず通す**
- `.claude/skills/python-embedded-js/` ← GUI HTML/JS 編集時
- `.claude/skills/jvlink-com/` ← JV-Link COM 周り
- `.claude/skills/jvdata-record/` ← レコード追加時
- `.claude/skills/keiba-feature/` ← 予想ロジック追加時
- `.claude/skills/keiba-backtest/` ← バックテスト設計時
- `.claude/skills/token-economy/` ← 大ファイル / 生成物の扱い

## 現在の状態 (2026-05 時点)

8 改修完了で全体平均 **3.06 → 4.09** (baseline 比 +1.03)。直近 p05 改修で **EVAL 41 戦 / 116.1% / +660 円** と初の +収支到達。

詳細スナップショット (実 backtest 数値 / 次の優先 5 件 / 既知の軽微回帰 など) は `.claude/skills/project-state/SKILL.md` を参照。新セッションは **まずこれを読む** ことから始める。

scorecards は `data/scorecards/<日時>_<topic>.md` に時系列で保存済。最新の集約は `20260512_2100_p05_wl_odds_8_20.md`。
