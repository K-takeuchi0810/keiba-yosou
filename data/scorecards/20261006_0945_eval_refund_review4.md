# 2026-10-06 09:45 — §8-6 共有の eval の修正 (4 名レビュー、マージの前)

- 対象: worktree `eval-refund`、レビュー SHA e30d06c (base main 62e9698)。**subagent CWD 限定運用での評価** (全員 `git -C <worktree>`)
- 指示: 外部の指示者 (2026-10-06) が validation / profitability / data-pipeline / code-quality の 4 視点を指定 (確率モデル自体は変えないので prediction-logic は不要)
- ai_builder_impact: none (db.py・jvlink_client・取り込み・schema・pit_t10・eval_stats は差分なし、data-pipeline が確認)

| 担当 | 判定 | 総合 | must-fix |
|---|---|---|---|
| validation-process-auditor | CONDITIONAL | 3.9 | §8-6b の表の再現物と改訂のきっかけの明記 / money_pass の testable 経路のテスト (自前の追加変異 5 本中 5 本が生存、うち S1 は金額の判定の式) / C′ の凍結の前に市場の列の単一の出典をテストで強制 |
| profitability-judge | CONDITIONAL | 3.8 | MONEY_UNDERPOWERED (100〜1,499 点) がコードに無く、100 点で「金額 合格」を表示しえた |
| data-pipeline-engineer | PASS | 4.5 | なし (本番 DB を mode=ro で突合: 取消の行は horse_races に残る / odds_snapshots にだけ居る馬番 0 / smoke の件数を完全に再現) |
| code-quality-reviewer | PASS | 4.0 | なし |

平均 4.05。

## 反映 (dcbeba0)

- must-fix 4 件をすべて反映: `predictor.race_market.money_class` (4 区分、合格は 1,500 点以上かつ区間の下限 > 100% だけ) / 130 点の人工標本で
  MONEY_UNDERPOWERED の経路を通すテスト / `market_term_table.py` と `.json` (学習期だけ、事前登録の表と一致) と §8-6b のきっかけの段落 /
  §8-6b・§8-9 に C′ の凍結の前提条件
- should-fix で反映: is_refunded の写しを削除 (db を再公開) / p_new は market_term を通す / winner_without_payout・特払いを 0 でも出す /
  refund_accounting を成果物に / select_race の空の行を拒否 / 対照 2 の同値を数値で / レースキー・ゼロ埋め・対照 1 のモデル非依存・1.75 の集合のテスト /
  4A の経路の見出しに 95% / §8-5 (626 と 630) / Group A の結果に錠の事前登録の版 (a34ae91)
- 変異 run2 (dcbeba0): 39 / 39 KILLED (validation の生存 5 本 S1・S2・S3・S7・S8 を E29〜E36 で取り込み)

## 持ち越し (should-fix、C′ の中で扱う)

- collect の戻り値の race_exclusions を model_info から独立させる (4 要素か NamedTuple) — code-quality
- select_race / _abnormal_codes / count_special_payouts / _final_market_odds を scripts/eval_common.py へ (兄弟 import の解消) — code-quality
- build_choice_set が最初に失敗した市場だけを理由にする (全市場の欠けを集める) — data-pipeline
- 再正規化の前後で比 ≥ 1.25 の判定が反転した頭数を counts に (T−10 の実購入可能性の主張への後知恵の量) — validation
- 金額の試験の診断 (3 集合と Jaccard・T−10 の β_market・対照 3) は §8-6b で宣言済み、実装は C′ の金額の試験の時
