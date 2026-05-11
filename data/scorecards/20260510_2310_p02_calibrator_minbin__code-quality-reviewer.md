# コード品質 / 保守性レビュアー 採点

## 総合: 3.0 / 5  (前回 2.8 → +0.2)

## 項目別

- **DRY / 重複コード: 4/5** (前回 4 → ±0) — `BUY_FILTER_DEFAULT` 一元化は維持。`scripts/backtest.py:29-43 buy_filter_from_generator()` は今回 `web.generator` 経由を捨てて `from config import BUY_FILTER_DEFAULT` を直接 import する形に変更され、依存方向が「scripts → config」の単一矢印に整理された (以前は scripts → web.generator → config の遠回りで、`web.generator` を読まないと既定値の出典が辿れなかった)。コメントも「出典は config.BUY_FILTER_DEFAULT 単一」と明示されており模範的。`predictor/rules.py:_score_one` の長大関数と類似シグナル重複は今回も対象外で残存。
- **dead code / 未使用シンボル: 2/5** (前回 2 → ±0) — features.py の 6 個未使用キー / `scripts/probe_*.py` 4 本は今回も手付かず。`buy_filter_from_generator` という関数名は「`web.generator` 経由」だった歴史的経緯を残す misnomer になった (実装は config 直読み) が、呼び出し側互換のためそのままにした判断は妥当。改名するなら `default_buy_filter()` 推奨だが小さい話。
- **マジックナンバー / 設定外出し: 4/5** (前回 3 → +1) — `gui/app.py:634` の直書き 30 が `max_age = int(BUY_FILTER_DEFAULT["max_odds_age_min"])` に置換され、warnings 文言も `f"...(>{max_age}分)..."` で動的化。前回指摘 #1 が完全解消。さらに `_apply_calibrator` 側で `min_count` (既定 50) と `shrinkage_alpha` (既定 30) が `predictor/calibrator.json` に外出しされ、環境変数 `PRED_CALIBRATOR_MIN_COUNT` でも上書き可能。`calibrator.json` 内に `_comment_min_count` で根拠と再生成手順まで書かれており「数値の意味が後から読める」状態。`predictor/rules.py` の直書き定数 60 箇所 / `weights.json` 経由 `_w()` 48 箇所の混在は不変、`jvlink_client/client.py` リトライ秒数も未対応で 5 には届かず。
- **テスト容易性 / 副作用分離: 2/5** (前回 2 → ±0) — `tests/` 不在は不変。ただし `_apply_calibrator(probabilities)` は引数で確率辞書を受け取り戻り値で辞書を返すピュア構造を維持しており (`_load_calibrator` のみ I/O だが `lru_cache`)、`min_count` / `alpha` 分岐ロジックは単体テストしやすい設計。テストファイル不在のため点数据え置き。
- **エラー処理 / ログ / 観測可能性: 2/5** (前回 2 → ±0) — `jvlink_client/client.py` の `except Exception:` 9 箇所は不変。`_apply_calibrator` の `try/except (TypeError, ValueError):` は `alpha_default` / `min_count_default` のパース個別に分けて狭く取られており良い設計だが、calibrator.json 全体が壊れた場合の警告ログは無い (`return probabilities` で静かに pass-through)。`logging` 導入ゼロは継続。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **`jvlink_client/client.py` の `except Exception: pass` 9 箇所を `logger.warning(..., exc_info=True)` に置換** — 前回・前々回と同じ最重要提案。`import logging; logger = logging.getLogger(__name__)` を入れて全 9 箇所を置換すれば項目 5 が 2 → 3.5、総合 3.0 → 3.3 まで上がる単発で最大効果のタスク。calibrator 周りで設定外出しは進んだので、次のレバーは観測可能性。
2. **`_apply_calibrator` の calibrator.json 破損時に warn ログを 1 行入れる** — `predictor/rules.py:754-756` で `if not calibrator or calibrator.get("type") != "bin": return probabilities` が静かに raw 返却するので、`predictor/calibrator.json` がうっかり壊れても予想は走り続けてしまう (バックテスト結果が静かに劣化する典型的サイレントバグ)。`logger.warning("calibrator disabled: type=%s", calibrator.get("type"))` を 1 行足すだけ。
3. **`scripts/backtest.py:buy_filter_from_generator` を `default_buy_filter` にリネーム + `scripts/probe_*.py` 4 本を `scripts/_archive/` へ退避** — 関数名と実装の乖離を解消、ad-hoc スクリプトの整理で項目 2 が 2 → 3 に上がる。grep して移動・置換するだけ。

## 前回からの差分

- 項目1 (DRY): 4 → 4 (±0) **維持**: backtest.py が config 直読みになり依存方向が単純化されたが既に 4 で頭打ち
- 項目2 (dead code): 2 → 2 (±0) **維持**: 未着手
- 項目3 (magic number): 3 → 4 (+1) **改善**: `gui/app.py:634` 直書き 30 解消 + `min_count`/`shrinkage_alpha` を calibrator.json に外出し + コメントで根拠記載
- 項目4 (test): 2 → 2 (±0) **維持**: tests/ 不在
- 項目5 (logging): 2 → 2 (±0) **維持**: except: pass 9 箇所 + print 6 箇所 + calibrator 破損時無警告

総合: 2.8 → 3.0 (+0.2)
