# 検証プロセス監査人 (最終ゲート) 採点 — Phase 0.5-4B T−10 取得元 感度分析 v2 (cf3f657, branch t10-source-sensitivity-20260926)

**subagent CWD 限定運用での評価 (worktree 絶対パス指定)**: 対象 SHA `cf3f657fd770b6a26980e074b397d4f0d4381a4a` (de89d32 = コード+テスト、cf3f657 = 成果物 v2 + 文書)、worktree `C:/Users/kizun/dev/keiba-yosou/.claude/worktrees/src-sens`。git は全て `git -C <wt>`。開始時・終了時の `rev-parse HEAD` = cf3f657 で不動、終了時 `status --porcelain` = 空。本番 DB は開いていない (今回は JSON / CSV / コード / git 履歴の照合と、scratchpad へ `git archive` した写しでの pytest のみ)。worktree・本番 checkout のファイルは未編集。**前回 scorecard (`20260926_2131_…validation-process-auditor.md`, PASS 4.3) の指摘に対する scoped 再確認**であり、ゼロからの再点検ではない (再現実行は v1 で byte 一致を確認済、v2 の 5 系列要約が v1 と同値であることを下記で確認したので再実行は省いた)。

## 判定: PASS (最終ゲート — CHAT 指定の 2 焦点はいずれも成立。前回の留保 4 件はすべて文書・成果物に反映済)

**改修タイプ**: type-B (分析スクリプト + テスト + 成果物 + 文書。predictor / weights / calibrator / BUY_FILTER / GUI 非接触、4A/4B JSON 未上書き)。P25 固有ゲートは **N/A (対象外)**。

### 焦点 (1) 50% を事前登録の確認的ルールとして扱っていないか — **成立**

- 文書 `docs/PHASE05_4B_SOURCE_SENSITIVITY.md:3-4` 「明示的な感度分析 (robustness analysis)。事前登録された確認的な検定ではない」、`:17-25` に **出典を分ける表**: 系列 5 本 / PIT 条件 / 一致分類 = main `491d2e6` 監査文書 3-bis (結果より前に main に入っている) ／ 50% 閾値・4 項目・同秒規則 = 結果と同じコミット `3fea521` (git では証明できない) → 「50% を判定の根拠にしない」と明記
- スクリプト docstring `scripts/t10_source_sensitivity.py:3-4, :30-35` 同旨 (「当初の 50% 閾値は事前固定を git で証明できないため格下げ」)。定数 `MIN_FRESH_SHARE` と `judgeable` は **削除済** (grep 0 件)、代わりに `COVERAGE_THRESHOLDS = (0.40, 0.45, 0.50, 0.55)` (`:80`)
- manifest `reading` (`:77`) 「coverage 閾値 40/45/50/55% の感度として読む。50% は事前固定を git で証明できないため判定の根拠にしない」。`fixed_reading_rules` キーは消えている
- 残留語の grep (「事前に固定」「結果を見る前」「事前固定」「pre-registered」「事前登録」): 3 ファイルで該当 4 行、いずれも **否定形または格下げの説明** で、確認的ルールとしての主張は 0
- 手続き上の改善: 今回は **コードを先にコミット (de89d32, 22:02:29) → 実行 (manifest created_at 22:13:10) → 成果物コミット (cf3f657, 22:15:59)** の 2 段。manifest `worktree_head_at_run=de89d32`・`worktree_porcelain_at_run=""`・`script_sha256 6e13f098…` = `git show de89d32:scripts/t10_source_sensitivity.py` の sha256 = cf3f657 の同ファイル (de89d32..cf3f657 で scripts/tests の差分 0)。**「走ったコードはこの commit」が git で追跡できる**ようになった (v1 で不可能だった点の是正)

### 焦点 (2) 40/45/50/55% の表と結論の文言 — **成立**

- `coverage_threshold_sensitivity.json` を `series_summary.json` から **当方が独立に再導出** (judged = fresh_races ≥ thr × 626、結論 4 項目の一致・不一致項目): 4 閾値 × 5 系列 = 20 セル **全て一致**。share: raw_0B30 0.4792、matched 0.0543
- 系列別: original_mixed / raw_mixed (757, 121%) / raw_0B31 (725, 116%) は 40〜55% すべてで 対象・同じ ✓。raw_0B30 (300, 47.9%) は 40/45% で対象・**違う (differs_in = rejected_by のみ)**、50/55% で参考 ✓。matched_same_state (34, 5.4%) は全閾値で参考 ✓。文書の表 `:71-76` と一致
- raw_0B30 の棄却条件 2: `rejection_2_stale_only_win` delta_fresh **+0.0000225**、delta_all −0.0000019 (当方読み出し) = 文書 `:65` 「+0.0000225 / −0.0000019」、結論 `:117-118` 「ΔLogLoss +0.00002 と極小で、主要仮説を支持する結果ではない」✓。主要仮説 (不合格)・金額 (判定不能)・比 ≥1.75 (0 頭) は全閾値・全系列で同一 (`conclusion_parts`)
- 結論の文言 `:115-124` は CHAT 固定文言と一致: 3 系列は 40〜55% で不変 / raw_0B30 は 47.9% で 50% 基準では参考、45% で対象となり棄却条件 2 だけ該当 / matched_same_state はいずれの合理的閾値でも結論を出せない / 4B は mixed-source の T−10 市場に対する結果で provenance・coverage に既知の欠陥 (3-bis / 3-ter / 3-quater) がある、注記は今後も残す

### 前回指摘の反映確認

| 前回の留保 | 状態 | 証拠 |
|---|---|---|
| 実効的な入替範囲 (191 + 42 レース、8 月のみ) を明記 | **反映** | 文書 `:82-86` 表に「T−10 市場が違うレース」列 (0 / 42 / 191、すべて 8 月)、`:90` 「実際に取得元が入れ替わった範囲は 8 月だけ」。`common_fresh_set.json` に `races_with_different_t10_market` と `different_races_by_month` を追加 (raw_0B31 {"08": 191}、raw_0B30 {"08": 42}) |
| paired Δβ と区間 | **反映** | `common_fresh_set.json.paired_delta_beta`: raw_0B31 −0.0489 [−0.0794, −0.0093]、raw_0B30 −0.0064 [−0.0282, +0.0146]、raw_mixed / matched 0 [0, 0] (市場同一なので自明)。方法 `eval_stats.block_boot`、SEED 固定、n_boot 300 (`t10_source_sensitivity.py:372-388`、レースを塊にして両系列を同じ抽選で再抽出 = 正しい paired 設計)。文書 `:85-86, :91, :121` と一致。当方の v1 時の独立計算 (−0.049 [−0.078, −0.013]) と点推定一致、端点差は再抽出の実装差 (MC 誤差の範囲) |
| CONSUMED_WINDOWS の持ち越し | **反映 (持ち越し宣言)** | 文書 `:129-130`、manifest `consumed_windows_note`: JST ブランチ解凍後に反映。**降格宣言の執行対象として本 agent が追跡する** (config.py は JST 凍結中で触れないのは妥当) |
| 「4B は mixed-source の T−10 結果 + 既知の provenance / coverage 欠陥」の注記 | **反映** | 文書 `:122-124` |
| script_git_sha が実行時 HEAD で自身の commit を指さない | **反映** | `worktree_head_at_run` に改名、porcelain も記録、実行前 commit の 2 段手続きに変更 |

### 追加で確認したこと

- **v2 の 5 系列要約は v1 と同値**: `git show 3fea521:…/series_summary.json` と v2 の共通キー (coverage / LogLoss / β₂ / CI / 棄却条件 1 / 比 / 購入条件 / verdict) を比較 → IDENTICAL。文書 `:11-12` の主張どおり。受信時刻の由来を epoch → 本番準拠 (backfill=epoch / live=mtime) に変えても選択は 1 件も変わらない (`selection_differs_if_epoch_used`=0、同秒件数 28→29 は分類のみ)
- **本番等価性ゲート**: manifest `production_equivalence_checked_races=1176 / both_none=239 / mismatched=0`。`build_market` が `t10_market` の写しであることのリスク (code-quality v1 HOLD 理由) を、起動時の全レース照合 + `test_equivalence_gate_stops_when_the_copy_drifts` で fail-closed に閉じている。本番モジュールの実パス 5 本と `production_tracked_changes_at_run=""` も記録
- **テスト**: `tests/test_t10_source_sensitivity.py` 15 本を scratchpad の `git archive cf3f657` 写しで実行 (PYTHONPATH に本番 root、worktree は未使用) → **15 passed**。閾値表の境界 (`test_threshold_table_classifies_a_series_just_below_half`)、cutoff ちょうど包含 / +1 秒除外、同秒規則の入力順非依存、鮮度境界の包含性、本番 writer と同じ受信時刻由来、を固定
- 統計の枝葉: 「≥1.75 が 0 頭」は max 1.738 / 1.743 と紙一重だが、文書は max を系列ごとに表示しており誤読は防げる (v1 と同じ所見、減点は維持しない)

## 総合: 4.6 / 5 (前回 4.3 → +0.3)

| 項目 | 点 | 所見 |
|---|---|---|
| 1. 検証 (感度分析) 設計の正しさ | 4.5 | 閾値そのものを感度の軸にした設計は正しい。実効入替範囲・集合差の切り分けが明文化。留保: 4 項目一致ルールは粗い二値 (数値は併記されているので実害なし) |
| 2. 時系列リーク防止 | 5 | v1 と同じ (受信 ≤ 決定時刻の二重強制、全系列 lead ≥ 10.05 分)。受信時刻を本番 writer と同じ由来に揃え、遡り無しの規則を本番と一致させ、テストで固定 |
| 3. calibration / reliability 計測 | 4 | v1 と同じ経路 (`moe.run`)。帯別較正は `series_full.json` に留まり文書には未掲載 (判定に不要) |
| 4. 再現性 / バージョン管理 | 5 | ベストプラクティス = 「コードを commit → 実行 → 成果物 commit、manifest に実行時 HEAD・porcelain・依存モジュールの実パス・モデル hash・DB version を残し、写しは等価性ゲートで守る」。本改修はこれを全て満たす |
| 5. 事前固定 / 過適合監視 / 統合判定 | 4.5 | 事前登録と同時記録の峻別、閾値 4 点の感度化、CHAT 文言との一致。減点: CONSUMED_WINDOWS が持ち越し (妥当な理由つき)、他 agent の v2 判定は執筆時点で未提出 |

## 根拠ファイル

- worktree: `docs/PHASE05_4B_SOURCE_SENSITIVITY.md` (:3-4, :14-25, :53-66, :67-78, :80-93, :113-124, :126-132)
- worktree: `scripts/t10_source_sensitivity.py` (:1-38 docstring, :80, :344-388 threshold_table / paired_delta_beta, :521-546 manifest)
- worktree: `tests/test_t10_source_sensitivity.py` (15 本)
- worktree: `data/backtest/src_sensitivity_20260926_v2/{manifest,series_summary,coverage_threshold_sensitivity,common_fresh_set}.json`
- git: `de89d32` (22:02:29) / `cf3f657` (22:15:59)、`3fea521:data/backtest/src_sensitivity_20260926/series_summary.json` (v1 比較)
- 当方 scratchpad `review_vpa/`: `v2_archive/` (pytest 15 passed)、v1 の `out/` と `paired_delta.py`

## 次アクション

1. (執行追跡) JST ブランチ解凍後に `config.CONSUMED_WINDOWS` へ 1 行追加。本 agent は次回 config.py 接触時に未執行なら降格する
2. (執行追跡) 7 月前半の取り込み漏れ・同秒上書き・発表時刻上書き (3-bis / 3-ter / 3-quater) は PIT データセット凍結前の修正対象のまま。凍結判定時に is-fixed を再確認
3. (任意、文書) 帯別較正の系列差は `series_full.json` から表 1 枚に起こせる。判定に不要なので優先度低
4. 他 agent の v2 判定 (data-pipeline / code-quality) が FAIL / NOT_EVALUABLE なら本判定は HOLD に降格。code-quality v1 HOLD の 3 理由 (写しの乖離 / import path / dead code) のうち、写しの乖離は等価性ゲート + テストで、import path は manifest 記録 + `production_tracked_changes_at_run` で構造的に閉じたと当方は読む
