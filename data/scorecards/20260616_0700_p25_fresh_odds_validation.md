# 採点 2026-06-16 07:00 - P25 fresh odds / validation observability

**改修内容**: P25 市場人気補正を採用判断へ進める前の検証基盤を強化。`market_snapshot`、fresh odds 自動取得、realtime raw の filenames/0 byte 処理、払戻欠損カウンタ、`git_dirty` 証跡、`buy_only_by_confidence`、追加テストを実装。

**対象ファイル**: `scripts/backtest.py`, `scripts/fetch_fresh_odds.py`, `scripts/fetch_fresh_odds.bat`, `jvlink_client/client.py`, `predictor/rules.py`, `tests/test_backtest_market_snapshot.py`, `tests/test_fetch_fresh_odds.py`, `tests/test_market_popularity_scoring.py`, `docs/P25_MARKET_POP_VALIDATION_PLAN.md`, `docs/OPERATION.md`

## 総合スコア

| 専門家 | 今回 | 前回目安 | 差分 |
|---|--:|--:|--:|
| GUI / UX | 3.8 | 3.8 | +0.0 |
| モバイル HTML | 4.2 | 4.4 | -0.2 |
| 予想ロジック | 3.7 | 3.6 | +0.1 |
| 収益性 / 投資判断 | 2.2 | 2.5 | -0.3 |
| データパイプライン | 4.1 | 3.8 | +0.3 |
| コード品質 | 4.1 | 4.1 | +0.0 |
| 検証プロセス | 4.0 | 3.6 | +0.4 |
| **平均** | **3.73** | **3.63** | **+0.10** |

## 警告

- **収益性 -0.3**: P25 はまだ投資戦略ではない。既存 A/B は buy_only 差なし、fresh coverage は 193/46,287 頭、bonus 候補 33 頭 / 11R のみ。控除率超えの証拠は無い。
- **モバイル -0.2**: 今回 web 変更は無いが、`.day-nav a` のタップ領域と一部 badge/waku コントラストは次回改善対象。

## レビュー後に反映した修正

1. `scripts/fetch_fresh_odds.py`
   - `records_total` 判定に修正。
   - `fetch_realtime()` の `filenames` を `ingest_all(only_files=...)` に接続。
   - レース単位の例外継続、取得直前の発走時刻再判定、lock heartbeat を追加。
   - 全レースが例外失敗した場合は exit 1。
   - `LOCK_PATH` を repo 相対に変更。

2. `jvlink_client/client.py`
   - realtime raw の 0 byte ファイルを削除。
   - 非空 raw の `filenames` を返却。

3. `scripts/backtest.py`
   - `market_snapshot` に `PRED_W_popularity_min_field/max_snapshot_age_min` を反映。
   - `meta.git_dirty` / `meta.git_status_short` を保存。
   - 全 `PRED_W_*` env override を `meta.env_overrides` に自動記録。
   - `races_missing_payouts`, `bets_missing_payouts`, `buy_only_bets_missing_payouts` を追加。
   - `buy_only_by_confidence` と `adoption_rate` を追加。

4. `scripts/fetch_fresh_odds.bat`
   - `%~dp0..` 基準へ変更。
   - `data\logs` を初回作成。

5. tests
   - market snapshot env override、payout missing、fresh odds 部分失敗/全失敗、任意 `PRED_W_*` meta 記録を追加。

## 検証

- `.venv64\Scripts\python.exe -m pytest tests\test_backtest_market_snapshot.py tests\test_market_popularity_scoring.py tests\test_fetch_fresh_odds.py -q`  
  **13 passed**
- `.venv32` / `.venv64` py_compile: **OK**
- `.venv32\Scripts\python.exe -m scripts.fetch_fresh_odds --dry-run`: **OK**
- `git diff --check`: exit 0、CRLF warning のみ
- 短期 saved smoke:
  - `data/backtest/20260616_070633_tan_p25-observability-smoke-v3-filtered.json`
  - `meta.git_dirty=True`
  - `meta.git_status_short` あり
  - `races_missing_payouts=0`
  - `buy_only_by_confidence` あり
  - `market_snapshot` あり

## 残る優先課題

1. fresh odds が数週間蓄積してから `pop_0_0_0`, `4_2_1`, `7_4_2`, `10_6_3` の paired A/B を再実行する。
2. P25 用 calibrator refit と `PRED_DISABLE_DISCOUNT=1` paired run を保存する。
3. GUI / HTML に fresh/stale/unknown/post_start と「30分以内 snapshot だけ有効」の説明を出す。
4. `fetch_fresh_odds` の no_data/timeout 連発をログ監視する。
5. `JVLinkClient.fetch_realtime` の fake COM テストを追加し、`rc=-1`, `rc=-3`, file split, retry を直接固定する。

## 判定

GATE: **検証基盤として PASS / 実弾採用は不可**。

P25 は「市場人気補正が効くかを測れる形」に近づいたが、現時点の数値は収益戦略の根拠ではない。次の正しい順序は、Task Scheduler で fresh odds を蓄積し、サンプル数が合格条件に届いてから paired A/B と calibrator refit を行うこと。
