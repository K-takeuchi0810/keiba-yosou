# §9 の改訂 (履歴としてだけの読みの例外) レビュー (2 名) — 2026-10-06

- 対象: `c3aaed3..09a8c5c` (docs/LOCKBOX_GOVERNANCE.md §9・§7、`scripts/research_window.check_history_for_fresh_targets`、テスト、変異 45/45)
- 外部の指示者の決定 (2026-10-06) の実装: reserved・consumed は fresh の対象の履歴としてだけ読める。対象・学習・検証・検出力・診断・金額には永久に使わない

| 専門家 | 初回 | 再判定 (`5f7408b`) | 主な must-fix |
|---|---|---|---|
| validation-process-auditor | 4.0 CONDITIONAL | **4.3 PASS** | 文書の過大な主張: 監査ログと対象ごとの history<target はコードで強制していない → 開封の実装時の要件として書き分け |
| code-quality-reviewer | 3.6 CONDITIONAL | **4.3 PASS** | 禁止の断片がスキーマの実列 (payouts.tan_pop1 等の人気・vote_counts.votes 等の票数) を通す → 「表.列」+ 市場の表の禁止 + schema.sql 全列の照合テスト |

反映後の平均 **4.3**。変異は run4 で H3 (`_pop` を落とす) が生存 → 市場の表の外の `_pop` 列のテストを足して run5 **51/51 KILLED**。全テスト 1552 passed (worktree の CRLF 由来の既知 1 本を除外)。

## 持ち越し (非ブロック、開封の手順・最初の事前登録の実装時)
- 別名 (alias) で渡すと表名の判定を素通りしうる (`w.refund_flag`) → 事前登録で「表.列」を実テーブル名の固定集合の完全一致で縛る、または `refund` を断片に
- `type(...) is not int` は numpy の整数も拒否する (安全側)。実装時に int へ正規化するかメッセージで明示
- `horse_races.odds_fetched_at` / `odds_dataspec` も禁止される (保守的側、必要なら事前登録で扱う)
