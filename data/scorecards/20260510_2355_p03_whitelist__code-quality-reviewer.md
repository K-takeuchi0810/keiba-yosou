# コード品質 / 保守性レビュアー 採点

## 総合: 3.5 / 5  (前回 3.4 → +0.1)

## 項目別

- **DRY / 重複コード: 4.5/5** (前回 4 → **+0.5**) — `is_whitelisted_race(race)` を `config.py:68-82` に一元定義し、`gui/app.py:237` / `web/generator.py:147` / `scripts/backtest.py:187,316` の **4 箇所全て同じ関数を共有**。grade/track の判定ロジックがどこにも複製されておらず、whitelist 仕様変更は config の 1 箇所修正で全経路に反映する設計。`buy_whitelist_enabled()` も同様に集約。前回懸念の `predictor/rules.py:_score_one` 直書き 60 行は不変だが、本改修では新規重複を一切持ち込まず、むしろ DRY を改善した点を評価して +0.5。-0.5 の理由は `scripts/backtest.py:186, 315` で同じ関数を 2 回ローカル import している (循環回避コメントあり) こと。トップで 1 度 import すれば足りる (循環は実際には起きない)。

- **dead code / 未使用シンボル: 2/5** (前回 2 → ±0) — 未着手 (想定通り)。`scripts/probe_*.py` 4 本、`features.py` の 6 個未使用キー、`buy_filter_from_generator` misnomer は全て残存。今回の改修範囲外なので据え置き。

- **マジックナンバー / 設定外出し: 4.5/5** (前回 4 → **+0.5**) — `whitelist_grades=["A","B","C","F"]` / `whitelist_tracks=["07","09"]` を `BUY_FILTER_DEFAULT` に外出し済で、コード内に grade コードや track コードの直書きは一切無い (grep 確認)。さらに **根拠コメントが秀逸**: `config.py:46-49` で「1,164 戦の長期 backtest (data/backtest/20260510_232027_*.json) で唯一控除率 80% を超えていた領域 (G1/G2/G3 = 115.4%、中山 91.4%、京都 80.3%)」と数値根拠と元データへのリンクを残しており、半年後の自分が「なぜ G1〜G3 と中山京都だけなのか」を即追跡できる。`predictor/rules.py` の直書き 60 / `weights.json` 経由 48 の混在は不変だが、新規定数で外し漏れが無い点を評価。`jvlink_client/client.py` の retry 秒数のみ残存で 5 には届かず。

- **テスト容易性 / 副作用分離: 2.5/5** (前回 2 → **+0.5**) — `tests/` 不在は不変だが、`is_whitelisted_race(race: dict) -> bool` は **環境変数読み取り 1 回 + dict.get 2 回 + 集合判定** だけのほぼピュア関数で、testable 度は極めて高い (`config.BUY_FILTER_DEFAULT["whitelist_mode"]` を monkeypatch するか `BET_WHITELIST` env を `monkeypatch.setenv` するだけで全分岐到達可能)。`buy_whitelist_enabled()` も同様。3 ファイル全てから同じ関数を呼ぶ設計なので、関数 1 個に対する unit test を書けば 3 経路の挙動を保証できる「テストの ROI が高い」コードになっており、構造的にはテスト容易性が改善した。test ファイル不在で +0.5 止まり。

- **エラー処理 / ログ / 観測可能性: 4.5/5** (前回 4.5 → ±0) — 今回の改修は新規 try/except / logger 呼び出しを追加していないが、`is_whitelisted_race` は例外を投げず `(race.get(...) or "").strip()` で None / 欠損を吸収する防御的実装。`backtest.py` の `whitelist_only_stats` も `_empty_bet_stats()` / `_finish_bet_stats()` 既存パターンを踏襲しており観測可能性 (whitelist 単独のベット数・的中率・回収率を JSON 出力に追加) を素直に拡張。前回完成済みのレベルを維持。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **`scripts/backtest.py:186, 315` の二重ローカル import を削除** — トップレベル import (`from config import is_whitelisted_race`) に昇格すれば 2 行削れる。「循環回避」コメントが付いているが、`config.py` は標準ライブラリと dotenv しか import しておらず `scripts/backtest.py` を逆参照しないので循環は発生しない。低リスクで項目 1 が 4.5 → 5、総合 3.5 → 3.6。

2. **`tests/test_whitelist.py` を 1 ファイルだけ新設** — `is_whitelisted_race({"grade_code": "A", "track_code": "01"})` / `({"grade_code": "", "track_code": "07"})` / `({"grade_code": "Z", "track_code": "01"})` / `BET_WHITELIST=0` で全 True / 空 dict 等 5 ケースを書けば、tests/ ディレクトリ初出として project に test 文化を持ち込める。項目 4 が 2.5 → 3.5、総合 3.5 → 3.7。

3. **(前回繰越) `scripts/probe_*.py` 4 本を `scripts/_archive/` へ退避** — dead code 整理で項目 2 が 2 → 3、総合 3.7 → 3.9 に届く。今回の改修とは独立した一発作業。

## 前回からの差分

- 項目1 (DRY): 4 → 4.5 (**+0.5**) **改善**: 新規共有関数 `is_whitelisted_race` を 4 経路で再利用、grade/track 判定の複製ゼロ
- 項目2 (dead code): 2 → 2 (±0) **維持**: 未着手 (改修範囲外、想定通り)
- 項目3 (magic number): 4 → 4.5 (**+0.5**) **改善**: whitelist_grades/tracks を config 外出し + 1,164 戦 backtest の根拠数値をコメントに残す
- 項目4 (test): 2 → 2.5 (**+0.5**) **微改善**: 新規関数がほぼピュアで testable、ROI 高い構造
- 項目5 (logging): 4.5 → 4.5 (±0) **維持**: 防御的 None 処理で例外を出さない既存品質を継続

総合: 3.4 → 3.5 (+0.1) — 4 経路 DRY と config 外出しで小幅改善。次のレバーは tests/ 初出 (提案 #2) と dead code 整理 (提案 #3)。
