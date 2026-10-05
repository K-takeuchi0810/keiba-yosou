"""scripts/group_a_explore.py の選択の規則 (探索台帳 A-3) と診断のテスト。"""
from __future__ import annotations

import math

import pytest

from scripts import group_a_explore as ex


def _res(name, z1, z2, w1_valid=(True, True)):
    out = []
    for z, ok in zip((z1, z2), w1_valid):
        out.append({"spec": name, "z": z, "w1": {"valid": ok} if name.endswith("W1") else None})
    return out


def test_selects_the_best_mean_z_when_clear():
    rs = _res("S1V0W0", 1.0, 1.0) + _res("S1V1W0", 2.0, 2.0)
    assert ex.select(rs)["selected"] == "S1V1W0"


def test_ties_go_to_the_simpler_candidate():
    rs = _res("S1V0W0", 1.9, 1.9) + _res("S1V1W0", 2.0, 2.0)       # 差 0.1 < 0.25
    sel = ex.select(rs)
    assert sel["selected"] == "S1V0W0" and sel["tie_set"] == ["S1V0W0", "S1V1W0"]


def test_tie_order_counts_non_default_axes_first():
    # S2V0W0 (既定でない軸 1) と S1V1W1 (2): 同点なら軸の少ない S2V0W0。S1V2W0 (1) とは V の順位で S2V0W0
    rs = _res("S2V0W0", 2.0, 2.0) + _res("S1V1W1", 2.1, 2.1) + _res("S1V2W0", 2.05, 2.05)
    assert ex.select(rs)["selected"] == "S2V0W0"


def test_tie_set_is_measured_from_the_best_not_chained():
    rs = _res("S1V0W0", 1.6, 1.6) + _res("S1V1W0", 1.8, 1.8) + _res("S1V2W0", 2.0, 2.0)
    sel = ex.select(rs)       # 1.8 は 0.2 差で集合に入るが、1.6 は最良から 0.4 差なので入らない
    assert sel["tie_set"] == ["S1V1W0", "S1V2W0"] and sel["selected"] == "S1V1W0"


def test_w1_invalid_in_either_fold_is_excluded():
    rs = _res("S1V0W0", 1.0, 1.0) + _res("S1V0W1", 5.0, 5.0, (True, False))
    sel = ex.select(rs)
    assert sel["selected"] == "S1V0W0" and "S1V0W1" in sel["excluded"]


def test_nan_z_is_excluded():
    rs = _res("S1V0W0", 1.0, math.nan) + _res("S1V1W0", 0.5, 0.5)
    sel = ex.select(rs)
    assert sel["selected"] == "S1V1W0" and "S1V0W0" in sel["excluded"]


def test_within_race_corr_removes_race_level_differences():
    rows = []
    for k in range(20):
        for i in range(4):
            # レース間で大きく違う水準 (k × 10) を持つが、レース内では a と b が逆向き
            rows.append({"race_id": f"r{k}", "a": k * 10 + i, "b": k * 10 - i})
    assert ex.within_race_corr(rows, "a", "b") == pytest.approx(-1.0)


def test_specs_are_the_twelve_registered_candidates():
    assert sorted(s.name for s in ex.SPECS) == sorted(
        f"{s}{v}{w}" for s in ("S1", "S2") for v in ("V0", "V1", "V2") for w in ("W0", "W1"))
    assert ex.FOLDS == [((2022,), (2023,)), ((2023,), (2022,))]
