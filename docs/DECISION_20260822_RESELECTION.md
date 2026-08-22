# 再選定判定 2026-08-22 — 買い候補フィルタは「サスペンド維持」

対象: `scripts/filter_sweep --recent-3fold` (オッズ鮮度ゲート ON、
`repair_odds_stamps --apply` 済み DB、73 フィルタ)
証跡: `data/backtest/20260822_recent3fold_gated.csv`
事前宣言された解除条件: config.py の `BUY_FILTER_DEFAULT["suspended"]` コメント
= 「3 fold すべて robust (点推定 ≥80% かつ CI 下限 ≥50%)」かつ
「回収率 CI 下限が 100% を超えない限り観察用から上げない」

## 1. 結果 — 形式基準は 2 件が通過した

| filter | 2025H1 | 2025H2 | 2026P | min_return | min_lo | robust |
|---|---|---|---|---|---|---|
| `only_t07_pop_1_3` (中京×1-3人気) | 147戦 92.0% | 171戦 88.1% | 132戦 92.0% | 88.1% | 65.0% | **Y** |
| `only_t07_pop_1_2` (中京×1-2人気) | 119戦 92.8% | 145戦 83.3% | 121戦 88.2% | 83.3% | 61.2% | **Y** |

73 フィルタ中 2 件が Y。他は n 判定。

## 2. 判定: **サスペンド維持 (再採用しない)**

形式基準を満たしたが、以下 4 点により「買い候補としての復活」は行わない。
これは事前宣言の第 2 条件 (CI 下限 100% 超えまで観察用から上げない) の
直接適用であり、基準の後出し変更ではない。

### (a) 決定的: 利益エッジが無い
`only_t07_pop_1_3` の最良 fold でも 92.0%、CI 下限は 65.0%。**損益分岐 100% に
点推定すら届かない**。「◎ベタ 66.2% より良い」は事実だが、これは「損の小さい
負け方」であって勝ち方ではない。

### (b) fold 設計の欠陥 — 3 fold のうち 2 fold が calibration in-sample
`recent-3fold` の fold は 2025H1 / 2025H2 / 2026P だが、現行 calibrator は
**2025 通年で fit** されている (`predictor/calibrator.json`: trained
20250101-20251231, isotonic)。つまり:

- 2025H1 / 2025H2 = **calibration in-sample** → 楽観バイアスが乗る
- 2026P = 唯一の clean OOS fold

**「3 fold robust」の実質的な独立証拠は 1 fold しかない**。これは
`--recent-3fold` の期間定義 (2026-05-15 の P12 緊急対応時に固定) が、その後
2026-07-03 の calibrator 再 fit (2025 通年) と衝突したまま放置されていた
構造的欠陥である。次回の四半期再選定より前に fold 定義を見直す必要がある
(下記 §4)。

### (c) clean OOS fold では 68 フィルタ中 **1 件も 100% に到達していない**
2026P (bets≥50) の最良は `only_t04_09_ev_ge_110` の 98.3% (n=53、CI 下限
19.6% = 無情報)、次が `only_t07` 96.1%。**点推定 100% 超え 0 件 / CI 下限
100% 超え 0 件**。

### (d) 形状が P12/P14/P15 の崩壊パターンと同型
`only_t07` は単一場 (中京) の whitelist。過去の崩壊は
- P05 `wl_odds_8_20`: TEST 116% → OOS 34%
- P12 `wl5_pop_1_2`: TEST 184% → PROD 45%
- P14/P15: 場 whitelist (新潟+阪神) を recent-3fold で採用 → 崩壊

いずれも「少数の場 × 人気帯」で、73 通りから選んだ勝者だった。多重比較補正は
本 sweep でも未適用 (73 検定で 2 通過は偶然でも起こりうる水準)。

## 3. 代わりに行うこと — 封印判定への事前登録

棄却ではなく **保留 (pre-registered hypothesis)** とする。中京の優位は
2026 通年 backtest の場別でも 85.6% (101戦) で上位だったため、偶然と断定も
できない。よって:

> **事前登録仮説 H-t07**: `only_t07_pop_1_3` (中京 × 1-3 番人気 × ◎単勝) は
> 封印窓 (2026-10-01 以降) において回収率 CI 下限 > 100% を満たす。
>
> - 検定は封印判定 (12 月、≥800 レース到達時) に **1 回だけ**、F3 残差モデルの
>   判定と同時に行う。
> - それまで買い候補として表示しない (`suspended=True` 維持)。
> - `build_daily_results.py` の `would_be_candidate` 列で仮想紙運用記録を蓄積し、
>   封印判定時の補助資料とする (判定の主体は封印窓 OOS)。
> - 多重比較: 本仮説は 73 検定から選ばれた 1 件であり、封印判定では F3 本命
>   仮説と合わせて family size 2 として扱う (Bonferroni α=0.025)。

## 4. 是正タスク (R1 に追加)

**`--recent-3fold` の fold 定義を calibrator 学習期間と disjoint にする。**
現行 (2025H1/2025H2/2026P) は 2/3 が in-sample。候補案:
- (i) fold を 2026 内で 3 分割 (2026H1a / 2026H1b / 2026Q3) — 全 fold clean だが
  各 fold の n が小さくなる
- (ii) calibrator を 2021-2024 に巻き戻して fit し、2025-2026 を全 fold clean に
  する (ただし現行 production calibrator の差し替えは別判断)
- (iii) sweep 実行時に `PRED_DISABLE_CALIBRATOR=1` で calibrator 抜きの
  raw blended 確率で選定する (フィルタは odds/popularity ベースが主なので
  影響は限定的、要 ablation)

どの案でも「選定に使う fold は calibrator と disjoint」を満たすこと。
決定は R1 タスク 3 (calibrator compat 確認) と併せて行う。
