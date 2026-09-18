# データパイプライン技術者 採点 — 2fb703a Phase 0.5-3 (Fundamental Model + 標本欠陥 2 件)

## 判定: HOLD

**理由**: 改修タイプは **type-B** (分析スクリプト新設、取得/ingest/schema 不変。`git show HEAD --stat` 12 files 全て新規)。P25 固有ゲート (fresh odds スケジューラ / coverage JSONL / market_snapshot / bonus_candidate) は **N/A (対象外)**。停止条件抵触は無いが、(1) 発見 (b) の原因診断が誤り (「結果未取込」ではなく **レース中止 data_div='9'**)、(2) 学習特徴の累積が **バイト破損した 1986-1992 / 2020 の行** を読んでおり報告値 (LogLoss 0.22798 等) がその上に立っている、(3) 成果物の `git_sha` が生成コードを含まないコミットを指す。いずれも追加 run で再評価可能。
**根拠ファイル**: `scripts/fundamental_model.py:83-121,146-152`, `db.py:319-322,437-451`, `predictor/provenance.py:62`, `docs/PHASE05_RESULTS.md:217-221`, 実測 SQL
**次アクション**: 2021 未満を累積から隔離 (or JVGets 再取得) して再 fit → 結果差分を PHASE05_RESULTS に追記。(b) の記述を「中止レース」に訂正し `data_div='9'` を明示除外に変更。

## 総合: 3.0 / 5 (前回 3.4、**-0.4 警告閾値超**)

## 質問への回答

**1. (a) 世代差の原因** — 取込コードの変更ではなく **オッズ供給源の差**。

- 2021-2025 の `win_odds` は SE 確定レコード (data_div 7) 由来のみ (`odds_fetched_at IS NOT NULL` が 2025 以前は **0 行**)。JV-Data 仕様で除外馬の SE 単勝オッズ欄は 0 (返還)。code 3: 2024 0/102、2025 0/111 が has_odds。
- 2026 は fresh odds (0B30/0B31) が発走前に `update_win_odds` で書き込み、その後の SE 確定 upsert は `CASE WHEN excluded.win_odds > 0` ガード (`db.py:319-322`) で 0 では上書きしない → 残る。実測: 2026 code 3 で has_odds 52 行は **全 52 行が odds_fetched_at 非 NULL・dataspec 0B30/0B31**、残り 38 行は未取得。
- 遡及是正は **不可能** (2021-2025 の発走前オッズはどこにも存在しない。odds_snapshots は 2026-05 以降)。Fundamental はオッズ不使用なので影響なし。市場比較を過去年に広げる場合は `runner_set_mismatch` で fail-closed に落ちる、これは正しい挙動。
- 補足: `abnormal_code='2'` は 2021-2026 に **0 行**。「発走除外を残す」分岐は実データで未検証 (code 3 は 496 行)。

**2. (b) 57 レースの実体 = レース中止**。DB 直接確認: 57 レース全てで `horse_races.data_div='9'` かつ `races.data_div='9'`、`starter_count=0`、`registered_count=n`、payouts 0、odds 0。内訳 2024-08-25 新潟12R / 2024-11-02 京都8R / 2025-02-08 京都全12R / 2025-05-31 東京9R / 2026-02-07〜09 東京・京都・小倉 42R。年別 2:13:42 = 57、頭数 31+174+567 = 772 (取消 1 頭を先に落として 771、一致)。

- **再取込では埋まらない** (raw `SESW20250531…` は 2026-06-29 に取込済で中身が 9)。
- 現コードのプロキシ (`confirmed_order=1` 不在) は 2021+ では同じ集合を選ぶが、原因ラベル (`skip_race_without_result`、コメント、docs、commit message、test docstring) が誤り。DB に明示信号 (`data_div='9'`) があるのに使っていない。将来「未取込だから再取得」と誤対応する温床。

**3. 1986-1992 / 2020 は「着順が無い」ではなく BSTR 破損のゴミ**。

- DB 実測: 馬名文字化け率 1986 36,374/36,375、2020 48,413/48,427 (2021 は 0)。2020 の `confirmed_order>18` が 13,510 行、`abnormal_code` に `'@'` 9,695 / `'?'` 6,337、`horse_weight='@?@'`、age 40/50、starter_count 不一致 2,415/3,466。
- 原因: `data/raw_old_bstr/RACE/SEVM*` は **全年代** で SJIS 先頭バイトが `'?'` に置換 (名前 36 byte 中 `?` 18.0 個、1986〜2024 で同率) かつ byte 長が伸びて後続フィールドがずれる (2021 の old_bstr 版 3,702,084 B vs JVGets 版 3,652,920 B、md5 不一致)。現行 parser でこの raw を再パースしても同じゴミが出る (実行確認)。2021+ が正しいのは `data/raw/RACE/SEVM2021…` 以降の JVGets 版が 2026-06-29 に上書きしたため。**1986-2020 の byte 正常 raw は存在しない** → 修復は JV-Link 再取得のみ。
- 現状の扱いは **不十分**。「勝ち馬のいないレースをスキップ」は 2020 の 2,715 レースを落とすが、ゴミ着順で偶然 `confirmed_order=1` が付いた 751 レース (847 行) は通過し、`blood_register_num` (offset 31-40、破損前) は正しいため **本物の馬に偽の着順・偽の勝利が付く** (h_last_finish / h_best_finish / h_recent3 / h_wins / s_winrate)。さらに 2019 はデータ無し (17 行)、2020 大半スキップで h_days_since・h_starts が 2021 学習行で系統的に歪む。
- 推奨: `build_dataset` の SQL に `h.race_year >= '2021'` の信頼下限を入れ、2021-01-01 左打切りを docs に明記 (打切りは全期間に一様でない点も)。再 fit の差分を報告。根治は 1986-2020 の JVGets 再取得 + `ingested_files` へ parser_version 列追加。

**4. build_dataset の I/O**: 実測 25.2 s (検証窓 2024-25、94,922 行出力、521,356 行走査)。うち SQL は 1.7 s (`EXPLAIN`: `SCAN h`、`race_year||race_month_day` と `CAST(track_code)` が index を殺す) で残りは Python 累積。fit で 2 回 + eval で 1 回 = 約 75 s。**I/O 問題ではない**。設計上の無駄は 3 回の全履歴リプレイと `finished_races` の 2 度目走査。1 パスで生成し日付で分割すれば 1/3。項目 3 の下限 2021 を入れれば走査行も 521k → 235k。

**5. 棚卸し (JRA、他に「行はあるが実体がない」)**:

- `data_div='9'` 中止: races 2020:10 / 2024:2 / 2025:13 / 2026:42、horse_races 145/31/174/567 行
- `data_div='1'` 出走馬名表 (未来): 72 行、2026-09-19/20/21。正当だが結果系データセットは必ず除外要
- RA あり SE なし: 1992:141 / 1993:7 / 1994:9 / 1998:1 レース
- SE あり RA なし (孤児): 1992-2019 に年 2-32 行、計約 350 行 (INNER JOIN で自然脱落)
- 勝ち馬あり payouts なし: 2016:1 / 2018:1 / 2019:2 (孤児期のみ、2021+ は 0)
- `confirmed_order>0 AND abnormal_code IN (1,2,3)` 10,510 行 — 全て破損年 (2021+ は 0)
- 健全: 重複レース 0、`horse_num='00'` 0、血統番号空 0、2021+ 着順ありオッズなし 0

## 項目別 (type-B 汎用軸に読み替え)

- **DB 読み取り規律・副作用: 4/5** — `mode=ro`、封印ガードを build_dataset 内部に配置、新規 tests 14 件 pass (実行)。留保: テスト DDL に `data_div` が無く真因を表現できない。
- **標本定義の正しさ: 3/5** — 除外の効果は 2021+ で正しい (件数一致) が原因誤診、明示信号未使用。競走除外 (code 3、496 行) を `hn_[bn] += 1` / `hlast` 更新で「出走」に数える。走っていない馬の分母に入る。
- **世代差の理解 (a): 3/5** — 「2/3 を残す」判断は妥当。反証 (2026 の取消 3 頭に odds あり) は取得時刻 11:06→発走 14:15 / 前日 20:00 / 08:45→17:30 で T−10 より前、不成立。ただし世代差を commit が未説明のまま。
- **過去データ品質 / 復旧可能性: 2/5** — 破損年が特徴に流入、byte 正常 raw 不在、`ingested_files` に版情報なし。改修前からの欠陥だが本改修の報告値の土台。
- **再現性 / 成果物: 3/5** — `git_sha=c19e716, git_dirty=false` だが生成スクリプトは c19e716 に存在しない。前回 scorecard が挙げた「成果物が自分について嘘をつく」類。件数 931/12,533 は整合。

## 停止条件チェック

- [x] git_sha 記録あり (ただし誤導的) / rule_version・env_overrides は type-B で N/A
- [x] baseline paired 比較: N/A (採用判断でない)
- [x] market_snapshot counts / payout 欠損: N/A
- [x] DB 書き込み副作用なし (grep で INSERT/UPDATE/DELETE 不在、`mode=ro`)
- [x] fresh odds スケジューラ / coverage JSONL: N/A (取得不変)

## 反証の試み

- 「57 レースは結果未取込で再取込で埋まる」→ **不成立** (全行 data_div 9、payouts 0、raw 取込済)
- 「取消は T−10 配信から消えている」→ 3/42 に odds ありも取得は T−10 より前 → 主張は維持
- 「2020 は着順が欠けているだけ」→ **不成立** (文字化け 99.97%、着順 98 まで分布、raw 自体が破損)
- 「raw から再パースすれば直る」→ **不成立** (現行 parser × old_bstr raw で同じゴミを再現)

## 主な改善提案

1. **信頼下限と明示除外** — `scripts/fundamental_model.py` の SQL に `AND h.race_year >= '2021'` と `AND r.data_div <> '9'` を追加、`finished_races` プロキシは保険に降格。`stats` キーを `skip_cancelled_race` に改名。docs と test docstring を訂正。再 fit して LogLoss 差分を記録。
2. **競走除外を出走に数えない** — 更新ブロックを `if abn not in {'2','3'}` で囲む (標本には残す)。
3. **provenance の dirty 判定** — `predictor/provenance.py:62` を `--untracked-files=normal` にし `scripts/ predictor/ tests/` 配下の `??` を dirty 扱い。長期: `ingested_files.parser_version` 追加 + SE ingest 時の妥当性ゲート (馬名 cp932 decode / `confirmed_order <= 28` / `abnormal_code` 数字)。

## 前回からの差分

- 前回 `20260914_1600_f3_sealed_holdout`: **3.4 / HOLD**。今回 3.0 / HOLD (-0.4)。後退理由は本改修が「標本欠陥 2 件是正」を掲げつつ、より大きい第 3 の欠陥 (破損年の流入) と (b) の誤診を含むため。
