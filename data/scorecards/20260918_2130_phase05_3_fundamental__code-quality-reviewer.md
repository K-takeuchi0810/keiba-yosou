# コード品質 / 保守性レビュアー 採点 — 2fb703a Phase 0.5-3 Fundamental Model

**改修タイプ宣言**: type-B (検証/診断ツール)。`predictor/fundamental_model.txt` は消費経路ゼロ (`grep fundamental_model` は scripts/tests 以外 0 件)、weights.json / backtest.py / filter.py 不変。P25 固有ゲート (meta.env_overrides / market_snapshot / PRED_DISABLE_BLEND 等) は **N/A (対象外)**。汎用ゲートで採点。

**採点対象**: 上記 6 ファイル + 生成 artifact 2 本 + `predictor/fundamental_model.meta.json`。**スコープ外**: 統計的解釈 (validation-auditor 領域) は参考所見に分離。

## 判定: HOLD

**理由**: 見出しの主張「市場由来特徴の混入を **コードで強制**」が、肝心の Fundamental Model のデータ経路 (`build_dataset` の SQL) に対しては **一切効いていない** (AST 検出器は `features.py` にしか当てられず、台帳照合は名前空間が交わらないため構造的に空)。数値自体は HEAD から完全再現できたので FAIL ではないが、実装補完 (テスト 1 本 + 照合 1 本) なしに「強制済み」と見なせない。
**根拠ファイル**: `tests/test_feature_manifest.py:70` (`market_reading_functions()` を既定 path でしか呼ばない) / `predictor/feature_manifest.py:129` / `scripts/fundamental_model.py:98-119`
**次アクション**: 改善提案 1〜3 を実装後、本 agent のみ再採点 (他 6 名の再走は不要)。

## 総合: 2.8 / 5 (前回 3.2、-0.4 ⚠ 後退)

## 項目別

- **DRY / 単一出典: 3/5** — `build_dataset` は騎手/調教師/父/同コース勝率・間隔日数を `predictor/features.py` (`jockey_winrate:319` `trainer_winrate:345` `sire_surface_stats:530` `_horse_track_stats:869`) と **別の平滑化・別の定義で再実装**。現状は消費者ゼロの研究モデルなので二重管理の実害は未発生だが、0.5-4 で「市場 + Fundamental 補正」を本番化する時点で live 経路の第 3 実装が生まれる構造。統合すべきかへの回答: **今は統合しない** (per-horse クエリ設計と一括ストリーミング設計は目的が違う) が、**Counter 状態を `observe(row)` / `features(row)` を持つクラスに切り出し、live/batch が同じ状態機械を共有する** 設計制約を今のうちに docstring に明記すること。小さい二重記述: seed `20260918` が 3 ファイル 4 箇所 / 95% 区間の添字が同一ファイル内で `boot[25], boot[974]` と `int(0.975*len)`=975 の 2 流儀 / docstring「同一 933 レース」vs 実 analysed 931。
- **dead code / 未使用シンボル: 3/5** — `scripts/fundamental_model.py` の usage `--eval` は **存在しない** (実行: `error: unrecognized arguments: --eval`)。`import math` 未使用。`MARKET_COLUMNS` の `betting_share` / `market_rank` / `odds` は **schema 上のどの table/column にも一致しない** (実測: sqlite_master 全走査) = 想像で書かれた集合。逆に市場派生の `payouts` / `win5_payouts` テーブルは未登録。
- **マジックナンバー / 設定外出し: 3/5** — `len(sel) < 20`、`len(g) >= 100`、`len(band) < 200`、`n_boot // 2` はいずれも根拠コメント無し。ブートストラップをレース塊で行う理由は丁寧に書かれている一方、閾値は裸。BANDS / PRICE_BANDS はモジュール定数化されており可。
- **テスト容易性 / 変更失敗モード: 3/5** — 良: `build_dataset(db_path=)` で注入可能、`tests/test_fundamental_dataset.py` は **非 vacuous** (実測: `DID_NOT_START=frozenset()` に mutation → `2 failed, 4 passed`)。対照実験テスト (`test_detector_finds_a_planted_market_read`) の発想は正しい。悪: 下記「変更失敗モード分析」の通り、本命経路の守りが 0。加えて `scripts/fundamental_eval.py` と `scripts/frontrun_analysis.py` は **単体テスト 0 本** (`band_calibration` / `delta_distribution` / `_block_boot` / `_band_stat` / `_residualise` はすべて list[dict] を取る純関数で、テスト可能なのに未テスト)。`test_code_paths_reading_market_columns_are_detected` は「含まれる」しか見ず **許可リストとの完全一致を要求していない** — 2026-09-14 scorecard で同型の指摘を受けた直後の再発。
- **エラー処理 / 観測可能性: 2/5** — (a) 3 artifact とも `git_sha=c19e716 / git_dirty=false` を刻印しているが、生成コード 3 本は当時 **untracked で c19e716 に存在しない**。原因は `provenance.git_dirty` の `--untracked-files=no` — 「新規スクリプトが未コミット」という、同関数 docstring が警告するまさにその事故クラスを見逃す設計。(b) `snapshot()` に `conn` を渡していないため 3 artifact とも `data_version: null`。(c) `build_dataset` の `stats` は **1954 年からの全走査を数える**ため `meta.json` の `excluded_train: skip_race_without_result=232480` は誤読を招く。実測: train 窓 2021-23 の勝ち馬無し行は **0 行** / DNS 223 行、232k は 2021 年以前 (283,778 行中 236,704 行 = 83% が勝ち馬行なし)。(d) `except Exception: pass` — 日付不正を NaN に変えてカウンタも残さない。(e) `delta_distribution["mean"]` は per-race 正規化により **恒等的に 0** (実値 1.9e-18) — 「AI は市場に対し無偏」と誤読される指標。

## 変更失敗モード分析 (核心)

「`build_dataset` の SELECT に `h.win_popularity wp,` を 1 列足したら何が起きるか」を実際に試した (`scripts/fundamental_model.py` の複製に植え込み):

- `market_reading_functions(Path("scripts/fundamental_model.py"))` → `{'build_dataset': ['win_popularity']}` = **検出器自体は捕まえられる**
- しかし既存テスト 14 本のどれも同 path で検出器を呼ばない → **全 PASS のまま市場列が学習に入る**
- `assert_no_market_features(FEATURES)` は台帳名 (`track_recent_*`) と `FEATURES` (`h_*`, `j_*` …) の集合積 — 名前空間が交わらないので **原理的に空振り**

→ 「3 段で守る」の実態は、Fundamental の実データ経路に対して 0 段。静かに壊れる。

## 依頼 5 点への回答

1. **実走で壊れる箇所**: 数値バグ (クラッシュ・切り詰め・単位混在) は `band_calibration` / `delta_distribution` / `_block_boot` / `_band_stat` / `_residualise` に **見つからなかった**。HEAD から `fundamental_eval` を再実行し `n_races 931 / n_horses 12533 / ΔLogLoss 0.016037084517765837 / corr 0.03316647207347025` が artifact と **bit 一致**。見つかったのは意味論の欠陥: 上記 (c)(e)、存在しない `--eval`、`corr_ci95` の 1000 回固定添字、CWD 相対の既定 CSV path。**未検証の食い違い**: commit message「勝ち馬無し 57 レース 771 頭を学習に入れていた」は本セッション再計測 (train 窓 0 行 / validation 窓 205 行) と一致しない — DB 更新の可能性、validation-auditor へ引継ぎ。
2. **単一出典**: 上記 DRY 項。今は許容、0.5-4 前に状態機械の共有設計が必須。
3. **検出器の網羅性**: `features.py` の実出力は `{horse_past_runs: [win_odds, win_popularity], _track_recent_stats: [win_popularity]}` の 2 関数のみ。市場列を f-string / 変数経由で組む箇所は **現状無い**。ただし probe で確認した盲点: モジュール定数経由 (`COL='win_odds'`; 関数外の Constant は走査外)、f-string プレースホルダ、属性アクセス `row.win_odds` は **すべて偽陰性**。`.format('win_odds')` とテーブル名 (`odds_snapshots`) は検出。docstring にこの限界の記述無し。`horse_past_runs` が `win_odds/win_popularity` を fetch している事実は「特徴には流していない (手作業確認)」で済ませており、テストで固定されていない。
4. **全履歴スキャン**: 実測 23.6 s / 呼び出し (556,762 JRA 行、最古 1954 年)。`fit()` は train → validation で **2 回スキャン** (後者は前者の上位集合) → `build_dataset(tr_from, va_to)` 1 回 + 日付分割で半減、意味論は同一。キャッシュ不在は妥当 (日次 ingest で無効化コストが 24 s を上回る)。ただし 2021 年以前の 83% が勝ち馬なしで skip されている事実は、スキャン下限 (例: 勝ち馬行が現れる年) を明示定数にすべきことを示す。
5. **テストの空虚性**: dataset 側は mutation で非空虚を確認。manifest 側は `test_the_actual_fundamental_feature_list_is_clean` が構造的に空虚、`test_code_paths_...` が包含のみで許可リスト非照合。

## 停止条件チェック

- [x] git_sha / git_dirty 記録あり — ただし **git_sha が生成コードを含まないコミットを指す**。数値は HEAD から再現できたため NOT_EVALUABLE にはしない。rule_version / env_overrides: type-B の LGBM 研究モデルには N/A
- [ ] baseline paired 比較 — N/A (type-B、採用主張なし)。参考: T−10 市場との同一 931 レース比較は paired
- [ ] market_snapshot counts — N/A (type-B)
- [ ] payout 欠損 race の扱い — N/A (払戻を使わない)
- [x] 専門領域別停止条件 — 未実装 env 前提の検証: **無し** (`PRED_DISABLE_BLEND` grep 0 件、本改修は env に依存しない)。weight=0 rationale / freshness guard: N/A

## 反証の試み

- 主張「市場由来特徴量数 0 をコードで強制」に対し、`build_dataset` へ市場列を植え込んで全テストを通過させられるかを確認 → **通過する** (上記)。主張は現時点の FEATURES については真 (検出器を手で当てると `{}`)、「強制」については不成立。
- 主張「artifact は c19e716 のクリーンなコードで生成」に対し、当該コミットにスクリプトが存在するか確認 → 存在しない。ただし HEAD で再実行して数値 bit 一致を確認したため、**結果の再現性は成立**、刻印だけが虚偽。

## 主な改善提案

1. **本命経路に検出器を当てるテストを追加 + 台帳照合の完全一致化** — `tests/test_feature_manifest.py` に `assert fm.market_reading_functions(Path("scripts/fundamental_model.py")) == {}` を 1 本、`market_reading_functions()` の features.py 出力が `{"horse_past_runs", "_track_recent_stats"}` と **完全一致** することを要求する 1 本 (新規の市場読み関数が現れたら台帳追記を強制)。さらに `assert_no_market_features` に `source_module: Path` 引数を足し、名前照合と AST 照合を同一関数で行う。
2. **provenance の untracked 検出と data_version** — `predictor/provenance.py` を `--untracked-files=all` に変え、`.gitignore` 外の `*.py` / `*.json` が untracked なら dirty 扱い。`snapshot()` に `conn` を渡す (frontrun は CSV 入力なので `source_csv` の sha256 を代替記録)。
3. **`build_dataset` の統計を窓内に限定し、fit の 2 重スキャンを解消** — `stats` を `r["d"] >= from_date` の分岐内でのみ加算 (窓外は `skipped_before_window` に一括)、`fit()` は `build_dataset(tr_from, va_to)` 1 回 + `date <= tr_to` で分割。併せて `delta_distribution` から恒等 0 の `mean` を削除し、`--eval` 記述を消す。

## 参考所見 (スコープ外・validation-auditor へ)

- `frontrun_analysis` の `n_hypotheses: 16` を meta に記録している点は誠実だが、各 95% 区間は未補正。
- abn `3` (競走除外) 50 頭を「敗者として残す」方針は、`fundamental_eval.py` の `runner_set_mismatch` (6 レース除外) と相互作用しうる (最終オッズから消えた馬がいるレースは丸ごと落ちる)。方針と評価集合の整合は未確認。

## 前回からの差分 (前回 20260914_1600 f3_sealed_holdout: 3.2 / HOLD)

- DRY: 3 → 3 (±0) 本改修固有の二重管理は研究段階として許容、細部の重複が新規発生
- dead code: — → 3 存在しない CLI 記述 / schema に無い列名集合
- マジックナンバー: — → 3
- テスト容易性: 4 (20260822) → 3 (-1) 本命経路の守りが 0 段、包含のみのテストは 09-14 指摘の再発
- 観測可能性: — → 2 artifact 刻印が生成コードを含まない sha を指す、カウンタが窓外を数える
- 前回判定 HOLD → 今回 HOLD。理由変更: 前回は封印の抜け道、今回は「強制」主張と実装の乖離 + provenance 刻印。
