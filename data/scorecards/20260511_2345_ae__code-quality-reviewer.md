# コード品質 / 保守性レビュアー 採点

## 総合: 4.2 / 5  (前回 4.1 → **+0.1**)

改修の本丸は **買い目フィルタ語彙の三層統一**: `config.BUY_FILTER_DEFAULT` を唯一の出典として `gui._is_buy_candidate` / `backtest._matches_buy_filter` / `web/generator.bet_candidate` の 3 経路が同じキー (`min_popularity` / `max_popularity` / `exclude_confidence`) を読むようになった。さらに `--no-filter-from-config` への反転で「既定 ON」が CLI 側にも明示。一方で `scripts/filter_sweep.py` に whitelist 定数を再持込してしまった点が小さい DRY 後退。

## 項目別

- **DRY / 重複コード: 4/5** (前回 4.5 → **-0.5**) — 三層 (gui/backtest/web) で同一フィルタ語彙を共有し、`is_whitelisted_race` を 3 箇所から呼ぶ構造は良。ただし `scripts/filter_sweep.py:23-24` で `WHITELIST_GRADES={"A","B","C","F"}` / `WHITELIST_TRACKS={"07","09"}` を **ハードコピー** している (`config.BUY_FILTER_DEFAULT["whitelist_grades"]/["whitelist_tracks"]` の再定義)。`Pick.is_whitelisted` も `is_whitelisted_race` を再実装。さらに `exclude_conf` のデフォルト `["暫定","混戦","接戦"]` が `gui/app.py:243` / `backtest.py:205` の 2 箇所にフォールバック値として複製されている (config 経由で取得しているので機能はするが、None 時のフォールバックが分散)。

- **dead code / 未使用シンボル: 4/5** (前回 4 → ±0) — 影響なし。`filter_sweep.py:155 _adjust_spec_for_non_whitelist` は実装が `return spec` (no-op) で未使用関数化しており削除候補。`Pick.fuku_payout` も sweep 内では `--bet tan` 系コードパスで参照されるのみで `--bet fuku` 自体は実運用なし。

- **マジックナンバー / 設定外出し: 4.8/5** (前回 4.9 → **-0.1**) — `min_popularity` / `max_popularity` / `exclude_confidence` が config 化された点は **+** で、`gui/app.py:239-244` / `backtest.py:205-226` / `web/generator.py:152-168` が同じ出典を読む。None 許容で「制約なし」を表現する規約も明文化。**-** は前述の `filter_sweep.py` 定数ハードコピーと、`scripts/filter_sweep.py:188-190 (design=2025/06-12, eval=2026/01-04)` の期間定数が CLI 引数化されていない点 (`--walk-forward` だけ ON にすると常に同じ 2 期間)。0.8 / 0.80 の robust 閾値 (`:208, 214`) も直書き。

- **テスト容易性 / 副作用分離: 2.5/5** (前回 2.5 → ±0) — `tests/` 未だ不在。とは言え今回の `_matches_buy_filter` は `spec` を引数で受け取るピュア寄り関数で、conn 不要のため単体テスト容易性は高い (テスト書きさえすれば fixture 不要)。`is_whitelisted_race` も同様。**「テスト可能な形にはなっているがテストが無い」** の状態が継続。

- **エラー処理 / ログ / 観測可能性: 4.5/5** (前回 4.5 → ±0) — 影響なし。`backtest._matches_buy_filter` 内の `from config import is_whitelisted_race` 関数スコープ import (`:198`) は循環回避コメント付きで意図明示。silent failure なし。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **`scripts/filter_sweep.py` の whitelist 定数を `config` 参照に置換** — `:23-24` の `WHITELIST_GRADES`/`WHITELIST_TRACKS` 定義削除、`Pick.is_whitelisted` を `is_whitelisted_race({"grade_code":..., "track_code":...})` 呼び出しに差し替え (BET_WHITELIST 環境変数で常に True 化されない用に `_is_whitelisted_raw` を新設するか、`whitelist_grades/whitelist_tracks` を直接参照)。項目1: 4 → 4.5、総合 4.2 → 4.3。
2. **`tests/test_buy_filter.py` 新設** — `_matches_buy_filter` (conn 不要) と `is_whitelisted_race` の入出力を pytest で網羅。3 経路間の語彙ズレを CI で検出可能に。項目4: 2.5 → 3.5、総合 4.2 → 4.4。
3. **`--walk-forward` の期間を引数化** — `filter_sweep.py:187-190` を `--design-from/--design-to/--eval-from/--eval-to` に分解 (デフォルトは現状値)。robust 閾値 0.80 も `--robust-threshold` で外出し。項目3: 4.8 → 4.9。

## 前回からの差分

- 項目1 (DRY): 4.5 → 4.0 (**-0.5**) — whitelist 定数の filter_sweep ハードコピーで小幅後退
- 項目2 (dead code): 4 → 4 (±0) — 新規 no-op `_adjust_spec_for_non_whitelist` 1 件追加だが影響軽微
- 項目3 (magic number): 4.9 → 4.8 (**-0.1**) — config 化は前進したが sweep 側の期間/閾値直書きで微減
- 項目4 (test): 2.5 → 2.5 (±0)
- 項目5 (logging): 4.5 → 4.5 (±0)

総合: 4.1 → **4.2** (+0.1) — 三層の語彙統一は構造的勝利 (買い目フィルタの「設定 = 挙動」が成立)、ただし `filter_sweep.py` が出典側に追随できていない。次レバーは #1 (filter_sweep 統合) > #2 (tests/ 新設)。
