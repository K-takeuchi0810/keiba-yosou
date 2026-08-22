# 予想ロジック分析官 — 20260822_1210 fresh_odds_recovery

**判定**: PASS
**総合**: 3.9 / 5 (前回 4.8、-0.9 ⚠ 後退)

| 項目 | 今回 |
|---|---|
| シグナル網羅性と市場残差性 | 4.5 |
| 重み妥当性 / 過適合リスク | 4 |
| 信頼度判定 / 確率推定の構造 | 4 |
| デッドコード / 設計の整合性 | 3.5 |
| train-serve skew | 4 |

**後退理由** (品質低下ではない): 前回は predictor 非接触の type-C 改修で満点近傍が出やすかった。
今回は BUY_FILTER_DEFAULT と backtest 契約に踏み込み、`buy_filter_from_generator()` の
`suspended` 脱落 + env 未捕捉という設計整合性の実欠陥を検出したため。

**主要所見**:
- db.py の post-start ガードは PIT 規律 (NULL=確定=発走後、発走前特徴に使用禁止) と意味論が一致。
  backtest の `race_odds_untrusted` とも矛盾しない。既存 pre-start snapshot は historical 側の
  `AND odds_fetched_at IS NULL` で保護される
- 修復の復元分岐 (4,153 行 / 544 レース) は市場人気加点を発火させうる = 予測が変わる。
  方向は PIT 的に正しいが apply 前後で backtest の互換性が切れる
- 最新 OOS 窓の fresh_rate = 46.7% で P25 compat 設計前提 (fresh≈0.4%) から分布が激変。
  再選定時に `evaluate_calibrator_compat` の確認を先行させるべき
- 印 (ルールスコア) と P (blend) の別ランカー構造 (◎≠最高P 39.2%)、朝生成で市場人気加点
  0/367 不発は本改修では不変。この構造下で EV/買い候補を出し続けることが実害経路であり、
  サスペンド + 開示は現時点で取り得る正しい封じ込め

**改善提案**: (1) backtest の suspended 契約を一貫させる → 是正済み (契約明文化 + テスト +
env_keys 登録)。(2) 修復 apply 後の backtest meta に repair audit の run_at を刻印。
(3) 印ランカーの P 統一を買い候補復活の前提条件に含める。
