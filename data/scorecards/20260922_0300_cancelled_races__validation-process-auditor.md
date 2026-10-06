# 検証プロセス監査人 採点 — b1733d7 中止レース (data_div='9') を評価・生成から外す

## 判定: FAIL

**理由**: 実装ロジック自体は 9/21 実データで正しく動く (下記) が、**改修が自ら掲げた証拠「変異 18 種を植えて全部落ちる」が一次データで反証された**。私の独立設計 15 変異を隔離した b1733d7 の木で全 suite に当てた結果 **生存 10 / 撃墜 5**。生存には (a) 中止レースに profit=-100 を計上する変異 (= この改修が直した当のバグの再発、`scripts/build_daily_results.py:708`)、(b) `prediction_accuracy.py` / `monitor.py` の `NOT EXISTS (中止)` 節を **丸ごと削除して改修前に戻す**変異、(c) `AND ({evaluable} OR 1=1)` で述語の語だけ残して効果を殺す変異 (backtest / generator) を含む。commit message が「その条件を緩めた瞬間に中止が再流入する」と自ら定義した脅威モデルに対し、テストは再流入を検知できない。「予想は残し評価だけ外す」本体 (`evaluable` / `race_status` / `actual_execution_date` / 損益) を **production 関数経由で叩く behavioral test は 0 本** (`tests/test_cancelled_races.py:121-138,405-420` は式を自前で再実装して自分と比較、`:423-439` はソース文字列の存在確認)。監査対象は「証拠を生む仕組み」なので、停止条件「実害のある欠陥 (回帰保護の不在 + 監査証跡上の過大主張)」に該当。作者の後続 commit `4ee70aa` (01:43:05、レビュー中に追加) でも同 10 変異は全生存。

**改修タイプ**: type-B (評価/診断) + type-C (db.py 述語)。P25 固有ゲート (factorial / market_snapshot / fresh odds / bonus_candidate / P25 PLAN) は **N/A**。`scripts/backtest.py` を触るが採用主張なし、race 集合は `require_confirmed` 経路で before/after 差 0 を実測 → type-A 扱いしない。

**運用条件**: ルール 1-bis (b) subagent CWD 限定運用。全 git は `git -C <worktree>`。親リポは read-only (DB は `?mode=ro`)。**レビュー中に共有 worktree が並行編集され** (HEAD が b1733d7 → 4ee70aa、01:45-01:47 に 6 ファイル未コミット変更、suite 実行中に diff ハッシュが変化)、共有木上の変異バッチ 2 は汚染 (無関係な `test_fetch_fresh_odds` / `test_fresh_odds_coverage` の fail による偽撃墜 6 件) と判定して **破棄**、`git archive` でスクラッチに展開した隔離木 (`src_b1733d7` / `src_4ee70aa`、各 `git init` 1 commit) で再実行した。復元はバイト一致 assert、共有木・隔離木とも終了時 clean。

**根拠ファイル**: `db.py:80-118`、`scripts/build_daily_results.py:570-580,692,705-711,742-746,792-801,829-838`、`scripts/backtest.py:590-610`、`scripts/monitor.py:113-117,170-197`、`scripts/prediction_accuracy.py:73-82`、`web/generator.py:312,319-337`、`scripts/auto_predict.py:76-138,307-370`、`tests/test_cancelled_races.py:121-138,194-284,405-439`、scratchpad `mutate3.py` / `out0921/evaluation_summary.csv` / `out0921/manifest.json`

**次アクション**: (1) `tests/test_build_daily_results.py::_run_main` の fixture に `data_div='9'` のレース + ◎ + `bet_candidate=True` を足し、`main()` 経由で `evaluable=False` / `profit_loss_yen_100unit=0` / `race_status=CANCELLED` / manifest の evaluable 件数を assert (M1/M2/M3/M13 を殺す)。(2) `prediction_accuracy.main` / `monitor.measure_mining_coverage` / `backtest.list_races(require_confirmed=False)` / `generator.build_view_model` に「中止 1 + 実施 1」の最小 DB を通す behavioral test を各 1 本 (M4/M5/M6/M8/M16/M17 を殺す)。(3) AST ガードは「races を読む SQL」の検査から「`horse_races` を読んで `confirmed_order` を評価に使う SQL は、`races` の中止述語を伴うこと」へ反転させる (読むのをやめた SQL を検知する唯一の方法)。

## 総合: 2.6 / 5 (参考スコア)

## 項目別

- **バックテスト設計の正しさ (対象集合 / N の表記): 3/5** — 述語は `db.py:86-118` に一本化、NULL は残す方針 (実 DB の NULL は 0 行)。実 DB: 9/21 = 中山 06 12R `data_div='9'` / 阪神 09 12R `'6'`、中山 horse_races 161 行すべて `confirmed_order=0`、payouts は阪神 12 件のみ。`build_daily_results.main` を ro DB + 11:01 HTML で scratch に走らせた結果 320 行 = CANCELLED 161 (`evaluable=False`, reason=cancelled) / RUN 159、◎ 24 発行・12 評価可・的中 3 → **素朴 3/24=12.5% に対し正しくは 3/12=25.0%** (作者・収益性判定者の再導出と一致)。買い候補 0 件なので金銭 0 円。欠陥: (a) b1733d7 の manifest は `evaluation_summary: 320` のみで **発行 N と評価可 N を分けて書く場所がない** (`:829-838`) — 「同じ N で表記しない」ルールの担保は CSV 列 5 個だけで、集計器は無い。4ee70aa で内訳 4 キーが追加されたが、消費者 (`scripts/analyze_misses.py:163-171` は `confirmed_order==1` の有無で判定し `evaluable` 列を読まない) は不変。(b) `evaluable` が「中止でない」と「結果がある」を混同: `race_info.get(rid, {})` (`:692`) で races 行欠落 → `data_div=None` → `evaluable=True / RUN`、阪神の取消 2 頭 (`confirmed_order=0`) も `evaluable=True`。(c) `actual_execution_date` は順延先 (9/22 中山 04/07 は DB に `data_div='2'` で存在) を引かず None 固定 — 属性名が約束する内容を満たさない。
- **時系列リーク防止 / 境界 (リーク分類学): 3/5** — 生成側で `data_div='9'` を使うのは前日 11:28 発行の公開情報でリークではない。backtest 側は現在の `data_div` (事後値) で除外するが、返還される馬券の除外なので評価上妥当。`list_races` を SQL で再現し `require_confirmed` あり before=after=**20,578** (差 0) を実測 → 「暗黙除外で落ちていた」主張は backtest について成立。なしなら 79 レース差。抜け: `data_div='9'` は「結果なし」と同義でない — 2020-03-29 中山 R3/R4 は `'9'` なのに `confirmed_order>0` が 6/5 頭 (1 着なし) 存在し、`analyze_misses` 型の「confirmed_order で判定」する経路とは答えがずれ得る。train-serve skew: `web/generator.py:328-337` の horse_rows は races で絞らず、中止レースの馬も `predict_race` に流れる (data-pipeline 指摘と一致、4ee70aa 後の未コミット編集で対応中)。
- **calibration / reliability 計測の継続: 3/5** — `monitor.measure_recent_brier` は `list_races(jra_only=True)` 経由 (`scripts/monitor.py:117`) で述語が効く。`measure_mining_coverage` は `NOT EXISTS` 明示化 (`:189-197`)。ただし M17 (その節を削除) が全 suite 素通り = Brier/カバレッジ計測から中止除外が消えても気付けない。`test_monitor_mining_coverage` は M7 (EXISTS 反転) は殺すが削除は殺せない。
- **A/B / 再現性 / 変異主張の裏取り: 2/5** — suite 実測 (`.venv64`、隔離 b1733d7): **1 failed (既知 data/ 欠如) / 683 passed / 11 skipped / 21 s** (主張 684 / 10 と 1 件ズレ)。変異 15 種の結果は下表。AST ガード (`tests/test_cancelled_races.py:194-284`) をロジック複製 probe で検査: **9 パターン中 8 が素通り** — `JOIN races` (`:272` は "from races" のみ照合)、`"FROM " + "races"`、`f"FROM {T}"`、`%` 整形、`main.races`、SQL コメントに "cancelled"、`SELECT data_div FROM races` (4ee70aa で是正)、`({evaluable} OR 1=1)` (4ee70aa でも残存)。「免除は allowed に本文ごと登録」は良いが、`build_daily_results` の SELECT は `data_div` 語免除にも同時該当し allowed 登録は b1733d7 時点で冗長だった。
- **過適合監視 / ドリフト / 統合判定: 2/5** — 採用戦略の変更なしで weekly_monitor 系は非該当 (schtasks は未実行、read-only 確認に切替)。監査プロセス上の問題 2 件: (a) expert-review 実行中に監査対象の HEAD が進み未コミット編集が継続 → 兄弟 agent と本 agent が **異なる木を採点している** (data-pipeline / profitability は b1733d7 を明記)。1-bis (b) 運用は「commit を固定して呼ぶ」前提であり、レビュー中の編集はその前提を壊す。(b) 前回宣言の執行先 (jst 系列 37eaf61 / aa0396f) は branch `jst-date-unify-20260920` のみに存在し **main 未マージ**、b1733d7 の木に `jst.py` は無い。`web/generator.py:312` は `datetime.now().date()` のまま = 前回 FAIL の是正は本番系統に届いていない (下記「宣言の執行」)。

## 変異テスト (独立設計 15 種、隔離 b1733d7、全 suite、失敗集合の差分で判定)

| ID | 変異 | b1733d7 | 4ee70aa | 撃墜した test |
|---|---|---|---|---|
| M1 | bdr `and evaluable` 除去 (中止に -100 計上) | 生存 | 生存 | — |
| M2 | bdr `evaluable = True` 固定 | 生存 | 生存 | — |
| M3 | bdr `race_status` 反転 | 生存 | 生存 | — |
| M13 | bdr `actual_execution_date` 常に記入 | 生存 | 生存 | — |
| M19 | bdr SELECT から `data_div` 列除去 | 撃墜 | (未実行) | AST ガード |
| M4 | backtest `({evaluable} OR 1=1)` | 生存 | 生存 | — |
| M5 | backtest `-- {evaluable}` (コメント化) | 生存 | 生存 | — |
| M6 | generator `({evaluable} OR 1=1)` | 生存 | 生存 | — |
| M7 | monitor `NOT EXISTS`→`EXISTS` | 撃墜 | (未実行) | test_monitor_mining_coverage ×2 |
| M17 | monitor `NOT EXISTS` 節を削除 (改修前へ) | 生存 | 生存 | — |
| M8 | prediction_accuracy `NOT EXISTS`→`EXISTS` | 生存 | 生存 | — |
| M16 | prediction_accuracy 節を削除 (改修前へ) | 生存 | 生存 | — |
| M9 | auto_predict `_race_days` 述語無効化 | 撃墜 (共有木) | — | test_a_fully_cancelled_day |
| M10 | auto_predict eligible 述語無効化 | 撃墜 (共有木) | — | test_coverage_denominator |
| M11 | db `is_evaluable_race` 常に True | 撃墜 (共有木) | — | test_python_and_sql_agree |

「共有木」の 3 件は並行編集前後の木で撃墜したが、殺した test は b1733d7 の test ファイルに存在するため採用。**撃墜 5 / 生存 10**。作者の「損益を計上する」「各経路から除外を外す」は同クラスの別綴りで生存。

## 停止条件チェック

- [x] git_sha / rule_version / env_overrides — N/A (backtest JSON 生成なし)。scorecard は commit hash `b1733d7` / `4ee70aa` を明記
- [x] baseline paired 比較 / market_snapshot / payout 欠損 — N/A (type-B/C)
- [ ] 専門領域: 証拠を生む仕組み — **抵触** (変異耐性の主張が 10/15 で不成立、改修前への完全回帰が素通り、本体の behavioral test 0 本)
- [x] 他 agent との不整合 — data-pipeline HOLD 3.6 / profitability PASS 4.0 (執筆時点で 2 名のみ)。本 agent の FAIL は両者が見ていない軸 (テストの実効性) に基づき、両者の事実認定 (実 DB 4 値 / 金銭 0 円) とは矛盾しない

## 反証の試み

- 「変異 18 種を植えて全部落ちる」→ 独立 15 種で 10 生存 (隔離木・全 suite) → **不成立**
- 「races を読む SQL リテラル 1 本ずつ検査」→ 節削除で races を読まなくなった SQL は検査対象外 (M16/M17)、probe 8/9 素通り → **設計として不成立**
- 「他経路は confirmed_order>0 で暗黙除外」→ backtest `require_confirmed` で差 0 を実測 → **成立** (2020-03-29 の `'9'`+`confirmed_order>0` 11 頭は 1 着なしで影響なし)
- 「9/21 は 3/12 が真値」→ 自分の scratch 出力で 3/24 vs 3/12 を再導出 → **成立**
- 「684 passed / 10 skipped」→ 683 / 11 (1 件が skip 化) → **軽微な不一致**
- 「本番 checkout に触れず worktree で作業」→ 親 `git status` に本改修由来の変更なし → **成立**。ただし worktree 自体がレビュー中に編集された

## 主な改善提案

1. **本体を main() 経由で叩く回帰テスト** — `tests/test_build_daily_results.py:_run_main` に `data_div` 引数を足し、`'9'` + `bet_candidate=True` の ◎ で `profit_loss_yen_100unit==0` / `evaluable==False` / `race_status=="CANCELLED"` / manifest `evaluation_rows_evaluable` を assert。式の再実装 (`tests/test_cancelled_races.py:121-138,405-420`) と文字列存在 (`:423-439`、4ee70aa の 2 本も同型) は削除
2. **ガードの向きを反転** — 「`horse_races` の `confirmed_order` を読む SQL は `races` の中止述語 (`{cancelled}`/`{evaluable}`) を **同じリテラル内に**持つこと」を offender 条件にする。加えて `OR 1=1` 型は behavioral test でしか殺せないので、監査対象 4 経路に「中止 1 + 実施 1」最小 DB を通す 4 本を追加
3. **レビュー中の木を凍結** — expert-review 起動時に `git -C <worktree> rev-parse HEAD` を各 agent の scorecard 冒頭へ刻印させ、終了まで commit / 編集を止める。今回は HEAD が 2 つ・未コミット差分が 3 世代あり、7 名の判定が同じ対象を指す保証がない

## 前回からの差分 / 宣言の執行

- 前回 (20260921_0040 jst_date_unify、`git show aa0396f:` から復元。作業ツリーには存在しない): **2.4 / FAIL** → 今回 **2.6 / FAIL** (+0.2)。系列が異なる (jst → cancelled races) ため項目対応は不可
- 前回宣言 (1) 「`test_jst_is_used_not_system_local_time` が実時刻依存のまま残れば再 FAIL」: b1733d7 の木では当該テストは **旧 monkeypatch 版**で、旧 `notify_dedup` 実装に対して 9/22 も pass (683 passed に含む)。jst 系列の実装 (`jst.py`) 自体が **main / 本 branch に無い** (`git branch --contains aa0396f` = `jst-date-unify-20260920` のみ、`git ls-tree main jst.py` 空) ため条件は「非該当」。ただし本番 main は前回指摘した `web/generator.py:312` ローカル時計のまま
- 前回宣言 (2) 「生存変異 M2/M4/M5/M6 が依然素通りなら HOLD 上限」: 執行先の code が本 branch に無く再実行不能。**未執行の理由を明記**し、`jst-date-unify-20260920` が main に乗る commit で執行する
- 今回の新宣言: 次回この系列で M1 (中止に -100 計上) と M16/M17 (節削除) のいずれかが全 suite 素通りなら **再度 FAIL**。M4/M5/M6/M8 が素通りなら HOLD 上限
