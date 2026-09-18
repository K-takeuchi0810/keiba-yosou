# 検証プロセス監査人 採点 — 2fb703a Phase 0.5-3 Fundamental Model

## 判定: HOLD

**理由**: 比較設計 (同一 931 レース paired) と統計手法 (レース単位 bootstrap / Bonferroni) は正しいが、(1) 成果物の provenance が「生成コードを含まない commit」を指す (`meta.git_sha=c19e716`、`git_dirty=false`、`data_version=null`) → 第三者が同 sha から再生成不能、(2) 標本修正 (b) の記録「57 レース 771 頭を学習に入れていた」が **DB 実測と食い違う** (学習窓 2021-23 の該当は 0 件)、(3) 0.5-3 の分析項目・価格帯・仮説数が **追跡可能な形で事前固定されていない** (層別分析は素の相関が null と分かった後に設計)。いずれも再評価で解消できる不足であり、実害バグ・比較不成立ではないため FAIL/NOT_EVALUABLE ではない。
**改修タイプ**: **type-B** (診断/分析ツール。`predictor/fundamental_model.txt` は本番から import されていないことを grep で確認)。P25 固有ゲート (factorial / market_snapshot / fresh odds / 他 agent 統合) は **N/A**。
**根拠ファイル**: `scripts/fundamental_model.py:86-230`、`scripts/fundamental_eval.py:131-267`、`scripts/frontrun_analysis.py:58-185`、`predictor/provenance.py:54-66`、`data/backtest/20260918_phase05_3_*.json`、`predictor/fundamental_model.meta.json`
**次アクション**: (a) `provenance.git_dirty()` を untracked 込みに変更 or 成果物を commit 後に再生成して sha を 2fb703a に揃える、(b) `docs/PHASE05_RESULTS.md` / commit message / `tests/test_fundamental_dataset.py` の (b) 記述を「検証窓 15 レース 205 頭 + 2026-02 の 42 レース、学習窓 0 件」に訂正、(c) 0.5-4 を走らせる **前に** 合格/棄却条件・帯・仮説数を tracked doc に固定、(d) strategy_dev 窓の eval 実行を追記型台帳に記録 (`config.CONSUMED_WINDOWS` と同型)。

## 総合: 3.4 / 5 (前回 3.4、±0)

## 項目別

- **バックテスト設計の正しさ: 4/5** — 市場と Fundamental は同一 931 レース / 12,533 頭で計算 (JSON `counts: analysed=931, runner_set_mismatch=6, no_t10=239` を実測)。0.21183 (933) と 0.21194 (931) は `PHASE05_RESULTS.md` で明示的に区別されており混同なし。931 = 933 − 2 の説明「取消なのに最終オッズが付く馬」は DB で裏取り: 該当 3 頭 (05/24 京都 9R, 07/05 福島 2R, 08/01 新潟 10R) のうち 07/05 は T−10 ゼロ日なので 2 レース減 = 一致。減点: (b) の記述が事実と異なる (後述)。
- **時系列リーク防止: 3/5** — ①時間リーク: `build_dataset` は `ORDER BY d, track_code, race_num` で累積更新するため、**同日別場の後続レース結果が調教師・種牡馬統計に混入**する (評価窓で調教師×日の複数場出走 3,056 組を実測)。1 レースぶんの微小量だが T−10 規律の厳密な違反。②ターゲットリーク: 特徴は全て当該レース前の値で `confirmed_order` はラベルのみ、問題なし。③市場混入: manifest 3 段は機能 (tests 14 件 pass 実測、`market_reading_functions(scripts/fundamental_model.py)` = `{}` を実測)。ただし検出器を **Fundamental 自身の生成コードに掛けるテストが無い** (既定は `predictor/features.py`)。`MARKET_COLUMNS` は `\b` 境界一致のため schema にある `sale_votes` / `hit_votes` / `odds_high` / `odds_low` を **拾えない**。④取消 (`abnormal_code=1`) の一律除外は 2 レースで T−10 後の情報を使っているが、当該レースは mismatch で落ちるので指標への影響ゼロ。
- **calibration / reliability 計測: 4/5** — 固定確率帯 × レース単位 bootstrap は適切。0-5 / 5-10 / 10-20% の系統ずれは z≈3.0 / 3.3 / 4.3 で 10 仮説 Bonferroni (z 2.81) を通る。市場側の同帯比較も併記。減点: 帯境界が事前固定文書に無い。
- **A/B 比較 / 再現性 / factorial: 3/5** — paired 比較は成立。**再現性欠陥**: `git show c19e716:scripts/fundamental_model.py` → "exists on disk, but not in 'c19e716'" (実測)。`git_dirty()` は `--untracked-files=no` なので新規ファイルが全部 untracked でも `false` を返す = 「動いたコード = sha」の保証が偽陽性。`data_version` は `snapshot()` に conn を渡していないため `null` = DB 状態が未記録。ハイパーパラメータはリテラル固定・early stopping は 2024-25 のみで、コード上 2026 参照は無いが、事前登録も掃引ログも無いので「2025 以前で決めた」は **検証不能な自己申告**。
- **過適合監視 / ドリフト / 統合判定: 3/5** — `DATA_SPLIT` が config で固定され `splits_are_disjoint()` あり は良い。減点: 0.5-3 の分析項目 (②③④・5 価格帯・三分位・16 仮説) を定めた tracked 文書が無い。eval は最低 2 回 (923 → 931) 走っているが、初回出力が残っていない。他 agent 統合は type-B のため N/A。

## 依頼された 6 点への回答

1. **「2025 以前で決めた」の裏付け** — コードは整合 (HP リテラル固定、early stopping = 2024-25、seed 固定、branch は単一 commit)。しかし反証不能: 事前登録無し・掃引記録無し・pre-fix eval の出力未保存。「2026 を見て調整した形跡は無い」が「無かったことの証明」にはならない。**判定: 整合的だが監査証跡不足**。
2. **標本の途中修正が 2026 を見た後の調整か** — 結果への **感度で反証**: (a) 取消除外が動かす学習行は 2021-23 で 223 行 (0.16%)、(b) 勝ち馬無しレースは **学習窓 2021-23 に 0 件**、検証窓 2024-25 に 15 レース 205 行 (0.2%、early stopping にしか効かない)、2026 は 42 レース 567 行が **02/07〜02/09** で評価窓外。DB 実測で 2+13+42=57 レース / 31+174+567=772 行 = 文書の「57 レース 771 頭」に一致。つまり修正 (b) は 2026 指標をほぼ動かせず、p-hack として **無効な操作**。動機が何であれ結果操作にはなっていない。ただし文書の「学習に入れていた」「『誰も勝たない』を教えていた」は **事実誤認** (訂正必須)。923 の機序は `fundamental_eval.py` の `set(m10.odds) != set_model` で mismatch と整合。
3. **933 → 931** — 正しく扱われている (上記)。副次指摘: 0.5-2 の「T−10 後に取消・除外 0」は集合比較で検出できない事例 (取消でもオッズが残る) を含んでおり、方法の限界を注記すべき。
4. **多重比較** — 20%+ 帯 −8.335pt: 区間半幅 6.62pt → SE 3.38 → z=2.47 (再計算一致、馬単位 SE 3.44 とも近い = レース相関が小さい帯)。Bonferroni 0.05/16 の z 2.95 を通らない結論は正しい。付記: 5 帯の ΔMarket 差は z=3.46 / 5.58 / 8.22 / 6.54 / 5.10 で **16 補正後も全帯有意** (文書は明記していないが成立)。問題は仮説数 16 が **実行時に算出**されており事前宣言でないこと、および層別分析自体が素の相関 null 後の設計 (forking paths)。効果量が大きいので結論は揺るがないが、確認的分析ではなく探索的分析として記録すべき。
5. **レース単位 bootstrap** — `_block_boot` はレースを塊に置換再抽出し、統計量関数を毎回丸ごと再計算する percentile bootstrap で正しい。`_band_stat` が三分位境界を再抽出ごとに引き直す設計は「推定手続き全体を bootstrap する」標準に合致し、境界固定より区間が広く出る側 = 保守的で妥当。軽微: 分位 index `int(0.025*n)` は 1 要素ぶん内側 (無視できる)。全 `_block_boot` が同 seed で同一再抽出列を使うのは common random numbers で問題なし。
6. **部分相関の交絡除去** — 3 次式残差化 +0.1800 を再現。代替仕様で頑健性を実測: p_T10 の 20/50/100 分位 FE で +0.188 / +0.185 / +0.179、市場順位×価格 FE で +0.189。ΔAI・ΔMarket はレース内で和ゼロ (実測 max 2.8e-16) なのでレース FE は暗黙に入っている。帯内残存交絡の符号: 0-20% の 4 帯では corr(p_T10,ΔM)×corr(p_T10,ΔAI) が負 = 交絡は結論と逆向き (保守的)。**20%+ 帯のみ** 同符号 (−0.077 × −0.680 ≈ +0.05) で帯内相関 +0.179 の一部が価格由来の可能性 → 帯内表の 20%+ 行は割り引いて読む。文書の解釈 (T−10 の誤差縮小 = errors-in-variables、最終市場に無い情報の証拠ではない、CLV 無し) は正しい。

## 停止条件チェック

- [x] git_sha / git_dirty 記録あり — **ただし sha は生成コード非含有 commit、dirty は untracked 盲点で偽陰性、data_version=null** (再現性欠陥として HOLD 事由)
- [x] baseline paired 比較成立 (同一 931 レース、同一 T−10 定義 `pit_t10.t10_market`)
- [ ] market_snapshot counts — N/A (type-B、T−10 集合は `counts.no_t10=239` で代替記録あり)
- [ ] payout 欠損 race — N/A (払戻を使わない)
- [x] 専門領域: 期間ズレ無し / コードパス同一 / bootstrap はレース単位 / 点推定のみの採用判断なし / 評価窓事後変更なし。**事前固定文書の不在は Required Evidence 不足** (HOLD)

## 反証の試み

- 主張「(b) は 2026 の成績を見ての調整ではない」→ 感度分析で **成立** (学習窓 0 行、評価窓 0 行、動かせる余地なし)。ただし「学習に入れていた」は **不成立** (DB 実測)。
- 主張「先読みは起きている」→ 4 種の代替 FE で +0.18〜0.19、Bonferroni 通過 → **成立**。ただし探索的設計であり、20%+ 帯内には価格残存交絡あり。
- 主張「T−10 のオッズ配信からも消えている (取消)」→ 評価窓に反例 3 頭 → **一般には不成立** (影響は 2 レースの除外に限定)。

## 主な改善提案

1. **provenance の偽陰性修正** — `predictor/provenance.py` の `--untracked-files=no` を外し `git_status_short` を meta に追加。`snapshot(conn)` を conn 付きに変更し `data_version` を埋める。
2. **記録の訂正 + 0.5-4 事前登録** — `docs/PHASE05_RESULTS.md` を実測値に訂正。0.5-4 着手前に `docs/PHASE05_PREREG.md` (合格 LogLoss < 0.21194 on 931、帯境界、仮説数、棄却条件) を commit。
3. **同日別場リークの除去** — `build_dataset` の並びを `races.start_time` 順にするか、更新を「日付が変わった時点で一括反映」に変更。併せて `tests/test_feature_manifest.py` に `market_reading_functions(Path("scripts/fundamental_model.py")) == {}` を追加し、`MARKET_COLUMNS` に `sale_votes` / `hit_votes` / `odds_high` / `odds_low` を追加。

## 前回からの差分

- 前回 (2026-09-14 f3_sealed_holdout): 3.4 / HOLD。今回 3.4 / HOLD (±0)。
- 改善: 統計手法 (レース単位 bootstrap を全区間に適用、多重比較を自己申告、errors-in-variables の自覚) は過去最良水準。
- 後退/持ち越し: 再現性メタが逆行 (sha が生成コードを含まない commit を指す)。前回指摘「事前登録は封印前に」の原則が 0.5-3 の分析設計には適用されておらず、**次回 0.5-4 で事前登録が無ければ FAIL に降格する**と宣言する。
