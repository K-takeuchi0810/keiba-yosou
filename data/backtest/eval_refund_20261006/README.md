# §8-6 の修正前後の集合の件数 (2026-10-06)

- `smoke_counts.py` で `market_offset_eval.collect` を 4A/4B の評価窓 (2026-05-09〜08-31、消費済み) で 1 回ずつ通し、**集合の件数だけ** を比べた
  (回収率・係数・的中は計算も表示もしていない)。DB は本番の keiba.db を mode=ro
- 旧 (`smoke_old.json`、main 62e9698): 931 レース (鮮度内 626)、`runner_set_mismatch` 6
- 新 (`smoke_new.json`、eval-refund): 937 レース (鮮度内 630)、除外 0。返還の対象 58 頭 / 54 レースを選択集合から除いた
  (T−10 で価格のあった返還の対象 44 頭・最終の列で価格のあった 48 頭 = 旧実装が外れの賭けに数えていた馬)。特払い 0
- 旧実装が黙って落とした 6 レースは、T−10・最終・標本の行で返還の対象の有無が食い違っただけのレース (新実装ではすべて残り、除外の理由に該当するものは 0)
- したがって「鮮度 30 分以内 626 レース」(0.5-3 の基準線・4A/4B) は、新しい規則では 630 レースになる。旧成果物の数値は書き換えない

## §8-6b の表の再現

- `market_term_table.py` → `market_term_table.json`。学習期 2022-2024 だけ (`group_a.load_races(2024)` は 2025 を拒否する)。本番 DB を mode=ro
- β_market (logit / log): 2022 0.900 / 1.055、2023 0.880 / 1.026、2024 0.895 / 1.047 (事前登録の表と一致)

## 変異テスト

- spec: `tests/mutation_specs/eval_refund_spec.py` (28 個)。`git archive 0e7c73d` の隔離コピー (scratchpad、`.git` 無し) + `.venv64` のジャンクション
  (実行後に `DirectoryInfo.Delete()` で外した)
- run1 (`0e7c73d`): **KILLED 28 / 28** (`mutation_r1_0e7c73d.txt`)。外部の指示者が必須とした対照の組 E1 (返還の対象の価格 0 でレースを落とす) /
  E2 (返還の対象でない馬の価格なしを除かない) は両方 KILLED
