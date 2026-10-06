# データパイプライン技術者 採点 — cf3f657 「T−10 取得元の感度分析 v2 (是正版)」— 限定再チェック

**subagent CWD 限定運用での評価 (worktree 絶対パス指定)**: 対象 SHA `cf3f657fd770b6a26980e074b397d4f0d4381a4a` (branch `t10-source-sensitivity-20260926`、`de89d32` = コード+テスト、`cf3f657` = 再生成した成果物 `data/backtest/src_sensitivity_20260926_v2/` + 文書)。worktree `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\src-sens`、git はすべて `git -C <worktree>`。開始時・終了時ともに `rev-parse HEAD` = cf3f657、`status --porcelain` 空、main checkout の tracked 変更 0。本番 `keiba.db` は `mode=ro` URI のみ。再実行は scratchpad `--out-dir` (`review_dpe\out_v2`) に 1 回 (exit 0)、テストは `git archive cf3f657` の scratch コピーで実行。自前の検証 (`verify_v2.py`) は対象スクリプトの関数を使わず raw と DB を直接読んだ。前回 scorecard: `20260926_2131_src_sensitivity__data-pipeline-engineer.md` (3fea521、PASS 4.6)。

## 判定: PASS

**理由**: CHAT 指定の 4 点はすべて一次データで成立を確認した。(1) 受信時刻の由来規則 (0B31 の 6/28 以前 = ファイル名 epoch、それ以外 = mtime 秒未満切り捨て) は **DB の fetched_at の実際の書き手と一致**: backfill 2,325 本は全件 epoch の秒に `backfill_0B31` 行があり、live 0B31 1,058 本・0B30 6,426 本は mtime の秒に同じ source の行がある。**「規則の時刻には無いが、もう一方の時刻 (epoch↔mtime) には行がある」ファイルは 0 本** = 規則が実際の書き手と食い違う証拠は無い。件数 6489 / 2325 / 1707 は自前集計と一致、同秒 29 (新規 1 件は 8/29 新潟 3R、0B30 epoch :01 → mtime :02 が 0B31 :02 と同秒、票数 62,077 で同一状態)、epoch を使った場合の選択差は 3 raw 系列とも 0 (manifest でキー不在 = 0 の意味と一致)。(2) 本番等価性ゲートは `dataclasses.asdict(T10Market)` の全 11 フィールド (race_id / decision_time / start_time_used / 各馬 odds / implied / market_rank / inverse_odds_mass / odds_received_at / odds_observed_at / n_horses / violations) を比較し、片側だけ None は不一致に数える。1,176 レース・不一致 0・両方 None 239 は再実行で再現。(3) モジュール実パスは 5 本とも main 配下、main HEAD 491d2e6・tracked 変更空を manifest と現況の両方で確認。(4) 出自 5 列は raw 4 系列で空欄 0、original_mixed の `t10_announced` 空欄 53 行は **mtime≠epoch の live 4 レース (16+11+10+16 頭) の DB NULL** に一致 (3-quater の記述どおり)。odds>0 が 0 頭の O1 は自前でも 0 件。成果物は再実行で **9 ファイルすべて sha256 一致** (manifest は created_at と worktree_head_at_run のみ差)。テスト 15 本 pass。

## 対象・改修タイプ

- diff `3fea521..cf3f657`: `scripts/t10_source_sensitivity.py` (+549/−384 の書き直し)、`tests/test_t10_source_sensitivity.py` (+198)、`docs/PHASE05_4B_SOURCE_SENSITIVITY.md`、成果物 v2 (初版ディレクトリは削除、履歴に残る)。取得・ingest・schema・predictor は不変。
- 改修タイプ: **type-B (診断/分析ツール)**。P25 固有ゲートは N/A (対象外)。
- スクリプト sha256 `6e13f098…6942` = `de89d32` 版 = manifest `script_sha256`。`de89d32..cf3f657` の差分は成果物と文書のみ (= 走ったコードは実行前に commit されたもの、manifest `worktree_porcelain_at_run` 空)。

## 総合: 4.8 / 5 (前回 4.6、+0.2)

## 項目別 (CHAT 指定 4 点 + 再現性)

- **(1) 受信時刻の由来 live=mtime / backfill=epoch: 5/5** — `raw_received()` は `BACKFILL_LAST_DAY=20260628` と spec で分岐し、`ingest.py:139` (`fromtimestamp(st_mtime).isoformat(timespec="seconds")` = 切り捨て) と `backfill_odds_snapshots.py:36` (epoch) の両方の書き手を写している。DB 照合 (自前、window 内 10,521 本): backfill 2,325/2,325 が epoch 秒に `backfill_0B31`、live 0B31 1,058 + 0B30 6,426 が mtime 秒に同 source、7 月前半 368 本は未取り込み (3-ter)、残り 0B31 280+1 / 0B30 62+1 は DB に行が無い (8 月 0B31 raw 978 − DB 697 = 281 と整合、3-bis の「同じ秒の上書き・未取り込み」)。**別の時刻に行があるケース 0** — 由来の取り違えは無い。7 月未取り込み分を live 規則 (mtime) で扱うのも「もし取り込まれていたら」の意味で正しく、`samples_raw_mixed.csv` の 7/04 行は `mtime_live` / `2026-07-04T09:30:04` / 票数 70,814 / 発表 07040929。`selection_differs_if_epoch_used` は 3 系列とも 0 (自前も 0)。テスト `test_received_origin_matches_the_production_writer` が境界日 6/28 と切り捨てを固定。
- **(2) 本番 t10_market との全件等価性ゲート: 5/5** — `db_market` は本番と同じ 2 本の SQL (MAX(fetched_at) ≤ cutoff、その秒の `win_odds > 0` 行) で 1 枚を選び `build_market` に通す。`asdict` 比較なので選んだ枚 (odds_received_at)・発表時刻 (odds_observed_at、`_parse_announced` 後)・各馬オッズ/implied/rank・違反リスト・欠損 (片側 None) をすべて覆う。ゲート不合格は `SystemExit` で分析を始めない (テスト `test_equivalence_gate_stops_when_the_copy_drifts` が違反検査 1 つ落とした写しで停止を固定)。`source` が T10Market に無いことは妥当: 本番の選択規則は source を見ないので等価性の定義に含める必要が無く、出自は `db_market` の第 2 戻り値 (その秒の source を `+` 結合) → CSV `t10_source` に別経路で残る。原理的な残余は 1 つ: ゲートは「DB 行 → build_market」の写しを検証するもので、「raw state → build_market の入力 (received_at, odds_tenths, announced)」が DB 行と同義かは別の検査に頼る — それが (1) の由来照合と前回の 626/626 オッズ一致であり、両方成立している。
- **(3) モジュール実パスの assert: 5/5** — import 直後に 5 モジュールの `__file__` が `ROOT` (resolve 済) 配下かを検査し、外なら `SystemExit`。manifest `production_module_path` 5 本すべて `C:\Users\kizun\dev\keiba-yosou\...`、`production_module_git_head` 491d2e6 (現況 `git -C main rev-parse HEAD` も 491d2e6)、`production_tracked_changes_at_run` 空 (現況 `--untracked-files=no` で 0 行)。`HERE` (worktree) の HEAD と porcelain も別に記録。前回の「KEIBA_PROD_ROOT で解決したつもりが別 checkout」の失敗モードは閉じた。
- **(4) raw 出自の列 / 空 O1 の扱い: 4.5/5** — 5 列 (`t10_source` / `t10_received_at` / `t10_received_origin` / `t10_total_votes` / `t10_announced`) が全系列に出力され、raw 4 系列で空欄 0。original_mixed は `received_origin=db`、`total_votes` は None (DB に票数が無いため、正しい)。odds>0 の馬が 0 頭の O1 は `insert_odds_snapshot` (`db.py:985-986` rows 空で 0 行) と同じく「存在しない」扱い、該当 0 件 (自前 0)。減点: original_mixed の `t10_source` に `+` 結合 (同秒複数 source) が現れるかは今回の DB では 0 件で未観測 — 主キーに source が無い以上 1 秒 1 行なので常に単一になるはずで、`+` 結合は事実上到達しないコード。害は無いが「同秒上書きで消えた側」は CSV から読めない (それは 3-bis の欠陥そのもの)。
- **再現性・文書整合: 4.5/5** — scratch 再実行で 9 成果物 sha256 一致、manifest は時刻と worktree HEAD のみ差。文書の数値 (2,325 / 6,489+1,707 / 78+18 / 29 vs 28 / 1,176・0・239 / 0B31 1 レース約 2.8 本 vs 0B30 約 20.3 本) は manifest・自前集計と一致。3-quater (`live-ingest-audit-20260926` 037e777) は実例 8/23 札幌 9R を一次確認して記録、`--reset` 後 NULL の条件も正しい。減点: 文書は `selection_differs_if_epoch_used = 0` と書くが manifest ではキー不在 (Counter に 0 が入らない) — 読み手が「記録されていない」と誤読しうるので、0 を明示的に書き出すか文書に「キー不在 = 0」と注記する。

## 一次確認の表

| 確認 | 判定 | 根拠 (実測) |
|---|---|---|
| raw_info 6489 / 2325 / 1707 | 成立 | 自前集計 `('0B30','mtime_live') 6489, ('0B31','epoch_backfill') 2325, ('0B31','mtime_live') 1707` |
| 規則の時刻に同 source の DB 行 | 成立 | backfill 2325/2325、live 0B31 1058、0B30 6426。別時刻にだけ行があるファイル 0 |
| 同秒 29 (epoch 28) | 成立 | 自前 29、追加分 `2026-0829-04-03-03-03` (同一状態) |
| epoch を使った場合の選択差 0 | 成立 | 自前 `{}` (3 系列)、manifest キー不在 |
| 等価性 1,176 / 0 / 239 | 成立 | 再実行の manifest で同値、asdict 全フィールド比較、片側 None は不一致 |
| モジュールパス / main HEAD / tracked 変更 | 成立 | manifest と現況の両方 (491d2e6、0 行) |
| 出自 5 列の空欄 | 成立 | raw 系列 0、original_mixed `t10_announced` 53 = mtime≠epoch 4 レースの DB NULL |
| 空 O1 = 存在しない | 成立 | 自前 0 件、manifest にキー不在 (= 0) |
| テスト | 成立 | `git archive` コピーで 15 passed (0.61 s) |
| 成果物再現 | 成立 | 9 ファイル sha256 一致 |

## 根拠ファイル

`.claude/worktrees/src-sens/scripts/t10_source_sensitivity.py:70-75,82,94-99,102-141,156-169,174-255,267-305,519-567`、`tests/test_t10_source_sensitivity.py:85-92,157-181`、`docs/PHASE05_4B_SOURCE_SENSITIVITY.md` (受信時刻 / 等価性 / 閾値 40-55% の節)、`data/backtest/src_sensitivity_20260926_v2/{manifest,series_summary,coverage_threshold_sensitivity,common_fresh_set,selection_classes}.json` + `samples_*.csv`、`jvlink_client/ingest.py:139`、`scripts/backfill_odds_snapshots.py:36`、`db.py:980-986`、`predictor/pit_t10.py:153-171,178-247`、3-quater: `git -C <worktree> show 037e777:docs/LIVE_INGEST_DATA_INTEGRITY_AUDIT.md` :200-214。

## 次アクション (いずれも merge を止めない)

1. manifest の `selection_audit_counts` に `selection_differs_if_epoch_used: 0` と `o1_without_positive_odds_treated_absent: 0` を **明示的に 0 で** 出す (Counter の既定値に頼らない)。
2. 3-quater の全件照合 (462 値のうち何件がこの機構で説明できるか) を、`backfill_announced_at` 修正の設計時にまとめて行う (凍結明け)。
3. raw にあって DB に無い live 0B31 280 本 / 0B30 62 本の内訳 (同秒上書きで消えた vs そもそも取り込まれなかった) を 3-bis の台帳に数として残す — 今回の自前照合で分離可能 (規則の秒に別 source の行があるか) だが、本 scorecard の範囲外なので数だけ提示: 0B31 live 1,707 本中 DB 同 source 行あり 1,058 / 7 月未取り込み 368 / 行なし 281。
