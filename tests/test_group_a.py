"""scripts/group_a.py (Phase 0.5-5 Group A の評価値の計算) の挙動のテスト。DB を使わない合成のデータで、既知の値を復元する。"""
from __future__ import annotations

import math
import random

import numpy as np
import pytest

from scripts import group_a as g


# ---------------------------------------------------------------------------------------------------- 合成の部品

def _race(rid, ymd="20230105", track="05", tt="11", dist=1600, going="T1", cls="005", age="3up", wt="3"):
    surf = g.surface_of(tt)
    return g.Race(rid, ymd, track, tt, surf, dist, going, wt, cls, age)


def _run(race, horse, finish, sec_per_km, burden=55.0, odds=5.0, abn="0", hn=None):
    r = g.Run(race.race_id, race.ymd, g.day_ordinal(race.ymd), horse, hn or horse[-2:], abn, finish, sec_per_km, burden, odds)
    race.runs.append(r)
    return r


# ---------------------------------------------------------------------------------------------------- 復号・分類

@pytest.mark.parametrize("raw, sec", [(1122, 72.2), (2096, 129.6), ("1341", 94.1), (539, 53.9)])
def test_decode_msst(raw, sec):
    assert g.decode_msst(raw) == pytest.approx(sec)


@pytest.mark.parametrize("raw", [0, None, "", "x", -5, 959, 1600])
def test_decode_msst_missing_is_nan(raw):
    assert math.isnan(g.decode_msst(raw))


def test_msst_is_not_subtracted_raw():
    """生の値の差 (1200 − 1159 = 41) は 0.1 秒ではなく、1:20.0 − 1:15.9 = 4.1 秒。"""
    assert g.decode_msst(1200) - g.decode_msst(1159) == pytest.approx(4.1)


@pytest.mark.parametrize("tt, s", [("10", "T"), ("11", "T"), ("22", "T"), ("23", "D"), ("24", "D"), ("29", "D"),
                                   ("51", None), ("52", None), ("57", None), ("", None), ("09", None)])
def test_surface_of(tt, s):
    assert g.surface_of(tt) == s


@pytest.mark.parametrize("codes, age", [
    (("701", "000", "000", "000"), "2yo"), (("000", "703", "000", "000"), "3yo"),
    (("000", "005", "005", "005"), "3up"), (("000", "000", "010", "010"), "4up"),
    (("000", "000", "000", "000"), None), (("005", "005", "000", "000"), None), (("000", "000", "000", "999"), None),
])
def test_age_restriction_rule(codes, age):
    assert g.age_restriction(*codes) == age


def test_loader_refuses_the_primary_year_without_the_flag():
    with pytest.raises(g.GroupAError, match="2025"):
        g.load_races(2025, db_path="does-not-exist.db")
    with pytest.raises(g.GroupAError):
        g.load_races(2026, db_path="does-not-exist.db")


# ---------------------------------------------------------------------------------------------------- 標準タイム

def _synthetic_world(seed=0, n_per_cell=30):
    """既知の係数で勝ち時計 / km を作る。セル 2 つ + 疎なセル 2 つ (共有で 20 を超える) + ごく疎なセル 1 つ。"""
    rng = random.Random(seed)
    cells = {("05", "11", 1600): 60.0, ("05", "24", 1400): 62.0}
    going = {"T1": 0.0, "T3": 0.8, "D1": 0.0, "D3": -0.3}
    cls_eff = {"005": 0.0, "999": -1.2, "703": 0.9}
    age_eff = {"3up": 0.0, "2yo": 1.5}
    races = {}
    k = 0

    def add(track, tt, dist, base, n, dayshift=0):
        nonlocal k
        for i in range(n):
            k += 1
            surf = g.surface_of(tt)
            gk = rng.choice([f"{surf}1", f"{surf}3"])
            c = rng.choice(list(cls_eff))
            a = rng.choice(list(age_eff))
            ymd = f"2023{1 + (i % 12):02d}{1 + (k % 27):02d}"
            r = _race(f"r{k:04d}", ymd, track, tt, dist, gk, c, a)
            t = base + going[gk] + cls_eff[c] + age_eff[a] + rng.gauss(0, 0.05)
            _run(r, f"h{k:04d}", 1, t)
            _run(r, f"x{k:04d}", 2, t + 0.3)
            races[r.race_id] = r

    for (track, tt, dist), base in cells.items():
        add(track, tt, dist, base, n_per_cell)
    add("06", "17", 2000, 61.0, 12)      # 疎 (12) と
    add("08", "18", 2000, 61.0, 12)      # 疎 (12) → 芝 2000 の共有の水準は 24 ≥ 20
    add("09", "17", 2600, 63.0, 5)       # ごく疎 (5) → 共有も 5 < 20 → 欠損
    return races, cells, going, cls_eff, age_eff


def test_par_model_recovers_known_effects_and_keeps_class_out_of_the_base():
    races, cells, going, cls_eff, age_eff = _synthetic_world()
    par = g.fit_par_model(races, (2023,))
    r = next(x for x in races.values() if (x.track, x.track_type, x.distance) == ("05", "11", 1600) and x.going == "T3")
    # 基準 = セル + 馬場状態 (クラスと年齢の区分は含めない = 2a)
    assert par.base(r) == pytest.approx(cells[("05", "11", 1600)] + going["T3"], abs=0.05)
    assert par.fitted(r) == pytest.approx(par.base(r) + cls_eff[r.cls] + age_eff[r.age], abs=0.05)
    assert par.coef["class=999"] == pytest.approx(-1.2, abs=0.05)
    assert par.coef["age=2yo"] == pytest.approx(1.5, abs=0.05)


def test_sparse_cells_pool_and_very_sparse_cells_are_unrated():
    races, *_ = _synthetic_world()
    par = g.fit_par_model(races, (2023,))
    assert par.cell_level[("06", "17", 2000)] == ("pooled", "T", 2000)
    assert par.cell_level[("08", "18", 2000)] == ("pooled", "T", 2000)
    assert par.cell_level[("09", "17", 2600)] is None
    very = next(x for x in races.values() if x.track == "09")
    assert math.isnan(par.base(very))
    assert par.counts["sparse_cells"] == 3 and par.counts["races_unrated_cells"] == 5


def test_par_model_uses_only_the_estimation_years():
    races, *_ = _synthetic_world()
    shifted = {}
    for rid, r in races.items():
        r2 = _race(rid + "b", "2022" + r.ymd[4:], r.track, r.track_type, r.distance, r.going, r.cls, r.age)
        for x in r.runs:
            _run(r2, x.horse + "b", x.finish, x.sec_per_km + 5.0)      # 2022 は 5 秒 / km 遅い世界
        shifted[r2.race_id] = r2
    races.update(shifted)
    par23 = g.fit_par_model(races, (2023,))
    r = next(x for x in races.values() if x.ymd.startswith("2023") and x.track == "05" and x.track_type == "11")
    assert par23.base(r) == pytest.approx(60.0 + (0.8 if r.going == "T3" else 0.0), abs=0.05)


def test_age_unknown_race_is_left_out_of_the_fit():
    races, *_ = _synthetic_world()
    odd = _race("odd", "20230301", "05", "11", 1600, "T1", "005", None)
    _run(odd, "hodd", 1, 99.0)                                     # 異常な時計でも推定に入らない
    races["odd"] = odd
    par = g.fit_par_model(races, (2023,))
    assert par.base(odd) == pytest.approx(60.0, abs=0.05) and math.isnan(par.fitted(odd))
    assert par.counts["races_age_unknown"] == 1


# ---------------------------------------------------------------------------------------------------- 馬場差・斤量・clip

def test_day_variant_mean_and_median_include_the_own_race_and_need_three():
    races, *_ = _synthetic_world()
    par = g.fit_par_model(races, (2023,))
    day = {}
    for i, extra in enumerate([0.3, 0.6, 1.5]):                     # 同じ日・場・芝ダに 3 レース
        r = _race(f"d{i}", "20231230", "05", "11", 1600, "T1", "005", "3up")
        _run(r, f"dh{i}", 1, par.fitted(r) + extra)
        day[r.race_id] = r
    lone = _race("lone", "20231231", "05", "11", 1600, "T1", "005", "3up")
    _run(lone, "lh", 1, par.fitted(lone) + 2.0)
    allr = {**races, **day, "lone": lone}
    v1 = g.day_variants(allr, par, "V1")
    v2 = g.day_variants(allr, par, "V2")
    assert v1[("20231230", "05", "T")] == pytest.approx(0.8, abs=1e-6)
    assert v2[("20231230", "05", "T")] == pytest.approx(0.6, abs=1e-6)
    assert ("20231231", "05", "T") not in v1                       # 1 レースだけの日は載せない (= 0)
    assert g.day_variants(allr, par, "V0") == {}


def test_raw_residual_subtracts_base_variant_and_weight_but_not_class():
    r = _race("a", "20230105", "05", "11", 1600, "T1", "999", "2yo")
    par = g.ParModel((2023,), {("05", "11", 1600): ("05", "11", 1600)}, {"intercept": 60.0, "class=999": -1.0,
                                                                          "age=2yo": 1.0}, [], {})
    run = _run(r, "h", 1, 61.0, burden=57.0)
    res = g.raw_residual(run, r, par, {("20230105", "05", "T"): 0.4}, w=0.1)
    assert res == pytest.approx(61.0 - 60.0 - 0.4 - 0.1 * 2.0)


@pytest.mark.parametrize("v, c", [(5.0, 3.0), (-5.0, -3.0), (2.9, 2.9), (-2.9, -2.9), (3.0, 3.0)])
def test_clip_is_symmetric_at_three(v, c):
    assert g.clip_residual(v) == c


def _weight_world(slope):
    races = {}
    par = g.ParModel((2023,), {("05", "11", 1600): ("05", "11", 1600)}, {"intercept": 60.0}, [], {})
    for h in range(40):
        for k, kg in enumerate((54.0, 56.0, 58.0)):
            r = _race(f"w{h}_{k}", f"2023{k + 1:02d}{h % 27 + 1:02d}", "05", "11", 1600, "T1", "005", "3up")
            _run(r, f"h{h}", 1, 60.0 + slope * (kg - 55.0) + 0.01 * h, burden=kg)
            races[r.race_id] = r
    return races, par


def test_weight_effect_is_estimated_within_horse():
    races, par = _weight_world(0.05)
    fit = g.fit_weight_effect(races, par, {}, (2023,))
    assert fit["w"] == pytest.approx(0.05, abs=1e-6) and fit["valid"] is True


def test_non_positive_weight_effect_disables_w1():
    races, par = _weight_world(-0.05)
    fit = g.fit_weight_effect(races, par, {}, (2023,))
    assert fit["w"] < 0 and fit["valid"] is False


def test_weight_effect_excludes_handicap_races():
    races, par = _weight_world(0.05)
    for r in races.values():
        if r.runs[0].burden_kg == 58.0:
            r.weight_type = g.HANDICAP
            r.runs[0].sec_per_km = 50.0                       # ハンデ戦のゴミ値は推定に入らない
    fit = g.fit_weight_effect(races, par, {}, (2023,))
    assert fit["w"] == pytest.approx(0.05, abs=1e-6)


# ---------------------------------------------------------------------------------------------------- 評価値・成分

def _tables(par, variants=None, w=0.0, scales=None):
    return g.RatingTables(g.Spec("S1", "V0", "W0"), par, variants or {}, w, None, scales)


def test_rate_runs_faster_is_larger_refunds_excluded_and_clip_counted():
    par = g.ParModel((2023,), {("05", "11", 1600): ("05", "11", 1600)}, {"intercept": 60.0}, [], {})
    r = _race("a", "20230105")
    _run(r, "fast", 1, 59.5)
    _run(r, "slow", 2, 64.0)                       # +4.0 → clip で +3.0
    _run(r, "scr", 0, math.nan, abn="1")
    _run(r, "dnf", 0, math.nan, abn="4")           # 時計なし → 評価値なし
    out, st = g.rate_runs({"a": r}, _tables(par))
    assert out["fast"][0][1] == pytest.approx(0.5) and out["slow"][0][1] == pytest.approx(-3.0)
    assert "scr" not in out and "dnf" not in out
    assert st["clipped_slow"] == 1 and st["unrated_runs"] == 1


def test_s2_divides_by_the_band_sd():
    par = g.ParModel((2023,), {("05", "11", 1600): ("05", "11", 1600)}, {"intercept": 60.0}, [], {})
    r = _race("a", "20230105")
    _run(r, "h", 1, 59.0)
    out, _ = g.rate_runs({"a": r}, _tables(par, scales={("T", 1): 0.5}))
    assert out["h"][0][1] == pytest.approx(2.0)


def test_components_use_the_365_day_window_before_the_target_day():
    t = g.day_ordinal("20240601")
    hist = [(t - 400, 9.0), (t - 300, 1.0), (t - 200, 2.0), (t - 100, 4.0), (t - 10, 3.0), (t, 99.0)]
    c = g.horse_components(hist, t)
    assert c["perf_rating_last"] == 3.0                              # 対象日の走 (99) は使わない
    assert c["perf_rating_best3_365"] == pytest.approx((4 + 3 + 2) / 3)   # 400 日前 (9) は窓の外
    x = np.array([-300, -200, -100, -10]) / 100.0
    y = np.array([1.0, 2.0, 4.0, 3.0])
    slope = ((x - x.mean()) @ (y - y.mean())) / ((x - x.mean()) @ (x - x.mean()))
    assert c["perf_rating_trend_365"] == pytest.approx(slope)


def test_components_window_edges():
    t = g.day_ordinal("20240601")
    assert g.horse_components([(t - 365, 5.0)], t)["perf_rating_last"] == 5.0     # ちょうど 365 日前は入る
    assert math.isnan(g.horse_components([(t - 366, 5.0)], t)["perf_rating_last"])
    c = g.horse_components([(t - 50, 1.0), (t - 20, 2.0)], t)
    assert c["perf_rating_best3_365"] == 1.5 and math.isnan(c["perf_rating_trend_365"])   # 3 走未満は trend なし


def test_rank_in_race_ties_and_missing():
    out = g.rank_in_race([3.0, math.nan, 1.0, 3.0])
    assert out[1] != out[1]                                          # NaN
    # 有効 3 頭: 3.0 が同値 2 頭 (順位 1.5)、1.0 は 3 位 → (3 − 1.5 + 0.5)/3 と (3 − 3 + 0.5)/3
    assert out[0] == out[3] == pytest.approx(2.0 / 3) and out[2] == pytest.approx(0.5 / 3)


def test_target_samples_renormalise_and_drop_bad_races():
    ok = _race("ok", "20230105")
    _run(ok, "a", 1, 60.0, odds=2.0)
    _run(ok, "b", 2, 60.5, odds=4.0)
    _run(ok, "c", 0, math.nan, odds=0.0, abn="3")        # 返還: 選択集合から除く (価格なしでも race は残す)
    noprice = _race("np", "20230106")
    _run(noprice, "d", 1, 60.0, odds=2.0)
    _run(noprice, "e", 2, 60.0, odds=0.0)                # 返還でないのに価格なし → レースを落とす
    heat = _race("dh", "20230107")
    _run(heat, "f", 1, 60.0, odds=2.0)
    _run(heat, "h", 1, 60.0, odds=3.0)
    counts = g.Counter()
    rows = g.target_samples({"ok": ok, "np": noprice, "dh": heat}, (2023,), {}, counts)
    assert [r["horse"] for r in rows] == ["a", "b"]
    assert sum(r["p_market"] for r in rows) == pytest.approx(1.0)
    assert rows[0]["p_market"] == pytest.approx((1 / 2) / (1 / 2 + 1 / 4))
    assert counts["drop_runner_without_price"] == 1 and counts["drop_dead_heat_or_no_winner"] == 1


def test_target_samples_skip_other_years():
    r = _race("ok", "20240105")
    _run(r, "a", 1, 60.0)
    assert g.target_samples({"ok": r}, (2023,), {}, g.Counter()) == []


# ---------------------------------------------------------------------------------------------------- 合成

def _clogit_world(seed=1, n_races=300, beta_s=0.6):
    rng = np.random.default_rng(seed)
    rows = []
    for k in range(n_races):
        n = 8
        m = rng.normal(size=n)
        good = rng.normal(size=n)          # 正の符号の成分
        bad = rng.normal(size=n)           # 逆の符号の成分
        u = m + beta_s * good - 0.5 * bad
        p = np.exp(u) / np.exp(u).sum()
        w = rng.choice(n, p=p)
        pm = np.exp(m) / np.exp(m).sum()
        for i in range(n):
            rows.append({"race_id": f"r{k}", "won": int(i == w), "p_market": float(pm[i]),
                         "perf_rating_last": float(good[i]), "perf_rating_best3_365": float(bad[i]),
                         "perf_rating_trend_365": math.nan if i == 0 else float(rng.normal()),
                         "perf_rating_rank_in_race": float(rng.normal())})
    return rows


def test_composite_zeroes_reverse_sign_components():
    rows = _clogit_world()
    g.add_market_logit(rows)
    comp = g.fit_composite(rows)
    assert comp["weights"]["perf_rating_last"] > 0
    assert comp["raw_weights"]["perf_rating_best3_365"] < 0 and comp["weights"]["perf_rating_best3_365"] == 0.0
    assert "perf_rating_best3_365" in comp["zeroed"]


def test_standardizer_uses_non_missing_rows_only():
    rows = [{"x": 1.0}, {"x": 3.0}, {"x": math.nan}]
    std = g.standardizer(rows, ["x"])
    assert std["x"] == (2.0, 1.0)
    g.apply_standardizer(rows, std)
    assert [r["x_z"] for r in rows] == [-1.0, 1.0, 0.0]


def test_apply_composite_standardises_with_the_fit_values():
    fit = _clogit_world(seed=2)
    ev = _clogit_world(seed=3)
    for rows in (fit, ev):
        g.add_market_logit(rows)
    comp = g.fit_composite(fit)
    g.apply_composite(ev, comp)
    res = g.clogit_with_se(ev, ["logit_p_market", "S"])
    assert res["converged"] and res["beta"][1] > 0 and 0 < res["se"][1] < 1


def test_clogit_se_shrinks_with_more_data():
    small = _clogit_world(seed=4, n_races=200)
    big = _clogit_world(seed=4, n_races=800)
    for rows in (small, big):
        g.add_market_logit(rows)
    se_s = g.clogit_with_se(small, ["logit_p_market", "perf_rating_last"])["se"][1]
    se_b = g.clogit_with_se(big, ["logit_p_market", "perf_rating_last"])["se"][1]
    assert se_b == pytest.approx(se_s / 2, rel=0.25)
