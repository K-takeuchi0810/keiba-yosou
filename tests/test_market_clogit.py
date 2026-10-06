"""C′ 以降の市場の列・尤度・Fisher 情報・購入の件数の見込みの契約 (事前登録 0.5-5 §8-6b、外部の指示者 2026-10-06 の最終ゲート)。

- 市場の変換は `race_market.market_feature` (log) の 1 つだけ。0 以下・1 超・NaN・非有限は止める (epsilon で丸めない)
- 恒等性: β_market = 1・β_S = 0 で P_new == P_market
- 尤度・Fisher・P_new・購入の件数がすべて同じ関数を通る (差し替えて呼ばれた回数を数える)
- レース内で P_market を定数倍しても (log では定数の足し算) 結果が変わらない
"""
from __future__ import annotations

import math
import random

import numpy as np
import pytest

from predictor import market_clogit as mc
from predictor import race_market as rm


def _races(n_races=40, k=8, seed=0, beta_market=1.0, beta_s=0.0, with_won=True):
    """log の市場の項のモデルから勝ち馬を引いた人工のレース。"""
    rng = random.Random(seed)
    rows = []
    for i in range(n_races):
        raw = [rng.random() ** 2 + 0.02 for _ in range(k)]
        tot = sum(raw)
        p = {f"{j + 1:02d}": x / tot for j, x in enumerate(raw)}
        s = {h: rng.gauss(0.0, 1.0) for h in p}
        pn = rm.p_new(p, s, beta_market, beta_s)
        u = rng.random()
        acc, winner = 0.0, None
        for h, q in pn.items():
            acc += q
            if winner is None and u <= acc:
                winner = h
        winner = winner or list(pn)[-1]
        for h in p:
            r = {"race_id": f"R{i:04d}", "horse_num": h, "p_market": p[h], "S": s[h]}
            if with_won:
                r["won"] = int(h == winner)
            rows.append(r)
    return rows


# --- market_feature ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [0.0, -0.1, 1.0000001, float("nan"), float("inf"), None, "0.5", True])
def test_market_feature_fails_closed_without_epsilon(bad):
    with pytest.raises(rm.MarketFeatureError):
        rm.market_feature(bad)


def test_market_feature_is_log():
    assert rm.market_feature(1.0) == 0.0
    assert rm.market_feature(0.125) == math.log(0.125)
    assert rm.market_feature(1e-300) == math.log(1e-300)     # 小さくても丸めない


def test_non_canonical_market_probabilities_are_refused():
    rows = [{"race_id": "A", "horse_num": "01", "p_market": 0.5, "S": 0.0},
            {"race_id": "A", "horse_num": "02", "p_market": 0.4, "S": 0.0}]
    with pytest.raises(mc.MarketClogitError, match="和が 1 でない"):
        mc.add_market_feature(rows)
    with pytest.raises(mc.MarketClogitError):
        mc.fisher_se_at_null(rows)
    with pytest.raises(mc.MarketClogitError):
        mc.ratio_buys_at(rows, 1.0, 0.1)


def test_a_zero_market_probability_stops_the_fit():
    rows = [{"race_id": "A", "horse_num": "01", "p_market": 1.0, "S": 0.0, "won": 1},
            {"race_id": "A", "horse_num": "02", "p_market": 0.0, "S": 0.0, "won": 0}]
    with pytest.raises(rm.MarketFeatureError):
        mc.fit_clogit(rows)


# --- 恒等性 ------------------------------------------------------------------------------------

def test_identity_p_new_equals_market_at_unit_market_and_zero_feature():
    for rs in mc._by_race(_races(n_races=20, seed=4, with_won=False)).values():
        p = {r["horse_num"]: r["p_market"] for r in rs}
        s = {r["horse_num"]: r["S"] for r in rs}
        assert rm.p_new(p, s, 1.0, 0.0) == pytest.approx(p, abs=1e-15)
    assert mc.ratio_buys_at(_races(n_races=20, seed=4, with_won=False), 1.0, 0.0) == []


def test_fit_recovers_unit_market_coefficient_under_the_log_model():
    """市場どおりに勝つ世界 (log のモデルで β_market = 1・β_S = 0) では、β̂_market ≈ 1・β̂_S ≈ 0。logit の列なら 1 を割る。"""
    rows = _races(n_races=4000, k=8, seed=11)
    fit = mc.fit_clogit(rows)
    assert fit["converged"] and fit["columns"] == ["market_feature", "S"]
    assert abs(fit["beta_market"] - 1.0) < 0.06 and abs(fit["beta_s"]) < 0.06


def test_fit_recovers_a_planted_feature_effect():
    rows = _races(n_races=4000, k=8, seed=12, beta_market=1.0, beta_s=0.3)
    fit = mc.fit_clogit(rows)
    assert abs(fit["beta_s"] - 0.3) < 0.07 and abs(fit["beta_market"] - 1.0) < 0.08


# --- Fisher 情報 (結果を読まない) ------------------------------------------------------------------

def test_fisher_uses_market_weights_and_log_market_column():
    rows = _races(n_races=30, seed=5, with_won=False)
    got = mc.fisher_se_at_null(rows)
    info = np.zeros((2, 2))
    for rs in mc._by_race(rows).values():
        p = np.array([r["p_market"] for r in rs])
        X = np.array([[math.log(r["p_market"]), r["S"]] for r in rs])
        m = p @ X
        info += (X * p[:, None]).T @ X - np.outer(m, m)
    assert np.allclose(got["info"], info, rtol=1e-12, atol=1e-12)
    assert got["se"] == pytest.approx(math.sqrt(np.linalg.inv(info)[1, 1]), rel=1e-12)
    assert got["n_races"] == 30


def test_fisher_refuses_rows_with_outcomes():
    with pytest.raises(mc.MarketClogitError, match="勝ちの列"):
        mc.fisher_se_at_null(_races(n_races=3, seed=1, with_won=True))


# --- 全経路が同じ変換を通る ------------------------------------------------------------------------

def test_likelihood_fisher_p_new_and_purchase_count_all_go_through_market_feature(monkeypatch):
    calls = {"n": 0}
    real = rm.market_feature

    def counting(p):
        calls["n"] += 1
        return real(p)

    monkeypatch.setattr(rm, "market_feature", counting)
    rows = _races(n_races=50, seed=7)
    n_rows = len(rows)
    for name, fn in (("fit_clogit", lambda: mc.fit_clogit([dict(r) for r in rows])),
                     ("fisher", lambda: mc.fisher_se_at_null([{k: v for k, v in r.items() if k != "won"} for r in rows])),
                     ("ratio_buys_at", lambda: mc.ratio_buys_at(rows, 1.0, 0.2))):
        before = calls["n"]
        fn()
        assert calls["n"] - before >= n_rows, name


def test_a_different_market_transform_changes_every_path(monkeypatch):
    """変換を logit に差し替えると、尤度・Fisher・購入の件数がすべて変わる (= どれも自前の変換を持っていない)。"""
    rows = _races(n_races=300, seed=9, beta_s=0.4)
    no_won = [{k: v for k, v in r.items() if k != "won"} for r in rows]
    base = (mc.fit_clogit([dict(r) for r in rows])["beta_market"], mc.fisher_se_at_null(no_won)["se"],
            len(mc.ratio_buys_at(rows, 0.9, 0.4)))
    monkeypatch.setattr(rm, "market_feature", lambda p: math.log(p / (1 - p)))
    alt = (mc.fit_clogit([dict(r) for r in rows])["beta_market"], mc.fisher_se_at_null(no_won)["se"],
           len(mc.ratio_buys_at(rows, 0.9, 0.4)))
    assert all(a != pytest.approx(b, rel=1e-6) for a, b in zip(base, alt))


# --- レース内の定数倍に対する不変性 ---------------------------------------------------------------

def test_results_are_invariant_to_scaling_market_probabilities_within_a_race(monkeypatch):
    """P_market を定数倍して正規化し直しても、log の列に定数を足しても、β・SE・P_new・購入の件数は変わらない。"""
    rows = _races(n_races=300, seed=13, beta_s=0.3)
    no_won = [{k: v for k, v in r.items() if k != "won"} for r in rows]
    fit = mc.fit_clogit([dict(r) for r in rows])
    se = mc.fisher_se_at_null(no_won)["se"]
    buys = mc.ratio_buys_at(rows, fit["beta_market"], fit["beta_s"])

    # (1) 定数倍して正規化し直す
    scaled = []
    for rs in mc._by_race(rows).values():
        c = 3.7
        tot = sum(c * r["p_market"] for r in rs)
        scaled.extend({**r, "p_market": c * r["p_market"] / tot} for r in rs)
    f2 = mc.fit_clogit([dict(r) for r in scaled])
    assert f2["beta_market"] == pytest.approx(fit["beta_market"], rel=1e-9)
    assert f2["beta_s"] == pytest.approx(fit["beta_s"], rel=1e-9)

    # (2) log の列に定数を足す (= レース内で P_market を定数倍した log) — 正規化前の定数倍そのものの効果
    real = rm.market_feature
    monkeypatch.setattr(rm, "market_feature", lambda p: real(p) + math.log(3.7))
    f3 = mc.fit_clogit([dict(r) for r in rows])
    assert f3["beta_market"] == pytest.approx(fit["beta_market"], rel=1e-9)
    assert f3["beta_s"] == pytest.approx(fit["beta_s"], rel=1e-9)
    assert mc.fisher_se_at_null(no_won)["se"] == pytest.approx(se, rel=1e-9)
    assert mc.ratio_buys_at(rows, fit["beta_market"], fit["beta_s"]) == buys


# --- 購入の件数の見込みと診断の 3 集合 -----------------------------------------------------------

def test_ratio_is_taken_against_the_race_normalised_p_new_not_exp_beta_s():
    """全頭の S が高いレースでは exp(β·S) ≥ 1.25 でも、正規化した P_new の比は 1.25 に届かない。"""
    rows = [{"race_id": "A", "horse_num": h, "p_market": 0.25, "S": 3.0} for h in ("01", "02", "03", "04")]
    assert math.exp(0.1116 * 3.0) > 1.25                              # 単純な exp(βS) の目安は 1.40
    assert mc.ratio_buys_at(rows, 1.0, 0.1116) == []
    rows[0]["S"] = 5.0
    rows[1]["S"] = rows[2]["S"] = rows[3]["S"] = 0.0
    pn = rm.p_new({r["horse_num"]: r["p_market"] for r in rows}, {r["horse_num"]: r["S"] for r in rows}, 1.0, 0.1116)
    assert pn["01"] / 0.25 >= 1.25
    assert mc.ratio_buys_at(rows, 1.0, 0.1116) == [("A", "01")]


def test_diagnostic_sets_separate_market_recalibration_from_s_correction():
    # 本命 (0.7) と人気薄 3 頭 (0.1)。S は 04 だけ高い
    rows = [{"race_id": "A", "horse_num": "01", "p_market": 0.7, "S": 0.0}] + \
           [{"race_id": "A", "horse_num": h, "p_market": 0.1, "S": 0.0} for h in ("02", "03")] + \
           [{"race_id": "A", "horse_num": "04", "p_market": 0.1, "S": 4.0}]
    d = mc.diagnostic_sets(rows, beta_market_hat=0.6, beta_s_hat=0.2)
    # 市場の再校正 (β_m < 1) は人気薄 3 頭を押し上げる / S の補正だけなら 04 だけ
    assert d["n"]["market_recalibration_only"] == 3 and d["n"]["s_correction_only"] == 1
    assert d["jaccard"]["market_recalibration_only|s_correction_only"] == pytest.approx(1 / 3)
    assert d["coefficients"]["s_correction_only"] == [1.0, 0.2]
    assert d["coefficients"]["market_recalibration_only"] == [0.6, 0.0]


def test_fisher_takes_both_the_column_and_the_null_weights_from_market_feature(monkeypatch):
    """変換を差し替えたとき、Fisher の列 (x) と仮定の重み (P_new(1, 0)) の両方が差し替えた変換で作られる。

    列だけ自前の log を持つ実装や、重みに P_market をそのまま使う実装は、log のときは区別できない (恒等) ので、ここで分ける。
    """
    rows = _races(n_races=25, seed=21, with_won=False)
    logit = lambda p: math.log(p / (1 - p))                         # noqa: E731
    monkeypatch.setattr(rm, "market_feature", logit)
    got = mc.fisher_se_at_null(rows)
    info = np.zeros((2, 2))
    for rs in mc._by_race(rows).values():
        z = np.array([logit(r["p_market"]) for r in rs])
        w = np.exp(z - z.max())
        w /= w.sum()
        X = np.column_stack([z, [r["S"] for r in rs]])
        m = w @ X
        info += (X * w[:, None]).T @ X - np.outer(m, m)
    assert np.allclose(got["info"], info, rtol=1e-12, atol=1e-12)
