"""F1 レース内相対化 / F2 枠順バイアス 特徴量のテスト (LGBM v6)。

リーク防止: F2 は馬番/頭数のみ (発走前既知)、F1 は compute_features の絶対特徴を
レース内で相対化するだけ (新規データ参照なし)。train/serve で同一適用されること。
"""
from __future__ import annotations

from predictor.features import (
    RACE_RELATIVE_BASES,
    _draw_position,
    _gate_zone,
    add_race_relative_inplace,
)


def test_draw_position_normalized():
    assert _draw_position("3", 12) == 0.25
    assert _draw_position(6, 12) == 0.5
    assert _draw_position("12", 12) == 1.0
    # 無効値は None (leak/型エラー防止)
    assert _draw_position("0", 12) is None
    assert _draw_position("5", 0) is None
    assert _draw_position(None, 12) is None
    assert _draw_position("x", 12) is None


def test_gate_zone_thirds():
    assert _gate_zone("1", 12) == "inner"
    assert _gate_zone("6", 12) == "middle"
    assert _gate_zone("12", 12) == "outer"
    assert _gate_zone("0", 12) == ""


def test_add_race_relative_rank_and_z():
    feats = [
        {"jockey_win_rate": 0.20},
        {"jockey_win_rate": 0.10},
        {"jockey_win_rate": None},  # 欠損 → 最下位 rank n, z 0
    ]
    add_race_relative_inplace(feats)
    # rank は値の昇順 (方向は LGBM が学習): 0.10→1, 0.20→2, None→n(=3)
    assert feats[1]["jockey_win_rate_rank_in_race"] == 1
    assert feats[0]["jockey_win_rate_rank_in_race"] == 2
    assert feats[2]["jockey_win_rate_rank_in_race"] == 3
    # z: mean([0.2,0.1])=0.15, sd=0.05
    assert abs(feats[0]["jockey_win_rate_z"] - 1.0) < 1e-9
    assert abs(feats[1]["jockey_win_rate_z"] + 1.0) < 1e-9
    assert feats[2]["jockey_win_rate_z"] == 0.0


def test_add_race_relative_covers_all_bases():
    feats = [{b: 1.0 for b in RACE_RELATIVE_BASES}, {b: 2.0 for b in RACE_RELATIVE_BASES}]
    add_race_relative_inplace(feats)
    for b in RACE_RELATIVE_BASES:
        assert b + "_rank_in_race" in feats[0]
        assert b + "_z" in feats[0]


def test_add_race_relative_bool_not_relativized():
    """bool 値は数値として相対化しない (is_wide_draw 等の誤混入防止)。"""
    feats = [{"jockey_win_rate": True}, {"jockey_win_rate": 0.1}]
    add_race_relative_inplace(feats)
    # True は数値扱いせず欠損 → 最下位
    assert feats[0]["jockey_win_rate_rank_in_race"] == 2
    assert feats[1]["jockey_win_rate_rank_in_race"] == 1


def test_add_race_relative_empty_and_single():
    add_race_relative_inplace([])  # 落ちない
    single = [{"jockey_win_rate": 0.5}]
    add_race_relative_inplace(single)
    assert single[0]["jockey_win_rate_rank_in_race"] == 1
    assert single[0]["jockey_win_rate_z"] == 0.0  # sd=0


def test_leg_code_never_reenters_feature_set():
    """leg_code (post-race リーク) の再流入ガード。

    2026-07-02 に leg_code が gain 32.6% を占め val_brier が偽改善する事故が発覚
    (未走馬0%/確定馬100%=レース後付与)。CATEGORICAL_MAPS に誰かが再追加すると
    _feature_vector → save_artifacts → serve まで自動伝播して静かに再発するため、
    ここで機械的に遮断する (code-quality 監査 2026-07-03 指摘の変更失敗モード)。
    """
    from scripts.train_lgbm import ALL_FEATURES
    assert "leg_code" not in ALL_FEATURES, \
        "leg_code は post-race リーク。使うなら発走前に取得可能なことを実証してから"


def test_train_serve_feature_vector_parity():
    """train (train_lgbm._feature_vector) と serve (ml_model._feature_vector) が
    同一 feat dict から同一ベクトルを生成する (train-serve skew の構造ガード)。
    """
    import json
    import math
    from pathlib import Path
    from predictor.ml_model import _feature_vector as serve_vec
    from scripts.train_lgbm import (
        ALL_FEATURES, BOOLEAN_FEATURES, CATEGORICAL_FEATURES, CATEGORICAL_MAPS,
        NUMERIC_FEATURES, _feature_vector as train_vec,
    )
    # 成果物 features.json とモジュール定数が一致 (単一出典の実体化)
    fdef = json.loads(Path("predictor/lgbm_features.json").read_text(encoding="utf-8"))
    assert fdef["all_features"] == ALL_FEATURES
    assert fdef["numeric"] == NUMERIC_FEATURES
    assert fdef["boolean"] == BOOLEAN_FEATURES
    assert fdef["categorical"] == CATEGORICAL_FEATURES

    # 混在 feat dict (数値/None/bool/カテゴリ/未知キー) で両経路のベクトルが一致
    feat = {k: None for k in NUMERIC_FEATURES}
    feat.update({
        "jockey_win_rate": 0.15, "draw_position": 0.25, "past_count": 3,
        "is_wide_draw": True, "leg_quality_available": False,
        "gate_zone": "inner", "current_bucket": "mile", "estimated_leg_code": "2",
        "unknown_extra_key": 999,  # 余剰キーは両経路とも無視される
    })
    tv = train_vec(feat)
    sv = serve_vec(feat, fdef)
    assert len(tv) == len(sv) == len(ALL_FEATURES)
    for i, (a, b) in enumerate(zip(tv, sv)):
        both_nan = isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b)
        assert both_nan or a == b, f"列 {ALL_FEATURES[i]} で train={a} serve={b}"
