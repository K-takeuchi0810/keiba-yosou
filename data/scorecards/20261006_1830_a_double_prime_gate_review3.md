# 次の世代の候補 A″ (実装・探索・候補の門の判定) レビュー (3 名) — 2026-10-06

- 対象: `009e6d1..c27a782` (仕様の前提 6d5673b → 台帳と門 787fd8d → 実装・変異 → E0 / E1 / E2 / gate → 判定 SIGN_INSTABILITY_REJECT)
- 凍結 SHA `c27a782` で 3 名 → 反映 (`071178a` / `eee5db1` / `446e388`) → CONDITIONAL の 2 名が再判定

| 専門家 | 初回 | 再判定 | 主な指摘 |
|---|---|---|---|
| validation-process-auditor | **4.4 PASS** | — | 順序 (仕様 → 門 → 値) を git の時刻で確認、E2 をビット一致で再現、N_primary 2,176 / r / 件数を再導出して一致。should-fix: 符号の門の性質 (β=0 でも約半分通る、3 本は独立でない)、E0 の但し書きを仕様の前提にも、ブートストラップは合成の重みのばらつきを含まない |
| code-quality-reviewer | 3.8 CONDITIONAL | **4.1 PASS** | must-fix: 最終判定のファイルに入力と来歴が無い (手で呼んだ) → `--mode verdict`。必要レース数の式が 2 か所 (本命の経路が変異の対象外) → 一本化 |
| prediction-logic-analyst | 3.6 CONDITIONAL | **3.8 PASS** | 4 成分は実質 2 因子 (best3–rank 0.865、last==best3 12.4%)、「逆符号は 0」が年ごとに別の S を選んだ。ただし固定合成でも符号は定まらない。C への引き継ぎ (重みを学習期で決めない・符号の門に大きさ・成分ごとの符号の事前・件数と市場確率の分位) |

反映後の平均 **4.1**。判定 `SIGN_INSTABILITY_REJECT` は 3 名とも妥当で維持。共線性と件数の構造の数値は私が再計算して一致。変異 27/27 KILLED (run1 で X6 生存 → テスト追加)。

## 持ち越し
- ブートストラップの設定 (1000 / seed / 1%) の prereg_runner への集約: 凍結済み runner に触れないので見送り、次の候補の runner で
- 来歴に実行の開始時刻と開始時の HEAD: 次の候補の runner から
- `verdict_result.json` の `money` は再実行していない gate の成果物の透過で、旧キー `races_for_1500` のまま (忠実な記録として改変しない)
