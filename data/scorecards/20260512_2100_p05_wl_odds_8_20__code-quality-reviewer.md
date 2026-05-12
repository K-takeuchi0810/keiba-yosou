# コード品質 / 保守性レビュアー 採点

## 総合: 4.3 / 5  (前回 4.2 → **+0.1**)

今回の改修は **「config 値域拡張に経路側が追随できる」** という構造的勝利が中心。
`BUY_FILTER_DEFAULT` で `min_popularity` / `max_popularity` / `exclude_confidence` を
`None` / `[]` に振っても、`gui/app.py:239-246` と `web/generator.py:153-157` が
None ガードで int 化を回避する形に揃った (旧コードは `int(None)` で TypeError)。
さらに前回 #1 で指摘した **`filter_sweep.py` の whitelist 定数ハードコピー** が
`BUY_FILTER_DEFAULT` 参照に置換され (`:23-24`)、DRY 後退が解消。一方で
`_score_one` 508 行 (rules.py:86-594) と `tests/` 不在は据え置き、`filter_sweep.py`
内 design/eval 期間と robust 閾値の直書きも継続のため大幅加点には至らず。

## 項目別

- **DRY / 重複コード: 4.3/5** (前回 4.0 → **+0.3**) — `filter_sweep.py:23-24` が
  `frozenset(BUY_FILTER_DEFAULT["whitelist_grades"])` 参照に変わり、前回 #1 の
  ハードコピー解消。一方で gui/app.py:233-246 と web/generator.py:152-157 で
  `_raw_min_pop = filters.get("min_popularity", BUY_FILTER_DEFAULT.get(...))` → 
  `int(...) if ... is not None else None` という **同一パターンが二箇所に複製**
  されつつあり、`config._coerce_pop(value)` のようなヘルパー化が次の DRY 課題。
  `Pick.is_whitelisted` (filter_sweep.py:39-44) も依然 `is_whitelisted_race` を
  再実装 (環境変数 `BET_WHITELIST` を意図的に無視するため別物だが、コメントが薄い)。

- **dead code / 未使用シンボル: 3.7/5** (前回 4.0 → **-0.3**) — 新規 9 種の
  hybrid フィルタを `FILTERS` に追加 (`:144-157`) したのは sweep 用途として
  健全だが、その中で `wl_odds_8_20_ex_unsure` 等は本文コメントで「17/7 戦,
  65%/0% に崩壊」と判明済の組合せが探索用として残置 (これは sweep の性質上 OK)。
  問題は **`_adjust_spec_for_non_whitelist` (filter_sweep.py:169-171) が依然
  no-op `return spec` のまま放置**。前回も指摘済み。`predictor/features.py` 側
  `estimated_leg_samples` / `same_track_type_runs` は rules.py で未参照 (前回未検出)。

- **マジックナンバー / 設定外出し: 4.7/5** (前回 4.8 → **-0.1**) — gui/web の
  None ガード追加で「config を緩めれば全経路が緩む」が成立した点は **+** で、
  config 中心の設計思想が一段強化。**-** は前回からの繰り越し: `filter_sweep.py`
  の `("design","20250601","20251231")` / `("eval","20260101","20260430")`
  (`:202-203`) と robust 閾値 `0.80` (`:222, 228`) が依然直書き。新規追加の 9 種
  hybrid 閾値 (odds 6/7/8/9/22/25, pop 4-10/5-9) も sweep 用なので OK だが、
  本採用フィルタ `wl_odds_8_20` 自体の odds 帯 8.0/20.0 (`config.py:57-58`) は
  config 内で完結しコメント根拠も明確、合格。

- **テスト容易性 / 副作用分離: 2.5/5** (前回 2.5 → ±0) — `tests/` 依然不在。
  `_is_buy_candidate` (gui/app.py:213-269) は `horse` / `pred` / `filters` /
  `race` を引数で受け取るピュア関数なので **DB 接続なしで pytest 即書ける**
  状態だが、テストが存在しない。`_score_one` (rules.py:86-594, **508 行**) の
  巨大化も未着手 — 分割すれば feature ベース単体テストが可能になるが、現状は
  関数全体を覆うインテグレーションテスト経由でしか挙動を固定できない。
  ユーザー指摘通り **次の最大レバー**。

- **エラー処理 / ログ / 観測可能性: 4.5/5** (前回 4.5 → ±0) — 影響なし。
  None ガードが TypeError を未然に防ぐ形になり observability は微増 (旧コードは
  `int(None)` で raise → silent でなく顕在化していたが UX は悪化していた)。
  `web/generator.py:290,292` の `print(f"wrote ...")` / `print(f"published ...")`
  は CLI 出力として妥当、`gui/app.py:1791-1806` の `print("[gui.app] ...")` も
  起動ログとして許容範囲 (logging 化候補ではある)。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **`_score_one` 分割 (rules.py:86-594, 508 行)** — feature 群ごとに
   `_score_record(horse, feat)` / `_score_form(horse, feat)` / `_score_pace(...)` 
   等へ責務分割し、各サブ関数が `(delta_score, reasons)` を返す pure 形に。
   testability が一段上がり (feat dict 直接渡しで unit test 可)、項目4: 2.5 → 3.5、
   項目1: 4.3 → 4.5、総合 4.3 → **4.5**。最大インパクト。

2. **`tests/test_buy_filter.py` 新設** — `_is_buy_candidate` / `_matches_buy_filter` /
   `is_whitelisted_race` の None 許容パスを網羅 (`min_popularity=None` で全 popularity
   通過、`exclude_confidence=[]` で全 confidence 通過 等)。今回の None ガード回帰を
   CI で防ぐ。項目4: 2.5 → 3.0、総合 4.3 → 4.4。

3. **`filter_sweep.py` の dead `_adjust_spec_for_non_whitelist` 削除 +
   期間/閾値の CLI 化** — `:169-171` 削除、`--design-from/--design-to/--eval-from/`
   `--eval-to/--robust-threshold` を argparse に追加 (default は現値)。項目2: 3.7 → 4.2、
   項目3: 4.7 → 4.9。

## 前回からの差分

- 項目1 (DRY): 4.0 → 4.3 (**+0.3**) — filter_sweep.py 二重定義解消で前回 #1 完了
- 項目2 (dead code): 4.0 → 3.7 (**-0.3**) — `_adjust_spec_for_non_whitelist` 据え置き
  +features.py の 2 features が rules で未参照と判明 (前回未検出分の顕在化)
- 項目3 (magic number): 4.8 → 4.7 (**-0.1**) — sweep 内期間/閾値の直書きが
  繰り越し (新規改修では None ガードで +0.05 だが、未解消分が累積したので微減)
- 項目4 (test): 2.5 → 2.5 (±0) — `_score_one` 508 行未着手 + tests/ 不在継続
- 項目5 (logging): 4.5 → 4.5 (±0) — 影響なし

総合: 4.2 → **4.3** (+0.1) — 前回 #1 (filter_sweep dedup) が解消され DRY +0.3 の
構造的勝利。次の壁は **#1 (_score_one 分割)** で、ここを抜くと testability 3.5/5
が見えてくる (テスト書く前提として関数分割が必須)。`tests/` 新設は依然第二の
レバーだが、`_score_one` 分割が先行する方が ROI 高。
