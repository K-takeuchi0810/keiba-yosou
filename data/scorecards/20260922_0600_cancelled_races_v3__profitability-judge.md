# 収益性 / 投資判断専門家 採点 — 中止レース v3: 払戻待ちの独立状態化 + planned/settled 分離 (worktree `data-div-cancelled-20260922`, commit 7f5d8de)

## 判定: PASS

**改修タイプ**: type-B (答え合わせ CSV の会計定義変更、`BUY_FILTER_DEFAULT` / calibrator / weights / Kelly 不変。
`git -C <worktree> show 7f5d8de --stat`: db.py, scripts/build_daily_results.py, tests/ 3 本)。
P25 固有ゲート (2026 holdout ROI 180% / CI 下限 / bonus_candidate / paired baseline) は **N/A (対象外)**。
**subagent CWD 限定運用での評価** (worktree 絶対パス + `git -C`。親リポ main には未反映、HEAD=7f5d8de 固定・clean を確認)。

**理由**: 実データ 2 日分 (9/21 320 行・9/22 161 行) を新コードで scratch 生成し、金額 3 列 (profit / planned / settled)
を独立再導出 → **不一致 0、不変量違反 0**。「賭けたが未決済」は planned=100・settled=0・reason 非空、「賭けていない」は
planned=0 で監査上区別できる。変異 7 種のうち 6 種を既存テストが撃墜。停止条件抵触なし。生存変異 1 件と横穴 2 件は
いずれも現状で実害 0 円 (下記留保)。前回留保 1 (stake 未ゲート) は解消。

**根拠ファイル**: `scripts/build_daily_results.py:686-689,731-778,824-835`, `db.py:112-139`,
`tests/test_build_daily_results.py:347-500`, `tests/test_cancelled_races.py:603-650`,
scratch `scratchpad/r0921/`, `scratchpad/r0922/evaluation_summary.csv` (本番 `data/results/` には書いていない)

**次アクション**: main へ反映可。次サイクルで (1) `tan_payout1>0` ガードの行を持つ fixture 追加 (生存変異 M3)、
(2) 馬単位の 取消/除外 (返還) を `refunded` として settled 0 に、(3) `would_be_candidate` 列出力 (P2)。

## 総合: 4.2 / 5 (参考スコア)

## 実測 (このセッション。DB は `mode=ro` URI で SELECT のみ)

| 項目 | 実測値 |
|---|---|
| 9/21 新コード出力 | 320 行 = CANCELLED 161 (reason=cancelled) / RUN 159 (resolved+payout)。`result_not_yet_available` 0 |
| 9/22 新コード出力 (12:00 頃) | 161 行 = evaluable 145 / `result_not_yet_available` 16 (12R 16 頭、発走 16:10 前)。payout_pending 0 |
| 金額 3 列の独立再導出 | 481 行 全一致。settled<=planned / 非evaluable 行の settled=profit=0 / evaluable と reason 空が同値 / actual_execution_date 一致 — 違反 0 |
| bet_candidate=True | **両日 0 件** (`config.py:568 suspended=True`)。planned=settled=profit 合計 = 0 / 0 / 0 円 |
| ◎ 的中 (evaluable のみ) | 9/21 阪神 3/12 (payout 280+270+140)、9/22 中山 2/11 (180+140)。n は 100 に遠く CI は語れない |
| 中止 9/21 中山 | `races.data_div='9'` 12R、confirmed 0、payout 行 0 → 永久除外で正しい |
| 9/22 速報段階の race | 7R,11R `data_div='4'` (5 着まで) / 8R,9R `'3'` (3 着まで) が **evaluable=True**。各 9-13 頭が confirmed_order=0 のまま |
| payouts.data_div | 9/22 全 11 行 `'1'` (速報)。9/19-9/21 の 60 行も `'1'` (races は `'6'`)。過去分 2,490 行は `'2'` (確定、月曜 `'7'` と同期) |
| payout 行あり・tan_payout1 空/0 | 全年で **0 行** (M3 の実データ露出なし) |
| 単勝同着 (tan_horse_num2 あり) | 2021-2026 で年 2-9 件。builder は tan_horse_num1 のみ展開 (既存仕様) |
| 馬単位 取消/除外 (abnormal 1/3) | 2026 年 210 頭、うち人気 1-3 位 **7 / 9,513** (0.07%) |
| CSV 消費者 grep | planned/settled/profit_loss を読む production コードは **0 件** (analyze_misses は evaluable/reason のみ、webapp/monitor は不使用) |
| pytest (worktree) | 3 ファイル **75 passed**。変異 7 種: 6 撃墜 / **1 生存 (M3)**。各変異は 1 つずつ当て即復元、`git status` clean 確認 |

## 依頼 5 点への回答

### 1. 回収率が歪まないか (planned を分母にする経路)
`planned_stake_yen_100unit` / `settled_stake_yen_100unit` / `profit_loss_yen_100unit` を読む消費者は repo 内に **存在しない**
(`analyze_misses.py:177-183` は evaluable/reason のみ、`webapp/` `scripts/monitor.py` `web/generator.py` は CSV を読まない)。
よって誤経路は 0 だが、裏返せば **「settled が分母」という規約はまだコードで強制されていない**。列名と
`build_daily_results.py:764-769` のコメントだけが守り。将来の集計 helper は sum(profit)/sum(settled) を単一関数に閉じ、
`planned` を受け取らない signature にすること (提案 3)。

### 2. 払戻待ちを 0 円決済にしていないか
していない。`profit` と `settled` は同じ `bet_candidate and evaluable` でゲート (`:732,:768`)。払戻待ち行は
planned=100 / settled=0 / profit=0 / reason=`payout_not_yet_available` で、「賭けていない」(planned=0) と区別できる。
fixture でも production `main()` 経由で固定 (`test_a_finished_race_without_payouts_is_not_a_loss`)、変異 M5/M6 撃墜。
**ただし「決済済み」の定義が緩い**: `payout_resolved` は payouts 行の存在 + `tan_payout1>0` であり、`payouts.data_div='1'`
(速報) を受け入れる。9/22 は全 11R が速報払戻で evaluable になった。降着・失格で単勝が付け替わると速報から確定で
金額が変わるが、JRA で年数件・かつ現状 stake 0 なので留保に留める。

### 3. 9/21・9/22 実データ
上表。9/21 は前回と同じ CANCELLED 161 / RUN 159 で金額 0。9/22 は 12R が `result_not_yet_available` (中止ではない、
一時状態) と正しく区別され、`data_div='2'` の未走 race に cancelled を付けていない。**速報段階 (3-5 着まで) の race を
evaluable にする設計**は単勝 P/L には無害 (勝馬と払戻は判明済) だが、`confirmed_order=0` が「未確定」と「着外」の
両義になる。着順分析の消費者向けに `races.data_div` (または `payout_data_div`) を CSV に併記すべき (提案 2)。

### 4. `would_be_candidate` dead field の優先度
**P2 (次 PR、マージ阻害ではない)**。理由: (a) 金銭影響 0 (仮想判定は planned/settled/profit のどこにも入らず、入れてはいけない)。
(b) しかし suspended=True の間 `bet_candidate` は常に False で、**戦略の反実仮想 N を CSV から復元できる唯一の列**が落ちて
いる (`:617,:759` で計算 → `write_csv` の列定義 `:805-809,:824-835` に無く `r.get(c)` で捨てられる)。8/22 以降の
紙運用の答え合わせが手元で再構成不能なのは観察プログラムとして損失。出力時は `would_be_planned_stake` 等の
**別名**で持ち、settled と混ざらない構造にすること。

### 5. 金額系回帰テスト + 変異
| 変異 | 結果 |
|---|---|
| M1 settled が evaluable を無視 | 撃墜 (`test_a_cancelled_race_books_no_loss_through_main`) |
| M2 profit が evaluable を無視 | 撃墜 (同上) |
| **M3 payout_resolved = 行存在のみ (`tan_payout1>0` 削除)** | **生存**。fixture `with_payout=False` は行そのものが無く、「行あり・金額 0/空」を持つケースが無い |
| M4 planned も evaluable でゲート | 撃墜 (planned=="100" の assert) |
| M5 payout_resolved = result_resolved | 撃墜 (`test_a_finished_race_without_payouts_is_not_a_loss`) |
| M6 is_evaluable が has_payout を無視 | 撃墜 (同上) |
| M7 exclusion_reason の分岐順入替 | 撃墜 (truth table) |
M3 は実 DB に該当行 0 のため現状無害だが、HR 取込途中 (行 INSERT 後に金額列 UPDATE) が起きればガードは意味を持つ。
守るなら fixture を追加する (提案 1)。

## 項目別

- **回収率 (損益会計の正しさ): 4/5** — 3 列の会計は実データ 481 行で完全一致、3 状態を分母から正しく外す。前回留保 1 解消。
  減点: 馬単位 取消/除外 (返還) が settled=100 / profit=-100 で計上される横穴 (2026 年の人気 1-3 位で 7 頭、中止レースと
  同型の「賭けていない金の負け」)。速報払戻を決済扱いにする点も未開示。
- **EV 計算の整合性: 4/5** — 不変 (本改修は EV 経路に触れない)。
- **Kelly / 資金管理: 4/5** — 不変 (suspended=True、stake は 100 円固定の観察会計)。
- **買い目フィルタの実用性 / 検証集合=表示集合: 4/5** — 不変。前回留保 4 の `"data_div" in sql` 免除は AST ガード側から
  外れ `tests/test_cancelled_races.py:551` の SQL 本文テストに移っている (弱いが範囲外、参考所見)。
- **不確実性開示 / 3 段階区別: 4/5** — manifest が total/evaluable/excluded/理由別を分離 (`:866-877`、前回留保 3(a) 解消)。
  減点: 9 列追加なのに `manifest.warnings.schema` が `2` のまま (`:848`) で、06-07 から 08-16 の旧列 CSV と混在しても読み手が
  版を判別できない。`would_be_candidate` dead field は継続。

## 停止条件チェック

- [x] git_sha / rule_version / env_overrides — N/A (backtest JSON なし)。manifest は builder_git_sha / dirty を記録
- [x] baseline paired 比較 — N/A (収益主張なし)
- [x] market_snapshot counts — N/A
- [x] payout 欠損 race の扱い — 中止 = cancelled、着順あり払戻なし = payout_not_yet_available と明示、金額 0・分母外
- [x] 専門領域別停止条件 (単勝/複勝混同、1 件依存、180% 混同、CI 下限 100% 未満を利益扱い) — 収益主張がなく不抵触

## 反証の試み

- 「planned を分母にする経路が残っていない」→ 全 `.py` を grep、planned/settled/profit_loss の読み手 0 件 → **成立**
  (ただし規約はコード強制されていない)。
- 「払戻待ちは 0 円決済にならない」→ 実データ不変量 + 変異 M5/M6 → **成立**。
- 「未決済と未購入は区別できる」→ planned 列と reason 列の組で 4 通りが分離 → **成立**。
- 「決済済み = 確定払戻」→ payouts.data_div='1' (速報) を受け入れているので **不成立** (降着時に金額が変わり得る、年数件)。
- 「馬券返還はすべて除外できている」→ 開催中止のみ。馬単位 取消/除外 (2026 年 210 頭) は -100 計上 → **不成立** (現状 stake 0 で実害なし)。

## 主な改善提案

1. **M3 を殺す fixture** — `tests/test_build_daily_results.py::_run_main` に `payout_row_without_amount=True` を追加し、
   payouts 行を `tan_horse_num1='01', tan_payout1=0` で INSERT → `payout_resolved=="False"` / `settled=="0"` を assert。
2. **決済状態の透明化** — `build_daily_results.py:759` 付近に `race_data_div` (races.data_div) と `payout_data_div`
   (payouts.data_div) を列出力。速報 (`'1'`) で evaluable になった行を事後に見分けられる。あわせて `:848` `schema` を 3 へ。
3. **馬単位返還を `refunded` に** — `horse_races.abnormal_code in ('1','3')` (取消/除外) かつ bet_candidate の行は
   `exclusion_reason='refunded'`・settled=0・profit=0。`db.exclusion_reason` に第 4 引数を足し truth table を 16 セルへ。

## 前回からの差分

- 前回 (b1733d7) 4.0 / PASS → 今回 4.2 / PASS。回収率 4→4 (留保 1 解消、返還横穴を新たに減点) / EV 4→4 / Kelly 4→4 /
  フィルタ 4→4 / 開示 4→4 (留保 3(a) 解消、schema 版未更新を新たに減点)。
- 戦略段階: **観察用** で不変。買い候補 0 件・収益主張なし・CI 下限 100% 超の証拠なし → 紙運用・実弾候補のどちらでもない。
