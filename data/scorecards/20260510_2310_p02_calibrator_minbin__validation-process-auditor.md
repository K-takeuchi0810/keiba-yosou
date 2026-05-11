# 検証プロセス監査人 採点

## 総合: 3.6 / 5  (前回 3.4 → +0.2)

P0-2 で `_apply_calibrator` (`predictor/rules.py:737-796`) に「count < min_count なら raw に恒等寄せ」のセーフティを追加し、`predictor/calibrator.json` の `min_count` を 20 → 50 に引き上げ。前回 calibrator.json で問題視した「count=27 の 0.15-0.20 bin が calibrated=0.3333 を吐いて高 EV 候補を量産する」病巣を封じ、`shrinkage_alpha=30` と二段で防御する設計に進化。さらに前回指摘 #2 (`scripts/backtest.py` の web.generator 経由間接参照) も吸収され、`scripts/backtest.py:36 from config import BUY_FILTER_DEFAULT` で直接参照に変更。**ただし P0-1/P0-2 後の backtest が依然として 1 件も保存されておらず (最新が 5/10 09:32、改修は 23:00 以降)**、効果測定は紙面上の話に留まる。

## 項目別

- **バックテスト設計の正しさ: 4/5 (±0)** — `buy_filter_from_generator` が config を直接読む形になり、フィルタ伝搬経路が 1 段短縮された (`scripts/backtest.py:36-43`)。馬連 BOX 未カバー / 多重的中合算なしは継続課題のため据え置き。
- **時系列リーク防止: 4/5 (±0)** — 改修対象外。calibrator は依然として「学習用日付と評価用日付の分離が強制されない」運用 (calibrator.json に `from_date`/`to_date` のメタが無い)。今回は触っていないため減点せず。
- **calibration / reliability 計測: 4/5 (3 → 4, +1)** — **今回の主役**。(a) `min_count=50` に引き上げで count=27 (0.15-0.20)、count=11 (0.20-0.25)、count=4 (0.25-0.30)、count=2 (0.35-0.40) の 4 bin が恒等寄せ対象に転落し、ノイズ駆動の偽 calibrated を遮断。(b) コード側で `< min_count` を `q = p` に確定させ、shrinkage と独立した強い安全弁を持った。(c) calibrator.json に `_comment_min_count` の運用メモが入り「値変更後は --save-calibrator で再生成」が形式知化。1 点減点は **(i) reliability diagram (PNG/SVG) を出力していない**、**(ii) `brier_score=0.058 / log_loss=0.211` の時系列推移を残す仕組みが無い (上書きで履歴消失)**、**(iii) min_count=50 引き上げで 0.05-0.10 (count=99) と 0.10-0.15 (count=52) ギリギリ通過の 2 bin しか実質校正が効かない状態 (校正の効くレンジが極端に狭い) ことが calibrator.json から自明だが、警告ログが backtest 出力に出ない**。
- **A/B 比較 / バージョン管理: 4/5 (±0)** — `scripts/backtest.py` の直接 config 参照化で前回提案 #2 が完了、A/B 軸の明示性は 4 軸 (filter × weights × calibrator × rule_version) のまま強化。`PRED_CALIBRATOR_MIN_COUNT` 環境変数 (`predictor/rules.py:772`) の追加で min_count スイープも可能になった。1 点減点の理由は前回と同じ (config / calibrator.json 変更時に rule_version 強制 bump の仕組みが無い、機械可読な変更履歴が無い)。
- **過適合監視 / 期間分割評価: 2/5 (±0)** — walk-forward / CV / 期間分離は未着手。**かつ P0-1 / P0-2 連続改修後の backtest が 0 件のまま**で、min_count=50 引き上げが本当に return_rate を改善したのか悪化させたのか誰も知らない。問答無用 2 点ルール継続。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **【警告】改修と backtest 保存をペアで運用ルール化** — 前回も同じ警告を出したが解消されず、P0-1 後の backtest 0 件のまま P0-2 が積まれた。最低限 `expert-review` メタスキルか pre-commit フックで「`predictor/{rules.py,weights.json,calibrator.json}` または `config.py` の git diff があるのに `data/backtest/*.json` の最新 mtime が改修より古い場合は警告」の機械的ガードを入れる。さもなくば改修ごとに「数値根拠なし採点」が積み重なる。即対応として `python scripts/backtest.py --from 20260101 --to 20260430 --rule-version p02-calibrator-minbin --bet tan --save` を 1 本走らせる。
2. **calibrator.json に学習期間メタを追加** — `from_date` / `to_date` / `source_count` (既存) / `generated_at` を必須化し、backtest 実行時に「評価期間が calibrator 学習期間と重複していたら警告」を `scripts/backtest.py` に組み込む (10 行未満)。これで calibrator.json の時系列リークを構造的に防げる。
3. **reliability diagram を `data/backtest/` に PNG 出力** — `scripts/backtest.py` 末尾で `bins[].avg_probability` vs `bins[].actual_win_rate` を 1 枚 plot し、`<rule_version>_reliability.png` で保存。min_count=50 引き上げで実質校正が効くのが 0.05-0.15 の 2 bin だけ、という現状が一目で分かるようになる。

## 前回からの差分

- バックテスト設計の正しさ: 4 → 4 (±0) 維持: backtest 本体ロジック未変更だが config 直参照化で配線整理は前進
- 時系列リーク防止: 4 → 4 (±0) 維持: 改修対象外
- calibration / reliability 計測: 3 → 4 (+1) 改善: min_count=50 + 少数 bin 恒等寄せの二段防御で「ノイズ bin が EV を暴走させる」リスクを構造的に封じた
- A/B 比較 / バージョン管理: 4 → 4 (±0) 維持: 前回提案 #2 (config 直参照化) が完了、`PRED_CALIBRATOR_MIN_COUNT` 環境変数も追加
- 過適合監視 / 期間分割評価: 2 → 2 (±0) 維持: walk-forward / CV 不在、**かつ P0-1/P0-2 後の backtest 未実行が継続**
