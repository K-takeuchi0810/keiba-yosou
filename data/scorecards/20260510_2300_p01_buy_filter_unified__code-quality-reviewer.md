# コード品質 / 保守性レビュアー 採点

## 総合: 2.8 / 5  (前回 2.6 → +0.2)

## 項目別

- **DRY / 重複コード: 4/5** (前回 3 → +1) — `BUY_FILTER_DEFAULT` を `config.py:38-44` の 1 箇所に集約し、`web/generator.py:35-39` (`BET_MIN_*` を `BUY_FILTER_DEFAULT[...]` から派生)、`gui/app.py:23,31,177-183,224-228`、`scripts/backtest.py:30-36 buy_filter_from_generator()` が全て同じソースを参照。GUI dashboard JS も `Api.get_buy_filter_default()` (`gui/app.py:1642-1644`) で Python 側 config を取りに行くので、HTML 直書き初期値と Python の二重管理が解消。`_score_one` (`predictor/rules.py`) の長大関数と類似シグナル 7 ブロック重複は今回の改修対象外なので残存しているが、買い目フィルタ系の DRY は模範的水準まで到達。
- **dead code / 未使用シンボル: 2/5** (前回 2 → ±0) — `features.py` で計算するが `rules.py` 未使用の 6 キー (`estimated_leg_samples` / `recent_avg_starters` / `same_day_leg_bias` / `same_day_leg_samples` / `same_track_type_runs` / `weight_trend`) は今回手付かず。`scripts/probe_*.py` 4 本も整理されないまま残っている。改修スコープ外。
- **マジックナンバー / 設定外出し: 3/5** (前回 2 → +1) — 買い目フィルタ 4 値 + `max_odds_age_min` (= 30 分) が `config.BUY_FILTER_DEFAULT` に集約され、`web/generator.py` `gui/app.py` `scripts/backtest.py` から「コメント付きで根拠が読める」状態に到達。ただし `gui/app.py:634` の `if odds_age is not None and odds_age > 30:` (warnings 表示分岐) は `BUY_FILTER_DEFAULT["max_odds_age_min"]` を参照すべきところ直書き 30 が残存しており、config 変更時にここだけ追従しない不整合リスクあり。`predictor/rules.py` の直書き定数は **60 箇所** で前回と同数 (`grep -nE 'score (\+|\-)= [0-9]+\.?[0-9]*'`)、`weights.json` 経由の `_w()` 利用 48 箇所と混在状態は不変。`jvlink_client/client.py` のリトライ秒数も config 化されていない。
- **テスト容易性 / 副作用分離: 2/5** (前回 2 → ±0) — `tests/` ディレクトリ依然不在 (`ls tests/` → No such file or directory)。今回の改修は config 集約のみで、純関数化や副作用分離には進んでいない。`get_buy_filter_default(self, options)` はピュアな辞書返却で副作用なしなので testable 設計だが、テストファイルが書かれていないため点数に反映できず。
- **エラー処理 / ログ / 観測可能性: 2/5** (前回 2 → ±0) — `jvlink_client/client.py` の `except Exception:` (123/148/176/265/303/359/384/394/522) **9 箇所** 全て握り潰しのまま (`grep -n "except.*:"` で確認)。`gui/app.py` `web/generator.py` の `print(..., flush=True)` 6 箇所も今回改修なし。`logging` 導入ゼロ。改修スコープ外。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **`gui/app.py:634` の直書き 30 を `BUY_FILTER_DEFAULT["max_odds_age_min"]` に置換** — 今回せっかく config 一元化したのに warnings 分岐 1 箇所だけ手書き 30 が残っている。`max_age_min = int(BUY_FILTER_DEFAULT["max_odds_age_min"])` を冒頭で取って `if odds_age is not None and odds_age > max_age_min:` に直すだけ。10 分の作業で項目 3 が 3.5 まで上がる。
2. **`jvlink_client/client.py` の `except Exception: pass` 9 箇所を `logger.warning(..., exc_info=True)` に置換** — 前回 scorecard と同じ最重要提案。`import logging; logger = logging.getLogger(__name__)` を入れて全 9 箇所を置換すれば、項目 5 が 2 → 3.5、総合 2.8 → 3.1 まで押し上がる単発で最大効果のタスク。
3. **`scripts/probe_*.py` 4 本を `scripts/_archive/` 等へ退避 + dead feature 6 個を `predictor/features.py` から削除** — リポジトリ直下の ad-hoc スクリプトと `weight_trend` 等の未使用 feat を一掃すれば項目 2 が 2 → 3 に上がる。改修コストは grep して移動 / 削除するだけ。

## 前回からの差分

- 項目1 (DRY): 3 → 4 (+1) **改善**: `BUY_FILTER_DEFAULT` 一元化 + GUI JS の `Api.get_buy_filter_default()` 連携で買い目フィルタの二重定義が完全消滅
- 項目2 (dead code): 2 → 2 (±0) **維持**: 改修スコープ外、6 features と probe_*.py は未着手
- 項目3 (magic number): 2 → 3 (+1) **改善**: 4 値 + `max_odds_age_min` が config 化、コメントに「唯一の出典」と明記。ただし `gui/app.py:634` の直書き 30 が漏れたため 3 止まり (4 には届かず)
- 項目4 (test): 2 → 2 (±0) **維持**: `tests/` 不在
- 項目5 (logging): 2 → 2 (±0) **維持**: `except: pass` 9 箇所 + `print` 6 箇所は不変

総合: 2.6 → 2.8 (+0.2)
