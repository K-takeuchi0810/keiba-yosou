# 予想ロジック分析官 採点 — Phase 0.5-3 Fundamental Model (commit `2fb703a`)

## 判定: HOLD

**理由**: 改修タイプは **type-B** (研究用推定器 + 診断ツール新設。`predictor/rules.py` `weights.json` `calibrator.json` 不変 → P25 固有ゲートは **N/A**)。停止条件抵触は無いが、0.5-4 の土台にする前に是正すべき **PIT/train-serve skew 3 件** と **provenance の穴 1 件** を実測で確認した。主結論 (「T−10 に無い情報は持つ / 最終市場に無い情報は未判定」) は自分の再導出と一致し、over-claim は無い。
**根拠ファイル**: `scripts/fundamental_model.py:53-64,86-230` / `predictor/feature_manifest.py:34-38,101-121` / `data/backtest/20260918_phase05_3_frontrun.json` / `predictor/fundamental_model.meta.json` / `predictor/provenance.py:62`
**次アクション**: 改善提案 1〜3 を実装 → `--fit` 再学習 → 同一 931 レースで LogLoss / 部分相関 / 条件付きロジット係数を再掲。加えて artifact を **本改修 commit 上で再生成**して `git_sha` を一致させる。

## 総合: 3.2 / 5

## 項目別

- **シグナル網羅性と市場残差性: 3/5** — 30 特徴は馬の通算/距離帯/場別成績、騎手・調教師・父の勝率、斤量・枠・頭数・馬場・馬体重・ブリンカー。**全件が馬柱に載る公開情報で、市場が確実に織り込む代理変数**。市場外情報 (タイム指数・上がり・相対走破時計・展開/脚質 × メンバー構成・クラス昇降・乗替り・初ブリンカー) は 1 つも無く、本番 112 特徴に既にある `relative_race_metrics` / `best_time_per_100m` 系も採っていない。Phase 0.5-3 の目的 (市場情報ゼロの基準器) には適合するが、「30 特徴のうちどの群が T−10 超過情報を運ぶか」の群別 ablation が無い。所感: 馬体重 (T−50 頃公表) や騎手・調教師成績は **遅れて織り込まれる公開情報**でもあり、「先読み」の少なくとも一部は市場外情報ではなく「同じ公開情報を終盤の大口も使う」で説明できる。
- **重み妥当性 / 過適合リスク: 3.5/5** — 学習 2021-23 / 早期停止 2024-25 (best_iteration 174) / 評価 2026 は未接触、seed 固定、meta 記録。2026 を見た調整痕は無い (標本欠陥 (a)(b) は頭数不一致起点で妥当)。減点: **カウント特徴 (`h_starts` `j_rides` `t_runs` `hd_starts` `ht_starts`) が DB 収録開始に依存して非定常**。実測: 2017-19 は 15 行以下、**2020 は 48,427 行中 23,619 行しか結果が無い**ため、2021 の学習行はカウンタがほぼ冷えた状態で始まり、2026 評価行は 5 年分積み上がった状態。木モデルは学習域外を定数外挿するので、`j_rides`=数千 の 2026 行は学習時に一度も見ていない領域。
- **信頼度判定 / 確率推定の構造: 4/5** — 二値 LGBM → race 内正規化は市場と同じ土俵にする最小限の変換で、正規化後の帯別較正をレース単位ブートストラップで出している。素の相関 U 字の交絡指摘、Bonferroni 16 仮説の明記、「T−10 に勝っても 1 円にならない」の明示は正しい。減点: 20%+ 帯の三分位は帯内で価格水準が残る (下位 p_T10 0.397 vs 上位 0.256) ので「5 帯すべてで正」は帯内価格交絡込み。部分相関 (3 次 logit 残差) の方を主統計とすべき。
- **デッドコード / 設計の整合性: 3/5** — 検出器の網に構造的な穴: (i) 走査対象が `predictor/features.py` のみ。`rules.py:1376-1377` (`front_runner_count` `same_leg_rivals`) のように features.py 外で作られる LGBM 特徴は見えない。(ii) `MARKET_COLUMNS` の裸の `odds` `popularity` は `\b` がアンダースコアを語文字とするため **`place_odds` `quinella_odds` `win_odds_final` に当たらない** (自分で実測)。(iii) `payouts.tan_pop1..3` `fuku_pop*` `umaren_pop*` `tan_payout*` `exotic_odds.odds_low/high` が集合に無い (現時点で features.py は payouts を読まないので**現状漏れではなく将来の穴**)。`market_features: 0` は名前リスト照合のみで、検出器結果との突き合わせは test に依存。tests 14/14 pass は確認。
- **本番運用との乖離リスク (train-serve skew): 2.5/5** — 実測 3 件:
  - (a) **同日クロス開催の更新順序**: `build_dataset` は `(d, track_code, race_num)` 順でカウンタ更新するため、低い場コードの後発走レース結果が高い場コードの先発走レースに漏れる。評価窓 15,871 行中 **3,196 行 (20.1%) で調教師カウンタに同日未来結果が混入、うち 324 行 (2.0%) は未来の勝利**。父カウンタも同構造。live T−10 では再現不能。`start_time` は 2021 以降空欄 0 なので `(d, start_time, …)` 順に直せる。
  - (b) **`starters` = 発走除外後の頭数**: 評価窓 1,176 レース全件で `starter_count == 行数 − 取消 − 除外`、除外ありの 46 レース全件がこの形 → T−10 に知りえない値。「除外馬は残す」判断と矛盾 (馬は残すのに頭数は除外後)。前セッション (2026-09-15) で自己検出済みの同一欠陥の再発。
  - (c) 上記カウント特徴の非定常性 (学習域と運用域の分布不一致)。

  Fundamental は未だ serving 経路に無いので現時点の実害はゼロだが、0.5-4 で `init_score=logit(市場)` の補正項に使うなら (a)(b) は必ず PIT 違反として乗る。

## 停止条件チェック

- [x] git_sha / rule_version 記録あり — **ただし** artifact の `git_sha=c19e716` は本スクリプトを含まない親 commit で `git_dirty=false`。原因は `provenance.py:62` の `--untracked-files=no`。**その SHA ではこの成果物を再生成できない**
- [x] env_overrides — 本ツールは env 分岐を持たない (N/A)
- [x] baseline paired 比較成立 — 同一 931 レース / 同一 12,533 頭
- [x] market_snapshot counts / payout 欠損扱い — type-B につき N/A
- [x] 専門領域別 — type-A ではないため N/A。「確率品質改善」の主張は無し (市場より悪いと明記)

## 反証の試み

1. 主張「Fundamental は T−10 市場に無い情報を持つ (部分相関 +0.180)」に対し、ΔAI と ΔMarket が共通項 −P_T10 を持つ機械的相関 (EIV) と race 内ゼロ和の交絡を避けるため、**race 条件付き (Benter 型) 多項ロジット** を samples.csv から自分で当てた:

   - `won ~ logit(P_T10) + logit(P_fund)` → P_fund 係数 **+0.159, レース bootstrap 95% [+0.032, +0.286]** → 成立 (T−10 に対しては情報あり)
   - `won ~ logit(P_final) + logit(P_fund)` → **+0.073 [−0.049, +0.187]** → 最終市場に対しては **0 をまたぐ**

   docs の「最終市場に無い情報の証拠にはならない」と一致。over-claim 無し。
2. 主張「市場依存は 112 中 2 件」に対し features.py を独自 grep: 市場列の読み出しは `horse_past_runs` の SELECT (派生特徴には未使用を全文 grep で確認) と `_track_recent_stats` のみ。`lgbm_features.json` の 112 名を市場語で照合 → 該当は 2 件のみ。**2/112 は成立**。ただし `mining_dm/tm_*` を「JRA のモデル出力で市場ではない」とする判定は JRA-VAN がアルゴリズムを開示していない以上 **外部検証不能**の留保付き。
3. 主張「(b) 結果未取込は 57 レース 771 頭」: meta の `skip_race_without_result` は学習で 232,480 行。年別実測で 1986-92 (約 199k) + 2020 (約 24.8k) が大半で、771 は 2024-26 分に一致。記述は誤りではないが **2020 の半分が結果欠落**という、カウンタの冷えに直結する事実が docs に無い。

## 主な改善提案

1. **PIT を時刻順に強制** — `ORDER BY d, h.track_code, h.race_num` を `ORDER BY d, r.start_time, …` に変え、同一 `(d, start_time)` のブロック処理後にまとめてカウンタ更新する。tests に「同日・別場・後発走の結果が先発走の `t_runs` に入らない」ケースを追加。
2. **`starters` を T−10 で知りえる値に** — `r.starter_count` を `r.registered_count − (abnormal_code='1' の頭数)` に置換。`w_abs/w_delta` は T−10 前公表なので現状可。
3. **カウント特徴の非定常性を断つ** — `h_starts` `j_rides` `t_runs` 等を「直近 365 日窓の件数」または上限クリップに置換し、学習開始を 2021-07 以降にして 2020 H2 の結果でカウンタを温める。あわせて群別 ablation で条件付きロジット係数 +0.159 の寄与源を出す。
4. (補) `MARKET_COLUMNS` を「裸の語」ではなく **スキーマから抽出した完全列名** にし、走査対象に `predictor/rules.py` を追加。`provenance.git_dirty` は untracked も dirty 扱いに。

## 前回からの差分 (前回: 20260822_1210 fresh_odds_recovery, PASS 3.9)

- シグナル網羅性: 4.5 → 3 (−1.5)。対象が異なるため 1 点超の下動だが、根拠は全件列挙で再現可能
- 重み妥当性: 4 → 3.5
- 確率推定の構造: 4 → 4 横ばい
- 設計整合性: 3.5 → 3
- train-serve skew: 4 → 2.5 (−1.5)。同日順序リーク 20.1% 行 / `starters` 除外後値 / 2020 結果欠落
- 判定 PASS → HOLD: 停止条件抵触ではなく、0.5-4 が乗る土台に PIT 違反 2 件が残っているため

## 追記 (bg クエリ完了後)

同日クロス開催の更新順序リーク: 調教師カウンタ 3,196 行 (20.1%) に加え、
**父カウンタ (`s_winrate`) は 4,978 行 (31.4%)** に同日後発走レースの結果が混入
(評価窓 15,871 行、`races.start_time` 基準で実測)。是正は改善提案 1
(並び順を `(d, start_time, …)` に変更 + 同一発走時刻ブロック後にまとめて
カウンタ更新) で両方同時に解消できる。

判定 HOLD / 総合 3.2 は変更なし。
