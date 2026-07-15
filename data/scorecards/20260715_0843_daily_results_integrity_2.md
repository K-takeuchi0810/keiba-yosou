# 採点 2026-07-15 08:43

**改修内容**: build_daily_results.py の 3 バグ修正 (オッズ/人気連結破損・horse_num='00' 幽霊行除外・race_num ゼロ埋め統一) + tests 新規 3 件 + 2026-07-12 CSV/manifest 再生成
**対象ファイル**: `scripts/build_daily_results.py`, `tests/test_build_daily_results.py`, `data/results/2026-07-12/*.csv`, `data/results/2026-07-12/manifest.json`, `data/results/2026-07-12/features_00_contamination.md`

> 注: 本 scorecard は正規の expert-review 機構 (rubric 準拠 7 subagent 並列) による採点。
> 同トピックの先行ファイル `20260715_0039_daily_results_integrity.md` は外部ツール (OpenAI Codex) が
> rubric 外の一般基準で単独作成した**参考値**であり、本採点で置換する (validation-process-auditor 所見参照)。
> 改修コード自体も Codex 作。経緯 artifact: `data/results/2026-07-12/audit_findings.md`,
> `docs/codex_audit_20260712_results.md`, `docs/codex_fix_20260712_results.md`。

## 総合スコア (項目平均) の推移

| 専門家 | 今回 | 前回 | 差分 | 判定 |
|---|---:|---:|---:|---|
| GUI / UX 監査人 | 3.6 | 3.6 | ±0 (GUI 無変更・維持。CSV 参考採点 3.8) | PASS |
| モバイル HTML レビュアー | 4.6 | 4.6 | ±0 | PASS |
| 予想ロジック分析官 | 4.3 | 4.0 | +0.3 | PASS |
| 収益性ジャッジ | 4.0 | — (前回 PASS、数値比較対象なし) | — | PASS |
| データ基盤エンジニア | 3.4 | — (比較不適) | — | **HOLD** |
| コード品質レビュアー | 4.0 | — (正規 rubric での直近比較対象なし) | — | PASS |
| 検証プロセス監査人 | 4.3 | 3.66 | +0.64 | PASS |
| **平均 (今回)** | **4.03** | | | 6 PASS / 1 HOLD |

- 0.3 以上の後退なし (全項目維持または改善)。
- **HOLD (データ基盤) の解除条件**: ① manifest に `builder_git_sha` / `git_dirty` / 再生成履歴を追記、② 本改修をコミットして sha 確定、③ 上流 '00' 掃除の実装判断。「数分で補完可能な軽い不足」と明記あり。
- Codex 版 scorecard (平均 4.30) と本採点 (4.03) の差は、主に manifest の builder 出所欠落・HTML ファイル名/footer の git sha 不一致・上流 '00' 未対策を Codex 版が見ていなかったことによる。

## 各専門家の所見

### GUI / UX 監査人

## 判定: PASS

**理由**: 改修タイプ = **type-B** (日次成果物生成スクリプトの誤読バグ修正。予測ロジック・GUI とも不変)。`git diff --stat HEAD -- gui/app.py web/` は空 = GUI/HTML 回帰ゼロを実測。よって本職域スコアは前回維持とし、CSV 成果物の誤読リスク監査 (親指示による参考採点) でも停止条件抵触なし。3 バグ修正はすべて再生成 CSV 上で自分で実測確認した。
**根拠ファイル**: `scripts/build_daily_results.py:172-176, 355-357, 385-390`、`data/results/2026-07-12/*.csv`、`data/results/2026-07-12/manifest.json`、`tests/test_build_daily_results.py` (3 passed 実測)
**次アクション**: 下記改善 1 (horse_num 表現統一) を次回 CSV 再生成前に。

## 総合: GUI 本体 = 前回維持 / CSV 成果物 (参考採点) = **3.8 / 5**

- GUI 本体: 前回 3.6 (20260703_1058 p26 swap 時、type-D 実評価の最終値) を維持。JS パース確認は CONTROL_HTML 無変更のため N/A (agent 定義どおり)。
- P25 固有ゲート (fresh/stale counts 表示・補正 ON/発火区別) は type-B につき N/A。

## 項目別 (CSV 成果物への参考採点)

- **タスクフロー / 結合しやすさ: 4/5** — 5 CSV が `race_id` (`20260712-02-01` 形式) で貫通し、`evaluation_summary.csv` 単体で表計算の答え合わせが完結する構成 (23 列、morning/final/払戻/損益を 1 行に集約)。race_num は全 5 CSV で 2 桁統一を実測 (`len dist: {2: ...}` 全ファイル)。
- **欠損の可視化 / 品質ゲート: 3/5** — `final_odds.csv` の `odds_fetched_at` 空欄 137/470 行が無警告で通過 (実測)。空欄は捏造より誠実だが、manifest に欠損カウントが無く、表計算利用者は「全行同鮮度」と誤読しうる (Nielsen 1: 状態の可視性)。bug① の再発検知ゲート (`1 <= popularity <= starter_count`) も出力側に無い。
- **再現性メタ / 状態可視性: 4/5** — manifest に counts・5 CSV の sha256・source HTML sha256・予測時 `git_sha` (f9d9f65) を記録。留保: **builder 自身の git_sha / dirty flag が無い** (`scripts/build_daily_results.py:289` は HTML フッタ由来の予測時 sha のみ)。今回の CSV は未コミットのパーサ修正コードから生成されており、記録された sha からは再現不能。
- **状態整合性 / 誤読防止 (重点): 4/5** — 3 バグとも実測で修正確認: ①非空 `morning_popularity` 169 件が全件 1-18・odds>1000 ゼロ (旧: "22.96人気"→pop=310 級の破損)、②`horse_num` 幽霊行 ('00'/空) は final_odds/race_results とも 0/470、③race_num 2 桁統一。修正箇所 `" ".join(self._td_buf)` (line 175) + 正規表現 `^\s*([\d.]+)` / `(\d+)人気` の分離抽出はコードで確認。回帰テスト 3 件 pass。残存: 下記 horse_num 表現不統一で 5 は不可。
- **列設計 / 誤読耐性: 4/5** — `morning_odds` / `final_odds` の prefix 命名で朝・確定を明示、`bet_candidate` boolean で観察と購入候補を区別 (P25 原則「観察/購入の混同禁止」に整合)。減点: **`payouts.csv` の馬番がゼロ埋め ("04"、26/36 行で先頭 0 実測) なのに他 4 CSV は `lstrip("0")` で "4"**。bug③ と同一クラスの表現不統一が馬番側に残っており、pandas 等の文字列結合で払戻照合が全滅する罠。

## 停止条件チェック

- [x] 再現性メタ: manifest に git_sha / calibrator / lgbm 版あり (builder dirty flag 欠落は留保、backtest JSON でないため停止条件外)
- [x] baseline paired 比較: N/A (type-B、数値改善主張なし)
- [x] market_snapshot counts: N/A (type-B)
- [x] payout 欠損の扱い: payouts 36/36 レース分あり、counts 一致を実測
- [x] 職域 Hard Fail (fresh/stale 表示・補正 ON/発火・JS パース): すべて N/A (GUI 無変更) — 回帰ゼロを diff で確認

## 反証の試み

- 主張「①連結破損の解消」に対し「join 分離しても正規表現が誤マッチする」シナリオを検証 → `" ".join` 後の `"22.9 6人気"` から `^\s*([\d.]+)`=22.9、`(\d+)人気`=6 が分離抽出される (line 191-198)。実データ 169 件で異常値ゼロ → 不成立 (修正は本物)。
- 主張「③表現統一」に対し「馬番はまだ不統一では」を検証 → **成立** (payouts "04" vs 他 "4")。race_num のみの統一で「キー表現統一」は完了していない。

## 主な改善提案 (最大 3 件)

1. **payouts.csv の馬番表現を他 CSV と統一** — `scripts/build_daily_results.py:474-479` 付近の `p.get("tan_horse_num1")` 等を race_num 同様の正規化関数 (2 桁ゼロ埋め or lstrip、全 5 CSV 共通) に通す。bug③ と同クラスの結合事故を予防。
2. **manifest に builder 側 provenance + 警告ブロック** — line 567-575 の manifest 構築に `builder_git_sha` / `builder_git_dirty` と `warnings: {odds_fetched_at_missing: 137}` を追加。未コミットコード生成物の追跡不能と鮮度欠損の不可視を同時解消。
3. **出力側の品質アサート** — 書き出し前に `morning_popularity` の範囲 (1..starter_count) と `horse_num != '00'` を assert (違反時は件数付き警告)。bug①②の再発を CSV 生成時点で loud fail 化。

## 前回からの差分

- GUI 本体: 3.6 → 3.6 (維持、無変更)。前回判定 PASS → 今回 PASS。
- 参考: 直近の別系統採点 (20260715_0039、旧 rubric 不在下の一般基準) は GUI 4.1 を付けたが、本採点は rubric v3/v4 準拠で type-B のため「GUI 維持 + CSV 参考採点 3.8」と整理した。同 scorecard の「鮮度欠損 137 件の警告化」提案は本採点でも未消化を確認 (放置 1 回目)。

### モバイル HTML レビュアー

## 判定: PASS

**理由**: 改修タイプ = **type-B** (結果検証スクリプト `scripts/build_daily_results.py` の未コミット working tree 変更)。`git status` / `git diff --stat` で **web/templates・web/generator.py・web/dist は無変更を実測** → 表示 HTML への回帰ゼロ。P25 固有ゲート・web/dist 再生成義務は N/A (rubric v4)。当該パーサ修正は実 HTML・実 CSV・テストで独立検証し正しさを確認した。
**根拠ファイル**: `scripts/build_daily_results.py:172-199`, `web/templates/index.html.j2:721-724`, `tests/test_build_daily_results.py`, `data/results/2026-07-12/predictions.csv`
**次アクション**: 改善提案 1 (オッズ td への class/data 属性付与 — type-D 小改修) を次の web 改修に同乗させる。

## 総合: 4.6 / 5 (前回維持)

前回基準は 20260703_1058 (rubric 下での直近 mobile 採点 4.6 PASS)。20260715_0039 scorecard の「mobile 4.8」は rubric 外の一般基準採点と当該 scorecard 自身が明記しており (line 6)、再現可能な根拠なくスコアを引き上げない (証拠規律 5)。web/ 無変更のため前回維持。

## 項目別 (表示 5 軸は無変更につき前回維持)

- **レスポンシブ / メディアクエリ: 4.5** — 無変更・維持
- **タップ領域 / 操作性: 4.5** — 無変更・維持
- **情報密度 / 可読性 / 誤読防止: 4.5** — 表示は無変更・維持。本改修は「答え合わせデータ側」の誤読 (odds=22.96 等) を解消するもので、スマホ表示の誤読防止には直接寄与しないが矛盾もしない
- **ダークモード / コントラスト: 4.5** — 無変更・維持
- **iOS / iCloud 互換 + 予算: 5** — 無変更・維持。`data/results/2026-07-12/` は公開対象外のローカル成果物であり、iCloud 配信ペイロードに混入しないことを確認 (predictions_source 370KB は日次アーカイブとして妥当、git sha `2642e8c` 刻印つきで出所追跡可)

## 参考所見 — パーサの頑健性・テンプレート耐性 (依頼された監査本体)

1. **修正の正しさを実データで確認**: テンプレート `index.html.j2:724` の出力 `<td>77.3<br><span class="pick-reason">10人気</span></td>` を source HTML から grep で現認 (`pick-reason` 出現 169 件)。再生成 CSV の非空人気 **169 件 (=span 数と一致) / min 1 / max 17**、朝オッズ **1.5〜196.5、小数 2 桁以上の連結痕跡 0 件**。旧 `"".join` なら不可能な分布であり、修正が効いている。
2. **hn00 / race_num も実測**: final_odds / race_results 各 470 行、horse_num='00' 0 件、race_num 非 2 桁 0 件。テスト 3/3 pass (`.venv64` pytest 実行)。
3. **テンプレート契約の脆弱性 (残存)**: パーサはオッズ列を「**class の無い td**」として else 分岐 (`build_daily_results.py:189-199`) で消去法識別している。テンプレートに class 無し td 列を 1 つ追加しただけで誤爆する設計。前回 scorecard の提案 (data 属性) は未実装のまま。
4. **反証の試み**: 「" ".join で誤読解消」の反例を探索 → テンプレートは `{% if h.odds %}` と `{% if h.popularity %}` が独立 (line 724) のため、**odds 欠損 + popularity あり** の場合 buf="6人気" → `^\s*([\d.]+)` が「6」に一致し **odds=6.0 と誤読する経路が残存**。2026-07-12 実データでは odds/pop 非空が共に 169 件で対になっており未発火だが、潜在バグ。
5. **" ".join の全 td 適用リスク**: mark-cell / horse-num / horse-name は現テンプレートで純テキスト (line 721-723) のため今日は無害だが、将来 horse-name にネスト span を足すと馬名に空白が混入する。前回 code-quality 指摘と同一、未対処。

## 停止条件チェック

- [x] 改修タイプ分類宣言済 (type-B、web/ 無変更を `git diff --stat` で実測)
- [x] P25 固有 Hard Fail (fresh/stale 表示等) — N/A (type-B、HTML 表示無変更)
- [x] web/dist 再生成義務 — N/A (type-D のみ)
- [x] 表示 HTML への回帰なし (working diff に web/ ファイルなし)
- [x] 専門領域別停止条件すべて不抵触

## 主な改善提案 (優先順)

1. **オッズ td に class + data 属性を付与** — `web/templates/index.html.j2:724` を `<td class="col-odds" data-odds="{{ h.odds }}" data-popularity="{{ h.popularity }}">` に。パーサは消去法でなく `col-odds` 正一致 + data 属性優先読取に変更 (`build_daily_results.py:189`)。テンプレート変更耐性が構造的に解決する。type-D 改修なので次回 web 改修時に同乗、その際は本 agent の全ゲート適用
2. **odds 欠損 + popularity あり の誤読ガード** — `build_daily_results.py:191` の `m_odds` を「buf が `人気` で始まらない場合のみ」適用、または `^\s*([\d.]+)(?!人気)` に。上記反証 4 の潜在経路を塞ぐ + 回帰テスト 1 件追加
3. **" ".join をオッズ列限定に** — 非オッズ td は従来 `"".join`、オッズ列 (改善 1 後は class 判定可) のみ区切る。ネスト要素追加時の馬名空白混入を予防

## 前回からの差分

- 総合: 4.6 → 4.6 (±0)。前回判定 PASS (20260703、web 無変更) → 今回も PASS。
- 20260620 の HOLD (4.38) 以降の表示側課題 (vb-sub コントラスト等) は本改修のスコープ外で状態変化なし

### 予想ロジック分析官

## 判定: PASS

**理由**: type-B (診断/結果集計ツール修正。predictor/ 無変更) と分類。features_00_contamination.md の主張 (19 クエリ全てで '00' 行が成績条件により自然除外、汚染 0 件) を **全 19 箇所のコード直読 + DB 実測クエリで独立再検証し、すべて成立** を確認。停止条件抵触なし。
**根拠ファイル**: `data/results/2026-07-12/features_00_contamination.md`、`predictor/features.py`、`scripts/build_daily_results.py` (working diff)、`data/keiba.db` (実測)
**次アクション**: '00' 行の ingest 段階防止 + implicit invariant (`horse_num='00' ⇒ confirmed_order=0`) の回帰テスト化

## 総合: 4.3 / 5 (参考スコア)

## 項目別

- **調査の網羅性・正確性: 5/5** — 監査表の 19 行を全件コード照合。grep 実測でも `features.py` の `FROM horse_races` は正確に 19 箇所で過不足なし。各除外条件を実コードで確認 (132/190/200/257/297/330/355/377/420/476/536/657/714/761/798/833/872/917/1272)。監査表と全一致。
- **DB 事実の再導出: 5/5** — 自分で実測: '00' 行 406 件 / `confirmed_order>0` は 0 件 / NULL 0 件 / `corner_order_4>0` 0 件 / `finish_time>0`・`win_odds>0`・`win_popularity>0` 全て 0 件 / blood・jockey・trainer コードは 406/406/406 で実在 ID が入っている。「識別子条件だけでは除外できない」という監査指摘は正しく、かつ重要 (entity キー系クエリは '00' 行にマッチするが confirmed_order 条件だけが防波堤)。日付範囲 20260510–20260712、07-12 は 36 件も確認。
- **確率推定・答え合わせ整合: 4/5** — 予測・確率パスは無変更。修正は `" ".join` 分離 + regex で構造的に妥当。テストが該当 HTML 断片を直接固定化。再生成 CSV 実測: final_odds.csv 470 行 / '00' 0 件 / race_num 全行 2 桁。留保: パーサは class 名依存で、テンプレート変更に脆い。
- **設計整合性: 4/5** — `race_num_of` helper で単一実装化 (DRY)。SQL の `horse_num != '00'` は `scripts/backtest.py:572-587` の既存除外と同パターンで一貫。テスト 3 件が 3 バグに 1:1 対応。manifest.json の再現性ゲートを満たす。留保: contamination md 自体に DB スナップショット時刻・git_sha が無い。
- **train-serve / 消費経路の乖離リスク: 4/5** — 監査スコープ外の horse_races 消費経路を独立に全数確認 (grep 32 hits): `web/generator.py:242-247` は Python 側で `("", "00")` 除外済 → **live 予想エントリに幽霊馬は入らず、race 内正規化の分母も汚染なし**。`scripts/backtest.py:585-587` 根元 SQL 除外。`gui/app.py:443,480` `scripts/monitor.py:149` は `confirmed_order>0`。`scripts/check_fresh_odds_health.py:249` は非汚染。留保: これらが「たまたま」除外している状態で、invariant の強制が無い。

## 反証の試み

1. 「'00' 行にいつか confirmed_order>0 が入る」→ 05-10〜07-05 の確定済み過去開催日の '00' 行も全て 0 のまま (実測)。結果 ingest が '00' 行を更新しない実証が 2 ヶ月分ある。不成立だが将来リスク残。
2. 「features.py に 19 箇所以外の参照がある」→ grep 実測 19 箇所で一致。不成立。
3. 「features.py 外の予測経路が汚染され、幽霊馬が正規化分母や HTML に混入」→ generator/backtest/gui/monitor/fresh_odds_health 全経路で除外条件を実コード確認。不成立。

## 主な改善提案 (優先順)

1. **invariant の回帰テスト化** — 「`horse_races` の `horse_num='00'` 行は `confirmed_order=0` かつ `odds_fetched_at IS NULL`」を検証するテスト (または ingest 側で '00' 行の挿入自体を拒否)。features.py の 19 クエリの安全性は全てこの invariant に依存しており、破れたら 19 箇所同時に汚染する単一障害点。
2. **contamination md に監査メタ追記** — 冒頭に監査実行日時・git_sha・DB 行数 (406) の実測時刻を 1 行。
3. **entity 系クエリへの防御的除外** — 提案 1 が通れば不要 (過剰防御は可読性コスト)。

## 前回からの差分

- 前回 (20260703_053033 LGBM v6 レビュー): 4.0 / PASS (条件付き) → 今回 **4.3 / PASS** (+0.3)。live 答え合わせ経路の計測破損 3 件が再現テスト付きで解消 + 監査主張の全数独立再検証が成立したため。

### 収益性ジャッジ

## 判定: PASS

**理由**: type-B (診断/答え合わせツール) 改修。予想ロジック・BUY_FILTER・backtest 本体は無変更で、答え合わせ CSV の 3 バグの修正を自分の再導出で全件確認した。収益主張は一切なく、観察専用運用の段階区別も維持されている。
**根拠ファイル**: `scripts/build_daily_results.py:173-199,352-357,382-385`、`data/results/2026-07-12/evaluation_summary.csv` (470 行実測)、`tests/test_build_daily_results.py` (3 passed 実測)
**次アクション**: manifest に **builder 自身の git_sha/dirty 状態** を刻印。コミット後に CSV を最終再生成して sha を固定すること。

## 総合: 4.0 / 5 (参考スコア、評価可能 4 軸の平均)

## 項目別

- **答え合わせデータの収益指標正確性: 4/5** — `profit_loss_yen_100unit` を 470 行全行再導出し**不一致 0**。当日は bet_candidate=1 件のみ (20260712-10-04 hn11、7 着、P/L −100 円)。n=1 は統計的に無意味だが、CSV は ROI 集計値を出力せず誤精度を作っていない。
- **EV 計算の整合性: 4/5** — 修正後を実測: morning/final オッズ比の min/med/max = 0.26/0.86/2.6 で連結痕跡 (比>3) は 0 行、morning_popularity は 1-17 で値域正常。`expected_value_morning ≈ p×morning_odds` を 60 行で再計算し最大絶対差 0.045 / 中央値 0.0039。残課題: 正規 137 頭で `odds_fetched_at` 欠損 → 当該 11 レースはオッズスリッページ監査が不能。
- **Kelly / 資金管理: N/A** — 無変更。CSV は定額 100 円単位の仮想 P/L でありサイジング主張なし。
- **買い目フィルタの実用性: 4/5** — 本ツールは**実際に公開された HTML** をパースして答え合わせするため、「検証した集合 = 表示した集合」が構成上保証される。幽霊行 36 件の除外を実測確認。
- **不確実性開示 / 段階区別: 4/5** — BUY_FILTER は観察マーカー格下げ済で、本改修も収益主張ゼロ。減点: 再生成 CSV は**未コミット working tree のコードで生成**されており、manifest に builder 自身の sha/dirty が無いため CSV→コードの追跡が閉じない。

## 反証の試み

- 「朝オッズ連結破損は修正された」→ 破損シグネチャ (人気>18、morning/final 比>3) を 169 行で探索 → 0 件、EV=p×odds が 60 行で閉じる。**反証不成立 = 修正は本物**。
- 「幽霊行除外は安全」→ 470 行 = HTML パース頭数 470 と完全一致、欠落なし。成立。

## 主な改善提案 (優先順)

1. **manifest に builder の git_sha + git_dirty を追記** — 答え合わせ CSV は将来の実力判定 (F3 封印ホールドアウト) の入力になり得るため、生成コードの追跡性は必須。
2. **`odds_fetched_at` 欠損 137 頭の上流調査** — final_odds の鮮度不明はスリッページ監査 (T−n 分 PIT 規律) の盲点。F3 着手前に取得経路を特定。
3. **evaluation_summary に「n<100 は判断不能」注記** — 少数日で ROI を語る誤読を予防。

## 最終所見 (段階判定)

現段階は **「観察用」** — 変更なし。本改修は「観察の測定器を正しく校正した」改修であり、実弾候補への昇格材料ではない。**CI 下限が 100% を超えない限り実弾投入不可**の原則は不変。

### データ基盤エンジニア

## 判定: HOLD

**理由**: 3 バグ修正はすべて実測で正しさを確認。ただし「改ざん防止の証跡」を自称する manifest.json に**生成コード側の git_sha / git_dirty / 再生成履歴が無く**、しかも今回の再生成は未コミットの working tree で実行された (= 証跡の生成コードを後から特定できない)。rubric v4 type-B の「診断ツールが artifact を出すのに git_sha を記録しない」に接触する軽い不足で、数分で補完可能 → HOLD。
**根拠ファイル**: `scripts/build_daily_results.py:566-593` (manifest 構築)、`data/results/2026-07-12/manifest.json`
**次アクション**: (1) manifest に `builder_git_sha` + `git_dirty` + `regenerated_from` を追記、(2) 本改修をコミットして sha を確定、(3) 上流 '00' 掃除の実装判断。以上で PASS 再評価可。

## 総合: 3.4 / 5 (参考スコア)

## 項目別

- **① HTML パーサ修正: 4/5** — 再生成 CSV を実測: `morning_popularity` 非空 169 行の >18 は 0 件 (修正前 139 件破損)、ホウオウワイズ `22.9 / 6` に復元。テスト 3 passed 実測。留保: `" ".join` は全セルに作用するが、現 HTML で複数 data 片を持つセルはオッズ列のみ — 実害なし確認。
- **② '00' プレースホルダ除外: 3/5** — 修正自体は正しい。**反証実測**: 406 行全件が `confirmed_order=0 / win_odds=0 / odds_fetched_at NULL`、「'00' のみのレース」0 件 → 除外による情報損失なし。減点は上流未対策: 消費側フィルタが **3 箇所目**に増殖し、`features.py` は「たまたま `confirmed_order>0` 条件で自然除外」という偶然依存。
- **③ 鮮度可視性 (odds_fetched_at NULL 137 頭): 3/5** — **根本原因を特定**: coverage JSONL 実測で 2026-07-12 は 35 run / error 0 だが、**11:50→14:00 に 2h10m のスケジューラ空白**があり、欠損 11 レース (昼帯 5〜8R) と正確に一致。取得失敗ではなく「起動しなかった」障害クラスで、`failed_reason` では原理的に検知不能。空白検知の監視が無い。
- **④ manifest 整合性設計: 3/5** — 欠陥 4 点: (a) builder の git_sha / git_dirty 無し — 今回まさに dirty tree で生成、(b) HTML ファイル名 `git2642e8c` と footer/manifest の `f9d9f65` が**不一致** (どちらが生成時 HEAD か曖昧なまま footer を盲信)、(c) docstring は「後から書き換えない」と宣言するのに再生成が旧証跡を無履歴で上書き、(d) manifest 自体の非冪等 (`generated_at`)。
- **⑤ テスト / 副作用なし: 4/5** — 3 テストが 3 バグに 1:1 対応。本体は SELECT のみで DB 副作用なし。留保: evaluation_summary の幽霊 join 回帰と payouts fuku4/5 経路が未カバー、テスト内 DDL が `data/schema.sql` と手動同期。

## 反証の試み

- 「'00' 除外でデータは失われない」→ 406 行全件確認 → **成立**
- 「オッズ/人気の分離が直った」→ pop>18 が 139→0、個別馬 2 頭照合 → **成立**
- 「NULL fetched_at は取得失敗」(監査所見の推定) → coverage JSONL では ok==eligible 全 run・error 0 で**不成立**。真因はスケジューラ空白 (11:50→14:00) — 別の障害クラス

## 主な改善提案 (優先順)

1. **上流 '00' 掃除 (ingest 後 DELETE)** — `jvlink_client/ingest.py` の SE 取込後 (同一トランザクション内) に `DELETE FROM horse_races WHERE horse_num='00' AND EXISTS (同レースに horse_num!='00' 行)` を追加 + 既存 406 行の一括掃除。挿入スキップは「枠順確定前の出走予定情報」を失うため不可、確定後掃除なら冪等・クラッシュ安全・情報損失ゼロ。
2. **manifest に builder 出所を追加** — `builder_git_sha` / `git_dirty` / `supersedes_sha256`。あわせて `excluded_placeholder_rows` と `null_odds_fetched_at_rows` (36 / 137) を counts に記録すると品質ドリフトが機械検知可能。
3. **スケジューラ空白検知** — `scripts/fresh_odds_coverage.py` または `scripts/monitor.py` に「開催日 9:00-16:40 の run 間隔 > 15 分で警告」を追加。07-12 の 2h10m 空白は現行のどの counter にも現れない障害クラス。

**参考所見**: `gui/app.py:824-840` のデータ件数表示は '00' 行 406 件ぶん微小に過大 (実害は表示のみ)。

### コード品質レビュアー

## 判定: PASS

**理由**: 3 バグの修正は正しく、各バグと 1:1 対応する回帰テストを伴う。停止条件抵触なし。留保 (3 変種に増えた horse_num 述語、span 分離が構造的でない) はいずれも非ブロッキング。
**根拠ファイル**: `git diff scripts/build_daily_results.py`、`tests/test_build_daily_results.py`
**次アクション**: horse_num 有効性述語の共通化と非オッズセル nesting ガードテストを次改修で。

## 総合: 4.0 / 5 (参考スコア)

## 項目別

- **DRY / 単一出典: 4/5** — `race_num_of()` の一元化は正しい構造化。一方で「有効な horse_num」という事実が **3 ファイル 3 変種**に: `backtest.py:585-587` (`IS NOT NULL AND TRIM != '' AND != '00'`)、`build_daily_results.py:357` (`!= '00'` のみ)、`diag_discrepancy.py:95` (`TRIM NOT IN ('','00')`)。新規追加分は最も弱い変種 (NULL/空文字は素通り)。実測では DB 全体で NULL=0 / 空=0 / '00'=406 行のため現時点の実害ゼロだが、共通化閾値には達している。
- **dead code / 未使用シンボル: 4/5** — 削除されたコメント「上記処理は handle_data + span end で吸収済」は**事実と異なる記述**であり、バグ本体と同時に嘘コメントを除去した規律は適切。新設コメントは具体例つきで良質。
- **マジックナンバー / 設定外出し: 4/5** — `'00'` リテラルが :357 に無コメントで直書き (backtest.py は docstring で説明あり)。
- **テスト容易性 / 変更失敗モード: 4/5** — 3 テストが 3 バグと 1:1 対応、in-memory DB + tmp_path で 0.12 秒、実測 3 passed。留保: (a) `sqlite3.connect` の monkeypatch は stdlib グローバル書換えで鈍器 (`--db` 引数が実際には使われない見かけ倒し)、(b) `race_num_of` が `main()` 内クロージャのため直接単体テスト不可。
- **エラー処理 / 観測可能性: 4/5** — `race_num_of` は非数値で fail-fast (良)、`None → "00"` の静かな補完は従来挙動の踏襲。新たな握り潰しなし。

## 変更失敗モード分析

`" ".join` は**全 td バッファ**に作用する。将来 horse-name td 内に子要素が追加されると、馬名が「テスト ホース」と空白入りで CSV に刻印され、馬名ベース照合が**静かに壊れる**。検出手段は現状ゼロ (非オッズセルの nested 回帰テストなし)。

## 反証の試み

1. **オッズ欠落 + 人気あり**のケース → buf = `"6人気"` となり `re.match(r"^\s*([\d.]+)")` が **"6" にマッチして odds=6.0 を誤設定**。テンプレートは `{% if h.odds %}` / `{% if h.popularity %}` が独立条件のため構文上生成可能。**部分的に成立** — 空白区切りは症状対処であり、span を専用バッファで構造分離する方式ならこの残存誤読も同時に消える。
2. 「22.96 誤読」の実在性 → コード読解で確認。成立 (コメントは正確)。

## 主な改善提案 (優先順)

1. **horse_num 有効性述語の単一出典化** — `db.py` に `SQL_VALID_HORSE_NUM` を定数化し、3 変種を置換。最弱変種の NULL 素通りも同時に解消。
2. **オッズセルの構造分離** — `handle_starttag` で `span.pick-reason` 検出時に専用バッファへ切替え。`" ".join` を `"".join` に戻せて将来影響と残存誤読が両方消える。「horse-name td に子 span がある HTML」の回帰テストを追加。
3. **テストの DB 注入方法** — monkeypatch をやめ、tmp_path 上の実ファイル DB を `--db` で渡す。

## 前回からの差分

- 前回 (20260715_0039 コード品質欄 4.2) は旧 rubric 不在下の一般基準かつ外部環境実行のため直接比較不可。今回 **4.0 / PASS** (-0.2、警告閾値未満)。

### 検証プロセス監査人

## 判定: PASS

**理由**: type-B (診断/検証データ生成ツールの是正) と分類。予想ロジック・backtest・calibration のコードパスに無変更で、答え合わせ CSV の 3 バグ是正は 6 項目検証+非同語反復テストで裏取り済み。停止条件抵触なし。留保 2 件 (旧日付 CSV の未再生成、manifest に生成器自身の git_sha 欠如) は PASS を覆さない。
**根拠ファイル**: `scripts/build_daily_results.py` (diff +13/-9)、`tests/test_build_daily_results.py`、`data/results/2026-07-12/manifest.json`、`data/results/2026-07-12/audit_findings.md`
**次アクション**: (1) 本改修のコミット、(2) `data/results/2026-06-21/` の再生成、(3) manifest に生成器自身の git_sha / git_dirty を追加

## 総合: 4.3 / 5 (参考スコア)

## 項目別

- **バックテスト設計への影響隔離: 5/5** — `grep -rn "data/results" scripts/ predictor/ gui/ web/` → 消費者ゼロ (build_daily_results 自身のみ)。生成器は DB に対し read-only。backtest/calibrator/weights は不変。全 316 tests + 4 skip pass を実測。
- **リーク分類学 / '00' 行の検証リスク: 4/5** — sqlite3 CLI で実測: '00' 行は **406 行、2026-05-10〜07-12、開催日ごとに約 36 行ずつ現在も増加中**。既存消費者は全て除外済みと裏取り。残リスク = **将来の新規クエリが除外を忘れる構造**。ingest 段階での拒否+既存 406 行整理が「別タスク」宣言済み — **宣言済み宿題として次サイクルでの執行を追跡対象とする**。
- **答え合わせデータの正しさ: 4/5** — 再生成 CSV を自分で再検証 (470 行 / 人気 1〜17 / 空馬番 0 / race_num 統一 / manifest SHA256 全 5 件一致 / 具体例一致)。テストは実 HTML と同じ構造を流す非同語反復回帰。留保: odds_fetched_at 欠損 137 頭は上流未解決のまま残存 — F3 の PIT 規律に照らすと、この 137 頭の final_odds を朝時点データと誤用する余地があり、manifest への警告記録が未実装。
- **再現性 / 監査証跡: 4/5** — 源泉 HTML も repo 保存済みで決定的再生成が可能 (SHA 一致を実測)。留保: ① `manifest.version_meta.git_sha` は HTML footer 由来の予想生成時 sha であり、CSV を生成した本スクリプト自身の sha/dirty は未記録。今回 CSV は未コミットの dirty tree で生成されており、コミット完了までは第三者が生成器バージョンを特定できない。② `data/results/2026-06-21/` は旧コード生成のまま **3 バグ全て残存を実測** (501 行中 pop>18 が 420 行 / 幽霊 36 行 / race_num 不統一)。源泉 HTML 保存済みなので再生成は決定的かつ低コスト → **日付横断の答え合わせ集約を行う前に再生成必須** (F3 封印ホールドアウトは 2026-07 以降なので封印集合は非汚染)。
- **プロセス規律 / 統合判定: 4/5** — 外部監査 (Codex 4 件検出) → 独立裏取り (問題 2 の根因を Codex 推定から DB '00' プレースホルダへ**訂正**した上で修正 — 推定を鵜呑みにしない規律として適切) → 修正 → 6 項目検証、全工程が artifact 化。**重大な手続き所見**: 先行 scorecard (20260715_0039) は「旧 `.Codex/agents/_rubric.md` が存在しない」として一般 5 段階で採点しているが、実際の rubric は `.claude/agents/_rubric.md` に存在する。つまり先行 review は正規の D1 expert-review 機構の外で実施された参考値であり、判定の重みは本採点 (正規 rubric 準拠) で置換する。

## 反証の試み

- 「169 行全部が誤値だった → 是正済み」→ 旧 06-21 CSV で同バグ再現 (pop>18 = 420/501) + 新 07-12 CSV で全 169 行 1〜17 を実測 → **成立**
- 「backtest/検証設計に影響しない」→ data/results の消費者を全コード grep + DB 書込み 0 件を確認 → **成立**
- 「'00' 行は features.py を汚染しない」→ 406 行全て confirmed_order=0 / corner=0 を追試 → **成立** (将来クエリへの構造リスクは残る)

## 主な改善提案 (優先順)

1. **`data/results/2026-06-21/` を修正済みコードで再生成** — 放置すると日付横断集約時に 84% 破損の morning_popularity が混入する
2. **manifest に生成器メタを追加** — `generator_git_sha` / `generator_git_dirty`
3. **odds_fetched_at 欠損 137 頭を manifest の warnings に機械記録** — F3 PIT 規律の運用と整合させる

## 前回からの差分

- 直近の正規 rubric 準拠評価 (20260706_1300): 3.66 → 今回 4.3 PASS。上昇理由: 監査→裏取り→修正→検証の全工程 artifact 化 + 非同語反復テスト + 自分での全数値再導出が成立。

## 横断的に見た優先課題

1. **manifest への builder provenance 追加 + コミット後の CSV 最終再生成** (担当: data-pipeline-engineer + profitability-judge + validation-process-auditor + gui-ux-auditor の 4 名一致 / **HOLD 解除条件**)
   - `build_daily_results.py` の manifest に `builder_git_sha` / `builder_git_dirty` / `supersedes_sha256` と警告カウント (`excluded_placeholder_rows: 36`, `null_odds_fetched_at_rows: 137`) を追加。本改修をコミットして sha を確定し、2026-07-12 の CSV を最終再生成して provenance を閉じる。あわせて `data/results/2026-06-21/` (3 バグ残存を実測済み、pop>18 = 420/501) も修正版で再生成する。
2. **'00' プレースホルダ行の上流対策** (担当: data-pipeline-engineer + prediction-logic-analyst)
   - `jvlink_client/ingest.py` の SE 取込後に同一トランザクションで確定後 DELETE (冪等・情報損失ゼロを反証実測済み) + 既存 406 行の一括掃除 + invariant (`horse_num='00' ⇒ confirmed_order=0`) の回帰テスト化。現状は消費側フィルタ 3 変種の増殖 + 偶然依存の自然除外で、将来クエリが除外を忘れると 19 箇所同時汚染する単一障害点。
3. **パーサ残存誤読の封鎖 + fresh odds スケジューラ空白検知** (担当: mobile-html-reviewer + code-quality-reviewer / data-pipeline-engineer)
   - 「odds 欠損 + popularity あり」で odds=6.0 と誤読する経路 (2 名が独立に発見、現データ未発火) を span 専用バッファ方式で構造的に解消。中期的にはテンプレートに `data-odds` / `data-popularity` 属性を付与してスクレイプ契約を解消。別件: 07-12 の odds_fetched_at 欠損 137 頭の真因は**フェッチャの 2h10m 起動空白 (11:50→14:00)** と特定済み — monitor に run 間隔 > 15 分の警告を追加。
