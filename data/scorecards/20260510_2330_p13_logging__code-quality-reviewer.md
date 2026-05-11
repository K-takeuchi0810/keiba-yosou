# コード品質 / 保守性レビュアー 採点

## 総合: 3.4 / 5  (前回 3.0 → +0.4)

## 項目別

- **DRY / 重複コード: 4/5** (前回 4 → ±0) — 観測性改修は logger を 3 ファイルに各 1 行で局所化されており重複は無い。`logger.warning("JVClose at __exit__ failed", ...)` / `"JVClose before fetch(%s) failed"` / `"JVClose during retry of %s failed"` のメッセージはコンテキスト (どの段階か) を文字列リテラルで個別化していて grep 容易。一方で `predictor/rules.py:_score_one` の長大関数と類似シグナル重複は今回も対象外で残存、`weights.json` 経由 48 / 直書き 60 の混在も不変。

- **dead code / 未使用シンボル: 2/5** (前回 2 → ±0) — 未着手。`scripts/probe_*.py` 4 本、`features.py` の 6 個未使用キー、`buy_filter_from_generator` misnomer は全て残存。今回の改修範囲外なので想定どおりだが据え置き。

- **マジックナンバー / 設定外出し: 4/5** (前回 4 → ±0) — 前回までに `gui/app.py:634` の 30 と calibrator の min_count / shrinkage_alpha が解決済みで 4 で頭打ち。`jvlink_client/client.py` の retry 秒数 (`time.sleep(delay)` 周辺) はまだ直書きで 5 には届かないが、今回の主役は別軸。

- **テスト容易性 / 副作用分離: 2/5** (前回 2 → ±0) — `tests/` 不在は不変。logger 化はピュア性を損ねず (`getLogger(__name__)` は標準 logging への副作用だが Python 慣習でテスト時は handler 差し替えで吸収可能) `caplog` fixture で検証可能な構造になり、むしろテスト容易性は微改善。ただし test ファイル不在のため点数据え置き。

- **エラー処理 / ログ / 観測可能性: 4.5/5** (前回 2 → **+2.5**) — 今回の主役。`jvlink_client/client.py:131-132, 156-157, 184-185, 273-278, 314-318, 372-376, 400-405, 413-417, 544-548` の **全 9 箇所** が `logger.warning(..., exc_info=True)` 化済み (grep で "except Exception:" → 直後 `pass` がゼロを確認、全て `logger.warning(...)` が続く)。各メッセージは「JVClose at __exit__ failed」「JVClose before fetch(%s) failed」「JVFiledelete(%r) failed for bad file in %s」のように **どの段階・どの引数で失敗したか** が文字列に埋め込まれており、ログ単体で原因切り分け可能。`jvlink_client/ingest.py:196` も `logger.error("ingest failed: %s", f.name, exc_info=True)` で `print(..., flush=True)` 時代より格段に追跡しやすく、かつ `summary["errors"]` への構造化記録と二重化されている (人間には stderr で見え、プログラムには summary dict で読める優れた設計)。`predictor/rules.py:763-766` は前回提案 #2 をそのまま実装、`unsupported type=%r in calibrator.json` で具体的な type 値を表示するので「typo」「古いスキーマ」「JSON 壊れ」を区別可能。`logging.getLogger(__name__)` で 3 ファイル全てモジュール名前空間を分離しており `logging.basicConfig(level=DEBUG)` で部分的に絞れる正攻法。CLI 起動時の `gui/app.py:1761,1774,1776` の `print` は維持されておりこれは妥当 (logging 初期化前に実行される起動ログなので print のままで良い)。**5 に届かない 0.5 点減**: (a) logger 用の handler / format を `config.py` 等で集約初期化する箇所が無く、デフォルト stderr 出力に頼っている (本番では `logs/jvlink.log` 等への書き出しが望ましい)、(b) `jvlink_client/ingest.py:202` の `print(ingest_all())` は CLI 戻り値表示なのでこれは print で正しい (除外対象)。改修範囲では満点に近い完成度。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **logging handler の集約初期化を `config.py` か `gui/app.py` 起動時に追加** — 現状 `getLogger(__name__)` のみで handler 未設定なので、`gui` 経由で起動した際 `logger.warning` が GUI コンソールに出ない or root logger 設定次第で消える可能性。`logging.basicConfig(level=os.environ.get("KEIBA_LOG_LEVEL", "WARNING"), format="%(asctime)s %(name)s %(levelname)s: %(message)s", handlers=[logging.StreamHandler(), logging.FileHandler("logs/keiba.log")])` を `gui/app.py` の `__main__` 直下と `scripts/*.py` の起動時に一発入れれば項目 5 が 4.5 → 5、総合 3.4 → 3.5。

2. **`scripts/probe_*.py` 4 本を `scripts/_archive/` へ退避 + `buy_filter_from_generator` を `default_buy_filter` にリネーム** — dead code 整理で項目 2 が 2 → 3、総合 3.4 → 3.6。grep して移動・置換するだけの低リスク作業。前回からの繰越。

3. **`jvlink_client/client.py` の retry 秒数 (`time.sleep(delay)` の `delay` 起源) を `config.py` の `JVLINK_RETRY_DELAYS` 定数化** — 項目 3 で 4 → 5 に届かない最後の壁。`(2, 5, 10)` のような tuple を config で定義し、import して使う。

## 前回からの差分

- 項目1 (DRY): 4 → 4 (±0) **維持**: 既に 4 で頭打ち、今回も新規重複なし
- 項目2 (dead code): 2 → 2 (±0) **維持**: 未着手 (改修範囲外)
- 項目3 (magic number): 4 → 4 (±0) **維持**: 既に 4、retry 秒数のみ未対応
- 項目4 (test): 2 → 2 (±0) **維持**: tests/ 不在 (logger 化でテスト容易性は内部的には微改善)
- 項目5 (logging): 2 → 4.5 (**+2.5**) **大幅改善**: `except Exception: pass` 9 箇所全置換 + ingest 運用 print 撲滅 + calibrator 破損時警告追加 + 3 ファイルに `getLogger(__name__)` 整備。前回 3 連続最優先提案がついに完了

総合: 3.0 → 3.4 (+0.4) — 観測性 1 軸で +2.5 / 5 軸平均 +0.5、丸めて +0.4。次のレバーは項目 2 (dead code 整理) と handler 集約初期化。
