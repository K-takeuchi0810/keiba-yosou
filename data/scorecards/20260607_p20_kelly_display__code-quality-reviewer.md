# コード品質 / 保守性レビュアー 採点

## 総合: 3.9 / 5  (前回 baseline 4.3 / 直近 P19 3.4 → 本タスク基準 4.3 から **-0.4**)

P20 の Kelly 表示是正は **DRY の正攻法**: full Kelly→quarter+cap の縮小ロジックを
`recommended_fraction` に切り出し、`kelly_size` がそれを内部利用する形で、
magic `0.25` の **計算ロジック重複は解消** した。しかし「単一出典化」は
**未完**: config に `BET_KELLY_MODE/MAX_PCT` を新設しながら、`risk.py` の
`recommended_fraction(mode="quarter", max_pct=0.05)` / `kelly_size(..., max_pct=0.05)`
のデフォルト引数が config を一切参照せず **値を独立に再記述** している (二重定義)。
さらに本タスクと無関係な iCloud sync-diagnostics コード (~90 行) が同じ working
tree に混入し generator.py を膨張させている。

## 項目別

- **DRY / 重複コード: 4/5** — `_KELLY_MODE_MULTIPLIER` 定数化 + `recommended_fraction`
  切り出しで、`kelly_size` が同 helper を内部呼出し (risk.py:103)、縮小ロジック
  重複は解消。generator.py の `recommended_kelly` も `**p` spread で buy_candidate に
  伝播し再計算なし。**減点**: `risk.py:65` `max_pct=0.05` と `risk.py:64/90` `mode=
  "quarter"` が config.BET_KELLY_MAX_PCT/MODE と **値として二重**。config を変えても
  risk.py 既定は追随しない (config はコメントで「既定と一致させる単一出典」と謳うが、
  実装上は単なる平行記述で、不一致を防ぐ仕組みが無い)。

- **dead code / 未使用シンボル: 4/5** — P20 で導入したシンボル
  (`recommended_fraction` / 3 config 定数 / `portfolio_info` 各キー) は全て消費先
  あり (template 参照確認済)。`per_bet_cap_pct` はバッジ判定 (★上限張り) と注記の
  両方で使用、`scale` は over-cap 時のみ表示。**減点**: 同 working tree に混入した
  `_file_sha256` / `_prune_old_files` / `SYNC_DIAGNOSTIC_RETENTION` は P20 と無関係な
  別タスク (sync-diagnostics)。死んではいないが **P20 の差分としては純度を下げる**。

- **マジックナンバー / 設定外出し: 3/5** — config 集約の **方向は正しい** が、
  目的の「単一出典化」が達成されていない。`recommended_fraction` 内
  `_KELLY_MODE_MULTIPLIER.get(mode, 0.25)` の fallback `0.25` が裸 (mode 不正時に
  silent で quarter 化、根拠コメント無し)。risk.py 既定 `0.05`/`"quarter"` が config
  と独立。`SYNC_DIAGNOSTIC_RETENTION = 20` は config 外 (別タスク分だが指摘)。
  template 側 `* 100` のパーセント換算が generator (`*100`) と template (`*100`) に
  分散気味だが許容。

- **テスト容易性 / 副作用分離: 4/5** — `recommended_fraction(f_star, mode, max_pct)`
  は **完全な純粋関数** で I/O ゼロ、境界 (f<=0→0.0 / cap 到達→max_pct) が pytest で
  即固定可能。`kelly_size` も bankroll を引数で受け純粋。`portfolio_info` の dict 構築
  (generator.py:352-366) は `recommended_total` 合計 / scale 算出が DB に依存せず
  `buy_candidates` list だけで決まる **抽出可能なロジック**。**減点**: それが
  `build_view_model` (DB open 必須の巨大関数) に **インライン埋め込み** で、
  `_compute_portfolio_info(buy_candidates, cap)` の純粋 helper に切れば単体テスト
  可能なのに未分離。tests/ 依然不在。

- **エラー処理 / ログ / 観測可能性: 4/5** — P20 本体は例外を増やさず健全。
  `recommended_fraction` の `mode` 不正は raise でなく default 吸収 (UX 上は妥当だが
  typo を silent 化する両刃)。混入した sync-diagnostics 側の `except OSError: pass`
  (`_prune_old_files` unlink) は **意図的な握り潰し** で許容範囲だが、prune 失敗が
  完全に不可視 (logger.debug 1 行が欲しい)。print デバッグ残存なし。

## 主な改善提案 (優先 1 件、最大 3 件)

1. **risk.py 既定を config 由来にして二重定義を解消** — `risk.py` 冒頭で
   `from config import BET_KELLY_MODE, BET_KELLY_MAX_PCT` し、
   `def recommended_fraction(f_star, mode=BET_KELLY_MODE, max_pct=BET_KELLY_MAX_PCT)`
   / `kelly_size(..., max_pct=BET_KELLY_MAX_PCT)` に変更。`_KELLY_MODE_MULTIPLIER.get
   (mode, 0.25)` の `0.25` も `_KELLY_MODE_MULTIPLIER["quarter"]` 参照に。これで
   config が真の単一出典になり項目3: 3→4.5、項目1: 4→4.5、総合 3.9→**4.2**。
   (循環 import 懸念: config は risk を import しないので一方向で安全)。

2. **portfolio_info を純粋 helper に抽出 + tests/test_risk.py 新設** —
   `_compute_portfolio_info(buy_candidates, cap_pct) -> dict` を generator.py に切り出し、
   `recommended_fraction` の境界 (f<=0 / cap 到達 / mode 不正) と portfolio scale
   (合計<=cap で scale=1.0 / 超過で按分) を pytest 化。DB 不要で即書ける。
   項目4: 4→4.5、総合 +0.1。

3. **sync-diagnostics コードを P20 から分離** — `_file_sha256` /`_prune_old_files` /
   `publish_to_icloud` の snapshot/status 追記 (~90 行) は別 topic
   (icloud_publish_sync_diagnostics)。P20 commit に混ぜず別 commit に分け、
   generator.py の責務肥大を避ける。レビュー純度 +、項目2: 4→4.5。

## 前回からの差分

過去 code-quality scorecard は (a) 20260512 P05 baseline 4.3、(b) 直近 commit a654368
の P19 B1-S0 で 3.4 (診断 script の DRY/magic 集中後退)。本 P20 は別ファイル群
(risk/config/generator/template) のため直接比較は近似。**P05 基準 4.3 から -0.4**:

- 項目1 (DRY): 4.3 → 4.0 (-0.3) — 縮小ロジック重複は解消も config↔risk 既定が二重定義
- 項目2 (dead code): ~4.0 → 4.0 (±0) — P20 シンボル全消費、ただし無関係コード混入
- 項目3 (magic): 4.7 → 3.0 (**-1.7**) — config 新設の意図に反し risk.py 既定が独立
  値、`0.25` 裸 fallback、単一出典化が **看板倒れ**
- 項目4 (test): 2.5 → 4.0 (**+1.5**) — `recommended_fraction` の純粋関数化は明確な
  前進 (境界テスト可能)。tests/ 不在は継続だが I/O 分離が改善
- 項目5 (logging): 4.5 → 4.0 (-0.5) — 本体健全、混入 prune の silent except 微減

総合 4.3 → **3.9**。最大の壁は **提案#1 (config↔risk.py 二重定義)**。ここを
抜けば「config を緩めれば表示も賭金も追随」が成立し、本タスクが掲げた単一出典化が
初めて実体を持つ。
