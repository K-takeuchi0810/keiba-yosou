# データパイプライン技術者 採点 — cross-date 混入修正 (`cross-date-fix-20260926` @ `c3be0e9`)

## 判定: PASS

**理由**: 停止条件抵触なし。修正の本体 (レース ID から日付を読み、対象日以外を評価から外して manifest に件数と ID を残し、◎ 2 頭 / 馬番重複 / 読めない ID なら何も書かずに exit 2) は、本物の HTML 10 日ぶん + 本番 DB の行を写した scratch DB に対する end-to-end 実行で **自分で再現** した。7/18 は 499 → 468 行 (差 = 台帳の 31 行そのもの、◎ 2 頭レース 2 → 0)、8/22 は 26 行落ち、非開催日 3 日は予想行 0 で foreign 全件計上。全出力行の race_id 日付 == 対象日、HTML 対象日レース集合 == DB レース集合 (36/36, 24/24)。留保は 2 つ: (1) `--db` は `sqlite3.connect(args.db)` の **読み書きハンドル** で開く (SELECT のみ・WAL なので実害は無いが `open_db_readonly` が db.py にありながら使っていない、改修前からの既存)。(2) 非開催日の「対象日の予想が 0」は manifest から導出できるが明示の状態語も終了コードの区別も無い。どちらも本改修が入れた欠陥ではなく、再生成計画を止める理由にもならない。
**根拠ファイル**: `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\cross-date\scripts\build_daily_results.py:352-401,596-613,616,991-998`、`tests\test_cross_date.py`、`tests\mutation_specs\cross_date_spec.py`、`C:\Users\kizun\dev\keiba-yosou\data\cross_date_mutation_20260928\run1_result.txt`、`C:\Users\kizun\dev\keiba-yosou\docs\EVALUATION_DATA_QUALITY.md:19-33,47-58`、自作検証 `C:\Users\kizun\AppData\Local\Temp\claude\C--Users-kizun-dev-keiba-yosou\ba1406e5-db88-4baa-8fae-bdcf86bee826\scratchpad\cross_dpe\verify_classify.py` / `e2e_scratch.py` (出力は同ディレクトリ `out\<date>\`)
**次アクション**: (1) 再生成の前に `main():616` を `open_db_readonly` (or `file:...?mode=ro` + `uri=True`) に置換 (2 行)。ai-builder は開催日に 1 分ごと本番 DB へ書くので、置換しないなら **非開催日にだけ** 流す。(2) 再生成は scratch → 差分確認 → `--output-dir data/results/<d>` で再実行 (この順でないと `supersedes_manifest_sha256` が None のままコピーされる)。(3) 非開催日 3 日は `--html data/results/<d>/archive/index_*.html` を明示 (既定探索は `predictions_source_*` のみで exit 2)。6/17 は archive が 2 本あり旧 manifest は `082325` を使っている — 同じ 1 本を固定。(4) 台帳に「非開催日は予想行 0 の空 CSV になる。6/17 は DB 由来 (final_odds / race_results) に地方交流 7 レース 75 行が残る」を書く。

## 対象・改修タイプ

- 対象: worktree `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\cross-date`、HEAD `c3be0e9c718d960a701c6d980a05aa60d4888c47` (開始時・終了時ともに確認、porcelain 空)。`git -C <wt> diff 4bc16e9 c3be0e9`: `scripts/build_daily_results.py` (+97/−12)、`tests/test_cross_date.py` (+175)、`tests/mutation_specs/cross_date_spec.py` (+67)、`tests/test_build_daily_results.py` (+47)。
- **subagent CWD 限定運用での評価** (main checkout `4bc16e9` には未反映。すべて `git -C` + 絶対パス)。
- 改修タイプ: **type-B (診断/検証ツール。取得・ingest・DB schema・予測ロジックは不変)**。P25 固有ゲート (fresh odds スケジューラ / coverage JSONL / market_snapshot / bonus_candidate) は **N/A (対象外)**。fresh odds を総合判定のゲートにしない。汎用採点: 出力の正当性、DB 読み取りの副作用なさ、スキーマ列の実在、artifact の再現性メタ、再生成の安全性。
- 採点軸は本改修に合わせ「評価出力のデータ正当性 / 再生成・冪等性 / DB アクセスの副作用 / 対象日 0 件 (非開催日) の振る舞い / テスト・変異・外部依存」の 5 つに置き換えた。
- スコープ外: 予想 HTML の生成側 (日次分割 `d38a566` 以降は翌日レースが入らないはずだが本 scorecard では確認していない)、`analyze_misses` 等の下流消費側。「1019 passed / 12 skipped」は再実行せず、関連 48 件のみ自分で再実行。

## 総合: 4.0 / 5 (参考スコア)

## 項目別

- **評価出力のデータ正当性 (行集合 / DB 結合 / manifest counts): 4/5** — ベストプラクティス「結合キーは自然キー全体 (日付・場・R・馬番) を持ち、キー契約を満たさない入力は fail-closed、落とした入力は件数と ID で計上」を満たす。**独立検証**: 保存済み HTML 全 79 本の anchor 2,664 件すべてが `RACE_ANCHOR_RE` に一致 (読めない ID の停止経路が過去データで誤発火しないことを確認)。10 日ぶんを `parse_predictions_html → split_races_by_date → check_prediction_invariants` に通し、対象日レース集合と本番 DB (`mode=ro`) の `races` 集合を比較: 7 開催日すべて HTML 対象日 = DB (36/36 ×6、24/24)、HTML にあって DB に無いレース 0、対象日の不変条件はすべて ok。foreign は全件が翌日 (7/18→7/19 等) で、**36 件中 36 件が対象日の同じ場・同じ R と衝突** = 旧コードが結合していた経路そのもの。scratch DB での e2e: 7/18 `predictions=468 / foreign_date_predictions_dropped=31 / html_horses_parsed=499` (499−31=468 の恒等式成立、旧 CSV 499 行との差集合 = 31 行、new-only 0)、8/22 `477 / 26 / 503`。5 CSV すべて `race_id` 先頭 8 桁 == 対象日 (違反 0)。留保: (a) `race_id_of()` (`:660-661`) は依然 `date` を無条件に刻む。守っているのは上流の `split_races_by_date` だけで、これを迂回する将来のリファクタで同じ欠陥が戻る (変異 X4 がこの経路を殺しているのは良い)。(b) `html_horses_parsed` の意味が「対象日のみ」→「HTML 全体」に変わった。新旧 manifest を並べる消費側は `predictions` で比べる必要がある (`schema` 版数は 3 のまま)。
- **再生成・冪等性 (tracked 成果物の上書き / superseded hash): 4/5** — 同じ入力で行集合は決定的 (manifest の `generated_at` のみ変わる)。既存 manifest があれば `supersedes_manifest_sha256` に旧 hash を刻む (`:575-578`)、`data/results` は git 追跡なので旧内容は履歴から復元可能。前提が崩れたときは **CSV も manifest も書かない** (`:601-606`、`_no_outputs` テストで確認)。留保: (a) 5 CSV → manifest の順に in-place 書き込みで tmp+rename ではない。途中で死ぬと旧 manifest の `csv_sha256` が新 CSV と一致しなくなる (検知は可能、自動復旧はしない、既存)。(b) scratch に生成してからコピーすると `supersedes_manifest_sha256` が None になる (e2e で実測 None)。本番ディレクトリへの再実行が必要 (次アクション 2)。(c) 非開催日 3 日は既定の HTML 探索が `predictions_source_*.html` 限定で `archive/index_*.html` を見ない → 明示指定が要る (安全側ではある)。
- **DB アクセスの副作用: 3/5** — `main():616` は `sqlite3.connect(args.db)` = 読み書きハンドル。実行する SQL は SELECT 3 本 + COUNT のみで `conn.close()` あり、本番は `journal_mode=wal` (ro で実測) なので reader が writer を塞ぐことはない。**それでも** `db.open_db_readonly` (2026-07-05、観察系ツール向け) が同じリポにありながら使っていない。20 GB の本番 DB に rw ハンドルを向ける道具を「読み取り専用」とは呼べず、プロは承認しない。本改修が入れた欠陥ではない (diff 外)。busy_timeout も無いので、ai-builder が書いている開催日の日中に走らせると稀に `database is locked` で落ちうる (落ちても書かないので害は無い)。スキーマ列の実在: SELECT に現れる全列で `CREATE TABLE ... AS SELECT` が本番 (ro ATTACH) に対して成功 = 列はすべて存在。
- **対象日 0 件 (非開催日) の振る舞い: 4/5** — 6/12 (金): HTML 168 レース全部が 5/30・5/31・6/06・6/07・6/13・6/14 の foreign → **rc=0**、5 CSV はヘッダのみ、manifest `predictions=0 / foreign_date_races_dropped=168 / foreign_date_predictions_dropped=1416 / foreign_date_race_ids=list[168]`。6/17 (水): HTML 36 レース全部 6/14 → rc=0、`predictions=0` だが DB 由来の `final_odds=75 / race_results=75` (地方交流 7 レース: track 30/45/48/50、data_div 'A')。7/03 も同形 (72 レース、479 頭)。**「NO_TARGET_DATE_PREDICTIONS」は新しい仕様なしで manifest から一意に導ける**: `predictions == 0 and html_races_parsed > 0 and foreign_date_races_dropped == html_races_parsed`。行の誤帰属は起きないので安全側。留保: 終了コードは通常日と同じ 0、明示の状態語は無いので、台帳 (`EVALUATION_DATA_QUALITY.md`) 側に導出式を書いておかないと「空 CSV = 生成失敗」と読み違える。
- **テスト・変異・外部依存: 5/5** — ベストプラクティス「本物の `main()` を通し出力を読むテスト + 変異で網の粗さを機械的に測る + 由来 (provenance) は fail-closed」を満たす。`tests/test_cross_date.py` 14 + `test_build_daily_results.py` 34 = **48 passed** (自分で再実行、`-p no:cacheprovider`)。変異 8 種 (`X1`〜`X8`: 日付無視 / 比較常真 / drop 件数 0 / 結合復活 / ◎ 2 頭許容 / 馬番重複許容 / 読めない ID 続行 / ID 一覧空) は **8/8 KILLED**、各変異を落としたテストが spec の「落ちるべきテスト」と一致 (`run1_result.txt`)。テストの衛生: `_run_main` が `git_provenance` を `FAKE_GIT_SHA` に固定し (隔離コピーで流せるようにした理由が書いてある)、本物の git は `test_git_provenance_matches_the_checkout_head` (`.git` 無しは skip) と fail-closed テスト (`CalledProcessError` を握らない) で別契約として担保。e2e の manifest `builder_git_sha` は `c3be0e9…` / `dirty=False` と実測一致。**ai_builder_impact: none** — `C:\Users\kizun\dev\ai-builder` を grep: import は `db.open_db` / `db.open_db_readonly` / `jvlink_client.*` / `scripts.backtest` のみで `build_daily_results` への参照は 0 件、`docs/EXTERNAL_DEPENDENTS.md` にも載っていない。本 diff はそれらのファイルに触れていない。

## 停止条件チェック (該当の有無を全項目明記)

- [x] P25 固有 (fresh odds スケジューラ / coverage JSONL / market_snapshot / bonus_candidate): **N/A (type-B)**
- [x] artifact の再現性メタ: manifest に `builder_git_sha` / `builder_git_dirty` / `source_html_sha256` / `supersedes_manifest_sha256` / `csv_sha256` — あり (実測)
- [x] DB への書き込み経路: **なし** (SELECT のみ。ただし rw ハンドル → 項目 3 の留保)
- [x] partial row を残す経路: 前提違反時は何も書かない。CSV 書き出し中のクラッシュは既存の非 atomic 書き込み (検知可能・自動修復なし)。**新規の悪化なし**
- [x] スキーマ列の実在: 全列を本番 (ro) で確認
- [x] 別系統データの混入: 旧コードの混入経路 (翌日レースの同場同 R 結合) を独立に再現し、新コードで 0 件を確認
- [x] テスト: 48 passed (自分で再実行)、変異 8/8 KILLED (result ファイル確認、再実行はしていない)

## 反証の試み

本番 DB は `mode=ro` のみ。builder は scratch DB (本番から ro ATTACH で 4 日ぶんを写した `scratch_keiba.db`: horse_races 1,020 / payouts 72 / races 79 行) にだけ向けた。main checkout の `data/results` は不変 (porcelain 空)。

| # | 反証シナリオ | 結果 |
|---|---|---|
| E1 | 保存済み HTML に `RACE_ANCHOR_RE` に合わない anchor があり、再生成が fail-closed で全部止まる | 79 本 2,664 anchor すべて一致。**不成立** |
| E2 | 対象日レースの中に ◎ 2 頭 / 馬番重複があり (予想側の正当な出力で) 止まる | 10 日すべて invariants ok。**不成立** |
| E3 | HTML の対象日レースに DB 側で対応が無い (結合漏れ) | 7 開催日すべて 0 件。**不成立** |
| E4 | 新コードでも別日の行が対象日 race_id で出る | 5 CSV × 4 日で違反 0。7/18 旧 CSV との差集合はちょうど 31 行 (台帳値と一致)、new-only 0。**不成立** |
| E5 | 非開催日で builder が失敗 (rc≠0) または foreign を黙って捨てる | rc=0、`foreign_date_*` に全件 (168/1,416、36/485)。**不成立** |
| E6 | `html_horses_parsed − foreign_date_predictions_dropped ≠ predictions` (計上漏れ) | 4 日とも等式成立 (499−31=468、503−26=477、1416−1416=0、485−485=0) |
| E7 | builder が `--db` を書き込みで開く | **成立 (rw ハンドル)**。ただし SQL は SELECT のみ、WAL。本番には向けていない |
| E8 | `git_provenance` を偽装したテストのせいで本物の由来が壊れても気付けない | 専用テスト 2 本 + e2e manifest の実 SHA 一致で担保。**不成立** |
| E9 | ai-builder が `build_daily_results` を import / 実行している | 参照 0 件。**不成立** (ai_builder_impact: none) |
| E10 | 既定の HTML 探索で非開催日を再生成できる | `predictions_source_*` が無く exit 2。**明示 `--html` が必要** (安全側の失敗) |
| E11 | builder を scheduler / bat / ps1 が自動起動していて exit 2 が無音になる | `scripts/` `deploy/` に呼び出し 0 件 = 手動起動のみ。exit 2 は操作者に届く |

## 再生成計画の実現性 (実行はしていない)

計画 (7 開催日 + 3 非開催日、scratch 先行、HTML → 日付分類 → DB 対象日集合 → 出力 CSV の独立検証) は **実現可能**。期待値 (本 scorecard の実測から):

| 日付 | HTML 対象日 / foreign レース | foreign 予想 (落ちる行) | 期待 predictions 行 | 備考 |
|---|---|---|---|---|
| 07/18 | 36 / 36 (07/19) | 31 | 468 (旧 499) | e2e 実測。◎ 2 頭レース 2 → 0 |
| 08/08 | 36 / 36 (08/09) | 30 | 旧 − 30 | 分類のみ実測 |
| 08/15 | 36 / 36 (08/16) | 32 | 旧 − 32 | HTML 候補 4 本、既定は辞書順最後 `090147` |
| 08/22 | 36 / 36 (08/23) | 26 | 477 | e2e 実測 (NOT_GENERATED → 初回生成、supersedes None が正) |
| 08/29 | 36 / 36 (08/30) | 20 | 分類のみ | |
| 09/05 | 36 / 36 (09/06) | 27 | 分類のみ | |
| 09/12 | 24 / 24 (09/13) | 28 | 分類のみ | |
| 06/12 | 0 / 168 (5/30〜6/14 の 6 日) | 1,416 | 0 | e2e 実測。DB 由来も 0 |
| 06/17 | 0 / 36 (06/14) | 485 | 0 | e2e 実測。**final_odds / race_results に地方 75 行** |
| 07/03 | 0 / 72 (07/04, 07/05) | 479 | 0 | 分類のみ |

条件: (a) 本番 DB へ向ける前に `open_db_readonly` 化、または非開催日に限定 (ai-builder が書かない日)。(b) INVALID 6 日は旧 manifest の `source_html` と同じファイルを `--html` で固定して差分を台帳に書く。(c) 検証の不変条件 2 つ (「出力行の race_date == 対象日」「HTML 対象日レース = 処理済 + 正当な除外」) は `verify_classify.py` / `e2e_scratch.py` の検査で機械化済み (scratchpad)。

## 主な改善提案 (優先順)

1. **`main():616` を読み取り専用に** — `from db import open_db_readonly` を使う (2 行)。本改修の範囲外だが、再生成計画で 20 GB の本番 DB に向ける直前なので今やる価値が最も高い。
2. **非開催日の状態語** — manifest `counts` に `target_date_predictions_present: bool` を 1 つ足すか、台帳に導出式 (`predictions == 0 and foreign_date_races_dropped == html_races_parsed > 0`) を明記。終了コードは 0 のままでよい (失敗ではない)。
3. **`race_id_of` に日付を渡す** — `race_id_of(track, rn)` を `f"{r['race_date']}-..."` に変え、対象日以外が到達したら例外にする (第二の門)。変異 X4 が殺せている今のうちに入れておくと、将来 `split_races_by_date` を迂回する改修に対しても網が残る。
4. **`html_horses_parsed` の意味変更** — `warnings.schema` を 4 に上げるか、docstring に「HTML 全体 (対象日 + 別の日)」と書く (コードのコメントにはある、manifest 消費側には見えない)。

## 前回からの差分

- 前回 (`20260928_0234_jst_unify_final__data-pipeline-engineer.md`) は JST 統一の評価で領域が異なるため直接比較なし。同じ builder を評価した `20260923_0000_cancelled_races_final__*` 系 (中止レース) からは、評価対象の行集合を「日付キーで」守る門が 1 つ増えた形で、退行は見つからない。

## 終了時の状態 (2026-09-28 09:05)

- worktree HEAD は開始時と同じ `c3be0e9c718d960a701c6d980a05aa60d4888c47`。**ただし終了時の porcelain は空でない**: `tests/mutation_specs/cross_date_spec.py` (+6) と `tests/test_cross_date.py` (+19) が 09:02:34 に変更されている (変異 `Y8 ◎ の数え方に ○ を含める` と `test_a_realistically_marked_target_race_is_scored_in_full` の追加、追記のみ)。**本 agent の書き込みではない** (本 agent の書き込みは scratchpad と本 scorecard のみ)。並走している別のレビュー/親セッションの作業と見られる。本 scorecard の評価対象はコミット済みの `c3be0e9` であり、この未コミット追加は採点に含めていない。
- main checkout: `data/results` / `docs` / `scripts` / `tests` / `db.py` / `config.py` に変更なし。`data/scorecards/` に本 scorecard (untracked) のみ追加。
- 本番 DB への接続は `mode=ro` URI のみ (`verify_classify.py` の SELECT、`e2e_scratch.py` の ro ATTACH)。builder は scratch DB にだけ向けた。
