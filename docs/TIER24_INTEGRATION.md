# Tier 2.4 race-internal 相対 features 統合プラン (2026-05-16)

SHAP v4 で「馬個体シグナル欠落」を確認 → Tier 2.3 (absolute 値) では既存 features
と相関し合って効果なし → **race-internal 相対値** で純粋な horse signal を提供する。

## 実装済 (このコミット時点)

- `predictor/features.py:compute_race_relative_features(conn, horses, race, cache)`
- 返り: `{horse_num: {horse_recent_top3_rel, horse_recent_avg_finish_rel, jockey_recent_top3_rel}}`

## 統合手順 (次セッション v6 訓練前に実施)

### 1. `scripts/train_lgbm.py:build_dataset` 改造

```python
from predictor.features import compute_features, compute_race_relative_features

def build_dataset(conn, from_date, to_date, ...):
    ...
    for race in races:
        horses = horses_for_race(conn, race)
        ...
        # race-relative features (Tier 2.4) を一括計算 → 各 horse に merge
        rel_map = compute_race_relative_features(conn, horses, race, cache=feature_cache)
        for h in horses:
            try:
                feat = compute_features(conn, h, race, cache=feature_cache)
                feat.update(rel_map.get(h.get("horse_num") or "", {}))
            except Exception as e:
                ...
```

### 2. `predictor/rules.py:predict_race` も同様に改造

```python
if use_features:
    rel_map = compute_race_relative_features(conn, horses, race, cache=feature_cache)
    for h in horses:
        ...
        feat = compute_features(...)
        feat.update(rel_map.get(h.get("horse_num") or "", {}))
```

### 3. `scripts/train_lgbm.py:NUMERIC_FEATURES` に 3 キー追加

```python
NUMERIC_FEATURES = [
    ...
    # Phase 6 Tier 2.4 (2026-05-16): race-internal 相対値
    "horse_recent_top3_rel",
    "horse_recent_avg_finish_rel",
    "jockey_recent_top3_rel",
]
```

合計 101 features (98 + 3)。

## 期待効果 (理論的)

| feature | 既存 absolute との独立度 | SHAP top-20 入り期待 |
|---|---|---|
| horse_recent_top3_rel | 高 (race 内偏差は absolute 値と直交) | ✓ |
| horse_recent_avg_finish_rel | 高 | △ |
| jockey_recent_top3_rel | 中 (jockey 偏重を補完するが、race 内では小さい変動) | △ |

特に **horse_recent_top3_rel** は、SHAP v4 で見えた jockey 偏重 (= 48%) を破壊する候補。
「同じレースで、この馬は他馬より直近の調子が良いか」を直接信号化。

## 期待 Brier 改善

| Version | features | val Brier 期待 |
|---|---|---|
| v5 (Tier 2.3) | 98 | 0.0606 (現在、ほぼ v4 と同等) |
| v6 (+ Tier 2.4) | 101 | 0.0595-0.0600 (-1〜-2%%) |

## v6 訓練後の確認項目

1. **SHAP 再実行** → top-20 に Tier 2.4 features 入るか
2. **jockey_win_rate の SHAP %% が下がるか** (48%% → 40%% 期待)
3. **recent-3fold sweep** で新 robust 戦略候補が増えるか
4. **TEST 全期 → PRODUCTION** で hold-out 安定性が向上するか

## 関連ファイル

- `predictor/features.py:617-665`: compute_race_relative_features 実装済
- `scripts/train_lgbm.py:NUMERIC_FEATURES`: 次セッションで 3 キー追加
- `docs/PHASE6_TIER23_DESIGN.md`: Tier 2.1/2.2/3.x の roadmap (Tier 2.4 を追記すべき)
