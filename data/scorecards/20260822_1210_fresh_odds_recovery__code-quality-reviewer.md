# コード品質レビュアー — 20260822_1210 fresh_odds_recovery

**判定**: HOLD (解除条件を本セッションで充足)
**総合**: 3.8 / 5 (前回 4.2、-0.4 ⚠ 後退)

| 項目 | 今回 | 前回 |
|---|---|---|
| DRY / 単一出典 | 3 | 4 |
| dead code / 未使用シンボル | 4 | — |
| マジックナンバー / 設定外出し | 4 | — |
| テスト容易性 / 変更失敗モード | 4 | 4 |
| エラー処理 / 観測可能性 | 4 | — |

**変更失敗モード分析 (核心)**: `buy_filter_from_generator()` の明示キーリストは
「BUY_FILTER_DEFAULT にキーを足すと backtest 側の追加を忘れて静かに乖離する」構造で、
本 diff がその実例。`suspended` が backtest に届かず、config のコメント (「計測は env で」) と
実挙動が矛盾したまま、どのテストにも検出されずに成立していた。

**是正内容**:
- 契約を「backtest は計測器なので suspended を伝播させない」と明文化し、契約テスト 2 本で固定
  (逆方向の事故 = 全キーコピーで backtest が無言の 0 bets 化、も検出できる)
- `BET_FILTER_IGNORE_SUSPENSION` を env_overrides 追跡集合に登録
- `repair_odds_stamps.py` に単体テスト 4 本 (発走時刻ちょうどの境界 / restore / clear / dry-run)
- `snap["source"]` を `odds_dataspec` に書くドメイン混在を修正 (source は "morning" 等の運用ラベル)
- db.py の重複デフォルト行を削除 (historical 分岐が return するため到達時は常に設定済み)
- サスペンド開始日を `config.BUY_FILTER_SUSPENDED_SINCE` に一元化 (Python↔Jinja↔GUI の 3 重記述を解消)

**残課題**: post-start の ISO 組立が db.py (Python) / repair_odds_stamps.py (SQL) /
backtest の `_snapshot_age_min` の 3 層平行記述 (言語境界またぎの再発パターン)。
env 真偽値パースがアドホック ("TRUE"/"yes" 非対応)。
