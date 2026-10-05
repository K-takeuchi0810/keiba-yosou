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
    young = next(x for x in races.values() if x.age == "2yo" and x.cls == "999" and par.level_of(x) is not None)
    assert par.fitted(young) == pytest.approx(par.base(young) - 1.2 + 1.5, abs=0.05)   # 年齢の区分も期待勝ち時計に入る
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
            r.runs[0].sec_per_km += 1.0                       # clip の内側のずれ: 除かなければ係数が変わる
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
            rows.append({"race_id": f"r{k}", "year": 2023, "won": int(i == w), "p_market": float(pm[i]),
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


# --- 2026-10-05 レビュー (74cf5ff の 4 名) の指摘の反映 -----------------------------------------------------

def test_estimation_refuses_the_primary_year():
    races, *_ = _synthetic_world()
    with pytest.raises(g.GroupAError, match="主検定の年"):
        g.fit_par_model(races, (2024, 2025))
    par = g.fit_par_model(races, (2023,))
    with pytest.raises(g.GroupAError, match="主検定の年"):
        g.fit_weight_effect(races, par, {}, (2025,))
    with pytest.raises(g.GroupAError, match="主検定の年"):
        g.fit_scale(races, par, {}, 0.0, (2025,))
    rows = _clogit_world()
    for r in rows:
        r["year"] = 2025
    g.add_market_logit(rows)
    with pytest.raises(g.GroupAError, match="主検定の年"):
        g.fit_composite(rows)


def test_all_reverse_sign_components_stop_instead_of_a_constant_s():
    rng = np.random.default_rng(9)
    rows = []
    for k in range(400):                             # 4 成分とも独立で、どれも勝ちと逆向き
        m = rng.normal(size=8)
        cs = rng.normal(size=(4, 8))
        u = m - 0.5 * cs.sum(axis=0)
        w = rng.choice(8, p=np.exp(u) / np.exp(u).sum())
        pm = np.exp(m) / np.exp(m).sum()
        for i in range(8):
            rows.append({"race_id": f"r{k}", "year": 2023, "won": int(i == w), "p_market": float(pm[i]),
                         **{c: float(cs[j, i]) for j, c in enumerate(g.COMPONENTS)}})
    g.add_market_logit(rows)
    with pytest.raises(g.GroupAError, match="全成分が逆符号"):
        g.fit_composite(rows)


def test_standardizer_stops_on_zero_sd():
    with pytest.raises(g.GroupAError, match="標準化できない"):
        g.standardizer([{"x": 1.0}, {"x": 1.0}, {"x": math.nan}], ["x"])


def test_invalid_w1_is_wired_to_zero_in_fit_tables():
    races, _ = _weight_world(-0.05)
    t = g.fit_tables(races, g.Spec("S1", "V0", "W1"), (2023,))
    assert t.weight_fit["valid"] is False and t.w == 0.0
    races, _ = _weight_world(0.05)
    t = g.fit_tables(races, g.Spec("S1", "V0", "W1"), (2023,))
    assert t.weight_fit["valid"] is True and t.w == pytest.approx(0.05, abs=1e-3)


def test_run_without_a_scale_band_is_counted_and_unrated():
    par = g.ParModel((2023,), {("05", "11", 1600): ("05", "11", 1600)}, {"intercept": 60.0}, [], {})
    r = _race("a", "20230105")
    _run(r, "h", 1, 59.0)
    out, st = g.rate_runs({"a": r}, _tables(par, scales={("D", 1): 0.5}))
    assert "h" not in out and st["unrated_no_scale"] == 1


def test_frozen_tables_reproduce_ratings_and_s_exactly():
    import json
    races, *_ = _synthetic_world()
    for spec in (g.Spec("S1", "V1", "W0"), g.Spec("S2", "V2", "W0")):
        t = g.fit_tables(races, spec, (2023,))
        comp_rows = _clogit_world(seed=5)
        g.add_market_logit(comp_rows)
        comp = g.fit_composite(comp_rows)
        payload = json.loads(json.dumps(g.freeze_payload(t, comp)))
        t2, comp2 = g.tables_from_payload(payload, races)
        assert g.rate_runs(races, t)[0] == g.rate_runs(races, t2)[0]
        a, b = _clogit_world(seed=6), _clogit_world(seed=6)
        for rows in (a, b):
            g.add_market_logit(rows)
        g.apply_composite(a, comp)
        g.apply_composite(b, comp2)
        assert [r["S"] for r in a] == [r["S"] for r in b]


def _fixture_db(tmp_path, extra_race=None):
    import sqlite3
    path = tmp_path / "f.db"
    con = sqlite3.connect(path)
    con.execute("""CREATE TABLE races (race_year, race_month_day, track_code, kaiji, nichiji, race_num, data_div,
                   track_type_code, distance, turf_condition, dirt_condition, weight_type_code)""")
    con.execute("""CREATE TABLE horse_races (race_year, race_month_day, track_code, kaiji, nichiji, race_num, horse_num,
                   blood_register_num, abnormal_code, confirmed_order, finish_time, burden_weight, win_odds)""")
    rows = [("2023", "0105", "05", "01", "01", "01", "7", "11", 1600, "1", "0", "3"),
            ("2023", "0105", "05", "01", "01", "02", "7", "52", 3000, "1", "0", "3"),      # 障害
            ("2023", "0105", "05", "01", "01", "03", "9", "24", 1400, "0", "1", "3")]      # 中止
    if extra_race:
        rows.append(extra_race)
    con.executemany("INSERT INTO races VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    con.executemany("INSERT INTO horse_races VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", [
        ("2023", "0105", "05", "01", "01", "01", "01", "H1", "0", 1, 1341, 550, 32),
        ("2023", "0105", "05", "01", "01", "01", "02", "H2", "1", 0, 0, 550, 0),
        ("2023", "0105", "05", "01", "01", "01", "00", "H3", "0", 2, 1350, 550, 50),      # 仮の馬番 00 は読まない
        ("2023", "0105", "05", "01", "01", "02", "01", "H4", "0", 1, 3300, 600, 20),
        ("2023", "0105", "05", "01", "01", "03", "01", "H5", "0", 1, 1300, 550, 20),
        ("2023", "0105", "05", "01", "01", "04", "01", "H6", "0", 1, 1300, 550, 20)])
    con.commit()
    con.close()
    return path


def test_load_races_sql_decoding_and_read_only(tmp_path, monkeypatch):
    import sqlite3
    path = _fixture_db(tmp_path)
    seen = []
    real = sqlite3.connect

    def spy(database, *a, **k):
        seen.append(database)
        return real(database, *a, **k)

    monkeypatch.setattr(g.sqlite3, "connect", spy)
    classes = {"20230105_05_01_01_01": ("005", "3up"), "20230105_05_01_01_02": ("703", "3up")}
    races, st = g.load_races(2023, min_year=2023, db_path=path, class_table=classes)
    assert all("mode=ro" in u for u in seen)
    assert list(races) == ["20230105_05_01_01_01"]                  # 障害・中止・仮の馬番は読まない
    runs = races["20230105_05_01_01_01"].runs
    assert [(x.horse, x.abnormal, x.finish) for x in runs] == [("H1", "0", 1), ("H2", "1", 0)]
    assert runs[0].sec_per_km == pytest.approx(94.1 / 1.6) and runs[0].burden_kg == 55.0 and runs[0].win_odds == 3.2
    assert math.isnan(runs[1].sec_per_km) and st["skip_obstacle_rows"] == 1


def test_load_races_stops_on_unknown_flat_track_type_and_missing_class(tmp_path):
    path = _fixture_db(tmp_path, ("2023", "0105", "05", "01", "01", "04", "7", "30", 1600, "1", "0", "3"))
    classes = {"20230105_05_01_01_01": ("005", "3up"), "20230105_05_01_01_04": ("005", "3up")}
    with pytest.raises(g.GroupAError, match="未知の track_type_code"):
        g.load_races(2023, min_year=2023, db_path=path, class_table=classes)
    (tmp_path / "b").mkdir()
    path2 = _fixture_db(tmp_path / "b")
    with pytest.raises(g.GroupAError, match="クラスの表に無い"):
        g.load_races(2023, min_year=2023, db_path=path2, class_table={})


def test_provenance_records_dirty_and_dependencies(tmp_path):
    p = g.provenance(tmp_path / "none.db", ["x"])
    assert p["git_sha"] and isinstance(p["git_dirty"], (bool, type(None)))
    assert "scripts/group_a.py" in p["files_sha256"] and p["argv"] == ["x"] and p["db"]["bytes"] is None


# --- 2026-10-05 事前登録 §8-4b-3 (P3 の座標の改訂 B) ------------------------------------------------------

def _b_par():
    return g.ParModel((2023,), {("05", "11", 1600): ("05", "11", 1600)},
                      {"intercept": 60.0, "class=703": 2.0, "class=999": -1.5, "age=2yo": 0.5}, [], {})


def test_p3_clips_relative_to_the_class_and_age_expectation_and_keeps_the_class_level():
    par = _b_par()
    low = _race("low", "20230105", cls="703")
    ref = _race("ref", "20230106", cls="005")
    top = _race("top", "20230107", cls="999")
    young = _race("yng", "20230108", cls="703", age="2yo")
    _run(low, "a", 1, 64.0)       # 残差 +4.0、c = +2.0 → 期待からは +2.0 (切らない) → 評価値 −4.0
    _run(ref, "b", 1, 64.0)       # 残差 +4.0、c = 0 → +4.0 を +3.0 に切る → 評価値 −3.0
    _run(top, "c", 1, 55.0)       # 残差 −5.0、c = −1.5 → −3.5 を −3.0 に切って c を戻す → −4.5 → 評価値 +4.5
    _run(young, "d", 1, 66.0)     # 残差 +6.0、c + d = +2.5 → +3.5 を +3.0 に → +5.5 → 評価値 −5.5
    out, st = g.rate_runs({x.race_id: x for x in (low, ref, top, young)}, _tables(par))
    assert out["a"][0][1] == pytest.approx(-4.0) and out["b"][0][1] == pytest.approx(-3.0)
    assert out["c"][0][1] == pytest.approx(4.5) and out["d"][0][1] == pytest.approx(-5.5)
    assert st["clipped_slow"] == 2 and st["clipped_fast"] == 1
    assert st["group|2023|703|3up|rated"] == 1 and "group|2023|703|3up|clipped_slow" not in st
    assert st["group|2023|005|3up|clipped_slow"] == 1 and st["group|2023|999|3up|clipped_fast"] == 1


def test_p3_without_a_nuisance_value_leaves_the_run_unrated():
    par = _b_par()
    r = _race("u", "20230105", cls="703", age=None)
    _run(r, "a", 1, 61.0)
    out, st = g.rate_runs({"u": r}, _tables(par))
    assert "a" not in out and st["unrated_no_nuisance"] == 1


def test_weight_outlier_filter_uses_the_same_coordinate_as_p3():
    races, par = _weight_world(0.05)
    par.coef["class=703"] = 2.5
    for r in races.values():                      # 全レースを 703 にし、時計を +2.5 遅くする (期待からは同じ)
        r.cls = "703"
        r.runs[0].sec_per_km += 2.5
    fit = g.fit_weight_effect(races, par, {}, (2023,))
    assert fit["w"] == pytest.approx(0.05, abs=1e-6) and fit["n_runs"] == 120   # 残差 +2.5〜+2.7 でも除外されない


def test_reading_the_primary_year_needs_a_recorded_purpose(tmp_path):
    with pytest.raises(g.GroupAError, match="primary_purpose"):
        g.load_races(2025, db_path="does-not-exist.db", allow_primary_year=True)



# --- 2026-10-05 限定再レビュー (c9688b5 の 4 名) の指摘の反映 -----------------------------------------------

def _frozen(spec=g.Spec("S1", "V1", "W0")):
    import json
    races, *_ = _synthetic_world()
    t = g.fit_tables(races, spec, (2023,))
    rows = _clogit_world(seed=5)
    g.add_market_logit(rows)
    comp = g.fit_composite(rows)
    return races, json.loads(json.dumps(g.freeze_payload(t, comp)))


def test_frozen_payload_version_and_constants_are_checked(monkeypatch):
    races, payload = _frozen()
    bad = {**payload, "payload_version": "old"}
    with pytest.raises(g.GroupAError, match="版が違う"):
        g.tables_from_payload(bad, races)
    monkeypatch.setattr(g, "CLIP_SEC_PER_KM", 2.5)          # 凍結の後に定数を変えたら読み込みで止まる
    with pytest.raises(g.GroupAError, match="定数"):
        g.tables_from_payload(payload, races)


def test_frozen_payload_spec_name_is_validated():
    races, payload = _frozen()
    with pytest.raises(g.GroupAError, match="候補の名前"):
        g.tables_from_payload({**payload, "spec": "S3V1W0"}, races)


def test_composite_without_year_stops():
    rows = _clogit_world(seed=7)
    for r in rows:
        del r["year"]
    g.add_market_logit(rows)
    with pytest.raises(g.GroupAError, match="year が無い"):
        g.fit_composite(rows)


def test_unsorted_history_stops():
    t = g.day_ordinal("20240601")
    with pytest.raises(g.GroupAError, match="日付順"):
        g.horse_components([(t - 10, 1.0), (t - 100, 2.0)], t)


def test_unknown_class_or_age_level_is_not_treated_as_the_reference():
    par = g.ParModel((2023,), {("05", "11", 1600): ("05", "11", 1600)}, {"intercept": 60.0, "class=703": 1.0}, [], {})
    ok = _race("ok", "20230105", cls="703")
    new_cls = _race("nc", "20230105", cls="016")            # 推定期間に無かったクラス
    new_age = _race("na", "20230105", cls="005", age="2yo")  # 推定期間に無かった年齢の区分
    assert par.fitted(ok) == pytest.approx(61.0)
    assert math.isnan(par.fitted(new_cls)) and math.isnan(par.fitted(new_age))


def test_provenance_stops_on_a_missing_dependency(monkeypatch, tmp_path):
    monkeypatch.setattr(g, "DEPENDENCIES", g.DEPENDENCIES + ("scripts/does_not_exist.py",))
    with pytest.raises(g.GroupAError, match="依存ファイルが無い"):
        g.provenance(tmp_path / "x.db")
