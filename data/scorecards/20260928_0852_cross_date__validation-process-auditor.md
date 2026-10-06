# validation-process-auditor 採点 — cross-date 汚染修正 (評価経路の改修)

**評価対象**: worktree `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\cross-date`、branch `cross-date-fix-20260926`、
HEAD `c3be0e9c718d960a701c6d980a05aa60d4888c47` (= main `4bc16e9` + `ead43ce` 修正 + `c3be0e9` テスト衛生)。
開始時・終了時ともに porcelain 0 行、HEAD 不変を確認。**subagent CWD 限定運用での評価** (`git -C <worktree>` と絶対パスのみ、
本番 checkout・worktree への書込みは本 scorecard 以外なし、本番 DB は開いていない)。

**改修タイプ宣言**: type-B (評価/検証ツール。`scripts/build_daily_results.py` = 日次答え合わせ成果物の生成器)。
予測ロジック・閾値・購入判断は変えない。したがって P25 固有ゲート (factorial C1-C5 / market_snapshot / fresh odds /
bonus_candidate / 他 6 agent 統合) は **N/A (対象外)**。適用するのは汎用ゲート = 評価母集団の正しさ・
評価データ汚染 (リーク分類学 ④) の閉鎖・停止条件の妥当性・再現性・変異テストの証拠。

## 判定: PASS (マージと scratch 再生成へ進んでよい。台帳の INVALID 解除は下記 3 条件の後)

**理由**: 評価母集団が「予想日 == 対象日」に限定され、外した別日レースが件数・ID で manifest に残り、
一次データ (保存 HTML 82 本の再解析・修正前コードでの 14/14 失敗・当方再実行の変異 8/8 KILLED・
フルスイート 1019 passed / 12 skipped) が作者の主張と一致。停止条件の抵触なし。テスト衛生パッチは既存の
検出力を落としていない。留保は「対象日レース 0 件の日」が **exit 0 + 空 CSV** という暗黙状態でしか表現できない点。

**根拠ファイル**:
- `scripts/build_daily_results.py:352-402` (`RACE_ANCHOR_RE` / `parse_race_anchor` / `split_races_by_date` / `check_prediction_invariants`)、`:596-613` (exit 2 経路)、`:991-998` (manifest の foreign_date_*)
- `tests/test_cross_date.py` (14 本)、`tests/mutation_specs/cross_date_spec.py` (X1-X8)、`tests/test_build_daily_results.py:162-166, 287-289, 796-823`
- `C:\Users\kizun\dev\keiba-yosou\data\cross_date_mutation_20260928\run1_result.txt` (作者)、当方再実行 `...\scratchpad\cross_vpa\mutation_rerun.txt`
- `C:\Users\kizun\dev\keiba-yosou\docs\EVALUATION_DATA_QUALITY.md` (台帳)

**次アクション** (レビュー後の再生成に向けて。いずれも本ブランチのコード変更を要さない):
1. 3 つの非開催日 (6/12, 6/17, 7/03) は `predictions_source_*.html` が無く HTML は `archive/index_*.html` にある。既定 glob では
   exit 2 (`HTML が見つからない`) になるので **`--html` を明示**し、使った HTML のファイル名と sha256 を修復記録に残す (6/17 は 2 本あるので選択理由も)。
2. 対象日レース 0 件の日の成果物は **exit 0 / 6 ファイル生成 / predictions=0 / evaluation_rows_total=0** になる (当方 scratch 実測)。
   `REPAIRED_NO_TARGET_DATE` と判定する根拠として、manifest の `html_races_parsed`・`foreign_date_races_dropped` (両者一致)・`predictions=0`・
   `supersedes_manifest_sha256` の 4 値を台帳行に転記する。builder は明示的な状態名を持たないため、CHAT 指示どおり **spec 追加はせず報告に留める**。
3. 台帳の `repair_pending=false` 化は、他レビュア (data-pipeline / code-quality) に FAIL / NOT_EVALUABLE が無いことと、7 開催日の新旧差分
   (旧 N − 新 N = 31/30/32/26/20/27/28 行) が記録されたことを確認した後。

## 総合: 4.4 / 5 (参考スコア)

## 項目別

- **評価母集団の定義と設計 (バックテスト設計の正しさ): 4.5/5** — 対象日レースのみが `predictions` → `eval_rows` に入る (`:642-668`, `:825` は `predictions` を起点)。
  当方が保存 HTML を新パーサで再解析: builder 既定 (最新) HTML で 7/18 = target 36 / foreign 36 (31 頭)、8/08 = 36/36 (30)、8/15 = 36/36 (32)、
  8/22 = 36/36 (26)、8/29 = 36/36 (20)、9/05 = 36/36 (27)、9/12 = 24/24 (28)。**全 foreign レースが対象日レースと (場, R) で衝突** = 旧コードの
  結合経路そのもので、台帳の 31/30/32 行・26/20/27/28 行と頭数まで一致。減点: 対象日レース 0 件でも exit 0 で空 CSV (下記「反証」B/C)。
- **評価データ汚染の閉鎖 (リーク分類学 ④ / 境界条件): 4.5/5** — 日付は `==` の完全一致 (`:377`)、前日も翌日も foreign (`test_a_past_date_race_is_also_foreign`)。
  レース ID が読めなければ止まる (`:372-375`)。82 本全 HTML で unreadable 0、対象日不変量違反 0 → 歴史データの再生成で exit 2 が誤発火する日は無い。
  参考所見: 下流 `scripts/analyze_misses.py:159-160` の「翌日分を除外」フィルタは、旧 builder が race_id を対象日で組み直していたため
  **実際の汚染に対しては無効だった**。汚染は生成器で止めるのが正しい層で、本修正はそこに当たっている。
- **停止条件 (exit 2) の設計 — 落とすか止めるか: 4.5/5** — 別日レース = 「評価対象外だが正常な入力」→ 落として記録、対象日レースの ◎ 2 頭・馬番重複・
  ID 不読 = 「生成器側の欠陥の徴候」→ 止めて何も書かない、という非対称は正しい。落とすと N が黙って縮む。foreign 側の矛盾では止めない
  (`test_the_invariants_look_only_at_the_target_date`) のも整合。減点: exit 2 が `--date` 不正・HTML 不在と同じ値で、rc だけでは区別できない (stderr 文言で区別)。
  `output_dir.mkdir` (`:574`) が exit 2 判定より前にあり、新規日付で空ディレクトリが残りうる (軽微)。
- **再現性 / テスト / 変異 (A/B 相当の証拠): 4.5/5** — 当方実測: (a) worktree フルスイート **1019 passed / 12 skipped** (169.6 s)、
  (b) main `4bc16e9` の builder に c3be0e9 の tests を当てると `tests/test_cross_date.py` **14/14 failed** (中心テストは元の欠陥で落ちる)、
  (c) `scripts.mutation_sandbox` を当方の `git archive c3be0e9` 隔離コピーで流し **X1-X8 8/8 KILLED、rc=0**、落ちたテストも spec の
  「落ちるべきテスト」と全件一致。manifest に `builder_git_sha` / `supersedes_manifest_sha256` / `source_html_sha256` あり。
  減点: 作者の `run1_result.txt` にコピーの sha・spec の hash・日時が無く、単体では「どのコードに対する結果か」を追えない。
- **テスト衛生パッチの影響 / 運用移行 / 統合: 4.0/5** — `c3be0e9` の変更は `test_manifest_records_builder_provenance_and_superseded_hash` の
  `assert first["builder_git_sha"]` (非空) → `== FAKE_GIT_SHA` のみ。旧アサーションは「本物の SHA と一致」も「書出し前に取得」も検査しておらず
  (`git log -S` で導入 `2a5ae4d` 以降変更なし)、失った検出力は無い。新設 `test_git_provenance_matches_the_checkout_head` は worktree で
  **PASSED** (skip ではない: `.git` はファイルでも `exists()` 真)、fail-closed テストも PASSED。減点: 対象日 0 件の日の状態が暗黙
  (次アクション 2)、非開催日は `--html` 明示が要る (次アクション 1)、sibling レビュアの判定は本 scorecard 執筆時点で未提出。

## 停止条件チェック (該当の有無を全項目明記)

- [x] git_sha / rule_version / env_overrides 記録あり — type-B: manifest の `builder_git_sha` / `builder_git_dirty` / `source_html_sha256` / `version_meta` で代替、記録あり
- [ ] baseline paired 比較成立 — N/A (type-B、収益/確率の改善主張なし)。代替として修正前 builder × 新テスト 14/14 failed を実測
- [ ] market_snapshot counts あり — N/A (type-B)
- [ ] payout 欠損 race の扱い明示 — N/A (本改修の範囲外。既存の 4 段階評価は不変)
- [x] 専門領域別の停止条件すべて不抵触 — 比較設計の不成立: 非該当 / 統計手法の不適: 非該当 (統計量を出す改修ではない) / 再現性不足: 非該当 / 他 agent 判定との不整合: 現時点で FAIL・NOT_EVALUABLE の提出なし (未提出は「不整合」ではない)

## 反証の試み

- 主張「保存済み 79 本の HTML はすべて `race-YYYYMMDD-TT-R`」→ `data/results/**/*.html` 82 本 (archive 含む) を新パーサで走査: unreadable 0、
  旧コメントにあった `race-2026-06-21-05-12` 形は 0 本。**成立** (件数は 82、主張の 79 との差は archive 3 本分と推定)。
- 主張「修正で 26/20/27/28 頭が落ちる」→ 8/22, 8/29, 9/05, 9/12 の builder 既定 HTML で foreign 26/20/27/28 頭。**成立**。7/18・8/08・8/15 も台帳の 31/30/32 と一致。
- 主張「変異 8/8 KILLED」→ 当方の隔離コピーで再実行、8/8 KILLED rc=0、落ちたテスト名も一致。**成立**。
- 反証シナリオ「テスト衛生で本物の git 由来が検査されなくなる」→ 専用テストが worktree で PASSED、fail-closed も PASSED。**不成立** (弱体化なし)。
- 反証シナリオ「対象日レース 0 件の日で builder が止まる / 壊れる」→ scratch (偽 DB、`--output-dir` は scratch) で 3 通り実測:
  A) 開催日 + HTML が全て別日 → **rc 0**、6 ファイル生成、`predictions=0` / `evaluation_rows_total=0` / `foreign_date_races_dropped=2=html_races_parsed`、DB 由来 CSV は行あり。
  B) 非開催日 (DB 0 行) + 全て別日 → **rc 0**、全 CSV 0 行。C) レースが 1 つも無い HTML / 0 バイト HTML → **rc 0**、全 CSV 0 行。
  → 止まりはしないが、**「別日しか無かった日」と「空 HTML」が rc・ファイル構成で区別できない** (manifest の `html_races_parsed` でのみ区別可)。
  これは修正前からの挙動で本ブランチの退行ではない。
- 3 非開催日の archive HTML を新パーサで走査: 6/12 = 168 レース (5/30, 5/31, 6/06, 6/07, 6/13, 6/14) / 対象日 0、6/17 = 36 (全て 6/14) / 0、
  7/03 = 72 (7/04, 7/05) / 0。いずれも split OK、exit 2 にはならず、A/B の形 (N=0) で再生成される見込み。

## 主な改善提案 (優先 1 件、最大 3 件。いずれも本ブランチのマージ条件ではない)

1. **対象日 0 件を明示状態にする (次サイクル、要ユーザ合意)** — `scripts/build_daily_results.py:606` 以降で `not races and all_races` のとき manifest に
   `evaluation_status: "NO_TARGET_DATE_PREDICTIONS"` を刻む (rc は 0 のまま)。空 HTML (`not all_races`) は別状態にする。CHAT の方針に従い今回は報告のみ。
2. **変異結果に来歴を付ける** — `scripts/mutation_sandbox.py` の出力先頭に copy の由来 sha・spec の sha256・python 実行体・日時を 1 行出す。
   `run1_result.txt` 単体で「c3be0e9 に対する結果」と言えるようにする。
3. **exit 2 の意味を分ける** — `:565` (`--date` 不正)・`:588` (HTML 不在) と `:606` (入力不変量違反) を別 rc (例: 3) にするか、少なくとも
   runbook に stderr 文言での識別を書く。Task Scheduler 経由では stderr が見えない場合がある。

## 前回からの差分

- 前回 (同 agent、別トピック `20260928_0234_jst_unify_final`): PASS 4.5。今回は別改修のため直接比較せず。
  本トピックの前回 scorecard は無し (初回)。判定 PASS の根拠は上記の一次データ再実行 (b)(c) と反証 5 件。
