# 収益性 / 投資判断専門家 採点 — 中止レース (data_div='9') を評価・生成から外す (worktree `data-div-cancelled-20260922`, commit b1733d7)

## 判定: PASS

**改修タイプ**: type-B (評価集合の定義変更 + 診断属性追加) に type-D (generator の描画集合) が付随。
`BUY_FILTER_DEFAULT` / calibrator / weights / Kelly は不変 (`git -C <worktree> show HEAD --stat`: db.py,
scripts/{auto_predict,backtest,build_daily_results,monitor,prediction_accuracy}.py, web/generator.py, tests/)。
P25 固有ゲート (2026 holdout ROI 180% / CI 下限 / bonus_candidate / paired baseline) は **N/A (対象外)**。
**subagent CWD 限定運用での評価** (worktree 絶対パス + `git -C` で実施。親リポ main には未反映)。

**理由**: 改修前の 9/21 実害を自分で再導出した結果、**金銭実害は 0 円** (買い候補 0 件、BUY_FILTER suspended)
だが **◎的中率の N が 2 倍に水増し** (3/24=12.5% と出るところ、真値は 3/12=25.0%) されていた。
改修後は損益・的中率の分母から中止 161 行が外れ、行は監査記録として残る。停止条件抵触なし。
留保 4 件 (下記) はいずれも資金喪失経路ではない。

**根拠ファイル**: worktree `scripts/build_daily_results.py:698-746`, `scripts/auto_predict.py:76-138,336-368`,
`db.py:67-118`, `tests/test_cancelled_races.py:202-285`, 実測出力 (scratchpad `res_0921/evaluation_summary.csv`, 320 行)

**次アクション**: main へ反映 (今日 9/22 は順延日で `races` 0922 中山 12R = data_div '2'、horse_races 161 行/odds 161 あり)。
併せて留保 1 (stake 列) と留保 2 (通知/HTML の中止開示) を次サイクルで。

## 総合: 4.0 / 5 (参考スコア)

## 実測 (このセッション。DB は SELECT のみ、出力は scratchpad)

| 項目 | 実測値 |
|---|---|
| `races` 2026-09-21 | 中山 (06) 12R すべて `data_div='9'` (data_created 20260920)、阪神 (09) 12R `'6'` |
| `horse_races` 2026-09-21 中山 | 161 行、confirmed_order>0 = **0**、win_odds あり 161 (odds_snapshots は 0 = 発走前市場情報なし) |
| 公開 HTML 11:01 版 (git 83e7644) | 24 レース = 中山 12 + 阪神 12、◎ 24、**bet_candidate=True 0 件** |
| `prediction_log` 9/21 | 中山 483 行 / 阪神 477 行 (08:00, 09:00, 11:00 の 3 版)、◎ 各 36 = 12R×3 版 |
| 新コードで build (--output-dir scratchpad) | eval 320 行 = CANCELLED 161 / RUN 159。◎ CANCELLED 12 行は confirmed_order=0 のまま、evaluable=False, reason=cancelled, actual_execution_date 空 |
| profit 合計 | RUN 0 円 / CANCELLED 0 円 (bet_candidate 0 のため両者 0) |
| RUN ◎ 成績 | 12 戦 3 的中、win_payout 合計 690 (◎ベタ 100 円なら 690/1200 = 57.5%、n=12 で CI は語れない) |
| 旧コード相当の実害 (再導出) | ◎ 12 頭 + 他 149 頭が confirmed_order=0 = 「不的中」。◎的中率 **3/24=12.5%** (真値 25.0%)。買い候補 0 → profit 計上 **0 円**。仮想 would_be_candidate も 0 (中山は morning_pop/EV 空欄) |
| 過去の中止 (2024-2026) | 2026-02-07〜09 雪 42R (567 頭, odds あり, confirmed 0) など計 10 件。`data/results/` は 06-07 開始 → **アーカイブは未汚染**。backtest は require_confirmed で暗黙除外済 → 既存 backtest JSON の数値は本改修で変わらない (推定: 中止 race に confirmed_order=1 は 0 件を確認) |
| pytest (worktree) | `test_cancelled_races.py` + `test_build_daily_results.py` + `test_auto_predict_artifacts.py` **50 passed** |

## 依頼 5 点への回答

### 1. 改修前の実害
上表の通り。**金銭 0 円**、**的中率 N 水増し 2 倍**。中山 ◎ には朝オッズも EV も無く (odds_snapshots 0)、
`require_market=True` で買い側は元から外れるため、suspended が解けていても実額は 0 だったと推定。
ただし 2026-02 雪の 42R は odds があり、当時 daily results が稼働していれば買い候補が -100 円/件で計上され得た。

### 2. 「0 円で残す」vs「行ごと消す」 — 回収率の分母
`profit_loss_yen_100unit` だけが `evaluable` でゲートされ、**`bet_candidate` は HTML 由来のまま True が残り得る**
(`build_daily_results.py:708,733`)。行を残す方針は正しい (監査記録) が、分母を `count(bet_candidate)` で取る集計は
中止分を「損益 0 の賭け」として含み、ROI を 100% 側へ引き寄せる (payout 合計/賭け数で取れば逆に下振れ)。
現状 repo 内の唯一の読み手 `scripts/analyze_misses.py:170-173` は winner 不在で skip するため実害なし。
→ **留保 1**: `stake_yen_100unit` (= 100 if bet_candidate and evaluable else 0) を追加し、分母を profit と同じゲートから導く。

### 3. coverage 分母を eligible にした判断
new = covered/eligible、old = covered/scheduled、eligible ≤ scheduled なので **new ≥ old が恒等的に成立**。
「中止を除いたら 0.8 を割る」日は存在し得ない (ゲートは緩くなる方向のみ)。9/21 は old なら 12/24=50% で
実施 12R の予想を落としていた。全中止日は専用 skip (`auto_predict.py:347-352`)。妥当。
反証として「中止フラグの誤付与で実施レースが分母からも消える」を検討: NULL は残す設計 (`db.py:92`) で
取込途中は守られるが、誤って '9' が付いた場合は静かに消える。4 値ログ (scheduled/cancelled) で事後検知可能。

### 4. 利用者の誤読リスク (9/21 に中山だけ無い)
生成側は `sql_evaluable_race()` で中山を描画しない (`web/generator.py:323`) が、**HTML にも Discord にも
「中山 12R は中止」の一文が無い**。`_completion_message` は `(12R, version)` のみ (`auto_predict.py:238-260`)。
金銭影響は無い (観察専用、買い候補 0) が「生成失敗 / 半分欠落」と誤読され、手動再生成を招く。
→ **留保 2**: 完了通知 payload/本文と HTML ヘッダに `cancelled` 数と場名を出す (`race_cancellations` は馬単位の
取消のみで開催中止は入らない → `races.data_div='9'` から場別集計)。

### 5. 5 属性で N 水増しを防げるか
`prediction_issued` (常に True、情報量ゼロ) / `race_status` / `actual_execution_date` / `evaluable` /
`evaluation_exclusion_reason` は「予想した N」と「評価した N」の分離に必要条件は満たす。不足は 2 点:
(a) manifest `counts.evaluation_summary=320` が evaluable/excluded に分かれておらず、最上位の集計から水増しが見える
(`build_daily_results.py:836-838`)。(b) 順延先 (9/22 中山) は DB 上は別レース。`actual_execution_date` が空なので
9/21 の予想を 9/22 の結果へ結合してはならないことが暗黙。属性名からは「後で埋まる」と読める。
→ **留保 3**: manifest に `evaluable_rows` / `excluded_rows`、`race_status` に `POSTPONED` を追加し
「順延先レースへの結合禁止」を docstring に明記。

## 項目別

- **回収率 (損益会計の正しさ): 4/5** — profit のゲートは実測で正しい (CANCELLED 161 行すべて 0)。留保 1 (stake 列不在、
  bet_candidate が未ゲート)。収益エッジの主張は無く、段階は **観察用** のまま。
- **EV 計算の整合性: 4/5** — 不変。参考所見: 中山 ◎ 12 頭は市場情報ゼロで発行 (EV 空欄)。`require_market` が買い側を守る。
- **Kelly / 資金管理: 4/5** — 不変 (suspended=True `config.py:568`)。回帰なし。
- **買い目フィルタの実用性 / 検証集合=表示集合: 4/5** — backtest `list_races` / generator / monitor / accuracy を単一述語で
  統一、AST ベースの強制テストあり。留保 4: `tests/test_cancelled_races.py:274-276` の免除判定が
  `"data_div" in sql` を含むため、`SELECT ..., data_div FROM races` と列挙するだけで述語なしでも通る
  (allowed 登録が形骸化)。免除は allowed 本文一致のみにすべき。
- **不確実性開示 / 3 段階区別: 4/5** — 5 属性は実測で全行に付与。留保 2, 3。参考所見: `would_be_candidate`
  (紙運用の仮想判定) は計算されるが predictions.csv / evaluation_summary.csv のどちらの列にも書かれない
  (`build_daily_results.py:617,735` vs 列定義 776-801) — 本改修以前からの dead field。

## 停止条件チェック

- [x] git_sha / rule_version / env_overrides — N/A (backtest JSON 生成なし)。manifest は builder_git_sha/dirty を記録
- [x] baseline paired 比較 — N/A (収益主張なし)
- [x] market_snapshot counts — N/A
- [x] payout 欠損 race の扱い — 中止は payouts 0 件 (実測 payouts=12 = 阪神のみ)、evaluable=False で明示
- [x] 専門領域別停止条件 (単勝/複勝混同、1 件依存、180% 混同、CI 下限 100% 未満を利益扱い) — いずれも不抵触 (収益主張なし)

## 反証の試み

- 「金銭実害 0 円」に対し、suspended 解除時を想定 → 中山 ◎ は EV/朝人気が空欄で `require_market` により買い候補不可。
  成立。ただし 2026-02 雪 42R は odds あり → 当時 daily results があれば -100 円/件が計上され得た (未発生、アーカイブは 06-07 開始)。
- 「coverage 分母変更で予想を落とす日が増える」→ new ≥ old の恒等式で不成立。
- 「既存 backtest 数値が変わる」→ 中止 race に confirmed_order=1 が 0 件のため require_confirmed 経路では不変。
  `require_confirmed=False` の経路は未検証 (推論)。

## 主な改善提案

1. **stake 列で分母を同じゲートに** — `build_daily_results.py:708` 付近で `stake = 100 if bet_candidate and evaluable else 0`
   を `stake_yen_100unit` として eval_rows と列定義 (792-801) に追加。ROI = Σpayout / Σstake が中止に汚れなくなる。
2. **中止の開示** — `auto_predict.py:228-260` の payload/本文に `cancelled` (場別) を追加、`web/generator.py` の日ヘッダに
   「中山 1-12R 中止 (data_div=9)」を 1 行。誤読による手動再生成を防ぐ。
3. **強制テストの抜け道を閉じる** — `tests/test_cancelled_races.py:274-276` の `or "data_div" in sql` を削除し、
   免除は allowed 完全一致のみに。

## 前回からの差分

- 指示にあった `20260921_0040_jst_date_unify` は親リポ・worktree のどちらにも存在しない (`find` で 0 件)。
  直近の本 agent 採点は `20260919_2100_notify_dedup__profitability-judge.md` (4.0 / PASS)。
- 回収率 4 → 4 (会計は正しくなったが stake 未ゲート) / EV 4 → 4 / Kelly 4 → 4 / フィルタ 4 → 4 / 開示 4 → 4。
- 前回判定 PASS → 今回 PASS。戦略段階は **観察用** で変わらず (CI 下限 100% 超の証拠なし、実弾候補ではない)。
