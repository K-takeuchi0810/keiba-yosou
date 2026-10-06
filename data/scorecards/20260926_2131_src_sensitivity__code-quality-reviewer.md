# コード品質 / 保守性レビュアー 採点 — 3fea521 Phase 0.5-4B T−10 市場取得元の感度分析

**改修タイプ宣言**: type-B (分析スクリプト + 成果物 + 文書。予測・モデル・閾値は変更なし)。P25 固有ゲート (meta.env_overrides / market_snapshot / test_market_popularity_scoring / PRED_DISABLE_BLEND 等) は **N/A (対象外)**。
**運用条件**: subagent CWD 限定運用での評価 (CLAUDE.md 1-bis (b))。対象は worktree `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\src-sens`、HEAD = `3fea5218f34b65c833d2d6b824d78f35fd00c9cd` を開始時・終了時に確認、porcelain 空を確認。本番 DB への接続は行っていない (CSV / JSON / コードの読み取りと、合成入力による純関数の検査のみ)。

## 判定: HOLD

**理由**: 停止条件抵触なし。必須確認 6 件はすべて **成立** (自分で再導出)。結論を支える数値 (4B の完全再現 / 共通 626 レースで市場が完全一致) は CSV から独立に再計算して一致した。ただし (1) `build_market` が `predictor/pit_t10.t10_market` の組み立て・違反検査 ~25 行を **コピーで保持**しており、docstring の「t10_market と同じ規則」は構造でなく写しで担保されている (再実行時の静かな乖離経路)、(2) `same_state` が dead code、(3) `KEIBA_PROD_ROOT` で取り込んだモジュールが本当に ROOT 配下かを **検証も記録もしない**、(4) 「結果を見る前に固定した」読み方 (50% 閾値) が規則と結果を同じ 1 commit に入れたため **git から監査できない** (raw_0B30 = 300 は閾値 313 に近い)。いずれも小さな補完で閉じるが、本スクリプトは DB の取り込み漏れ修復後に再実行される前提 (docs 「残る留保」) なので、(1)(3) は今のうちに構造で閉じるべき。
**根拠ファイル**: `.claude/worktrees/src-sens/scripts/t10_source_sensitivity.py:101-115,126-137,167-195,249-256,340-342` / `predictor/pit_t10.py:178-247` / `scripts/market_offset_eval.py:105-184,195-291` / `data/backtest/src_sensitivity_20260926/manifest.json` / `data/backtest/20260919_phase05_4B_market_offset.json`
**次アクション**: 下記「主な改善提案」1〜3 を適用 (合計 ~40 行、成果物の再生成は不要。ただし 1 を適用したら `reproduction_of_4B.sets_equal` と `races_with_identical_t10_market == 626` が変わらないことを再実行で確認)。以後の分析スクリプトは「規則の commit → 実行 → 成果物の commit」の 2 段で pre-registration を git に残す。

## 総合: 3.9 / 5 (前回 code-quality 3.0 @ 4B foundation、+0.9)

## 項目別

- **DRY / 単一出典: 3.5/5** — 減点: (a) `t10_source_sensitivity.py:167-195 build_market` は `pit_t10.py:213-247` の写し (odds→implied→rank、受信時刻 / 発表時刻 / 発走時刻既知性の 3 違反検査、`T10Market` 生成)。`pit_t10` に検査を 1 つ足しても raw 系列には届かず、**黙って raw 系列だけ緩くなる**。(b) `classify` (`:106-115`) と `same_state` (`:101-103`) は同じ 3 条件の平行記述。(c) 単勝票数合計の位置 `rec[927:938]` (`:88`) は `jvlink_client/parser.py` の `O1Odds` に無い field を script 側で独自に切り出しており、根拠は `docs/LIVE_INGEST_DATA_INTEGRITY_AUDIT.md:121` (位置 928) にしかない。加点: 閾値・窓・鮮度・購入条件は `moe.DEFAULT_MAX_LEAD_MINUTES / BUY_EDGE_PT / N_BOOT_PRIMARY` を参照して再定義していない (`:201,212,223,290,295`)。共通集合の β₂ / CI も `moe.run` と同じ `conditional_logit(["z_t10","margin"])` + `coefficient_ci(..., 1, n_boot=N_BOOT_PRIMARY)` (`:289-290` ↔ `market_offset_eval.py:225-226`)。
- **dead code / 未使用シンボル: 4/5** — `same_state` は定義のみで呼び出し 0 (`inspect.getsource` で `same_state(` の出現 1 = 定義)。他の import / 定数は全部使用。未実装 env を前提にした記述なし (N/A)。
- **マジックナンバー / 設定外出し: 4/5** — `MIN_FRESH_SHARE = 0.5` (`:61`)、`FROM/TO` (`:58`)、`REF_4B` (`:62`) は命名され、manifest にも `fixed_reading_rules` として書き出される (`:351-353`)。留保: 共通集合の下限 `30` レース (`:283`) と一致判定の `1e-12` (`:298`) は根拠コメント無し (30 は「両方で鮮度内が 30 未満なら skip」と文言はあるが、なぜ 30 かは無い)。`927:938` は上記。
- **テスト容易性 / 変更失敗モード: 3.5/5** — 加点: 選択規則が `RawSelector._pick` / `classify` / `ratio_stats` / `conclusion_key` の純関数に分離され、DB 無しで検査できる (下記「合成入力による検査」で実施、全て仕様どおり)。`moe.t10_market` の差し替えは `try/finally` で復元 (`:265-269`)。減点: (i) `tests/` に 1 本も無い (ties の順序 / votes None / 決定時刻ちょうどの包含は再発防止価値が高い)。(ii) `moe.build_dataset` はキャッシュ版に差し替えたまま復元しない (`:256`)。キャッシュの共有は `collect` が `data` を破壊的に変えない (`d["margin"]` を同じ値で上書きするだけ、`market_offset_eval.py:116-117`) ことに暗黙に依存。(iii) **変更失敗モード**: `KEIBA_PROD_ROOT` 未設定なら `ROOT = HERE` = worktree になり、`db.DB_PATH` が worktree 側に解決する。manifest に `prod_root` は残るが、モジュールの実解決パス (`moe.__file__`) は記録も assert もされない。今回は両者が同一コード (491d2e6) なので無害だが、worktree が main から離れた後に再実行すると **静かに別コードで走る**。`scripts/` に `__init__.py` が無く namespace package なので、`python -m` 起点で CWD が sys.path に入ると合流の余地もある。
- **エラー処理 / 観測可能性: 4.5/5** — 加点: 出力先が空でなければ `SystemExit` (`:244-245`、既存 4A/4B JSON を上書きしない)。manifest に `prod_git_sha` / `db_snapshot.git_sha, git_dirty=false, data_version` / モデル 4 ファイルの sha256 / `raw_info` (mtime とファイル名 epoch の食い違い 78+18 本、名前不一致 1,980 本) / 選択監査カウンタ / `reproduction_of_4B` を残す。日本語を含む最終 print は **ファイル書き出しの後** (`:357-369` → `:370`) なので、4B foundation で指摘した cp932 クラッシュで成果物を失う順序にはなっていない。raw の parse 失敗は握り潰さず落ちる。減点: `script_git_sha` (`:340`) は「実行時の worktree HEAD」であり、その時点でスクリプトは未追跡 (`491d2e6` にこのファイルは無い)。ラベルが誤解を招く。sha256 は committed file と一致 (`50ee9d02…`、`git show 3fea521:scripts/t10_source_sensitivity.py | sha256sum` で確認) ので再現性は保たれているが、HERE 側の dirty / untracked 状態は記録されていない。

## 必須確認 (依頼 6 件、すべて自分で実測)

| # | 確認 | 結果 | 根拠 |
|---|---|---|---|
| 1 | original_mixed が 4B を完全再現 | **成立** | `samples_original_mixed.csv` (12,533 行) と `20260919_phase05_4B_samples.csv` を (race_id, horse_num) で突合、15 列すべて一致・不一致 0 行。sets {931/12,533, 626/8,279}、β₂ 0.4996637467589598、CI [−0.8279, +1.7259]、offset LogLoss 0.21348138623836102 が 4B JSON と同値。4B は data_version `35626:cce388ce8e`、今回は `44292:3527feed56` で DB が進んでいても評価窓の値は不変 |
| 2 | raw 系列が未来の raw を使わない | **成立** | `_pick` は `s["received"] <= cutoff` で絞る (`:128`)、`build_market` は `received_at > cutoff` を違反に積む (`:178-179`)、`collect` は `not m10.ok` を除外 (`market_offset_eval.py:142`)。合成入力: 決定時刻 +1 秒の記録は不採用、ちょうど決定時刻は採用 (規則「以前 = ≤」と一致)。matched 系列の受信時刻は `max(s30, s31)` (`:159`) で保守側 |
| 3 | 同じ秒の tie-break = 票数多い方 → 0B31 | **成立** | `top.sort(key=(votes or -1, source=="0B31"), reverse=True)` (`:136`)。合成入力 8 ケース: 100 vs 90 → 多い方 (どちらの取得元でも)、同数 → 0B31 (入力順を入れ替えても)、None vs 50 → 50、両 None → 0B31、後の秒は票数に関係なく勝つ。留保: `votes == 0` は `-1` に潰れ None と同格になるが実害なし。`top` 内の同一取得元・同票の並びは `iterdir` 順に依存 (実データでは同秒同取得元 2 枚は 0 バイトの重複名だけで発生しない) |
| 4 | 共通 626 レースの一致判定が値の比較か | **成立** | `:296-299` は (race_id, horse_num) → p_t10 の dict を両系列で作り、各馬 `abs(a-b) < 1e-12`、片側欠損は `-1` で不一致。集合でなく値。CSV から独立に再計算: raw_mixed 626/626、raw_0B31 594 中 403、raw_0B30 299 中 257 = 文書の表と一致。馬集合は両系列とも `runner_set_mismatch` を通過した同じ `data` 行に対して検査済なので片方向 `all` で十分 |
| 5 | 50% 閾値が宣言どおりに使われている | **成立 (使用は)** / **事前固定は監査不能** | `MIN_FRESH_SHARE = 0.5` は `:306` と manifest `:352` の 2 箇所だけで使われ、途中で書き換えなし。ただし規則と結果が同一 commit `3fea521` (21:28:47) に入り、manifest `created_at` 21:27:38 → 実行後 1 分で commit。「結果を見る前に書いた」は作者の記述以外に証拠が無い |
| 6 | 判定不能系列を「同じ結論」推論から除外 | **成立** | `:307-308` で `judgeable` が偽なら `same_conclusion_as_original_mixed = None`。`series_summary.json` で raw_0B30 / matched_same_state は `judgeable: false, same_conclusion: null`、raw_0B30 の `rejected_by: ["古いオッズにだけ勝っている"]` は結論に使われていない (文書 `:42-43` も同旨) |

## 停止条件チェック

- [x] 再現性メタ (type-B 汎用): `prod_git_sha` / `db_snapshot.git_sha, git_dirty` / `data_version` / `from_date, to_date` / モデル sha256 / `script_sha256` (committed file と一致) — あり。`meta.env_overrides` / `rule_version` は type-B N/A (env 依存は `KEIBA_PROD_ROOT` のみで `prod_root` として記録)
- [x] baseline paired 比較成立: 5 系列すべて同じ `moe.run(FROM, TO, run_index=0)`、同じ `build_dataset` キャッシュ、同じモデル、差し替えは `t10_market` のみ。`decision_time` は `collect` 内で直接呼ばれ全系列同一
- [x] market_snapshot counts: N/A (backtest ではない)。代替として `counts.no_t10 / t10_fresh / runner_set_mismatch` と選択監査カウンタあり
- [x] payout 欠損の扱い: N/A。`confirmed_win_payouts` は 4B と同じ経路で不変
- [x] 専門領域別 (未実装 env 前提 / weight=0 虚偽表示 / 発走後 snapshot fresh 扱い): N/A または不抵触 (raw の発走後は `received <= decision_time` で除外)
- [x] 読み取り専用: script 自身は DB を開かず、DB 接続は `market_offset_eval.py:123,205` / `fundamental_model.py:152,381` の `mode=ro` のみ。書き込みは `--out-dir` 配下のみ。`data/raw` は `stat` / `read_bytes` のみ

## 反証の試み

- 主張「原系列は 4B を完全再現」→ CSV 12,533 行 15 列の全突合で不一致 0 → **成立**
- 主張「4B の 626 レースでは同じ秒の上書きが T−10 市場を 1 レースも変えていない」→ raw_mixed との p_t10 を馬単位で再計算、626/626 一致 → **成立**
- 主張「raw の選択規則は t10_market と同じ」→ 1 点で **不成立 (辺縁)**: `t10_market` は `MAX(fetched_at)` を `win_odds > 0` を条件にせず取り、その枚に正の odds が無ければ `None` (`pit_t10.py:194-211`)。`_pick` は `s["odds"]` が空の記録を候補から外して **その前の枚に遡る** (`:128`)。全馬 odds 0 の枚が最新にある場合だけ挙動が違う (今回のデータで発生したかは未検証、影響は欠損 → 1 枚前の採用)。docstring の「同じ」を維持するなら `_pick` から `and s["odds"]` を外し `build_market` 側で空を欠損にする
- 主張「モジュールは main 491d2e6 のもの」→ `KEIBA_PROD_ROOT` を付けて import し `moe.__file__` / `pit_t10.__file__` / `ingest.__file__` がすべて `C:\Users\kizun\dev\keiba-yosou\` 配下に解決することを確認 → **成立** (ただしコード側に assert は無い)

## 合成入力による検査 (scratch で実行、worktree / main は無変更、porcelain 空を確認)

`_pick` 13 ケース (上表 #2, #3)、`classify` 5 ケース (matched / same_total_discordant / different_state / different_announced / one_source_missing)、`ratio_stats` 空入力 → `n=0, max=None`、`p_t10 == 0` を除外、`lead_min > 30` を除外、`conclusion_key` が (primary, money, ge_1_75==0, rejected_by tuple) の 4 組。すべて仕様どおり。

## 主な改善提案

1. **`t10_market` の組み立てを `pit_t10` 内で関数化し、script はそれを呼ぶ** — `pit_t10.py:213-247` を `assemble_market(conn, race, target, start_used, odds_by_horse: dict[str,int], received_at: str, observed_raw: str|None) -> T10Market` に切り出し、`t10_market` は DB 行を渡す薄い層にする。`t10_source_sensitivity.py:167-195 build_market` を削除して `assemble_market` を呼ぶ。効果: 違反検査を足したとき raw 系列にも自動で届く (静かな乖離の解消)。適用後は `reproduction_of_4B.sets_equal == true` と `races_with_identical_t10_market == 626` の不変を再実行で確認する。
2. **import 解決パスを assert + manifest に記録** — `:55` の直後に `for mod in (moe, pit_t10): assert Path(mod.__file__).resolve().is_relative_to(ROOT), mod.__file__` を置き、manifest に `"module_paths": {...}` を足す。`script_git_sha` は `worktree_head_at_run` に改名し、`git -C HERE status --porcelain` の空/非空も併記する。
3. **dead code と単一出典の小修正** — `same_state` (`:101-103`) を削除 (または `classify` の最終分岐で使う)。単勝票数合計は `jvlink_client/parser.py O1Odds` に `win_vote_total: int` (位置 928, 11 桁) を追加して `parse_o1` で読み、script の `rec[927:938]` を消す (fetch/backfill 側も将来同じ値を参照できる)。`30` (`:283`) に根拠コメント。

## 参考所見 (スコープ外、採点に含めない)

- `datetime.fromtimestamp(epoch)` (`:92`) は naive ローカル時刻。`backfill_odds_snapshots.py:36` と同じ由来なので今回の比較は整合するが、JST 統一 (凍結中 `89a3840`) の対象になりうる。
- `summarise` の日付キー分岐 (`:211`、`"-"` の有無で 7 桁 / 6 桁) は `data` の date 形式を 2 通り想定している。実データは 8 桁のみ。

## 前回からの差分

- 前回 (20260919_1100 4B foundation、code-quality): 3.0 / HOLD。今回 3.9 / HOLD。
- 改善: 成果物の書き出しが print より先 (cp932 クラッシュで成果物を失う順序の再発なし)、閾値は上流定数を参照、純関数分離で DB 無し検査が可能、4B 再現を機械的に照合する `reproduction_of_4B` を manifest に内蔵。
- 残課題の同型: 前回「レース 6 列 JOIN 4 重」と同じく、本番規則の写しを分析スクリプトが持つパターン (`build_market`)。
