# コード品質 / 保守性レビュアー 採点 — cf3f657 Phase 0.5-4B T−10 市場取得元の感度分析 (v2 再レビュー)

**改修タイプ宣言**: type-B (分析スクリプト + テスト + 成果物 + 文書。予測・モデル・閾値・本番コードは変更なし)。P25 固有ゲートは **N/A (対象外)**。
**運用条件**: subagent CWD 限定運用での評価 (CLAUDE.md 1-bis (b))。worktree `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\src-sens`、HEAD = `cf3f657fd770b6a26980e074b397d4f0d4381a4a` を開始時・終了時に確認、porcelain 空。本番 DB は `mode=ro` の読み取り 5 クエリのみ (件数確認)。変異・合成入力の検査は `git archive cf3f657` の写し (scratch `review_cqr2`) で実施。前回 (3fea521、HOLD 3.9) からの **全項目再採点**。

## 判定: PASS

**理由**: 停止条件抵触なし。前回 HOLD の 4 点は、(1) 写し `build_market` の乖離 → **起動時に評価窓 1,176 レース全件で本番 `t10_market` と `dataclasses.asdict` 等価を検査し、不一致なら出力先を作る前に `SystemExit`** (manifest: checked 1176 / mismatched 0 / both_none 239) + 写しを意図的に壊すテストで停止を確認、(2) `same_state` 削除、(3) import 直後に 5 モジュールの実パスが ROOT 配下かを検査し manifest に記録 (`production_module_path` 5 件すべて main 配下、`production_module_git_head`=491d2e6、tracked 変更なし)、(4) 50% 閾値の事前固定を主張から外し 40/45/50/55% の感度表に格下げ、スクリプトを commit (`de89d32` 22:02:29) してから実行 (manifest `worktree_head_at_run`=de89d32、porcelain 空、`script_sha256` = de89d32 と cf3f657 の両方の committed file と一致 `6e13f098…`)。5 系列の要約は v1 と全項目同値、4B の再現は CSV 12,533 行で不一致 0 (自分で再導出)。残るのは軽微な留保のみ (下記)。
**根拠ファイル**: `.claude/worktrees/src-sens/scripts/t10_source_sensitivity.py:57-75,94-99,156-169,174-255,267-305,372-388,391-428,435-450,469-477` / `tests/test_t10_source_sensitivity.py` (15 件 PASS、0.34s) / `data/backtest/src_sensitivity_20260926_v2/{manifest,series_summary,coverage_threshold_sensitivity,common_fresh_set}.json` / `jvlink_client/ingest.py:139` / `db.py:977-990` / `predictor/eval_stats.py:41-66`
**次アクション**: 改善提案 1〜3 (いずれも成果物の再生成不要、次に本スクリプトを再実行する時にまとめて入れればよい)。マージ可。

## 総合: 4.4 / 5 (前回 3.9、+0.5)

## 項目別

- **DRY / 単一出典: 4/5** (前回 3.5) — 写しは残っている (`build_market` `:174-201` ↔ `pit_t10.py:213-247`、および `db_market` の SQL 2 本 `:211-223` ↔ `pit_t10.py:194-209`) が、**写しであることを明示し、実行ごとに本番との等価を全件で検査して不一致なら止める**設計に変わった。「構造で守る」の次善だが、fail-fast で静かな乖離は消えた。残る二重契約 1 件: CSV の `t10_announced` が original_mixed では ISO 分 (`2026-05-09T09:40`、`db_market:234` が `m.odds_observed_at` を返す) で、raw 系列では生の MMDDHHMM (`05090940`、`:302`)。同じ列名で 2 形式 (実測)。
- **dead code / 未使用シンボル: 4.5/5** (前回 4) — `same_state` 削除。`state["data_div"]` (`:137`) は保存されるだけで参照なし (監査の出力にも出ない)。他は使用。
- **マジックナンバー / 設定外出し: 4.5/5** (前回 4) — `WIN_VOTES_SLICE` に JV-Data4901 の出典、`BACKFILL_LAST_DAY=20260628` は DB の事実と一致 (ro 実測: `backfill_0B31` 最終日 20260628、ライブ `0B31` 初日 20260718)、`MIN_COMMON_RACES` に「統計的根拠ではない」と正直な注記、`COVERAGE_THRESHOLDS` 定数化。残: `1e-12` (`:421`) は無注記。
- **テスト容易性 / 変更失敗モード: 4.5/5** (前回 3.5) — `tests/test_t10_source_sensitivity.py` 15 件 (worktree で実行、全 PASS)。決定時刻ちょうど / +1 秒、遡らない、同秒 tie (入力順 2 通り・同数・None)、epoch キー、classify 4 分類、受信時刻の由来、鮮度境界、in-memory DB で 7 ケースの等価性、写しを壊すと `SystemExit`、閾値表。**変更失敗モード**: `pit_t10` に違反検査を足す → `build_market` に無い → 起動時の等価ゲートが **DB データでその検査が発火するレースがあれば** 止まる。留保: 本窓では `both_none (239) == counts.no_t10 (239)` なので **DB 側で違反により除外されたレースは 0**、すなわち本番データ上でゲートが違反分岐を通った実績は無く、違反分岐の等価性は fixture (`announced_late` / `after_only` / `start_change` / `mixed_second`) だけが担保している。fixture に「発表時刻を解釈できない」(`_parse_announced` → None) のケースは無い。
- **エラー処理 / 観測可能性: 4.5/5** (前回 4.5) — 等価ゲートは `out_dir.mkdir` の前 (`:475-477`) なので失敗時に空ディレクトリを残さない。manifest に等価件数・モジュール実パス・両 checkout の HEAD と porcelain・受信時刻の由来別件数・選択監査。`paired_delta_beta` は `block_boot` (SEED 固定、None を捨てる、収束 < 半数で NaN) を再利用。減点: (i) **0 件のカウンタはキーが無い** (`selection_differs_if_epoch_used`、`*_o1_without_positive_odds_treated_absent`)。文書は「= 0」「該当 0 件」と書くが、artifact だけでは「0」と「未計測」を区別できない。(ii) `paired_delta_beta.stat` の `except Exception: return None` (`:381-384`) は点推定にも使われ、失敗すると `delta_beta: null` が黙って書かれる。(iii) `block_boot` が NaN を返した場合 `json.dumps` は `NaN` を書き、厳密な JSON でなくなる (本 run では未発生)。

## 依頼された確認 (すべて自分で実測)

| # | 確認 | 結果 | 根拠 |
|---|---|---|---|
| 1 | 等価ゲート | **成立** | `production_equivalence` (`:237-255`) は `pit_t10.t10_market` と `db_market` を `asdict` で比較 (選んだ枚・received_at・observed_at・odds・implied・rank・violations 文言・None の扱い)。manifest: 1176 / 0 / 239。1,176 は ro 実測の races 件数と一致。`test_equivalence_gate_stops_when_the_copy_drifts` は violations を落とした写しで `SystemExit` を確認。留保は上記 (DB 上で違反分岐が通った実績 0) |
| 2 | odds 0 頭の O1 を「存在しない」扱い、遡らない | **成立** | `db.insert_odds_snapshot` は `o1.win_odds` (parse_o1 で odds>0 のみ) から行を作り、空なら何も書かない (`db.py:983-985`)。ro 実測: 窓内 `win_odds<=0 or NULL` の行 0。`pick` は `s["odds"]` で絞らず最新の枚を返す (`:161-169`)。`test_pick_does_not_step_back_past_the_latest_state` + fixture `partial_latest` で本番と同値 |
| 3 | モジュールパス検査 + manifest | **成立** | `:70-75` で 5 モジュールを `is_relative_to(ROOT)`。archive 写しから import して 5 件とも main 配下を確認。manifest `production_module_path` 5 件・`worktree_head_at_run`=de89d32・`worktree_porcelain_at_run`="" |
| 4 | patch の復元 | **成立** | `build_dataset` は `:484-492` の `try/finally`、`t10_market` は `run_series` の `try/finally` (`:446-449`) |
| 5 | 定数の整理 | **成立** | `same_state` なし、`WIN_VOTES_SLICE` (`:83-85`)、`MIN_COMMON_RACES` (`:86-88`) |
| 6 | 出自の列 | **成立 (形式に不揃い)** | 5 列追加。original_mixed の `t10_source` は `backfill_0B31 / 0B30 / 0B31` (6,053 / 3,473 / 3,007 頭)、raw_mixed は `(0B31, epoch_backfill) 6,053 / (0B31, mtime_live) 5,062 / (0B30, mtime_live) 3,138`。`t10_announced` の 2 形式は上記 |
| 7 | 受信時刻の由来 | **成立** | `raw_received` (`:94-99`): 0B31 かつ day <= 20260628 → epoch、それ以外 → mtime 秒未満切り捨て。`ingest.py:139` は `fromtimestamp(st_mtime).isoformat(timespec="seconds")` = 同じ切り捨て。`backfill_odds_snapshots.py:36` は epoch。境界日は DB 実測と一致。`selection_differs_if_epoch_used` は 3 系列ともキー無し (= 0)、同秒 tie 29 |
| 8 | 新出力 | **成立** | `coverage_threshold_sensitivity.json`: 40/45% で raw_0B30 は judged=True・same=False・differs_in=["rejected_by"]、50/55% で judged=False・same=None; matched は全閾値で judged=False。`common_fresh_set.json`: raw_mixed 626/626 一致 Δβ 0 [0,0]、raw_0B30 42 件違い (8 月) Δβ −0.0064 [−0.028, +0.015]、raw_0B31 191 件違い (8 月) Δβ −0.0489 [−0.079, −0.009] |
| 9 | テスト | **成立 / 失敗は環境要因と確認** | 新テスト 15 PASS。`test_f3_phase0_0_eval.py::test_saved_pair_reproduces_frozen_validation_auc` を worktree で単独実行 → `FileNotFoundError: ...\src-sens\data\f3_phase0_0\metrics.json`。main では同ファイルが存在するが `git ls-files --error-unmatch` → **未追跡**。本改修と無関係の既存テスト衛生の問題 (参考所見) |
| 補 | 4B 再現 / v1 との同値 | **成立** | v2 `samples_original_mixed.csv` 12,533 行 × 4B の 15 列で不一致 0。`series_summary.json` v1 (git show 3fea521) と v2 の 7 セクション (coverage / logloss / beta / rejection_1 / ratio / purchase / verdict) が 5 系列とも同値 |
| 補 | カウンタ論理 `(st or {}).get("file") != (alt or {}).get("file")` | **成立** | 合成: 同ファイル → 数えない、別ファイル → 数える、None vs 状態 → 数える (欠損と存在の入替も検出)、None vs None → 数えない。matched 系列は `alt = st` で恒等 (`:293`) なので常に 0 — 意図どおりだが、matched で「epoch なら別の状態が選ばれる」ケースは測っていないことは明記した方がよい |
| 補 | matched_same_state 経路 | **成立** | 合成 (in-memory conn + start_time_changes 空): 一致ペアで `received_at = max(s30, s31)`、`source="0B30=0B31"`、`ok=True`、audit `selected_0B30=0B31_mtime_live`。`different_state` ペア → None、audit にその分類のみ。raw_0B30 で 0B30 が無い → None、audit 空 |
| 補 | tie-break の `votes==0` | **成立 (前回の留保が解消)** | `s["votes"] if s["votes"] is not None else -1` (`:167`)。合成: 0 vs None → 0 の方が勝つ、0 vs 0 → 0B31 |

## 停止条件チェック

- [x] 再現性メタ (type-B 汎用): 両 checkout の HEAD / porcelain / モジュール実パス / script_sha256 (committed file と一致) / db data_version / モデル sha256 / 窓 — あり。`env_overrides`・`rule_version` は N/A (env 依存は `KEIBA_PROD_ROOT` のみで `production_root` として記録)
- [x] paired 比較成立: 5 系列同一 `moe.run(FROM, TO, 0)`、同一 dataset キャッシュ、差し替えは `t10_market` のみ。共通集合は同じレースを塊にした block bootstrap
- [x] market_snapshot counts / payout 欠損: N/A (backtest でない)。代替: `counts` + 等価件数 + 選択監査
- [x] 専門領域別停止条件 (未実装 env / weight=0 虚偽表示 / 発走後 snapshot fresh 扱い): 不抵触または N/A
- [x] 読み取り専用: script の DB 接続は `:469` の `mode=ro` 1 本 (等価ゲート) と `moe` / `fundamental_model` の `mode=ro`。書き込みは `--out-dir` のみ。v1 成果物は `cf3f657` で rename (R050〜R100) され tree から消えている (`git ls-tree cf3f657` に `src_sensitivity_20260926/` は 0 件、`3fea521` には 10 件)。4A/4B の JSON は無変更

## 反証の試み

- 「等価ゲートが写しの乖離を止める」→ テストの他に fixture の 7 ケースを読み、`t10_market` の違反分岐のうち「受信 > 決定」「発表 > 決定」「発走時刻が既知でない」は通るが、「発表時刻を解釈できない」は fixture に無い → **部分的に不成立** (本番データでも該当 0 なので、この分岐だけは写し側に検査があることをコードで確認した `:187-188`)
- 「50% を根拠にしない」→ `threshold_table` で 4 閾値を機械的に並べ、文書の表と JSON が一致。raw_0B30 が 40/45% で違うのは `rejected_by` のみで、主要仮説・金額・比は同じ → **成立**
- 「受信時刻を本番と同じ由来にしても選択は変わらない」→ `selection_differs_if_epoch_used` はキー無し (= 0)、要約が v1 と同値 → **成立** (ただし「キー無し = 0」の読み替えが要る)
- 「artifact の日本語が化けていない」→ `common_fresh_set.json` の `SEED 固定` はバイト列 `e5 9b ba e5 ae 9a` = 正しい UTF-8 (自分のコンソール出力だけが化けた) → **成立**

## 主な改善提案 (成果物の再生成は不要)

1. **0 件のカウンタを明示的に 0 で初期化する** — `RawSelector.__init__` で `self.audit[series]["selection_differs_if_epoch_used"] = 0`、`load_raw_states` で `info[f"{spec}_o1_without_positive_odds_treated_absent"] = 0` を先に置く。artifact 単体で「0」と「未計測」を区別できるようにする (`:130,295`)。
2. **`t10_announced` の形式を 1 つに** — `db_market:234` は `announced` に生の `announced_at` (rows の `r[2]`) を返し、raw 側と同じ MMDDHHMM に揃える (または両方 ISO)。列の契約を docstring に 1 行。
3. **等価 fixture に「解釈できない発表時刻」ケースを 1 つ追加** (`tests/test_t10_source_sensitivity.py:131` の case に `announced="99999999"`) — 写しの違反分岐すべてが fixture で本番と比較されるようにする。あわせて `paired_delta_beta.stat` の `except Exception` を `conditional_logit` が投げる型に絞るか、点推定が None なら manifest に理由を残す。

## 参考所見 (スコープ外)

- `tests/test_f3_phase0_0_eval.py::test_saved_pair_reproduces_frozen_validation_auc` は main の **未追跡** ファイル `data/f3_phase0_0/metrics.json` に依存しており、clean checkout / worktree では必ず落ちる。本改修とは無関係だが、main 側で追跡するか skip にするべき既存の欠陥。
- 文書 `docs/PHASE05_4B_SOURCE_SENSITIVITY.md:41` の「(±1 秒)」は manifest から再導出できない (件数しか無い)。主張を残すなら差の分布を `raw_info` に足す。
- raw_0B31 共通集合の Δβ₂ −0.049 [−0.079, −0.009] の解釈 (「小さいが有意」) は validation-process-auditor の領域。コード側は SEED 固定 block bootstrap で再現可能。

## 前回からの差分

- 判定 HOLD → **PASS**。総合 3.9 → 4.4。
- DRY 3.5 → 4: 写しは残るが全件等価ゲート + 乖離テストで fail-fast 化。
- dead code 4 → 4.5: `same_state` 削除 (`data_div` 未参照が残る)。
- 設定外出し 4 → 4.5: 定数に出典、境界日は DB 事実と一致。
- テスト容易性 3.5 → 4.5: 0 本 → 15 本、変異 (写しの検査落ち) で停止を確認。
- 観測可能性 4.5 → 4.5: 記録は充実したが「0 件 = キー無し」の読み替えが新たに必要。
