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
