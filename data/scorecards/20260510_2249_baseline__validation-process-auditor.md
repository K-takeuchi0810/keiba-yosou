# 検証プロセス監査人 採点

## 総合: 3.2 / 5

ベースライン採点 (前回 scorecard なし)。基本構造は揃っている (rule_version タグ、calibration 計測、ブレイクダウン 4 軸、リーク防止のための strict `<` 境界) ため 1〜2 点ではなく 3 点台に置く。ただし高確率帯のサンプル枯渇、A/B 結果の集約・比較ハーネス不在、walk-forward / CV 不在で 4 には届かない。

## 項目別

- **バックテスト設計の正しさ: 4/5** — `scripts/backtest.py:74-86` が中央場 (track_code 1-10) を SQL レベルで限定、`races_total / no_horses / no_pick / filtered / tentative / bet` の分流カウントあり、`by_track / by_class / by_bucket / by_confidence` と `all_*` / `buy_only_*` の二系統並列出力。設計は良好で、不足は「`--bet` が tan/fuku のみで馬連 BOX 等を未カバー」「`get_payout` で同着行を 1〜3 / 1〜5 まで走査するが多重的中の合算ロジックが無い (現状単勝なので影響軽微)」程度。
- **時系列リーク防止: 4/5** — `predictor/features.py` 全 7 箇所の過去走サブクエリが `(hr.race_year || hr.race_month_day) < ?` の strict `<` を使用 (154/211/277/302/492/560 行)。同日バイアス系も `r.start_time < ?` (331/374/430 行) で前向き厳格。確認できる範囲ではリーク無し。1 点減点は「calibrator.json (`source_count=512`) が `--save-calibrator` で同じ期間のデータから fit され、その後同期間で評価されると軽い自己参照が発生し得る — 期間分離の運用ルールがコードでは強制されていない」点。
- **calibration / reliability 計測: 3/5** — `predictor/calibration.py` 経由で Brier / log_loss / bin 別 actual vs avg_probability が `result["calibration"]` に格納され、保存 JSON にも入る (recent 6 件中 5 件で `calibration` キー有)。`calibrator.json` は `shrinkage_alpha=30 / min_count=20` を明記。一方で **0.30 以上のビンは count=0〜4** で実質ノイズ、0.15-0.20 の `calibrated_probability=0.3333` (avg=0.1725) は shrinkage の挙動に疑義。`source_count=512` は標本としても薄い。reliability diagram の可視化も無い。
- **A/B 比較 / バージョン管理: 3/5** — `--rule-version` が CLI 引数として存在し、保存 JSON のファイル名と本文両方に反映される (`v1-baseline / v2-grade / current-week-check / tuned-week-check` が直近 8 件で確認)。環境変数による切替 (`V2_GRADE` `V2_DIST` `PRED_CALIBRATOR_ALPHA` 等) も `predictor/rules.py` に存在。ただし **A/B を並べる比較スクリプトが無い** (`data/backtest/*.json` を読んで rule_version × 期間で diff を出すツールが未整備)。`weights.json` / `calibrator.json` はバージョン履歴を残さず上書きで、git に依存。
- **過適合監視 / 期間分割評価: 2/5** — 直近 6 件中 5 件が **20260502-20260503 の 2 日間** または **20260430-20260503 の 4 日間** に集中、長期サンプル (20250601-20260430) は 1 件のみで 5 月 6 日以降走らせていない。「直近 2 日で重み調整 → 直近 2 日で評価」が `tuned-week-check` (52.2%) と `current-week-check` (50.7%) の比較で実際に発生しており自己参照リスクが高い。walk-forward / k-fold / train-test 期間分離の仕組みは無く、CV 的な分割運用も未確立。問答無用 1〜2 点ルールに該当する側面 (期間分割評価不在) のため 2 点。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **walk-forward 評価ハーネスを追加 (最優先)** — `scripts/walk_forward.py` を新設し、`--from 20250601 --to 20260430 --window 30 --step 7` のように学習窓と評価窓を分離して連続 backtest。各窓の return_rate を CSV / JSON に出して trend を見られるようにする。短期 2 日の回収率 52% を「本物か」と判定する唯一の方法はこれ。`scripts/backtest.py:194` の `run_backtest` を窓ごとに呼び出すラッパで実装可能。
2. **calibrator の高確率帯対策と reliability diagram** — `predictor/calibrator.json` で count<10 のビンは `calibrated_probability` を `avg_probability` に固定 (現実装は既にそうだが 0.15-0.20 の異常値 0.3333 が混入しており要検証)、かつ count<min_count なら近隣ビンへ merge する isotonic regression または monotonic 制約を入れる。並行して `scripts/plot_calibration.py` で X=avg_probability / Y=actual_win_rate の reliability curve を PNG 保存 (matplotlib 1 ファイルで十分)。
3. **A/B 比較スクリプトを追加** — `scripts/compare_runs.py --base v1-baseline --new v2-grade [--from --to]` で `data/backtest/*.json` から該当 rule_version をロードし、return_rate / hit_rate / Brier / by_class / by_bucket を side-by-side 表示し有意差判定 (bootstrap で十分)。`weights.json` / `calibrator.json` の保存時に rule_version を内部に書き込み、後から「このバックテスト結果が使った重みは何か」を追跡可能にする (`scripts/backtest.py:558-564` の `--save-calibrator` 出力に `"rule_version": args.rule_version` を追記するだけでも前進)。

## 前回からの差分

ベースライン採点のため差分なし。
