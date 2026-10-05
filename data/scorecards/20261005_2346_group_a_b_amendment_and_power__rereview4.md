# 2026-10-05 23:46 — Group A: P3 の改訂 B + must-fix の反映 + 検出力の経路 (4 名の限定再レビュー)

- 対象: worktree `group-a-class`、74cf5ff..c9688b5。**subagent CWD 限定運用での評価**。2025 は誰も読んでいない
- ai_builder_impact: none

| 担当 | 判定 | 総合 (前回) | must-fix |
|---|---|---|---|
| validation-process-auditor | CONDITIONAL | 4.3 (4.2) | M1 forking path の錠 (§8-4b-3 に「E1 の z・選択と E2 の z を見た後の改訂」と明記、P1〜P3 の改訂はこの 1 回限り、E1 と E1b の z の比較を選択に使わない、E2b は新鮮な点検ではない) |
| prediction-logic-analyst | PASS | 4.2 (4.0) | なし |
| data-pipeline-engineer | CONDITIONAL | 4.2 (4.1) | M1 allow-list の検査が部分文字列の照合で抜ける (`h.*`、`front3f_time`・`last3f_time`・`lap_times`・`leg_quality_code`・生の `abnormal_code`・`starter_count`)。`*` を禁止し、`cursor.description` の列名が allow-list と完全一致することを実 DB で確かめる |
| code-quality-reviewer | CONDITIONAL | 4.3 (4.1) | M1 凍結物の版と定数の照合が無い (定数を変えると黙って別の評価値) / M2 `fit_composite` の年のガードが `year` の欠落で素通り |

平均 4.25 (前回 4.10)。前回の must-fix (code-quality 4 件、validation 3 件) は解消と判定。

## 確かめられたこと

- prediction-logic (2021-2024 の実データ、推定 2022-2023、S1V1W0): 遅い側の clip 率は 新馬 2 歳 26〜27% → 4.8〜6.0%、新馬 3 歳 28〜38% →
  7.5〜11.2%、未勝利 2 歳 13〜14% → 3.7〜4.5%、未勝利 3 歳 10〜11% → 4.6〜5.1%、1 勝 0.5〜0.9% (不変)、2 勝 / OP 0.1〜0.6% → 0.2〜0.9%。
  **速い側は 64 区分すべて 0%** (勝ち時計の基準からの残差は下に有界なので、対称の ±3 は事実上片側)。残る差は分散の差 (残差 − c − d の
  p95: 701/3 歳 3.48、016/4 歳以上 1.56) と、クラス × 年齢の交互作用の取りこぼし (701/3 歳は過小、701/2 歳は過大に補正)
- data-pipeline: `load_target_fields(2024)` と `load_races(2024)` は 3,327 レース / 45,796 走で完全一致。同日・未来の評価値を植え込んでも成分は不変
- code-quality: 凍結物の往復 (tuple の鍵の復元・型) は正しい。前回の must-fix 4 件は解消

## should-fix (要旨)

- validation: §8-7 の「勝ち馬の列を読まずに」を「主検定の標本の行に載せない / ロジットに渡さない」に (馬場差は 2025 の勝ち時計を使う) /
  `DEPENDENCIES` に group_a_power.py / 検出力の側に S と市場の相関 ρ / 学習期のブートストラップの値の固定 (n_boot 1000、seed 20261004、
  レース単位、凍結した S を固定して β_S、SE = SD (ddof 1)、不収束は捨てて 1% 超なら NA、N は fit 行のレース数と target_races_used)
- prediction-logic: 速い側 0% と分散由来の差を台帳に数値で / 未知の class / age の係数を黙って基準扱いにしない (件数を残す) /
  交互作用は将来の改訂の候補として記録だけ
- data-pipeline: `horse_components` の日付順の前提を assert / 対象レースの結果を書き換えても `outcome_blind_rows` が一致する植え込み試験 /
  検出力の N は同着を含む (N_power ≥ N_primary) / CASE の返還を `g.REFUNDED` から / 評価年の基準なしレースの競馬場別 (持ち越し)
- code-quality: リテラル 2025 を `PRIMARY_YEAR` に / `TARGET_SELECT` を完全一致で固定 / 選択集合の規則の二重実装 (同着の扱いの差を明記) /
  provenance が欠けた依存を黙って飛ばす / Spec の値域の検証 / `__import__("datetime")`
