# 検証プロセス監査人 採点

## 総合: 3.4 / 5  (前回 3.2 → +0.2)

P0-1 で `config.BUY_FILTER_DEFAULT` が単一出典になり、生成側 (`web/generator.py:14,32-39`) と GUI dashboard (`gui/app.py:23,177-183,1642-1644`) が同じ値を参照するようになった。**ただし `scripts/backtest.py` は依然として `web.generator` の `BET_MIN_*` 経由 (`scripts/backtest.py:30`) で読み込む構図のため、結果として config を間接参照しているにすぎず、「config を変えれば backtest も追随する」動線は確かに成立 (web.generator が config を import するため)** 。A/B 比較性は前進したが、過適合監視・期間分割の不在は未着手。

## 項目別

- **バックテスト設計の正しさ: 4/5 (±0)** — `scripts/backtest.py` 本体未変更だが、デフォルト引数の出所が `BUY_FILTER_DEFAULT` に紐づいたことで「テスト時のフィルタが実本番と一致する」保証が形式化された。前回指摘 (馬連 BOX 未カバー / 多重的中合算なし) は未着手のため +1 には届かず据え置き。
- **時系列リーク防止: 4/5 (±0)** — 今回の改修対象外。`predictor/features.py` の strict `<` 境界も calibrator 期間分離未強制も変化なし。
- **calibration / reliability 計測: 3/5 (±0)** — `predictor/calibrator.json` は変更ファイルに含まれるがビン定義・shrinkage 運用は同じ。高確率帯のサンプル枯渇 (count<10 多数)、reliability diagram 未生成は未対応。
- **A/B 比較 / バージョン管理: 4/5 (3 → 4, +1)** — **ここが今回の主改善点**。フィルタ値が config に集約されたことで「`config.BUY_FILTER_DEFAULT` (買い基準) × `weights.json` (スコアリング) × `calibrator.json` (校正) × `--rule-version` タグ」の 4 軸で実験を切れるようになった。`gui/app.py:177-183` の `get_buy_filter_default` API も dashboard 側のハードコード重複を排除し、UI 表示値とバックテストのデフォルトが乖離するバグの種を潰した。1 点減点は「config の値を変えても rule_version を強制的に bump する仕組みが無い」「`config.py` 自体を git diff で追うしかない (機械可読な変更履歴が無い)」点。
- **過適合監視 / 期間分割評価: 2/5 (±0)** — walk-forward / CV / 期間分離は未着手。直近 backtest 5 件 (`20260510_093223_*` 〜 `20260509_115246_*`) も依然として 5/2-5/3 の 2 日間と週確認に集中、5/6 以降 backtest を走らせていない。**P0-1 改修後に新たな backtest が 1 件も保存されていない** (最新が 09:32、改修は 23:00 頃) のは A/B 検証の機会損失。問答無用 2 点ルール該当のため据え置き。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **P0-1 の効果を測る backtest を即座に 1 本走らせる** — 改修後 backtest が 0 件のままだと「config 一元化したけど数値は何も変わらないと信じている」状態。`scripts/backtest.py --from 20260101 --to 20260430 --rule-version p01-buy-filter-unified --bet tan` を実行し、`p01-buy-filter-unified.json` を `data/backtest/` に保存。前回の `tuned-week-check` (52.2%) と同期間で取り直し、return_rate が一致することを確認する (一致しなければ参照経路にバグ)。
2. **`scripts/backtest.py:29-37` を直接 config 参照に置換** — 現状 `from web.generator import BET_MIN_EV, ...` 経由で間接的に config を読んでいるが、`from config import BUY_FILTER_DEFAULT` に置換すれば「web/generator が将来削除/リネームされても backtest が壊れない」「buy_filter の単一出典という設計意図が backtest 側のコードからも明示される」。10 行未満の変更で前回指摘の A/B 軸明示性がさらに上がる。
3. **walk-forward ハーネス (前回 1 番手提案を継続)** — `scripts/walk_forward.py` を新設し、`--window 30 --step 7` で連続評価。P0-1 が「frozen config を信じて長期で測る」前提を整えたので、次の自然な投資先はこれ。短期 2 日 52% が本物か判定する唯一の手段。

## 前回からの差分

- バックテスト設計の正しさ: 4 → 4 (±0) 維持: backtest スクリプト本体未変更
- 時系列リーク防止: 4 → 4 (±0) 維持: 改修対象外
- calibration / reliability 計測: 3 → 3 (±0) 維持: ビン運用に変更なし
- A/B 比較 / バージョン管理: 3 → 4 (+1) 改善: config による単一出典化で「フィルタ × 重み × 校正 × タグ」の 4 軸に整理
- 過適合監視 / 期間分割評価: 2 → 2 (±0) 維持: walk-forward / CV 不在は変わらず、改修後 backtest も未実行
