# Phase 6 Tier 2 / Tier 3 features 設計 (2026-05-16)

LGBM v4 (Tier 1 込み 84 features) は val Brier 0.0604 で、jockey_track_top3_rate が
重要度 2 位という強い場別相性を捕捉している。Tier 2/3 で「**まだ捕捉できていない
信号**」を追加し、`年間 110%, 月次変動許容` という目標へ近づける。

## 設計指針

1. **動的更新を許容する設計** — 馬場改修 / 開催プロモーション変更で 5 年単位で
   特性が変動する。「固定された場別 prior」より「直近 N 戦の rolling 統計」を
   優先。
2. **race-internal context** — 「同じレース内の他馬との相対」シグナルを増やす。
   絶対値より race 内の差分のほうがレース内 ranking 学習に効く。
3. **時間軸別の特徴量** — 春/夏/秋/冬の季節バイアスを明示。月単位 (race_month) は
   Tier 1 にあるが、季節として大きな分けも追加。

---

## Tier 2 (高優先、~10 features)

### 2.1 ペース動態

**現状**: `front_runner_count` だけ (`predict_race` で計算)。先行馬の頭数のみ。

**追加候補:**
- `pace_runners_count_pct` — 先行馬の頭数 / 出走頭数 (= 比率化)
- `same_leg_rivals_pct` — 同脚質の競合 / 全馬数
- `expected_pace_index` — 過去走の上がり 3F の race 内 平均から想定ペース推定
  - 速いペース → 差し有利、遅いペース → 逃げ有利
- `is_front_only_race` — 全馬が逃げ/先行のみ (= 持続力勝負想定)

**実装方針:**
- `compute_features` 内で race ごとの集計を `cache` に保存
- 1 レース分の horses リストを ahead で見て計算

### 2.2 馬場×コース×季節の相性 (3 次元キー集計)

**現状**: `sire_surface_top3_rate`, `same_track_type_runs` 等の 2 次元のみ。

**追加候補:**
- `track_surface_distance_top3_rate` — (track, surface, distance_bucket) の過去
  top3 率 (= レース条件の総合 prior)
- `track_going_top3_rate` — (track, going) の過去 top3 率
- `track_season_top3_rate` — (track, season) の過去 top3 率
  - season は 1-4 (1月-3月, 4月-6月, 7月-9月, 10月-12月)

**実装方針:**
- 3 次元キーは SQL クエリで集計 (適切な index 追加検討)
- cache size 大きめ想定 (1 race あたり 数十エントリ)

### 2.3 直近の rolling 統計 (馬場改修対応)

**現状**: TRAIN 期間全体での集計 = 馬場改修前後を区別しない。

**追加候補:**
- `track_recent_top3_rate_30d` — (track) の直近 30 日 top3 率
- `track_recent_top3_rate_90d` — 同 90 日
- `track_recent_pace_index` — 直近 30 日の場の「先行有利度」(= 1着馬の脚質分布)

**実装方針:**
- before_date を center に、(before - 30day, before) の window で集計
- 馬場改修等で trend が変わってもモデルが追従可能

---

## Tier 3 (中優先、~5 features、効果不確実)

### 3.1 4 角通過順位 (JV-Data の真のペース指標)

**現状**: 一切無し (JV-Data の SE record に `corner_order` field あるが parse 未対応)。

**追加候補:**
- `recent_4corner_avg_position` — 直近 N 戦の平均 4 角通過順位
- `recent_4corner_position_change` — 4 角→ゴールでの順位上昇 (= 差し脚力)
- `same_track_4corner_avg` — この場で過去どの位置から走ったか

**実装方針:**
- 既存 parse_se を拡張して corner_order_4 を field 化 (SE record の position 要確認)
- schema.sql の horse_races に 4_corner_position カラム追加
- 既存 raw を再 ingest

**注意**: parse_se の byte offset は PDF page 12 から再検証必要。
HC/WC parser でも同じ問題があり要対応。

### 3.2 馬場バイアス direction (内/外有利傾向)

**現状**: 完全に無し。

**追加候補:**
- `track_bias_inside_outside` — 同場直近 30 日の 1 着馬の枠順分布
  - 1-3 枠頻度 vs 7-9 枠頻度 で「内有利」「外有利」を識別
- `horse_waku_match_bias` — この馬の枠順 × 場バイアスの整合

**実装方針:**
- waku × 場 × date でグループ化、直近 30 日の 1 着分布を集計
- bias_score = (内側勝率 - 外側勝率) / (内側勝率 + 外側勝率)

### 3.3 馬体重 delta (発走前の状態)

**現状**: `horse_weight` のみ。`weight_change_diff` はあるが parse 不完全の可能性。

**追加候補:**
- `pre_race_horse_weight_delta` — 発走前公式の前走比馬体重差
- `weight_volatility_recent_3` — 直近 3 走の馬体重 std (= 体重不安定さ)

**実装方針:**
- WH record (0B12 / 速報系) を新規 parse 実装
- schema.sql に pre_race_weight, weight_delta 追加
- 課題: WH は速報なので直前更新を要確実取得

---

## Tier 4 (低優先 / 実験的、~5 features)

### 4.1 騎手×厩舎の同期 (= 鞍上指示への馬の慣れ)

- `jockey_trainer_pair_top3_rate` — この騎手×厩舎の組合せの過去成績

### 4.2 馬主×厩舎の組合せ

- `owner_trainer_pair_top3_rate` — 経済的動機ベース信号
  - 強い馬主は強い厩舎に預ける傾向 → 同じ組合せのレースは平均的にレベル高い

### 4.3 競走間隔の質

- `weeks_since_grade_run` — 重賞挑戦からの経過週
- `class_step_velocity` — 過去 5 戦のクラス変化率 (上昇トレンド検出)

---

## 実装ロードマップ

### Sprint 1 (1-2 セッション)
1. Tier 2.3 (rolling 統計 30/90 日) — 既存 SQL 改造で実装可能、改造コスト低
2. SHAP 分析実行 (`scripts.analyze_lgbm`) で Tier 1 features の効きを SHAP で確認
3. Tier 2.1 (ペース動態) — `compute_features` の race-level cache を拡張

### Sprint 2 (2-3 セッション)
4. Tier 2.2 (3 次元キー集計) — index 追加 + 集計 SQL
5. Tier 3.1 (4 角通過順位) — parse_se 拡張 + schema migration + 再 ingest
6. LGBM v5 訓練 + recent-3fold sweep

### Sprint 3 (1-2 セッション)
7. Tier 3.2 (馬場バイアス) + Tier 3.3 (馬体重 delta、要 WH parser)
8. LGBM v6 訓練 + 比較

### Sprint 4 (1 セッション)
9. SHAP 再分析、Tier 4 候補から効きそうなものを選定

---

## 期待効果

各 Tier 追加で見込まれる val Brier 改善 (推定):

| Phase | features | val Brier | 期待効果 |
|---|---|---|---|
| v4 (現在) | 84 | 0.0604 | baseline |
| v5 + Tier 2 | ~95 | 0.058-0.059 | -2 〜 -4%% |
| v6 + Tier 3 | ~100 | 0.056-0.058 | -1 〜 -3%% |
| v7 + Tier 4 (一部) | ~105 | 0.055-0.057 | -1 〜 -2%% |

Brier 改善 1%% で recent-3fold の robust 戦略数が ~+2-3 個増える経験則。
真の効果は train_lgbm + recent-3fold + hold-out で実証してから判断。

---

## 教訓: P12 失敗を踏まえた設計判断

「TEST 通年 robust → PRODUCTION で同等」は成立しない (P12 が実証)。
Tier 2/3 でも「採用判断後の hold-out」を必ず通すこと。設計時に
「動的更新を許容する features (rolling 統計)」を優先する。
