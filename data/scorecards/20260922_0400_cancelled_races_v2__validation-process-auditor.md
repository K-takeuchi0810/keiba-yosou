# 検証プロセス監査人 採点 — db39d55 中止レース是正 v2 (evaluable 三分割 + main() 経由テスト + analyze_misses 除外)

## 判定: HOLD

**理由**: 前回 FAIL の主因は解消された。前回生存 10 変異のうち **7 が撃墜** (M1 -100 復活 / M2 evaluable 固定 / M3 race_status 反転 / M13 actual_execution_date / M8 / M16 / M17 節削除)。前回宣言「M1 または M16/M17 が素通りなら再 FAIL」は **非該当** → FAIL は出さない。一方、前回宣言「M4/M5/M6 が素通りなら HOLD 上限」は **該当** (backtest / generator の `({evaluable} OR 1=1)` は依然 behavioral test なし)。加えて新規設計 20 変異のうち **8 が生存**、うち 1 件は改修の核心命題を直撃する: **M23 (cancelled / pending の分岐順序を入れ替える) が全 suite 素通り**し、実 9/21 データに当てると **中山 161 行 (中止) が `result_not_yet_available` (一時) と記録される** — commit message が「潰してはいけない」と定義した当の状態。原因はテストの中止 fixture が `confirmed_order=1` (中止レースに着順がある非現実な組合せ) で、現実の「中止 かつ 着順 0」セルが未検査。commit 主張「変異 7 種すべて落ちる」は本人の綴りでは成立するが、`analyze_misses` の 2 件 (除外を外す / 理由をまとめる) は **語を残して効果を殺す綴り (M30/M32) だと生存** = 保護は文字列存在チェック。総合すると「金額経路 (stake / profit) の回帰保護は成立、状態区別と分析系の保護は文字列と分岐順序に依存」で、採用ではなく HOLD。

**改修タイプ**: type-B (評価/診断) + type-C (db.py 述語)。P25 固有ゲート (factorial / market_snapshot / fresh odds / bonus_candidate / P25 PLAN / 他 6 agent 統合) は **N/A**。backtest.py は述語 1 行のみで採用主張なし。

**運用条件**: ルール 1-bis (b)。対象 SHA `db39d55` を開始・終了時に `git -C <worktree> rev-parse HEAD` で確認 (**両時点で一致、worktree clean、親リポ tracked 差分 0**)。変異は `git archive db39d55` で展開した隔離木 3 本 (scratchpad `iso` / `iso2` / `iso3`、各 `git init` 1 commit) でのみ実施、各変異後 `git checkout -- <file>` + `status --porcelain` 空を assert。実 DB は `file:...keiba.db?mode=ro` で ATTACH し 9/21・9/22 の races / horse_races / payouts のみ scratch DB に抽出、production `main()` はそこへ向けた。9/22 HTML は `git show 6cb23d7:data/results/2026-09-22/...html` から取得 (本番 checkout 不使用)。

**根拠ファイル**: `db.py:79-127`、`scripts/build_daily_results.py:676-683,709-727,755-770,853-868`、`scripts/analyze_misses.py:139-183`、`tests/test_build_daily_results.py:35-100,344-429`、`tests/test_cancelled_races.py:194-297,501-595`、scratchpad `mut.py` / `mut_A.json` / `mut_B.json` / `out0921` / `out0922` / `out0921_m23`

**次アクション**: (1) 中止 fixture を `confirmed_order=0` にし (現実の中止レースは着順 0)、「data_div=9 かつ 着順 0 → reason=cancelled / race_status=CANCELLED」を main() 経由で assert (M23 を殺す)。(2) 理由の導出を `db.exclusion_reason(not_cancelled, result_resolved)` 1 関数に集約し、4 セル真理値表テストを置く (分岐順序を構造で固定)。(3) `analyze_misses.build()` に tmp `RESULTS_DIR` + 最小 DB を通し `skipped` が `excluded_cancelled:1 / excluded_result_not_yet_available:1` を持つことを assert (本監査で同手順が動くことを実証済: 実 9/21+9/22 で 12 / 12 / 12)。(4) backtest `list_races` / generator `build_view_model` の horse_rows に「中止 1 + 実施 1」最小 DB を通す behavioral test 各 1 本 (M4/M5/M6/M6b)。(5) `test_the_real_query_text_still_excludes_cancelled` は「NOT EXISTS が文字列にある」ではなく実行で確認する (M16b/M17b)。

## 総合: 3.2 / 5 (参考スコア、前回 2.6 → +0.6)

## 項目別

- **バックテスト設計の正しさ (対象集合 / N の表記): 4/5** — production `main()` を実データで再実行: **9/21** = 320 行 → CANCELLED 161 (`result_resolved=False`, reason=cancelled, `actual_execution_date` 空) / RUN 159 (resolved, evaluable, 実施日 20260921)、manifest `evaluation_rows_total=320 / evaluable=159 / excluded=161 / reasons={cancelled:161}`。**9/22 (本日、発走前)** = 161 行すべて RUN / `result_resolved=False` / reason=`result_not_yet_available`、evaluable 0 — 「未取得を負けにしない」が実データで成立。`analyze_misses.build()` を両日の出力に当てると rows 12 / `excluded_cancelled 12` / `excluded_result_not_yet_available 12`。buy 候補は両日 0 件で金銭 0 円。減点: (a) manifest の `evaluation_exclusion_reasons` を理由で潰す M25 が生存 (fixture が単一理由のみ)。(b) 中止 fixture が `confirmed_order=1` で現実と乖離 (下記 M23)。
- **時系列リーク防止 / 境界: 3/5** — 前回と同じ。生成側 `data_div=9` は前日公開情報でリークではない。`actual_execution_date` は evaluable のときのみ記入 (順延先への誤紐付け入口は閉じた、M13 撃墜)。抜け: backtest `AND {evaluable}` を `OR 1=1` / コメント化しても素通り (M4/M5)、generator の races 側 (M6) と **horse_rows 側 NOT EXISTS (M6b、data-pipeline が HOLD 理由にした predict ループ)** も素通り = 述語の存在は AST ガードが見るが、効果は誰も見ていない。
- **calibration / reliability 計測の継続: 3/5** — monitor: M7 (EXISTS 反転) と M17 (節削除) は撃墜、しかし **M17b (`(1=1 OR NOT EXISTS (...))`) は生存**。`test_monitor_mining_coverage` の fixture に中止レースが無いため、カバレッジ計測から中止除外が消えても文字列にさえ残れば気付けない。prediction_accuracy も同型 (M16 撃墜 / M16b 生存)。
- **A/B / 再現性 / 変異主張の裏取り: 3/5** — suite 実測 (隔離 db39d55、`.venv64`): **1 failed (既知 data/ 欠如) / 696 passed / 11 skipped / 23 s** (主張 695/11 と 1 件ズレ、軽微)。独立 30 変異: **撃墜 19 / 生存 11** (前回 5/15 → 大幅改善)。金額系 (stake / profit) は M1 / M1b / 対照 (`test_a_running_race_still_books_its_loss_through_main`) で三方向から固定され、`tests/test_evaluation.py` 等 54 件も pass。commit の「7 種すべて落ちる」は、私の同義変異で bdr 側 5 種は再現 (M2b/M20/M21/M22/M3)、analyze_misses 側 2 種は **綴り依存** (M30/M32 生存)。
- **過適合監視 / 統合判定 / 監査プロセス: 3/5** — 採用戦略の変更なしで weekly_monitor は非該当。**対象 SHA 固定は今回守られた** (開始・終了で db39d55 一致、レビュー中の編集なし) — 前回指摘 (3) は執行済と認める。兄弟 agent の db39d55 についての再判定は執筆時点で **未提出** (0300 版: data-pipeline HOLD 3.6 / profitability PASS 4.0)。data-pipeline の HOLD 3 件 (generator predict ループ / 全中止日無音 / fresh odds 述語) は `da365b0` で対象ファイルが変更され parametrize にも追加されているが、generator 側は M6b が示す通り **効果のテストが無い** — data-pipeline の再判定を待たず PASS に上げる根拠はない。

## 変異テスト (独立設計 30 種、隔離 db39d55、全 suite、失敗集合の差分で判定)

| ID | 変異 | 結果 | 撃墜した test |
|---|---|---|---|
| M1 | bdr profit の `and evaluable` 除去 (中止に -100) | **撃墜** | cancelled_books_no_loss / pending_not_a_loss |
| M1b | bdr stake の `and evaluable` 除去 | 撃墜 | 同上 |
| M2b | bdr `evaluable = not_cancelled` を後置 (語は残す) | 撃墜 | pending_not_a_loss |
| M2c | bdr `... or True` | 撃墜 | 3 本 |
| M3 | bdr race_status 反転 | 撃墜 | 3 本 |
| M13 | bdr actual_execution_date 常に記入 | 撃墜 | cancelled_books_no_loss |
| M20 | bdr `result_resolved = True` | 撃墜 | pending_not_a_loss |
| M21 | bdr resolved 判定 `> 0` → `>= 0` | 撃墜 | pending_not_a_loss |
| M22 | bdr pending 理由を cancelled に | 撃墜 | pending_not_a_loss |
| **M23** | bdr 分岐順序入替 (pending 先) | **生存** | — 実 9/21: 中止 161 行が result_not_yet_available に |
| M24 | bdr `race.get(data_div_)` (常に非中止) | 撃墜 | 3 本 |
| **M25** | bdr manifest 理由内訳を潰す | **生存** | — |
| M26 | bdr evaluable 件数 = total | 撃墜 | manifest_counts_split |
| M27 | bdr result_resolved 列に not_cancelled | 撃墜 | pending_not_a_loss |
| M28 | bdr evaluable 列に not_cancelled | 撃墜 | pending_not_a_loss |
| **M30** | am `if False and reason:` (理由別カウント無効、語は残す) | **生存** | — |
| **M31** | am 両条件無効 (中止が分析に復活) | **生存** | — |
| **M32** | am 理由をすべて cancelled に潰す | **生存** | — |
| **M4** | backtest `({evaluable} OR 1=1)` | **生存** | — (前回も生存) |
| **M5** | backtest `-- AND {evaluable}` | **生存** | — (前回も生存) |
| **M6** | generator races `({evaluable} OR 1=1)` | **生存** | — (前回も生存) |
| **M6b** | generator horse_rows `({cancelled} AND 1=0)` | **生存** | — |
| M8 | pred_acc NOT EXISTS → EXISTS | 撃墜 | real_query_text |
| M16 | pred_acc 節削除 (改修前へ) | 撃墜 | real_query_text |
| **M16b** | pred_acc `(1=1 OR NOT EXISTS (...))` | **生存** | — |
| M7 | monitor NOT EXISTS → EXISTS | 撃墜 | real_query_text / mining_coverage ×2 |
| M17 | monitor 節削除 | 撃墜 | real_query_text |
| **M17b** | monitor `(1=1 OR NOT EXISTS (...))` | **生存** | — |
| M40 | db `EXCLUSION_RESULT_PENDING` の値を cancelled に | 撃墜 | different_reasons / pending_not_a_loss |
| M41 | db `is_evaluable_race(None)` → False | 撃墜 | missing_data_div_is_kept |

前回生存 10 の再判定: M1 K / M2 K / M3 K / M13 K / M8 K / M16 K / M17 K / **M4 S / M5 S / M6 S**。

## 「cancelled と result_not_yet_available を潰さない」の担保は何か

構造ではなく **(a) `build_daily_results.py:719-724` の if/elif の並び順** と **(b) 文字列** に依存している。
- (a) 現実の中止レースは `not_cancelled=False かつ result_resolved=False` の両該当セル。優先順位を入れ替える M23 で永久除外が一時状態に化けるが、テストの中止 fixture は `confirmed_order=1` (着順あり) なので両該当セルを踏まず検知不能。9/21 実データで 161 行が化けることを `iso3` で確認済。
- (b) `EXCLUSION_*` は str 定数で閉じた型 (Enum) ではない。`analyze_misses` は CSV 文字列を `excluded_{reason}` で無制限にバケット化し、理由が欠けて `evaluable=False` のときは `excluded_not_evaluable` という **第 3 の潰しバケット** に落ちる (M30 で実際にそうなる)。M40 を殺したのも定数値の文字列比較。CSV 経由なので文字列自体は避けられないが、**理由の導出関数 + 4 セル真理値表テスト**がないと分岐順序の担保にならない。

## 停止条件チェック

- [x] git_sha / rule_version / env_overrides — N/A (backtest JSON 生成なし)。対象 SHA `db39d55` を明記、開始・終了で一致
- [x] baseline paired 比較 / market_snapshot / payout 欠損 — N/A (type-B/C)
- [ ] 専門領域: 証拠を生む仕組み — **部分抵触** (核心命題の分岐順序が未検査 = M23、`OR 1=1` 型 6 件が生存)。実害のある欠陥 (-100 復活 / 節削除の素通り) は解消済なので FAIL ではなく HOLD
- [x] 他 agent との不整合 — db39d55 についての兄弟判定は未提出。0300 版 data-pipeline HOLD を上書きする根拠は持たない (M6b)

## 反証の試み

- 「変異 7 種すべて落ちる」→ bdr 側 5 種は同義変異で再現、analyze_misses 側 2 種は綴りを変えると生存 → **部分成立**
- 「前回の 10 生存を落とした」→ 7/10 撃墜、M4/M5/M6 は前回と同じく生存 → **部分成立**
- 「未取得を負けにしない」→ 9/22 実データ 161 行すべて pending / profit 0 / stake 0 → **成立**
- 「cancelled と pending を潰さない」→ 値の差し替え (M22/M40) は検知、**順序の入替 (M23) は検知不能** → **構造としては不成立**
- 「695 passed / 11 skipped」→ 696 / 11 (+1 failed は data/ 欠如) → **軽微な不一致**
- 「対象 SHA を固定し作業停止」→ HEAD・作業木とも不変 → **成立**

## 前回からの差分 / 宣言の執行

- 前回 (20260922_0300、同系列): **2.6 / FAIL** → 今回 **3.2 / HOLD** (+0.6)。項目別: 設計 3→4、リーク 3→3、calibration 3→3、再現性 2→3、統合 2→3。-0.3 以上の低下項目なし
- 前回宣言「M1 または M16/M17 が全 suite 素通りなら再度 FAIL」→ 3 件とも撃墜、**非該当**
- 前回宣言「M4/M5/M6/M8 が素通りなら HOLD 上限」→ M4/M5/M6 生存、**執行 → HOLD**
- 前回の改善提案 (1) main() 経由テスト → 執行済 (13/15 撃墜)。(2) 各経路の behavioral test → **未執行** (backtest / generator / prediction_accuracy / monitor は文字列検査で代替、`OR 1=1` 型に無力)。(3) ガードの向き反転 → 文字列本文検査で部分代替、`(1=1 OR NOT EXISTS` に無力
- jst 系列の宣言 (`jst-date-unify-20260920` が main に乗る commit で執行) は本系列では引き続き非該当。`web/generator.py:312` はローカル時計のまま
- **今回の新宣言**: 次回この系列で **M23 (分岐順序入替) が素通りなら FAIL**。M4/M5/M6/M6b/M16b/M17b/M30/M32 のいずれかが素通りなら **HOLD 上限**。兄弟 agent (特に data-pipeline) の db39d55 についての再判定が無いまま統合 PASS を出すことはしない
