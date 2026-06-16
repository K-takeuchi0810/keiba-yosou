# 採点 2026-06-16 21:47

**改修内容**: 買い候補 3〜5頭から、検証用の推奨買い目（単勝・複勝・馬連軸流し・三連複軸流し）を生成し、確定結果と最終払戻があるレースでは的中/不的中と払戻を HTML/GUI に表示。
**対象ファイル**: `predictor/tickets.py`, `predictor/candidates.py`, `web/generator.py`, `web/templates/index.html.j2`, `gui/app.py`, `predictor/portfolio.py`, `tests/test_recommended_tickets.py`, `tests/test_template_render.py`, `tests/test_portfolio_budget.py`

## 総合スコア

| 専門家 | 今回 | 状態 |
|---|---:|---|
| GUI / UX 監査人 | 3.7 | 完了 |
| モバイル HTML レビュアー | 4.2 | 完了 |
| 予想ロジック分析 | 3.6 | 完了 |
| 収益性 / 投資判断 | 2.0 | 完了 |
| データパイプライン | 4.2 | 完了 |
| コード品質 | 4.0 | 完了 |
| 検証プロセス | N/A | 起動後 8 分以上応答なしのため shutdown |

6 役平均: **3.62 / 5**

## 主な所見

### GUI / UX

- 日予算、買付額、単勝買い目、候補 3〜5頭表示はユーザー判断に効く改善。
- 検証モード（オッズ鮮度無視）は通常運用との差をさらに強調すべき。
- 主要ボタンの `title` と操作ヘルプは不足。

### モバイル HTML

- viewport、sticky header、横スクロール、外部リソース非依存は良好。
- day-nav link のタップ領域と一部小バッジのコントラストに改善余地。

### 予想ロジック

- 候補 3〜5頭表示は core scoring を変えていない。
- P25 `RULES_VERSION` に対して calibrator が p21 のまま。EV/Kelly は参考値扱いが必要。
- 市場人気ボーナスと market probability blend / odds discount の二重取り込みリスクがある。

### 収益性

- 実弾採用は不可。直近 backtest は控除率 80% を超えていない。
- 日予算配分と円表示は資金管理として前進だが、勝てる買い目である証明ではない。

### データパイプライン

- fresh odds と RACE 差分 ingest の流れは実用的。
- 非リアルタイム `JVStatus()` の無制限待ち、`no_data/timeout` の監視弱さは残る。

### コード品質

- `predictor.candidates` / `predictor.tickets` への分離で責務は整理された。
- 複数日の日予算表示は `total_allocated_yen` と `budget_days` を併記し、誤解を軽減。
- 100円単位は `unit_yen` を返すようにしたが、GUI input の `step=100` は UI 契約として残る。

## 実施した検証

- `.venv64\Scripts\python.exe -m pytest tests\test_recommended_tickets.py tests\test_portfolio_budget.py tests\test_template_render.py tests\test_gui_js_contract.py tests\test_backtest_market_snapshot.py tests\test_market_popularity_scoring.py tests\test_fetch_fresh_odds.py -q`
  - **30 passed**
- `.venv64\Scripts\python.exe -m py_compile predictor\tickets.py predictor\candidates.py web\generator.py gui\app.py predictor\portfolio.py tests\test_recommended_tickets.py tests\test_template_render.py tests\test_gui_js_contract.py`
  - PASS
- `.venv32` で `gui.app.CONTROL_HTML` から JS 抽出後、`node --check`
  - PASS
- `.venv32` で RACE 差分取得 `fromtime=20260613000000`, `dataspecs=["RACE"]`
  - fetch: 24 files / 2221 records
  - ingest: 24 files processed, RA 72, SE 983, HR 72, O1 72
- `.venv64\Scripts\python.exe -m web.generator --from 20260614 --to 20260614 --no-publish --json --daily-budget-yen 10000 --ignore-odds-freshness`
  - `web/dist/index.html` 生成成功
  - 2026/06/14 の `payouts` は 36R まで取り込み済み
  - HTML に 5 買い候補、各レースに単勝・複勝・馬連・三連複の推奨買い目、的中/不的中、払戻、回収率を確認

## 残リスク

1. **calibrator mismatch**: `calibrator=p21-2026-06-13`, `current=p25-market-pop-score-2026-06-14` の警告が残る。
2. **収益性未証明**: 今回の推奨買い目表示は検証支援であり、年間 180% 達成の証明ではない。
3. **検証モード誤運用**: `--ignore-odds-freshness` は公開経路にも渡せるため、実運用では使い分けをさらに強く UI 表示すべき。
