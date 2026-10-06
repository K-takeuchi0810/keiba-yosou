# 2026-10-06 12:00 — Group C′ 凍結の前の 4 名レビュー

- 対象: worktree `c-prime`、レビュー SHA ddc12b6 (base main 5c7add0)。**subagent CWD 限定運用での評価** (全員 `git -C <worktree>`、2025 は未閲覧)
- ai_builder_impact: none (db.py・jvlink_client・取り込み・schema は差分なし、data-pipeline が確認)

| 担当 | 判定 | 総合 | must-fix |
|---|---|---|---|
| data-pipeline-engineer | PASS | 4.4 | なし (本番 DB の 2021-2024 を mode=ro で集計: 脚質コードの欠けは取消・除外・中止の走と完全一致、同じ日の 2 走 0 件、件数は成果物と完全一致) |
| validation-process-auditor | CONDITIONAL | 4.0 | 向きの定まらない合成で主検定に進むときの読み方を事前に台帳へ / 合格した場合の監視の要件を主検定の前に書く |
| prediction-logic-analyst | CONDITIONAL | 3.8 | 解釈の規則を結果の前に固定 (S は脚質の主効果とレース内相関 0.93) / §2 C の反証の条件の学習期の結果を記録 |
| code-quality-reviewer | CONDITIONAL | 3.6 | 固定のファイルの照合を fail-closed に / 検出力の経路の行動テスト (独自の追加変異 8 本が全部生存、うち対象日を窓に含める X2) / .gitattributes |

平均 3.95。

## 重要な指摘 (prediction-logic、自分で再計算して一致を確認)

- C′ の S はレース内で脚質の主効果 (先行・差し) とほぼ同じ (相関 0.92)。pace の交互作用に固有の情報は約 1 割
- 事前登録 §2 C の反証の条件を学習期で測ると該当 (高圧のレースの先行馬 実勝 / Σp 0.999)
- 脚質の推定の精度は低い (前後の 2 分類 68.5% vs 基準 65.7%、κ 0.31)
- 仕様は変えない (E1 / E2 の後の変更は forking path)。解釈の錠を結果の前に掛ける

## 反映

- コード (`da6fce1`): fail-closed / 検出力の経路の行動テスト 2 本 / 2025 の履歴は着順・オッズを SQL で NULL / 2025 の履歴の digest を arm と primary の開始の印の前に照合 /
  上書きしない / 判定を副次の記録より先に書くテスト / 特異な情報行列 / 符号一致率・単独の当てはめ・既知の頭数・合成の向きの印・副次の記録の追加 / z の命名 /
  返還の代表のコード / .gitattributes
- 台帳 (`1af54bb`): 仮説の直接の診断 / 主検定の結果の読み方 (予告 PRIMARY_FAIL、MDE 約 0.066) / 合格した場合の監視の要件 / 主検定の年の履歴の扱い

## 持ち越し

- code-quality: C′ と Group A の runner の共通の純粋関数を共通モジュールへ (Group A は錠で触れない。金額の試験・Group D の前に検討)
- code-quality: c_prime_explore の書き込みを原子的に (E1 / E2 は実行済み)、静的テストの禁止語を正規表現に
- validation: runner の端から端で build_choice_set の控除率付き implied の経路の不変性
