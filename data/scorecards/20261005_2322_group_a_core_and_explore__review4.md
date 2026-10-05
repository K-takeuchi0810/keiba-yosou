# 2026-10-05 23:22 — Group A の本体・探索・交差 E1・dry run E2 (4 名レビュー)

- 対象: worktree `group-a-class`、2ae320f..74cf5ff。**subagent CWD 限定運用での評価** (main には未反映)。2025 は誰も読んでいない
- ai_builder_impact: none (data-pipeline が確認)

| 担当 | 判定 | 総合 | must-fix |
|---|---|---|---|
| validation-process-auditor | CONDITIONAL | 4.2 | M1 2025 の読み込みに結果を実体化しない経路が無い / M2 再現性の記録 (全ツリーの dirty、eval_stats・config の SHA) / M3 検出力の SE の計算器を結果に依存しない形で分ける |
| prediction-logic-analyst | PASS | 4.0 | なし (バグ無し)。最重要の should-fix: clip のクラス別の偏り |
| data-pipeline-engineer | PASS | 4.1 | なし (2025 の経路の前提として、列の allow-list の別関数 + 実行 SQL を捕まえるテスト) |
| code-quality-reviewer | CONDITIONAL | 4.1 | 全成分が逆符号のとき黙って NaN / 来歴の記録の一元化 / 凍結物の書き出しと読み込み + 2025 の行を推定に渡したら止める / 2025 の検出力の経路の分離 |

平均 4.10 (前回 4.08)。

## 確かめられたこと

- validation: cross_results.json から選択を独立に再計算し、S1V1W0 が台帳 A-3 の規則と一致。コミットの順と時刻も守られている
- prediction-logic: 2021-2024 の実データで本体が仕様どおり (標準タイム・馬場差・成分・選択集合・合成)、PIT の漏れなし。設計行列は rank が 1 落ちる
  (馬場状態の参照が芝ダで 1 つ) が、`base` / `fitted` が使う列の組は零空間と直交し、結果は不変 (|B·null| = 4e-15)
- data-pipeline: load_races の実測が成果物と一致、クラスの表と双方向で差 0、DB の mtime 不変。京都 (2022-2023 推定) は 15 セル中 7 が欠損、
  2024 の京都 707 レース中 151 が基準なし。ただし対象行への波及は 115 行

## 仕様に関わる発見 (外部の指示者に諮る)

- **clip (P3) のクラス別の偏り** (prediction-logic): 残差の基準が 005 / 3 歳以上なので、上側 (遅い側) の clip 率は 新馬 701: 2 歳 26% / 3 歳 32.5%、
  未勝利 703: 11〜13%、005: 1.4〜2%、016 / 999: 1% 未満。「1 走の極端な値の有界化」ではなく、若い世代・下級条件の走への系統的な打ち切りに
  なっている。E1 の「約 7%」は全体の値だけの報告だった (裾の内訳を報告していない)
- 単一の成分でも向きで符号が反転する (best3 の評価の z: 2022→23 +2.11 / 2023→22 +0.13 / →2024 −0.52、trend +1.98 / −1.88 / +1.72)。
  best3 と rank のレース内の相関 0.90、last 0.69 (共線)

## should-fix (要旨)

- validation: SE の非対称 (0.023 vs 0.048) は S の構成の差 (レース内の変数かどうか) による。E2 の見込みはこの条件付きであることと、見込みの後に
  検出力を上げる方向の仕様変更をしないことを明記 / 最終の推定は argv・開始と終了の時刻を記録 / 疎なセル・評価値なしを競馬場別×年別で
- prediction-logic: rank の落ちの明記とガード / E1 の解釈の精緻化 (成分自体に安定した情報が無く、重みの不安定はその帰結) / 京都のセルを MANIFEST に /
  S の欠損 (4 成分すべて欠損) の定義を台帳に / S = 0 の行が評価行の 11〜12% であることを E2 に併記
- data-pipeline: 封印の門の情報を成果物に / mode=ro をテストで強制 / 評価の年で基準が無いレースの競馬場別の件数
- code-quality: REFUNDED を db から import / `OBSTACLE_FROM` は振る舞いを持たない (未知の track_type を別に数える) / W1 無効時の w=0 の配線と
  `unrated_no_scale` のテスト / `fit_scale`・`target_samples` の空の馬 ID / load_races の SQL と evaluate の end-to-end のテスト /
  fit と apply の副作用の分離・Spec の frozen / explore の `next()` の誤用
