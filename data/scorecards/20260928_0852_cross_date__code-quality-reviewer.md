# code-quality-reviewer — cross-date 汚染修正 (別の日の予想を対象日として採点しない)

- 対象: worktree `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\cross-date`, branch `cross-date-fix-20260926`, HEAD `c3be0e9c718d960a701c6d980a05aa60d4888c47` (main `4bc16e9` の上に `ead43ce` 修正 + `c3be0e9` テスト衛生の 2 commit)
- 評価方式: **subagent CWD 限定運用での評価** (すべて `git -C <worktree>` / 絶対パス)。開始・終了とも HEAD `c3be0e9`、porcelain 空 (0 行) を確認
- 改修タイプ: **type-B (評価/診断ツール `scripts/build_daily_results.py` の入力検証 + テスト)**。予測ロジック・weights・backtest は不変。P25 固有項目 (meta.env_overrides / market_snapshot / PRED_DISABLE_BLEND / test_market_popularity_scoring 等) は **N/A (対象外)**。汎用ゲート (DRY・dead code・設定外出し・テスト容易性/変更失敗モード・例外処理/観測可能性) で採点
- 安全: 本番 DB には触れていない (builder の実行なし)。実 HTML の確認は `data/results/*/predictions_source_*.html` を **読むだけ** の純関数呼び出し。変異は scratchpad `cross_cqr/copy` (`git archive c3be0e9`、`.venv64` はジャンクション) で `scripts.mutation_sandbox` 経由のみ。main checkout / worktree への書き込みは本 scorecard のみ

## 判定: PASS

停止条件への抵触なし。must-fix は 1 件 (テストの網の穴、本体コードの変更は不要) で、マージ前に足すことを条件とする「留保付き PASS」。

## 総合: 4.1 / 5

| 軸 | 点 | 要点 |
|---|---|---|
| DRY / 単一出典 | 4.0 | レース ID の**読み手**は `RACE_ANCHOR_RE` / `parse_race_anchor` の 1 か所に集約 (`scripts/build_daily_results.py:353-361`)。ただし同じ契約 `race-YYYYMMDD-TT-R` を **書く側** `web/generator.py:563` と、日付だけを嗅ぐ別の正規表現 `web/generator.py:157` (`_prediction_date_from_html`) が独立に持つ = 3 か所の平行記述。`f"{date}-{track}-{race_num_of(...)}"` の race_id 組み立ても bdr 内 3 か所 (`:391`, `:608`, `:661`) |
| dead code / 未実装前提 | 4.5 | 旧の末尾一致 regex は完全に置換、`race_anchor` は例外文言で使用中、`race_date` を race dict に追加して初期化も揃う。未実装 env を前提にした記述なし。`scripts/analyze_misses.py:163` の `startswith(date)` 翌日除外は本修正で **冗長な二重防御** になる (dead ではない。残すなら「builder 側で既に除外済、防御線として残す」の 1 行を) |
| マジックナンバー / 設定外出し | 4.0 | 例外文言の `[:5]` / stdout の `[:6]` は表示の切り詰めで許容。exit 2 は `--date` 形式不正 (`:565`) と同じ「入力不良」の意味で一貫。ただし **モジュール docstring (`:1-30`) に終了コードと manifest 新キー 3 つの記載なし**、`docs/EVALUATION_DATA_QUALITY.md:47` は 2 キーのみで `foreign_date_races_dropped` が漏れ |
| テスト容易性 / 変更失敗モード | 4.0 | 14 本 (parametrize 6 + main() 経由 8) はすべて出力 CSV / manifest / rc を読む挙動テスト。著者 X1-X8 は 8/8 KILLED (再現)。**自分の追加変異 11 本は 7 KILLED / 4 SURVIVED**、うち **Y8 (◎ 判定を ○ にも広げる) の生存は実害級の網の穴** (下記) |
| 例外処理 / 観測可能性 | 4.0 | fail-closed: `PredictionInputError` で CSV / manifest を 1 つも書かず rc 2、文言に race_id と読めない ID 最大 5 件。別日レースは manifest 3 キー + stdout 1 行で **黙って捨てない**。留保: stderr であること・文言はテストで固定されていない (Y2 生存)、`output_dir.mkdir` (`:574`) が検証より前なので rc 2 でも空 dir が残る |

## 検証した事実 (自分で実行)

1. `git -C <wt> diff --stat 4bc16e9 c3be0e9`: 4 ファイル +374/−12。`scripts/build_daily_results.py` +97/−12 のみが本体、他は tests。スコープ逸脱なし
2. worktree で `tests/test_cross_date.py tests/test_build_daily_results.py`: **48 passed** (2.2s)。全体: **1019 passed / 12 skipped, rc=0** (2:54) — 著者申告と一致
3. `test_git_provenance_matches_the_checkout_head` は worktree (`.git` はファイル) で **skip せず実行され pass** (`-rs` で確認)。`_run_main` の `git_provenance` 固定は評価ロジックのテストから「git の有無」を切り離すだけで、manifest の `builder_git_sha == "0"*40` 完全一致に強化されている → 本物の呼び出し経路を隠していない
4. 著者の 8 変異 (`tests/mutation_specs/cross_date_spec.py`): `data/cross_date_mutation_20260928/run1_result.txt` = 8/8 KILLED, rc=0 (読了)
5. **自分の 11 変異** (`scratchpad/cross_cqr/cqr_spec.py`, 結果 `cqr_result.txt`, sandbox rc=1):
   - KILLED: Y3 日付比較を月まで (`[:6]`) / Y4 不変条件を all_races に / Y5 exit 2→1 / Y6 manifest だけ外して評価は全レース / Y7 対象日と衝突する別日レースだけ外す / Y11 別日レースを 1 件だけ残す
   - SURVIVED: **Y8 `== "◎"` → `in ("◎","○")`** / Y1 regex の `^ $` を外す / Y2 stderr→stdout / Y9 馬番の `lstrip("0")` を外す / Y10 `sorted`→`list`
6. **実 HTML の読み取り専用検査** (worktree の `parse_predictions_html` → `split_races_by_date` → `check_prediction_invariants`、DB 不使用): `data/results/*/predictions_source_*.html` **67 本 / 2,664 レース / 読めない ID 0**。別日レースを含む日は **17 本 (7/18, 7/25, 8/08, 8/15, 8/22, 8/29, 9/05, 9/12、いずれも翌日分 24-36 レース、馬行は 20-32 頭)**。**対象日レースの不変条件違反は 0 件** → 10 日ぶんの再生成で rc 2 が誤発火する経路は現データに無い。なお docstring `:352` の「79 本」は `data/results` 配下では 67 本で、数え方の出典が不明 (実害なし、記述の正確さのみ)
7. 他の anchor 解析器の有無 (grep `race-` / `race_anchor` 全 .py): `web/generator.py:157` (日付だけ取り出す、日付を捨てない) と `web/generator.py:563` (書き手) のみ。`analyze_misses` は CSV の `race_id` を読むだけ (`:163`)。**日付を捨てる解析器は他に残っていない**
8. builder を呼ぶ .bat/.ps1/.py は repo に無い (手動起動)。rc 2 の消費者は人。`auto_predict.py` は HTML を `predictions_source_*` として保存する書き手側で解析はしない

## 所見

- **変更失敗モード (must-fix の根拠)**: `check_prediction_invariants` の ◎ 判定を誰かが「印付き馬は 1 頭」と誤って広げる (Y8) と、本番 HTML は全レースに ◎○▲△☆ が並ぶので **すべての日で rc 2 = 答え合わせが 100% 止まる**。落ち方は fail-fast (静かではない) が、**テストは緑のまま**。原因は、対象日レースで ○ / ▲ を持ちつつ rc 0 を期待するフィクスチャが 1 本も無いこと (`test_cross_date.py:147` の ◎+○ は重複馬番で rc 2 を期待するテスト、`:77/:95` の ○ は別日レース)。「現実の形の 1 レース (◎○▲ + 印なし数頭) が main() を通って全頭 summary に出る」を 1 本足せば Y8 は落ちる。1 キー追加時の触り箇所という観点でも、この happy path が無いと不変条件の追加が本番だけで壊れる
- **変更失敗モード (良い方向)**: 日付比較の粒度 (Y3)・不変条件の適用範囲 (Y4)・「評価は全部、manifest だけ外す」(Y6)・「衝突分だけ外す」(Y7)・「1 件取りこぼす」(Y11) はいずれも `test_a_foreign_race_with_the_same_track_and_number_is_not_scored` / `test_foreign_races_are_recorded_not_silently_dropped` が即座に落とす。元の欠陥と同型の回帰は網に掛かる
- **単一出典**: anchor 契約の書き手 (`generator.py:563`) と読み手 (`bdr:353`) が別モジュールの文字列リテラル。テンプレート側は `test_template_render.py` が `race-20260613-05-1` を、builder 側は `test_the_anchor_keeps_the_date` が実サンプルを固定しているので**乖離すれば 2 つのテストのどちらかが落ちる**設計にはなっている。構造的一元化 (`web/anchor.py` に `format_race_anchor` / `parse_race_anchor` / regex を置き、`generator.py:157` もそれを使う) は改善提案に留める
- **git_provenance の固定が隠すもの**: `git status --porcelain -- . ":!data/results"` の dirty 判定は固定テストでは検証されない (本物テストは `isinstance(dirty, bool)` まで)。今回の改修範囲では問題ないが、dirty 判定の除外パスを変える改修があれば専用テストを足すこと
- **Y1 / Y9 / Y10 生存の評価**: Y1 は `xrace-…` / `…-111` のような形を許すだけで実 HTML には出ない。Y9 はテンプレート `index.html.j2:795` が `{{ h.num }}` を整数で出すため実害なし。Y10 は表示順のみ。いずれも must-fix にしない
- **Y2 生存の評価**: 手動起動なので stderr の文言が唯一の説明。`capsys` で「予想 HTML が評価の前提を満たさない」と race_id が stderr に出ることを 3 本の stop テストに足すのは数行

## 次アクション

1. **(must-fix、マージ前)** `tests/test_cross_date.py` に「現実の形の対象日レース (◎○▲ + 印なし 2-3 頭、馬番 1..N) が rc 0 で全頭 `evaluation_summary.csv` に出る」テストを 1 本追加し、`cross_date_spec.py` に Y8 (`== "◎"` → `in ("◎","○")`) を加えて KILLED を確認する。本体コードの変更は不要
2. (小) stop テスト 3 本で `capsys` の stderr に文言と race_id が出ることを固定 (Y2 を落とす)
3. (小) モジュール docstring に終了コード (0 / 0 sealed / 2 入力不良) と manifest の `foreign_date_races_dropped` / `foreign_date_predictions_dropped` / `foreign_date_race_ids` を追記。`docs/EVALUATION_DATA_QUALITY.md:47` に `foreign_date_races_dropped` を追加。docstring `:352` の「79 本」は出典を書くか 67 に直す
4. (任意) anchor 契約の一元化: `web/generator.py:157` / `:563` と `bdr:353` の 3 リテラルを 1 モジュールへ。`analyze_misses.py:163` に「builder 側で除外済、二重防御として残す」の注記
5. (任意) `output_dir.mkdir` を検証成功後に移す (rc 2 で空 dir を残さない)
