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
