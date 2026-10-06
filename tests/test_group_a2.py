"""次の世代の候補 A″ の計算の契約 (`scripts/group_a2.py`、docs/A_DOUBLE_PRIME_PREREG.md)。

- 成分は Group A と同じ 4 つ (365 日・対象日の前日まで)。標準化は pooled within-race SD、欠損はレース内の平均、全欠損のレースは全頭 0
- 選択集合は §8-6 (返還の除外と再正規化、価格の無い馬がいれば除く)
- 合成は [log P_market, 成分] の条件付きロジットで逆符号は 0、推定に 2025 以降を渡すと止まる
- 構造の量・検出力は結果の列を読まない
"""
from __future__ import annotations

import math
import random
from collections import Counter

import numpy as np
import pytest

from predictor import race_market as rm
from scripts import group_a as ga
from scripts import group_a2 as a2


def _race(rid, ymd, runs):
    r = ga.Race(race_id=rid, ymd=ymd, track="05", track_type="24", surface="D", distance=1600, going="D1", weight_type="2",
                cls="005", age="3up", runs=[])
    for hn, horse, fin, odds, abn in runs:
        r.runs.append(ga.Run(rid, ymd, ga.day_ordinal(ymd), horse, hn, abn, fin, math.nan, 55.0, odds))
    return r


def test_components_use_only_days_before_the_target_within_365():
    t = ga.day_ordinal("20240601")
    hist = [(t - 366, 9.0), (t - 365, 1.0), (t - 10, 2.0), (t, 50.0)]
    comp = ga.horse_components(hist, t)
    assert comp["perf_rating_last"] == 2.0 and comp["perf_rating_best3_365"] == 1.5     # 同じ日 (50) と 366 日前 (9) は使わない


def test_last_finish_pct_uses_the_latest_run_before_the_target():
    t = 1000
    h = [(t - 366, 0.9), (t - 30, 0.1), (t - 5, 0.7), (t, 0.99)]
    assert a2.last_finish_pct(h, t) == 0.7
    assert math.isnan(a2.last_finish_pct(h[:1], t))


def test_finish_history_percentile_is_good_high_and_skips_refunds():
    r = _race("R1", "20240105", [("01", "A", 1, 2.0, "0"), ("02", "B", 2, 3.0, "0"), ("03", "C", 3, 9.0, "0"),
                                  ("04", "D", 0, 0.0, "1")])                                   # D は取消 (返還)
    h = a2.finish_history({"R1": r})
    assert h["A"][0][1] == pytest.approx(2.5 / 3) and h["C"][0][1] == pytest.approx(0.5 / 3) and "D" not in h


def _world(n_races=40, seed=1):
    rng = random.Random(seed)
    races, ratings = {}, {}
    for i in range(n_races):
        ymd = f"2023{1 + i % 12:02d}{1 + i % 27:02d}"
        rid = f"{ymd}_05_1_1_{i % 12 + 1:02d}"
        runs = []
        for k in range(8):
            horse = f"H{i}_{k}"
            runs.append((f"{k + 1:02d}", horse, k + 1, round(2 + 3 * rng.random() * (k + 1), 1), "0"))
            ratings[horse] = [(ga.day_ordinal(ymd) - 30, rng.gauss(0, 1)), (ga.day_ordinal(ymd) - 60, rng.gauss(0, 1)),
                              (ga.day_ordinal(ymd) - 90, rng.gauss(0, 1))]
            ratings[horse].sort()
        races[rid] = _race(rid, ymd, runs)
    return races, ratings


def test_target_rows_follow_the_choice_set_and_record_exclusions():
    races, ratings = _world(5)
    rid0 = sorted(races)[0]
    races[rid0].runs[3].win_odds = 0.0                         # 返還でない馬に価格が無い → レースごと除く
    rid1 = sorted(races)[1]
    races[rid1].runs[7].abnormal = "1"                         # 取消 → 選択集合から除き再正規化
    counts, ex = Counter(), []
    rows = a2.target_rows(races, (2023,), ratings, {}, counts, ex)
    assert [e["race_id"] for e in ex] == [rid0] and ex[0]["reason"].startswith("nonrefund_runner_without_price")
    r1 = [r for r in rows if r["race_id"] == rid1]
    assert len(r1) == 7 and sum(r["p_market"] for r in r1) == pytest.approx(1.0)
    assert counts["target_races_used"] == 4 and counts["refunded_runners_excluded"] == 1


def test_missing_components_are_filled_with_the_race_mean_and_all_missing_races_are_zero():
    rows = [{"race_id": "A", "x": 1.0}, {"race_id": "A", "x": 3.0}, {"race_id": "A", "x": math.nan},
            {"race_id": "B", "x": math.nan}, {"race_id": "B", "x": math.nan}]
    from scripts import c_prime as cp
    cp.standardize(rows, "x", 2.0, "x_w")
    assert [r["x_w"] for r in rows] == [0.5, 1.5, 1.0, 0.0, 0.0]


def _fit_rows(seed=3, n=300, effect=(0.0, 0.8, 0.0, 0.0)):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        k = 8
        comps = rng.normal(size=(k, 4))
        p = rng.dirichlet(np.ones(k))
        s_true = comps @ np.array(effect)
        u = np.log(p) + s_true
        w = int(np.argmax(u + rng.gumbel(size=k)))
        for j in range(k):
            rows.append({"race_id": f"R{i}", "year": 2022 + i % 3, "horse_num": f"{j + 1:02d}", "won": int(j == w),
                         "p_market": float(p[j]), **{c: float(comps[j, m]) for m, c in enumerate(ga.COMPONENTS)},
                         "last_finish_pct": float(rng.random())})
        rows[-1]["perf_rating_trend_365"] = math.nan
    return rows


def test_composite_keeps_positive_components_and_zeroes_negative_ones():
    rows = _fit_rows(effect=(-0.8, 0.8, 0.0, 0.0))                     # last は逆向き、best3 は正
    comp = a2.fit_composite(rows)
    assert comp["weights"]["perf_rating_best3_365"] > 0 and "perf_rating_last" in comp["zeroed"]
    out = a2.apply_composite(rows, comp)
    from scripts import c_prime as cp
    assert cp.within_sd(out, "S")["sd"] == pytest.approx(1.0)          # S は pooled within-race SD 1 単位


def test_composite_refuses_estimation_rows_from_2025():
    rows = _fit_rows()
    rows[0]["year"] = 2025
    with pytest.raises(a2.GroupA2Error, match="2025"):
        a2.fit_composite(rows)


def test_all_negative_components_stop():
    rows = _fit_rows(effect=(-0.8, -0.8, -0.8, -0.8), n=600)
    with pytest.raises(a2.GroupA2Error, match="逆符号"):
        a2.fit_composite(rows)


def test_structural_quantities_refuse_outcomes_and_measure_the_finish_restatement():
    rows = _fit_rows()
    comp = a2.fit_composite(rows)
    out = a2.apply_composite(rows, comp)
    with pytest.raises(a2.GroupA2Error, match="勝ち"):
        a2.structural(out)
    blind = a2.rows_without_outcome(out)
    for r in blind:                                                    # S を着順の言い換えにすると決定係数は 1
        r["last_finish_pct"] = r["S"] * 2.0 + 1.0
    st = a2.structural(blind)
    assert st["within_race_r2_S_on_finish_only"]["r2"] == pytest.approx(1.0)
    assert st["within_race_corr_S_last_finish"] == pytest.approx(1.0)


def test_power_reads_no_outcome_and_gives_the_required_races():
    rows = _fit_rows()
    out = a2.apply_composite(rows, a2.fit_composite(rows))
    pw = a2.outcome_blind_power(out, beta_target=math.log(1.25) / 2, critical=3.4174)
    s1 = pw["sigma_per_race"]
    assert pw["n_primary_required"] == math.ceil((3.4174 * s1 / (math.log(1.25) / 2)) ** 2)
    assert pw["fisher"]["se"] == pytest.approx(s1 / math.sqrt(pw["n_races"]))
    flipped = [dict(r, won=1 - r["won"]) for r in out]                 # 勝ち負けを入れ替えても同じ (結果を読まない)
    assert a2.outcome_blind_power(flipped, math.log(1.25) / 2, 3.4174) == pw


def test_loader_is_the_guarded_group_a_loader():
    """A″ の読み込みは研究の窓の関所を通る group_a.load_races (2025 以降は止まる)。"""
    with pytest.raises(Exception, match="2025|reproduces|RESERVED"):
        ga.load_races(2025, min_year=2021, db_path="unused.db")


# --- 候補の門 (台帳 A2-1) ------------------------------------------------------------------------

from scripts import group_a2_explore as ex  # noqa: E402


def test_gate_passes_only_when_all_four_hold():
    ok = dict(construct_r2=0.5, e_betas=[(0.01, 0.5), (0.02, 1.0), (-0.01, -0.3)], pooled_beta=0.01, within_var=0.6, n_calendar=6800)
    assert ex.gate_verdict(**ok) == {"passed": True, "reasons": []}
    assert ex.gate_verdict(**{**ok, "construct_r2": 0.80})["reasons"] == ["STRUCTURAL_REJECT"]
    assert ex.gate_verdict(**{**ok, "within_var": 0.4999})["reasons"] == ["INSUFFICIENT_WITHIN_RACE_VARIATION"]
    assert ex.gate_verdict(**{**ok, "n_calendar": 6801})["reasons"] == ["PRIMARY_INFEASIBLE"]


@pytest.mark.parametrize("betas,pooled", [
    ([(0.01, 0.5), (-0.02, -1.0), (-0.01, -0.3)], 0.01),     # 正が 1 本だけ
    ([(0.01, 0.5), (0.02, 1.0), (-0.05, -2.0)], 0.01),       # z ≤ −2 が 1 本
    ([(0.01, 0.5), (0.02, 1.0), (0.01, 0.3)], 0.0),          # pooled が正でない
    ([(0.01, 0.5), (0.02, 1.0)], 0.01),                      # 3 本そろっていない
])
def test_sign_stability_gate(betas, pooled):
    assert "SIGN_INSTABILITY_REJECT" in ex.gate_verdict(0.5, betas, pooled, 0.6, 100)["reasons"]


def test_money_state_does_not_reject_and_marks_no_buys():
    assert ex.money_state(0, 3000)["state"] == "MONEY_UNTESTABLE_NO_EXPECTED_BUYS"
    assert ex.money_state(300, 3400) == {"state": "MONEY_MATURABLE", "races_for_1500": 17000.0}
    assert ex.money_state(299, 3400)["state"] == "MONEY_UNTESTABLE_WITHIN_5Y"
