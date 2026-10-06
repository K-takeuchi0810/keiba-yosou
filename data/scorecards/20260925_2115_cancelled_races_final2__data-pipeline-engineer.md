# データパイプライン技術者 採点 (最終ゲート再レビュー) — 3cd1871 中止レース data_div='9' 対応シリーズ 最終是正版

> **subagent CWD 限定運用での評価 (worktree 絶対パス指定)**。対象は
> `C:\Users\kizun\dev\keiba-yosou\.claude\worktrees\data-div-cancelled` の **HEAD `3cd1871`** に固定
> (開始・終了時に `git -C <wt> rev-parse HEAD` 一致、`git status --short` 0 行を確認)。
> 実行実験はすべて隔離コピー (`git archive 3cd1871` の `iso` + `git clone` で作った `isogit`、
> いずれも scratchpad `gate2_pipeline/`) で行い、変異は 1 件ごとに `git checkout --` で復元。
> 実 DB `data/keiba.db` は `mode=ro` で読取のみ。本番 checkout の `data/results/2026-09-2{1,2}/` は
> 未変更 (CSV 0 本のまま)。封印データは参照していない。

## 判定: PASS (留保 2 件、次サイクルの HOLD/FAIL 条件として明記)

**理由**: 依頼された重点 4 項目はすべて **実データで成立**。(1) production `build_daily_results` を
実 DB + 公開予想 HTML で実行し、9/21 = `cancelled 161 (中山 06) / evaluable 159 (阪神 09)`、
9/22 = `evaluable 161 / excluded 0`。返還馬 (阪神 4R #7, abnormal 3) は profit 0 / settled 0、
`actual_execution_date` は evaluable 行にのみ記入。(2) 滞留監視は実 DB で `OK`、9/19〜9/22 の
滞留 (9/23 時点 ERROR/72) が確定払戻の到着で **手動操作なしに解消** したことを確認、
9/21 は `中止 12 / 実施 12 / 払戻確定 12` で中止を数えない。検出範囲と表示窓の分離は
実 DB (`--days 14` と `--days 30` で status 同一) と変異 MP2 (撃墜) の両方で確認。
`PENDING_SCAN_FROM=20200101` は実 DB の payouts 年別件数 (1993〜2019 は 0 件、2020+ は
各年 races '7' 件数と完全一致) から妥当。(3) db.py の異常区分: JRA 2021+ の実データに
現れる区分は `0/1/3/4/7` のみ、`7` (降着) は 2 行とも着順あり (3 着) で「着順が付く」扱いが
正しい。`5` の追加は正しく、見落とし区分は **無い** (`2/5/6/8/9` は 2021+ JRA に 0 行)。
(4) 旧 CSV 21 ディレクトリの `horse_refunded` 欠落の実害は **◎ 1 レース** (2026-07-11 02-06、
bet_candidate False → 金額 0、的中率の分母 +1/564) に限定。停止条件抵触なし。
留保: (a) 監視スクリプトは **DB を開けないと未捕捉例外で exit 1 = WARN と同じコード** になり、
Task Scheduler からは「払戻が遅い」と「監視が壊れた」を区別できない (実測: 不在 DB →
`OperationalError`、破損 DB → `DatabaseError`、いずれも exit 1)。(b) 監視はどの Task Scheduler
タスク / .bat / .ps1 からも呼ばれておらず (登録タスク 10 件に参照 0、`register_*.ps1` に無し)、
現状は手動ツール。(a) は 3 行 + テスト 1 本、(b) は登録スクリプト 1 本で閉じる。どちらも
評価ロジック (本シリーズの主目的) の正しさには影響しないため PASS とするが、**監視を
スケジューラ登録する改修で (a) を同時に閉じなければ、その時点で FAIL** とする。

**根拠ファイル**: `db.py:128-198` (異常区分集合・`exclusion_reason` keyword-only)、
`scripts/payout_finality_monitor.py:82-83,108-176,179-222,225-253`、
`scripts/build_daily_results.py:544,681-731,753-818,904-918`、`scripts/analyze_misses.py:177-195`、
`tests/test_payout_finality_monitor.py:237,262-436`、`tests/test_build_daily_results.py`、
scratchpad `gate2_pipeline/bdr/0921|0922/{manifest.json,evaluation_summary.csv}`、`q1..q7.py`、
`mon_real.py`、`oldcsv.py`、`am_real.py`。

**次アクション**: (1) `payout_finality_monitor.main()` で `sqlite3.Error` を捕捉して
`status=MONITOR_BROKEN` を出力し **exit 3** (WARN=1 / ERROR=2 と衝突しない) にする + 不在 DB
のテスト (現状 MP3「DB 失敗を握り潰して OK」が全 test 素通り)。(2) `register_payout_finality_task.ps1`
を追加し、開催翌日 (月/火) 朝に `--json` で起動、exit≠0 を通知経路へ。(3) `latest_race_source_timestamp`
の `None` を「state ファイル無し / JSON 破損 / RACE キー無し」の 3 状態で分けて表示する
(docstring が約束する「供給遅れ vs 取込障害の切り分け」が None では成立しない)。
(4) 旧 21 ディレクトリの再ビルド (`supersedes_manifest_sha256` あり) — CSV は git 管理なので
tracked diff になる点を承知の上で。

## 改修タイプ

**type-B (答え合わせの状態モデル / 監視) + type-C (`db.py` 判定関数)**。今回差分
(`4867a0e..3cd1871`) は `db.py` / `analyze_misses.py` / `build_daily_results.py` /
`payout_finality_monitor.py` + tests のみで、`jvlink_client/` と取得系 (`fetch_fresh_odds.py`) に
変更なし。P25 固有ゲート (market_snapshot / bonus_candidate / paired backtest) は **N/A**。
fresh odds 取得運用はシリーズ全体 (`50fc046...3cd1871`) に `fetch_fresh_odds.py` の述語追加が
含まれるため、前回同様に実測して採点軸に載せる。

## 総合: 4.0 / 5 (参考スコア、前回 3.8 → +0.2)

## 項目別

- **述語設計 / 異常区分 / ingest 整合: 4/5** — 実 DB (JRA track 01-10) の `abnormal_code` 分布:
  **2021+ は `0` (着順あり 235,838) / `1` (取消 407、着順 0) / `3` (競走除外 588、着順 0) /
  `4` (競走中止 1,227、着順 0) / `7` (降着 2、着順 3)** のみ。`2 / 5 / 6 / 8 / 9` は 0 行。
  `REFUNDED={1,2,3}` / `NON_FINISHER={1,2,3,4,5}` は実データと矛盾せず、`7` を「着順が付く」に
  残したのは正しい (`db.py:139`)。`5` の追加で「失格馬 1 頭で永久に結果待ち」の穴は閉じ
  (変異 MP1「5 を外す」は `tests/` で撃墜)。**2020 年は別問題**: `abnormal_code` に `?` `@` `+`
  等の破損値が 17,105 行、`0` なのに着順 0 が 7,158 行あり、新定義で `result_final` になれる
  レースは **27 / 3,456** のみ (raw バイト破損、既知)。監視・評価とも 2020 は「永久に結果待ち」
  で沈黙するが誤警報にはならない。留保: `6/8/9` など未出現コードは「着順が付く」側に倒れる
  ので、将来 1 頭でも出ると同じ穴が再発する (改善提案 2 で汎用的に塞ぐ)。
- **評価経路 (4 段階 / 返還 / keyword-only): 4.5/5** — production `main()` 実行 (isogit、
  `builder_git_sha=3cd1871`、dirty=False): 9/21 320 行 → `{'cancelled': 161}` / evaluable 159、
  track 06 は全行 `race_status=CANCELLED`、`actual_execution_date` 空、planned/settled stake 0。
  阪神 4R #7 (abnormal 3) は `horse_refunded=True`、profit 0、settled 0。阪神 6R #15 (abnormal 4、
  競走中止、☆) は evaluable / order 0 / refunded False = 「走って負け」の設計どおり。9/22 は
  161 行すべて evaluable (payouts 12 レース全部 `data_div='2'`、9/23 時点の `payout_not_yet_final`
  から遷移済)。`payout_final` の keyword-only 化で `4867a0e` の fail-open は消えた
  (`db.py:156-157,194-195`、呼び出し側 `build_daily_results.py:759-762`)。`analyze_misses` を
  本番 `data/results` + 実 DB で read-only 実行: 564 レース / hit 117、`pick_finish=0` は 3 件で
  内訳 = 競走中止 2 (07-11 02-02 #11、08-08 07-09 #7: 設計どおり miss) + **競走除外 1 (07-11
  02-06 #5: 旧 CSV に `horse_refunded` 列が無いため miss 扱い)**。減点: `build_daily_results`
  は `sqlite3.connect(args.db)` (rw、`:544`) のまま — 読取専用経路は `mode=ro` にすべき
  (非回帰)。`race_results.csv` に `abnormal_code` が書き出されないので CSV だけから返還を
  再導出できない (evaluation_summary の `horse_refunded` が唯一の記録)。
- **滞留監視 (payout_finality_monitor): 3.5/5** — 実 DB: `OK`、**1.09 秒** で 2020 年以降
  728 開催日を走査 (性能問題なし)。9/21 行 `予定24 中止12 実施12 着順確定12 払戻確定12 評価可12`。
  自動解消: 9/23 の ERROR/72 レースが 9/25 に OK/0 (手動フラグなし)。`--days 14/30` で status・
  pending 件数が同一、`pending_scan_from` を JSON に含む、text は「※表示窓の外」を付ける
  (`:244-248`)。`PENDING_SCAN_FROM=20200101` の妥当性: payouts は 1986-1991 完備 (各年 races と
  同数)、1992 は 815/815、**1993-2019 は 0 件** (races は 1993:7 / 1994:9 / 1998:1 と 1954-1985 に
  約 170 件、着順ありも含む) → 下限を 1986 以前へ下げると永久 ERROR、2020 は payouts 3,456 =
  races '7' 3,456。下限は妥当。docstring の「1986-1992 は一部だけ」は実データでは 1986-1991
  完備 / 1992 のみ部分 (軽微な記述誤り)。減点 3 つ: **(a) DB 不在 / 破損で未捕捉例外 → exit 1
  (= WARN)** (実測)、docstring の「3 つの状態を混同しない」に反する。**(b) どのタスクからも
  呼ばれていない** (schtasks 10 件、`register_*.ps1` 6 本に参照 0)。(c) `latest_race_source_timestamp`
  は state ファイル不在 / JSON 破損 / キー無しがすべて `None` (実測 3 通り)、本番パスでは
  `20260925112831` を返す。
- **fresh odds 取得運用 (シリーズ持ち越し、type-C 要素): 4/5** — `schtasks`: `keiba-fresh-odds`
  前回 9/25 19:00 rc=0、次回 9/26 09:00 準備完了。`fresh_odds_coverage --last 7` (本番 JSONL を
  `--path` で read-only): 9/19 83/83 100% → 9/20 81/81 100% → 9/21 83/83 **55.4%** (旧コード、
  中止 中山 37 件が no_data) → **9/22 37/37 100%** (述語導入後、順延 中山 12R のみ eligible)。
  `lock_skipped=0`、`failed_reasons` は 3 日とも `-`。今回差分に取得系の変更は無く、前回
  実測どおり順延先は新 PK 行 (`0922`) として自然に列挙される。留保 (前回と同じ): 当日発表の
  中止を `races.data_div` へ反映する job は無い。
- **テスト / 変異耐性: 4/5** — isogit で対象 8 ファイル **181 passed / 1 skipped**。
  (`git archive` 木では 23 failed = すべて `git_provenance()` が `.git` 無しで abort する設計
  どおりの挙動。provenance 無しで artifact を出さないのは正しい)。自分で設計した変異 7 種:

| # | 変異 | 結果 |
|---|---|---|
| MP1 | `NON_FINISHER` から `5` を外す | 撃墜 |
| MP2 | 監視の検出を `shown_from` に再結合 (15 日で黙る旧挙動) | 撃墜 |
| MP3 | 監視 `build()` の例外を握り潰して `OK` を返す | **素通り** (DB 障害のテスト無し) |
| MP4 | 監視の確定判定を `== '2'` → `!= '1'` | 素通り (実 DB は全期間 `'2'` のみ格納、無害) |
| MP5 | bdr `races_with_payout` から `tan_payout1 > 0` を外す | 素通り (該当行 2020+ で 0 件、無害) |
| MP6 | 監視 pending を `executed - payout_final` に (結果待ちも鳴らす) | 撃墜 |
| MP7 | 監視 LEFT JOIN から kaiji/nichiji を落とす | 素通り (同日同場は単一開催、無害) |

  前回の M-A / M-D (述語無効化) は validation-auditor が実行型テストで撃墜済と報告しており、
  今回は自分の領域 (異常区分・監視・払戻確定) に絞った。MP3 だけが実害側の生存。

## 停止条件チェック

- [x] git_sha / rule_version / env_overrides — N/A (backtest JSON 生成なし)。bdr manifest は
  `builder_git_sha=3cd1871` / `builder_git_dirty=False` を記録
- [x] baseline paired 比較 / market_snapshot / bonus_candidate — N/A (type-B/C)
- [x] payout 欠損 race の扱い — `payout_not_yet_available` として明示 (`db.py:95,187-188`)
- [x] 専門領域 Hard Fail: `_wait_download_complete` / JVOpen rc / ingest rollback / 0 byte raw /
  lock / 発走時刻再判定 — **経路不変** (`jvlink_client/` 差分なし)
- [x] post-start snapshot 混入 — 9/21・9/22 とも manifest `post_start_stamped_rows=0`
- [x] スケジューラ記録 / coverage JSONL — あり (上記実測)
- [x] partial row を残す新経路 — なし (今回差分に DB 書込みなし)

## 反証の試み

| # | 主張 | 結果 |
|---|---|---|
| R1 | 9/21 は阪神 evaluable / 中山 cancelled に分かれる | **成立** (159 / 161、実 DB + 公開 HTML、production main()) |
| R2 | 9/22 は実施・着順確定・確定払戻の揃ったものだけ evaluable | **成立** (161 / 161、payouts 12 件すべて `'2'`) |
| R3 | 監視は 15 日放置しても黙らない | **成立** (MP2 撃墜 + `--days 14/30` 同一 status) |
| R4 | 監視は中止を pending に入れない | **成立** (9/21 行 中止 12 / pending 0) |
| R5 | `PENDING_SCAN_FROM=20200101` より前に下げると永久 ERROR になる | **成立** (1954-1998 に payouts 0 の着順ありレースが存在) |
| R6 | 失格 5 以外に見落とし区分がある | **不成立 (見落とし無し)**: JRA 2021+ は `0/1/3/4/7` のみ |
| R7 | 監視は「壊れた」と「遅い」を exit code で区別できる | **不成立**: DB 不在 / 破損とも exit 1 = WARN |
| R8 | 旧 CSV の `horse_refunded` 欠落は無害 | **ほぼ成立**: ◎ 1 レースが miss 扱い (金額 0)。中止レースは旧 CSV 期間に無し |

## 主な改善提案 (優先順)

1. **監視の障害コード分離** — `scripts/payout_finality_monitor.py:231` の `build()` 呼び出しを
   `sqlite3.Error` で捕捉し、`payout finality: MONITOR_BROKEN <err>` を出力して **exit 3** を返す。
   `EXIT_CODES` に `MONITOR_BROKEN: 3` を追加。テスト: 不在パスで `main()` が 3 を返す
   (MP3 を殺す)。
2. **未知の異常区分 / 永久結果待ちを汎用に鳴らす** — `race_day_counts` に
   `result_pending_over_48h` (実施済み・着順未確定・開催日 +48h 超) を追加し ERROR に含める。
   区分コードの列挙 (`5` の追加のような事後対応) に頼らず、失格・破損コード・行欠落を
   1 つの経路で検出できる。`tests/test_payout_finality_monitor.py:237` の「結果待ちは
   pending でない」は「48h 以内は pending でない」に条件を絞る。
3. **監視のスケジューラ登録** — `scripts/register_payout_finality_task.ps1` (既存
   `register_fresh_odds_healthcheck_task.ps1` と同型) を追加し、月・火 09:30 に `--json` で起動。
   1 と同じ PR で行う (1 無しで登録すると DB 障害が WARN として静かに埋もれる)。

## 前回からの差分

- 述語設計 / ingest 整合: 4 → 4 (±0)。異常区分の実データ照合を追加、`5` の追加は正しい
- 生成経路 (generator / auto_predict): 前回 4、今回差分なし → 評価経路の項へ統合
- 評価経路: 4 → 4.5 (+0.5)。前回留保「resolved が払戻を見ない」は 4 段階化で解消、
  keyword-only で fail-open も解消、実 2 日分で production 実行確認
- fresh odds 取得運用: 4 → 4 (±0)。9/22 に述語の効果 (37/37 100%) が実測で出た
- テスト / 変異耐性: 3 → 4 (+1)。前回の M-A / M-D は実行型テストで撃墜済、今回の自前 7 変異中
  実害側の生存は MP3 のみ (1 点超の上昇の根拠: 上表)
- 新規軸「滞留監視」: 3.5 (初回)
- 前回判定 PASS (留保つき) → 今回 **PASS**。validation-auditor の HOLD 条件のうち私の領域に
  掛かるもの (窓依存 / 返還 ◎ / 失格) は実データ + 変異で閉じたことを確認
- **今回の新宣言**: 次サイクルで監視がスケジューラ登録されているのに DB 障害が exit 1 のまま
  なら **FAIL**。旧 21 ディレクトリを再ビルドしないまま `analyze_misses` の的中率を対外報告に
  使うなら HOLD 上限

## 参考所見 (スコープ外、越権採点しない)

- 2020 年の JRA `horse_races` は raw バイト破損で 3,429 / 3,456 レースが新定義の
  「着順確定」に到達しない。`backtest.list_races` の 2020 窓は `confirmed_order>0` の副作用で
  すでに減っているはずだが、baseline 再凍結時は 2021 以降に窓を切ることを勧める
  (validation-auditor 領域)
- 旧 CSV 21 本のうち 108 レースが `no_result` (結果取込前にビルドされた土曜生成の既知問題)。
  本シリーズとは無関係だが、再ビルドすれば新列とともに解消する
