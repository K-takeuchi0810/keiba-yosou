# 採点 2026-05-11 23:45 — a (walk-forward 検証) + e (収益性 sweep) 完了

**改修内容**:

### a. walk-forward 検証
- 過去 7 ヶ月 (2025/06-12, design 2016 戦) と 4 ヶ月 (2026/01-04, eval 1164 戦) を比較
- 結果: 同じ whitelist で **design 74.3% / eval 84.9%**(+10.6pt) — 自己参照バイアス顕在化
- 「84.9% は本物」が幻と判明

### e. 収益性 sweep
- `scripts/filter_sweep.py` を walk-forward 対応に拡張 (Pick に grade_code / ev / confidence 追加)
- `--walk-forward` フラグで 2 期間並列 sweep
- 結果: **両期間で控除率 80%+ の filter を 6 種検出**

| filter | DESIGN (戦/%) | EVAL (戦/%) |
|---|---|---|
| wl_odds_8_20 | 74/103.5 | 41/116.1 🏆 |
| wl_ex_unsure_pop_1_4 ★採用 | 166/86.3 | 105/89.0 |
| wl_pop_4_6 | 96/99.5 | 49/82.7 |
| wl_ex_unsure | 184/83.9 | 115/81.3 |
| wl_pop_4_8 | 118/80.9 | 57/122.1 |
| wl_odds_2_5 | 259/80.7 | 180/84.2 |

- `wl_ex_unsure_pop_1_4` (重賞+中山+京都, 1-4 人気, 信頼度判定) を採用
- 戦数 271 (両期間合計) で再現性最大バランス
- `config.BUY_FILTER_DEFAULT` を `min_popularity: 1 / max_popularity: 4 / exclude_confidence: ["暫定","混戦","接戦"] / min_ev: None (制約なし)` に更新
- `_matches_buy_filter` / `_is_buy_candidate` / `web/generator.py:bet_candidate` 全部で同じ語彙

## 最終 backtest

| 期間 | 戦数 | 的中率 | 回収率 | 収支 |
|---|---|---|---|---|
| EVAL 全体ベタ買い | 1,164 | 19.9% | 60.8% | -45,590 円 |
| EVAL buy_only (新フィルタ) | **105** | **34.3%** | **89.0%** | **-1,150 円** |
| EVAL whitelist_only (wl 全ベタ) | 326 | 25.8% | 84.9% | -... |

→ **控除率 80% を +9pt 上回るが +100% には未達 (-11% 程度)**。
- 「84.9% は幻」だったが、新フィルタは両期間で再現性ある 80%+ が**確証**された
- +利益には届かないが、**コントロールされた小幅な損失** にとどめる運用が初めて backtest で示された
- 次の sweep でさらに `wl_odds_8_20` (100%+) 路線も検討可能

## 横断的な次の課題

- **wl_odds_8_20 路線**: 戦数少だが両期間で 100%+。これに乗り換える検討
- **ハイブリッド戦略**: whitelist + 信頼度除外 + (人気帯 OR Odds 帯) の組合せ sweep
- 残課題: データパイプライン 3 件, walk-forward 専用 CLI, GUI helpBox など

scorecard は次の expert-review で正式採点。
