# 検証プロセス監査人 (最終ゲート) 採点 — Phase 0.5-4B T−10 市場の取得元に対する感度分析 (3fea521, branch t10-source-sensitivity-20260926)

**subagent CWD 限定運用での評価 (worktree 絶対パス指定)**: 対象 SHA `3fea5218f34b65c833d2d6b824d78f35fd00c9cd` (base main `491d2e6`)、worktree `C:/Users/kizun/dev/keiba-yosou/.claude/worktrees/src-sens`。git は全て `git -C <wt>`、Read/Grep は worktree 絶対パス。開始時・終了時の `rev-parse HEAD` = 3fea521 で不動、終了時 `status --porcelain` = 空。本番 DB は `mode=ro` URI のみ (当方の照会 3 本、評価スクリプト自体も `mode=ro`)。worktree・本番 checkout のファイルは未編集、変異実験は無し。再現実行は scratchpad `review_vpa/out` に `--out-dir` を向けて 1 回 (約 16 分、21:28〜21:44)。

## 判定: PASS (最終ゲート — 感度分析としての設計・PIT 規律・再現性は成立。留保 4 件は結論を覆さないが次回までに文書へ反映すること)

**改修タイプ**: type-B (診断/検証スクリプト + 成果物 + 文書。predictor / weights / calibrator / BUY_FILTER / GUI 非接触、4B の JSON も未上書き)。P25 固有ゲート (factorial C1-C5 / market_snapshot / fresh odds / bonus_candidate / P25 PLAN) は **N/A (対象外)**。

**PASS の根拠 (すべて一次データで裏取り)**:
- 6 件の必須確認は **5 件成立・1 件は部分成立 (証拠の限界を明記)**。下表参照
- 成果物は **第三者 (当方) が同じスクリプトで再生成して byte 単位で一致** (`series_summary` / `series_full` (data_version 含む) / `common_fresh_set` / `selection_classes` / 5 本の `samples_*.csv` すべて IDENTICAL。manifest の差は `created_at` と `script_git_sha` (実行時 HEAD 491d2e6 → 当方は 3fea521) だけ)。`script_sha256` は committed ファイルと一致
- 文書の数値は JSON と全件一致。結論文は「判定可能な 3 系列で 4 項目一致」「raw_0B30 / matched_same_state は判定不能で否定にも肯定にも使わない」に留まり、4B の再判定 (合否の書き換え・閾値変更・モデル差し替え) は無い

**留保 (PASS を覆さないが記録)**:
1. **50% 閾値の事前固定は単一コミットの内側でしか確認できない**。系列 5 本・`fetched_at <= cutoff` 絶対条件・受信時刻の由来を manifest に残す・一致の 3 分類は main `491d2e6` の `docs/LIVE_INGEST_DATA_INTEGRITY_AUDIT.md:174-181` に **事前登録済み** (成立)。一方「判定可能 = 50%」「結論が同じ = 4 項目一致」「同じ秒は票数合計の多い方」は本コミット (21:28:47) にしか無く、manifest `created_at` 21:27:38 の **1 分後** に一括コミットされているため、結果より前に書かれた証拠は docstring の自己申告のみ。しかも raw_0B30 は 300 / 313 (47.9%) で **閾値のすぐ下** にあり、閾値が 45% なら判定可能となって棄却条件 2 (古いオッズにだけ勝っている) により「結論が違う」に転じる (ただし方向は仮説にとってさらに否定的で、ΔLogLoss は +0.00002 と無意味な大きさ)。文書は raw_0B30 の棄却条件 2 該当を隠さず開示している (`docs/PHASE05_4B_SOURCE_SENSITIVITY.md:42-43`) ので誤導ではないが、「閾値は結果を見る前に固定」は **検証不能な主張** として書き分けるべき
2. **実質的な「取得元の入替」の証拠は 8 月の 191 レースに限られる**。raw_mixed は 626 共通レースで original と **完全同一** (当方 CSV 再計算: 差 0 レース)、つまり raw_mixed の「同じ結論」は取得元感度ではなく 7 月の 131 レース追加 (集合差) に対する頑健性。取得元が実際に入れ替わったのは raw_0B31 の 594 共通レース中 191 (594−403、すべて 8 月) と raw_0B30 の 42。文書は「取得元ではなく集合の違い」と正しく書くが、**191 という数は明示していない**。「判定できた取得元の構成に対しては頑健」は、この範囲を添えれば正確
3. **Δβ の統計的枝葉**: 文書は「共通集合で Δβ ≤ 0.05、区間の幅 (約 2.5) より十分小さい」と marginal CI の幅と比べているが、正しい比較は **paired** 区間。当方が 594 共通レースで race 単位ブロック再抽出 (n_boot=300、seed 固定) した Δβ(raw_0B31 − original) = **−0.049 [−0.078, −0.013]** — 0 を含まない小さな負の効果で、β₂ ≈ +0.5 ± 1.3 の合否を動かす大きさではない (結論の方向は支持)。raw_0B30 は −0.006 [−0.027, +0.012]。点推定は決定的 (MLE) なので MC 雑音の問題は無く、区間端点の ±0.1 級 MC 誤差 (PHASE05_RESULTS.md:864-865 に自認) も Δβ 点推定の比較には影響しない
4. **多重観察の会計**: `config.CONSUMED_WINDOWS` は strategy_dev 窓 (05-09〜08-31) の再読を「見るたびに記録する」台帳だが、本改修は同窓を 4 回追加で読みつつ台帳を更新していない (config.py は diff に無い)。採用判断を伴わない感度分析なので実害は無いが、台帳の趣旨 (レビュー 2 回指摘) に照らして 1 行足すべき

## 必須確認 6 件 — 成立表 (自分で実行)

| # | 確認 | 判定 | 一次証拠 |
|---|---|---|---|
| 1 | original_mixed が 4B を完全再現 (集合・β₂・LogLoss) | **成立** | 4B JSON: sets all 931/12,533・fresh 626/8,279、β₂ 0.4996637467589598 [−0.8279, +1.7259]、offset LogLoss 0.21348138623836102 → original_mixed で **全桁一致** (manifest `reproduction_of_4B.sets_equal=true`)。CI まで一致するのは `predictor/eval_stats.py` の `SEED=20260918` 固定のため (run_index 2→0 の差は影響しない)。補足: 4B 成果物は `git_dirty=True` で `market_offset_model.txt` が dirty_paths に居たが、clean な 491d2e6 で同値 → committed モデル (sha256 fd84304d…) が 4B の実体と一致することも同時に確認できた |
| 2 | raw 系列が未来の raw を使わない + 受信時刻の由来を manifest に記録 | **成立** | `t10_source_sensitivity.py:127-128` で received <= cutoff (cutoff = `pit_t10.decision_time`、発走変更の既知性込み) + `build_market:177-187` で本番 `t10_market` と同じ 3 違反検査 (受信・発表時刻・既知発走)。5 系列の `samples_*.csv` で **min lead_min = 10.05〜10.45、lead<10 は 0 行** (= 受信 ≤ 発走−10 分が全行成立)。manifest `raw_received_at_origin` = ファイル名 epoch、`raw_info` に mtime 不一致 0B30 78 / 0B31 18 本。当方でその差を実測: **全件 ±1 秒** (PIT 境界に無関係)。二重名 1,980 本は当方実測でも **全て 0 バイト** (文書 :25 の主張どおり) |
| 3 | raw_mixed の同じ秒の衝突処理が宣言 (票数合計の多い方 → 0B31) と一致し件数を記録 | **成立** | `:136` の sort key = (票数, source==0B31) 降順 = 票数の多い方、同数なら 0B31。manifest `selection_audit_counts.raw_mixed.same_second_both_sources = 28`、`raw_mixed_tie_rule` に文言記録。文書 :24「28 レース」一致。なお 626 共通レースで raw_mixed = original 完全同一なので、DB の上書きは評価集合の T−10 選択を 1 レースも変えていない (当方 CSV で再確認) |
| 4 | 共通 626 レース比較が「値の差」と「集合の差」を分離 | **成立** | `common_fresh_set.json`: raw_mixed 626/626 同一 (β₂ +0.4997 → +0.4997、全指標同値)。raw_0B31 594 共通中 403 同一・191 相違 (当方 CSV 再計算で一致、相違はすべて 8 月)、β₂ +0.537 → +0.488。raw_0B30 299 中 257 同一。→ 全系列の β₂ +0.72 への上昇は 7 月 131 レース (7/04・05・11・12、DB `odds_snapshots` 0 行 = 当方 RO 照会で races 144 / snapshots 0 を確認) の追加による集合差、と読める |
| 5 | 50% 閾値が結果を見た後に変更されていない | **部分成立 (検証不能な部分を明記)** | 系列・PIT 条件・manifest 記録・一致分類は main `491d2e6` の監査文書に事前登録 (成立)。50% / 4 項目 / 同秒規則は単一コミット内のみ、manifest 生成の 1 分後にコミット。**git 履歴からは「結果より前に書いた」を裏付けられない**。境界近接 (300 vs 313) の決定関連性は上記留保 1 |
| 6 | 判定不能系列 (raw_0B30 / matched_same_state) が結論の根拠に使われていない | **成立** | 文書 :79-85 の結論は判定可能 3 系列のみ。:82-83「否定にも肯定にも使わない / matched_same_state で差が消えるか残るかは判定できない」、:42-43 で raw_0B30 の棄却条件 2 該当を開示しつつ不使用。`series_summary.json` で両系列 `judgeable=false`、`same_conclusion_as_original_mixed=null` |

補助確認: 文書の表 (:33-39、:48-52、:67-73) の全数値を `series_summary.json` / `common_fresh_set.json` / `selection_classes.json` と照合し **不一致 0**。8 月 0B31 の DB 側「697」は当方 RO 照会 (distinct race×fetched_at) で 697 を確認。評価スクリプト・特徴構築は `mode=ro` (`market_offset_eval.py:123,205`, `fundamental_model.py:152`)、成果物以外への書き込み経路は無し。

## 総合: 4.3 / 5

| 項目 | 点 | 所見 |
|---|---|---|
| 1. 検証 (感度分析) 設計の正しさ | 4.5 | 5 系列 + 監査専用 2 分類 + 共通集合での分離、判定不能の扱いが正しい。減点: 実効的な入替証拠の範囲 (191 レース・8 月のみ) が文書に無い、「≥1.75 が 0 頭」判定は max 1.738 / 1.743 と紙一重で 4 項目一致ルールが粗い (数値は開示されているので誤読は防げる) |
| 2. 時系列リーク防止 (リーク分類学) | 5 | ベストプラクティス = 「選択時に PIT cutoff を強制し、組み立て後に独立した違反検査で再監査、決定時刻は発走変更の既知性で解く」。本実装は `_pick` で強制 + `build_market` で本番同一の 3 検査 + `pit_t10.decision_time` を共用し、全 5 系列で lead ≥ 10.05 分を当方が実測。受信時刻由来 (epoch) と mtime の差 ±1 秒も実測 |
| 3. calibration / reliability 計測 | 4 | 4B と同じ `moe.run` を経由するので LogLoss・帯別較正・比分布は系列ごとに同じ規則で出る。P25 の Brier/監視項目は N/A。減点: 文書は LogLoss と比だけを表にし、帯別較正は `series_full.json` に埋まったまま (判定に不要なので軽微) |
| 4. A/B・再現性・バージョン管理 | 4.5 | 成果物が byte 一致で再生成可能、モデル 4 ファイルの sha256・DB `data_version`・script sha256・両 git sha・PIT 規則・同秒規則・読み方を manifest に記録、4B JSON 未上書き。減点: `CONSUMED_WINDOWS` 未更新 (留保 4)、`script_git_sha` が実行時 HEAD (491d2e6) で成果物を生んだスクリプト自身のコミットを指さない (sha256 で補えるが、次回は commit 後に再実行するか manifest に明記) |
| 5. 過適合監視 / 事前固定 / 統合判定 | 3.5 | 50% 閾値・4 項目ルールの事前固定が単一コミット内の自己申告に留まり、境界近接 (47.9%) で決定関連 (留保 1)。Δβ の比較が marginal 幅対比 (留保 3)。採用判断ではないので監視義務は N/A。他 agent 判定の統合は末尾 |

## 根拠ファイル

- worktree: `scripts/t10_source_sensitivity.py` (:58-62 定数, :126-137 選択/同秒, :167-195 build_market, :274-300 共通集合, :302-308 判定規則, :323-356 manifest)
- worktree: `docs/PHASE05_4B_SOURCE_SENSITIVITY.md` (:21-29 事前固定, :33-39 表, :46-57 共通集合, :77-85 結論)
- worktree: `data/backtest/src_sensitivity_20260926/{manifest,series_summary,series_full,common_fresh_set,selection_classes}.json`, `samples_*.csv`
- worktree: `data/backtest/20260919_phase05_4B_market_offset.json` (4B 正本)、`predictor/pit_t10.py` (:132-150 decision_time, :178-247 t10_market)、`scripts/market_offset_eval.py` (:105-184 collect, :195-291 run)、`predictor/eval_stats.py` (:27 SEED, :42-60 block_boot)
- main `491d2e6`: `docs/LIVE_INGEST_DATA_INTEGRITY_AUDIT.md:167-181` (事前登録)、`config.py:141-160` (CONSUMED_WINDOWS)
- 当方 scratchpad `review_vpa/`: `out/` (再現成果物一式)、`repro_stdout.txt` (EXIT=0)、`paired_delta.py` (paired Δβ 区間)

## 次アクション

1. (文書、必須) `PHASE05_4B_SOURCE_SENSITIVITY.md` の「事前に固定した読み方」に、**事前登録の出典を分ける**: 系列・PIT 条件・一致分類 = main 491d2e6 監査文書に登録済み / 50%・4 項目・同秒規則 = 本コミット内で結果と同時に記録 (git 履歴では前後を証明できない)。あわせて raw_0B30 が 47.9% で閾値直下にあり、45% なら棄却条件 2 で「結論が違う」に転じる (方向は否定側) ことを 1 文
2. (文書、必須) 実効的な取得元入替の範囲を明記: raw_mixed は 626 共通レースで完全同一 (集合差のみ)、入替が起きたのは raw_0B31 191 レース + raw_0B30 42 レース (いずれも 8 月)。paired Δβ = −0.049 [−0.078, −0.013] (当方計測、`paired_delta.py`) を採るなら「区間の幅より小さい」を paired 区間の表現に置き換える
3. (config、軽微) `CONSUMED_WINDOWS` に strategy_dev 窓の再読 (t10_source_sensitivity、4 系列、採用判断なし、2026-09-26) を 1 行追加。台帳更新が JST 凍結 (`config.py` 接触) に抵触するなら JST マージ後に実施し、文書に持ち越しを記す
4. (運用) 7 月前半 (7/04・05・11・12) の `odds_snapshots` 欠落と同じ秒の上書きは、本分析では評価結論を変えなかったが `DATA_PROVENANCE_DEFECT / REQUIRES_FIX_BEFORE_PIT_DATASET_FREEZE` のまま。PIT データセット凍結の前に is-fixed を本 agent が再確認する (降格宣言の執行対象として記録)
5. 他 agent 判定の追跡: code-quality の HOLD 解除条件 (build_market の pit_t10 側への関数化 / import 解決パスの assert / dead code) が適用されたら、`reproduction_of_4B.sets_equal == true` と `races_with_identical_t10_market == 626` の不変を再実行で当方が再確認する

## 他 agent 判定の統合 (執筆時点で提出済の 2 件)

| agent | 判定 | 点 | 本 agent の読み |
|---|---|---|---|
| data-pipeline-engineer | PASS | 4.6 | 必須確認 6 件を自前実装で再計算し全件成立。50% 閾値は「検証不能 (不成立の証拠も無し)」で当方と同じ読み。追加所見 (backfill_announced_at の同秒上書き機構、受信順 ≠ 市場状態順) は本改修の欠陥ではなく台帳追記事項 |
| code-quality-reviewer | HOLD | 3.9 | 必須確認 6 件は全件成立、停止条件抵触なし。HOLD の理由は保守性 (`build_market` が `pit_t10.t10_market` の写し / `same_state` dead code / import 解決パスの assert 無し / 事前固定が git から監査不能)。**証拠の妥当性・結論の正しさへの異議ではない**。辺縁の規則差 (`_pick` が odds 空の raw を飛ばして 1 枚前へ遡る点) は今回のデータで発火した形跡が無い (全系列 lead ≥ 10.05、DB 経路と 626/626 一致) |

- 3 agent が **独立に同じ分岐点** (raw_0B30 = 300 / 313、閾値 45% なら棄却条件 2 で「結論が違う」) を検出し、いずれも「方向は否定側で結論を覆さない」と読んだ。整合している
- 本改修は type-B のため、他 agent 判定の統合ゲート (FAIL / NOT_EVALUABLE → 本 agent も保留) は **N/A**。参考として type-A 流の統合を当てるなら code-quality の HOLD により総合は HOLD 相当になるが、その HOLD は「証拠を生み出す仕組み」の欠陥ではなく再実行時の乖離予防なので、当方は検証設計単独の判定として PASS を維持し、merge 判断者には「PASS (保守性 follow-up 3 件つき)」として渡す
- 他 agent が本 scorecard 以後に FAIL / NOT_EVALUABLE を出した場合、本判定は HOLD に降格する
