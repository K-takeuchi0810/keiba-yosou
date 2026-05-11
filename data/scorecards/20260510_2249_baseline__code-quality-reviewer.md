# コード品質 / 保守性レビュアー 採点

## 総合: 2.6 / 5

## 項目別

- **DRY / 重複コード: 3/5** — `_w("path", default)` で `weights.json` 経由のスコア集約は確立 (`predictor/rules.py:54-63`、48 箇所で利用) だが、`_score_one` (`predictor/rules.py:83-573`) が 491 行の単一関数で中で「同種T / 同距離 / 同場 / 同場距離帯 / 長距離」など同一形 (`if X_wins>=1: score += min(X_wins,N)*W` の繰り返し) が 7 ブロック以上重複しており、共通ヘルパに抽出されていない。`gui/app.py` (1752 行) でも `_safe` ラッパは 10 箇所で使われているが `_set_status` / `_check_cancel` の呼び出し漏れが手書きで散らばる。
- **dead code / 未使用シンボル: 2/5** — `features.py` で計算されているが `rules.py` で 1 度も `feat.get(...)` されていないキーが 6 個 (`estimated_leg_samples` / `recent_avg_starters` / `same_day_leg_bias` / `same_day_leg_samples` / `same_track_type_runs` / `weight_trend`)。これらの計算コードが残っているため特徴量関数が読みにくい。`scripts/probe_*.py` (`probe_jockey.py` / `probe_jvread.py` / `probe_ra_record.py` / `probe_ramm.py`) は名前から ad-hoc な調査スクリプトと推測でき、整理されないままレポジトリに残っている。
- **マジックナンバー / 設定外出し: 2/5** — `predictor/rules.py` 内に `score += <int>` / `score -= <int>` の直書きが **60 箇所** 残存 (`grep -nE 'score (\+|\-)= [0-9]+'` 集計)。`_w()` 経由の 48 箇所と混在しているため「どの数字が外出し / どれが直書きか」が読まないと判別できない。`gui/app.py:228 _odds_age_minutes` 周辺の 30 分鮮度しきい値や `client.py` のリトライ秒数も config.py には集約されておらず、環境変数または直書きが各所に散在。`config.py` は 36 行と極小で、本来集約すべき定数の受け皿として機能していない。
- **テスト容易性 / 副作用分離: 2/5** — `tests/` ディレクトリが **存在しない** (`ls tests/` → No such file or directory)。`predict_race(conn, ...)` のように `conn` を引数化している点は良 (`rules.py`) だが、`gui/app.py` の `App` クラスは webview / DB / config / fetch を一体保持し pure 部分の単体テストが書けない。`features.py` 内も `conn` を受ける純関数群は良いが、`_score_one` の 491 行に DB 副作用と純計算が混じり始めている (calibrator load 等)。
- **エラー処理 / ログ / 観測可能性: 2/5** — `import logging` / `logger.` の利用が **ゼロ** (`gui/app.py` `predictor/rules.py` `jvlink_client/ingest.py` `web/generator.py` 全て 0 件)。代わりに `print(..., flush=True)` が運用パスに 6 箇所残存 (`gui/app.py:1733,1746,1748` `jvlink_client/ingest.py:193,199` `web/generator.py:268,270`)。`jvlink_client/client.py` に `except Exception: pass` の握り潰しが **9 箇所** (`123-124,148-149,176-177,265-266,303-304,359-360,384-385,394-395,522-523`) あり、JV-Link COM 失敗の根本原因が握り潰されたまま GUI 上は無言で進行する危険。`_safe` の hint (`gui/app.py:44 _error_hint`) は良い仕組みだが client 層には届いていない。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **`jvlink_client/client.py` の `except Exception: pass` 9 箇所を logging に置換** — 最低限 `import logging; logger = logging.getLogger(__name__)` を導入し、握り潰している全ての箇所を `logger.warning("...", exc_info=True)` に変える。原因不明のサイレント失敗が運用の最大リスクで、scorecard 全体を 2.6 → 3.2 まで押し上げる単発で最も効くタスク。`gui/app.py` `web/generator.py` の `print()` 6 箇所も同じ logger に寄せる。
2. **`_score_one` (`predictor/rules.py:83-573`) を 5〜7 個のシグナル関数に分解 + 直書き 60 箇所を `weights.json` に移送** — 「同種T / 同距離 / 同場 / 同場距離帯 / 長距離 / 階級 / 騎手厩舎」を `_score_track_type(feat) -> (delta, reasons)` のような純関数に切り出し、各関数内の `score += 4` 等を全て `_w("track_type.win_per", 4)` 形式に置換。491 行の 1 関数が 100 行強の 6 関数になり、weights.json の sweep スクリプト (`scripts/sweep_weights.py`) が網羅的にチューニングできる。
3. **`tests/` ディレクトリ新設 + `predictor/features.py` の純関数 5 本に最小スモークテスト** — `tests/test_features.py` で `_distance_bucket` `_race_level` `_gate_zone` `estimate_leg_code` `_days_between` を pytest で固定入出力テスト。`requirements.txt` に `pytest` を追加し `run.bat` 系列に `test.bat` を新規。dead feature 6 個 (`weight_trend` 等) はこの段で features.py から削除して dead code を一掃する。

## 前回からの差分

ベースライン採点のため前回スコアなし。
