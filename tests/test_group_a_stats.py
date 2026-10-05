"""scripts/group_a_stats.py (配列にまとめた条件付きロジット) が predictor.eval_stats.conditional_logit と一致することのテスト。"""
from __future__ import annotations

import math
import random

import numpy as np
import pytest

from predictor import eval_stats as es
from scripts import group_a_stats as st


def _world(seed, n_races=150, beta=(1.0, 0.3)):
    rng = np.random.default_rng(seed)
    rows = []
    for k in range(n_races):
        n = int(rng.integers(5, 18))                 # 頭数がレースで違う (詰め物の扱いの確認)
        m = rng.normal(size=n)
        s = 0.5 * m + rng.normal(size=n)
        u = beta[0] * m + beta[1] * s
        p = np.exp(u) / np.exp(u).sum()
        w = rng.choice(n, p=p)
        for i in range(n):
            rows.append({"race_id": f"r{k:03d}", "won": int(i == w), "m": float(m[i]), "s": float(s[i])})
    return rows


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_packed_clogit_matches_eval_stats(seed):
    rows = _world(seed)
    ref, ok_ref = es.conditional_logit(rows, ["m", "s"], with_status=True)
    p = st.pack(rows, ["m", "s"])
    got, ok = st.clogit_packed(p)
    assert ok and ok_ref
    assert got == pytest.approx(ref, abs=1e-10, rel=1e-10)


def test_packed_clogit_on_a_resample_matches_eval_stats_on_the_same_draw():
    rows = _world(4)
    p = st.pack(rows, ["m", "s"])
    vals_es, _ = es._block_resample(rows, lambda d: es.conditional_logit(d, ["m", "s"], with_status=True)[0][1], 20, 7)
    vals_st, _ = es._block_resample(rows, st.make_beta_stat(p, "s"), 20, 7)
    assert vals_st == pytest.approx(vals_es, abs=1e-10)


def test_races_without_a_winner_are_ignored_like_eval_stats():
    rows = _world(5, n_races=60)
    for r in rows:
        if r["race_id"] == "r000":
            r["won"] = 0
    ref, _ = es.conditional_logit(rows, ["m", "s"], with_status=True)
    got, _ = st.clogit_packed(st.pack(rows, ["m", "s"]))
    assert got == pytest.approx(ref, abs=1e-10)


def test_pack_marks_the_first_row_of_each_race_in_first_appearance_order():
    rows = [{"race_id": r, "won": 0, "m": 0.0} for r in ("b", "b", "a", "c", "c", "c")]
    p = st.pack(rows, ["m"])
    assert p.race_ids == ["b", "a", "c"] and [r["_ri"] for r in rows] == [0, 0, 1, 2, 2, 2]
    assert [r["_first"] for r in rows] == [True, False, True, True, False, False]
    assert list(st.races_of_draw(rows[2:3] + rows[:2] + rows[2:3])) == [1, 0, 1]


def test_separated_data_gets_the_same_verdict_as_eval_stats():
    """完全に分離したデータ (S の最大の馬が必ず勝つ) でも、収束の判定と値が eval_stats と同じ。"""
    rows = []
    for k in range(30):
        for i in range(4):
            rows.append({"race_id": f"r{k}", "won": int(i == 0), "s": float(4 - i)})
    beta, ok = st.clogit_packed(st.pack(rows, ["s"]))
    ref, ok_ref = es.conditional_logit(rows, ["s"], with_status=True)
    assert ok == ok_ref
    assert (math.isnan(beta[0]) and math.isnan(ref[0])) or beta[0] == pytest.approx(ref[0], rel=1e-9)


def test_singular_information_returns_nan_and_the_stat_returns_none():
    """S がレースの中で一定なら情報が 0 で解けない。NaN と未収束を返し、統計量は None (捨てる)。"""
    rows = []
    for k in range(30):
        for i in range(4):
            rows.append({"race_id": f"r{k}", "won": int(i == k % 4), "s": float(k)})
    p = st.pack(rows, ["s"])
    beta, ok = st.clogit_packed(p)
    ref, ok_ref = es.conditional_logit(rows, ["s"], with_status=True)
    assert ok is False and ok_ref is False and math.isnan(beta[0])
    assert st.make_beta_stat(p, "s")(rows) is None



def _heavy_tail_world(seed=5, n_races=20, b=4.0):
    """裾の重い特徴 (t 分布、自由度 1) で効果が大きい世界。1 歩の上限が収束の判定を変える (上限なしの Newton は別の値で止まる)。"""
    rng = np.random.default_rng(seed)
    rows = []
    for k in range(n_races):
        x = rng.standard_t(1, size=8)
        u = b * x
        p = np.exp(u - u.max())
        p /= p.sum()
        w = rng.choice(8, p=p)
        for i in range(8):
            rows.append({"race_id": f"r{k}", "won": int(i == w), "x": float(x[i])})
    return rows


def test_step_cap_matters_and_matches_eval_stats_on_heavy_tails():
    rows = _heavy_tail_world()
    ref, ok_ref = es.conditional_logit(rows, ["x"], with_status=True)
    got, ok = st.clogit_packed(st.pack(rows, ["x"]))
    assert ok == ok_ref
    assert (math.isnan(got[0]) and math.isnan(ref[0])) or got[0] == pytest.approx(ref[0], rel=1e-9)
    assert ok_ref is False                       # この世界は上限ありだと 100 回で収束しない (上限なしだと 2.85 で止まる)


def test_races_without_a_winner_do_not_enter_the_scale():
    """勝ち馬のいないレース (極端な値) は、標準化の SD にも入れない (eval_stats と同じ)。上限の効き方が変わるので結果も変わる。"""
    rows = _heavy_tail_world(seed=1, n_races=15, b=6.0)
    rows += [{"race_id": "z", "won": 0, "x": v} for v in (900.0, -900.0, 0.0, 450.0)]
    ref, ok_ref = es.conditional_logit(rows, ["x"], with_status=True)
    got, ok = st.clogit_packed(st.pack(rows, ["x"]))
    assert ok == ok_ref and ok_ref is True        # SD に勝ち馬なしのレースを入れると、この世界は収束しなくなる (変異 S4)
    assert (math.isnan(got[0]) and math.isnan(ref[0])) or got[0] == pytest.approx(ref[0], rel=1e-9)
