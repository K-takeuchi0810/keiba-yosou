# Group D 停止 + Phase 0.5-5 族の総括 レビュー (3 名) — 2026-10-06

- 対象: worktree `group-d`、凍結 SHA `035d37e` (`git diff b7bbbc4..035d37e`: 3b3c209 D の停止 / e6423d4 族の総括 / 035d37e 凍結前レビューのスコアカード)
- 2025 と確認窓 (2026-09-14 以降) は 3 名とも読んでいない。structural_check は validation・code-quality が本番 DB (mode=ro) で独立に再実行し、ビット一致

| 専門家 | 点 (前回) | 判定 | must-fix |
|---|---|---|---|
| validation-process-auditor | 4.3 (4.5) | CONDITIONAL → 反映済 | (1) PREREG §8-3 D 行・§8-4d 末尾に日付つき追補が無い (D の終端状態・新しい状態名) (2) D の「0.6 頭 / 100 レース」に出典の成果物が無い |
| profitability-judge | 4.1 (4.2) | PASS | 族の総括の件数比較の数え方が混在 (A 2.9 は S ≥ 2 の目安、C′/D は ratio_buys_at) |
| code-quality-reviewer | 3.8 (4.0) | PASS | structural_check.json に来歴が無い (族の停止の唯一の数値成果物) |

**平均 4.07**。前回比 −0.3 以上の低下なし (最大 −0.2)。前回の code-quality の must-fix 2 件 (探索スクリプトの import が来歴から漏れる / テスト冒頭の過大な主張) は解消を一次ソースで確認。

## 反映 (このスコアカードと同じ一連のコミット)

- `structural_check.py`: `pr.provenance` を記録、2024 のレース数を `e2/e2_result.json` から読む (手書きの 3019 を廃止)、注記の「約 8%」を実測 (9.5%) から生成、
  件数の見込み (年別 0.73 / 0.73 / 0.56、pooled 0.67 頭 per 100 レース、1,500 点に約 21〜27 万レース) を追加。コミットしてから再実行し、構造の量は追加の前とビット一致、`git_dirty = false`
- `tests/test_group_d_run.py`: `group_d_run.py` が import する repo 内モジュール ⊆ `DEPENDENCIES` のテスト (依存を 1 つ外すと落ちることを確認)。33 passed
- `scripts/group_d_run.py`: docstring に「主検定は実行しない」決定を記載 (コードの sentinel は操作つまみになるので入れない)
- `docs/PHASE05_5_PREREG.md`: §8-3 D 行と §8-4d 末尾に 2026-10-06 追補 (状態 `BLOCKED_BY_IDENTIFIABILITY` / `PRIMARY_NOT_RUN` の新設、2025 は 2 回のまま、他の条項と α は不変)
- `docs/PHASE05_5_GROUP_D_RESULT.md`: 停止の量は E1/E2 の前にも計算でき §8-4d の代数から予見できたのに見落とした、と明記 / 件数の見込みと D′ の門 (1,500 点に現実的な期間で届かない設計は登録しない)
- `docs/PHASE05_5_FAMILY_SUMMARY.md`: PASS 0 の適用の意味 (5 群否定ではない) / SEALED_FROM と確認窓の書き分け / 140% 級 (β ≈ 0.280) は A・C′ の 99% 区間の外 /
  件数の数え方の脚注 / 教訓 6 を「2 例で一致」に弱める / A″ を 2025 で通すときの条件 (CONSUMED_WINDOWS に記録・変種の選択に使わない) / D′ の到達可能性

## 見送り (理由つき)

- validation should-fix 8 (レビュー時点で agent 別ファイルを保存): 今後の運用とする。本スコアカードは要点の転記
- code-quality 参考所見 (来歴 helper が 3 系統): A・C′ は錠で凍結済みなので触らない。次世代は `scripts/prereg_runner.py` だけを使う
