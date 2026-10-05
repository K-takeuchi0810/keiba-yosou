"""scripts/group_a_power.py (検出力の固定、2025 の対象レースの結果を読まない経路) のテスト。"""
from __future__ import annotations

import math
import sqlite3
from collections import Counter

import numpy as np
import pytest

from scripts import group_a as g
from scripts import group_a_power as pw


def _db(tmp_path):
    path = tmp_path / "t.db"
    con = sqlite3.connect(path)
    con.execute("""CREATE TABLE races (race_year, race_month_day, track_code, kaiji, nichiji, race_num, data_div,
                   track_type_code, distance)""")
    con.execute("""CREATE TABLE horse_races (race_year, race_month_day, track_code, kaiji, nichiji, race_num, horse_num,
                   blood_register_num, abnormal_code, confirmed_order, finish_time, final_3f, win_odds)""")
    con.executemany("INSERT INTO races VALUES (?,?,?,?,?,?,?,?,?)", [
        ("2025", "0105", "05", "01", "01", "01", "7", "11", 1600),
        ("2025", "0105", "05", "01", "01", "02", "7", "54", 3000),     # 障害
        ("2025", "0105", "05", "01", "01", "03", "9", "11", 1600)])    # 中止
    con.executemany("INSERT INTO horse_races VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", [
        ("2025", "0105", "05", "01", "01", "01", "01", "H1", "0", 1, 1341, 345, 20),
        ("2025", "0105", "05", "01", "01", "01", "02", "H2", "4", 0, 0, 0, 40),      # 競走中止 (結果): 選択集合に残す
        ("2025", "0105", "05", "01", "01", "01", "03", "H3", "1", 0, 0, 0, 0),       # 出走取消 (返還)
        ("2025", "0105", "05", "01", "01", "02", "01", "H4", "0", 1, 3300, 400, 20),
        ("2025", "0105", "05", "01", "01", "03", "01", "H5", "0", 1, 1300, 350, 20)])
    con.commit()
    con.close()
    return path


def test_target_sql_contains_no_outcome_columns(tmp_path, monkeypatch):
    path = _db(tmp_path)
    executed = []
    real = sqlite3.connect

    def spy(database, *a, **k):
        con = real(database, *a, **k)
        con.set_trace_callback(executed.append)
        assert "mode=ro" in database
        return con

    monkeypatch.setattr(pw.sqlite3, "connect", spy)
    targets = pw.load_target_fields(2025, path)
    sql = " ".join(executed).lower()
    assert executed and not [c for c in pw.FORBIDDEN_COLUMNS if c in sql]
    assert list(targets) == ["20250105_05_01_01_01"]                    # 障害と中止は入らない
    runners = targets["20250105_05_01_01_01"]
    assert [(x.horse, x.refunded) for x in runners] == [("H1", False), ("H2", False), ("H3", True)]
    assert not any(hasattr(x, "finish") or hasattr(x, "won") or hasattr(x, "abnormal") for x in runners)


def test_target_sql_guard_rejects_an_outcome_column(monkeypatch):
    monkeypatch.setattr(pw, "TARGET_SELECT", pw.TARGET_SELECT + (("h.confirmed_order", "c"),))
    with pytest.raises(pw.PowerError, match="結果の列"):
        pw.target_sql()
    for expr in ("h.*", "r.lap_times", "r.front3f_time", "h.leg_quality_code", "r.starter_count"):
        monkeypatch.setattr(pw, "TARGET_SELECT", pw.TARGET_SELECT[:12] + ((expr, "x"),))
        with pytest.raises(pw.PowerError):
            pw.target_sql()


def test_outcome_blind_rows_drop_refunds_renormalise_and_have_no_won(tmp_path):
    targets = pw.load_target_fields(2025, _db(tmp_path))
    c = Counter()
    rows = pw.outcome_blind_rows(targets, {}, c)
    assert [r["horse"] for r in rows] == ["H1", "H2"] and all("won" not in r for r in rows)
    assert sum(r["p_market"] for r in rows) == pytest.approx(1.0)
    assert rows[0]["p_market"] == pytest.approx((1 / 2.0) / (1 / 2.0 + 1 / 4.0))
    assert c["refunded_runners"] == 1 and c["runners_in_choice_set"] == 2


def test_fisher_se_refuses_rows_with_outcomes():
    with pytest.raises(pw.PowerError, match="勝ち"):
        pw.fisher_se_at_null([{"race_id": "r", "p_market": 1.0, "S": 0.0, "logit_p_market": 0.0, "won": 1}])


def _null_world(seed, n_races=600, rho=0.5):
    """勝つ確率 = 市場の確率 (β_S = 0, β_market = 1)。S は市場の logit と相関 rho。"""
    rng = np.random.default_rng(seed)
    rows = []
    for k in range(n_races):
        m = rng.normal(size=10)
        pm = np.exp(m) / np.exp(m).sum()
        s = rho * (m - m.mean()) / m.std() + math.sqrt(1 - rho ** 2) * rng.normal(size=10)
        w = rng.choice(10, p=pm)
        for i in range(10):
            rows.append({"race_id": f"r{k}", "won": int(i == w), "p_market": float(pm[i]), "S": float(s[i])})
    g.add_market_logit(rows)
    return rows


def test_fisher_se_matches_the_hessian_se_under_the_null():
    rows = _null_world(1)
    blind = [{k: v for k, v in r.items() if k != "won"} for r in rows]
    fisher = pw.fisher_se_at_null(blind)["se"]
    hess = g.clogit_with_se(rows, ["logit_p_market", "S"])["se"][1]
    assert fisher == pytest.approx(hess, rel=0.1)


def test_market_correlation_inflates_the_se():
    se_lo = pw.fisher_se_at_null([{k: v for k, v in r.items() if k != "won"} for r in _null_world(2, rho=0.0)])["se"]
    se_hi = pw.fisher_se_at_null([{k: v for k, v in r.items() if k != "won"} for r in _null_world(2, rho=0.8)])["se"]
    assert se_hi > se_lo * 1.3


def test_fixed_power_takes_the_larger_se_and_sets_the_category():
    p = pw.fixed_power(se_analytic=0.02, se_train_boot=0.02, n_train_races=10000, n_target_races=2500)
    assert p["se_train_scaled"] == pytest.approx(0.04) and p["se_fixed"] == pytest.approx(0.04)
    assert p["mde"] == pytest.approx(pw.CRITICAL_MULTIPLIER * 0.04) and p["inconclusive_by_power"] is True
    q = pw.fixed_power(se_analytic=0.02, se_train_boot=0.01, n_train_races=10000, n_target_races=10000)
    assert q["se_fixed"] == 0.02 and q["inconclusive_by_power"] is False      # 3.418 × 0.02 = 0.068 < 0.112
    assert pw.CRITICAL_MULTIPLIER == pytest.approx(2.5758 + 0.8416, abs=1e-3)
    assert pw.BETA_TARGET == pytest.approx(0.1116, abs=1e-4)


def test_purchase_count_uses_s_at_least_two():
    rows = [{"S": v} for v in (1.99, 2.0, 2.5, -3.0)]
    out = pw.purchase_count_at_target(rows)
    assert out["threshold_S"] == pytest.approx(2.0) and out["n_horses"] == 2


def test_power_module_never_estimates_beta(monkeypatch):
    """この module は β を推定しない (条件付きロジットを呼ばない)。"""
    import inspect
    src = inspect.getsource(pw)
    assert "conditional_logit" not in src.replace("条件付きロジット", "") and "clogit_with_se" not in src


def test_fisher_information_uses_the_market_probabilities_exactly():
    """1 レース 3 頭、p = (0.6, 0.3, 0.1)、S = (1, 0, 0): 市場の確率で重み付けた S の分散 = 0.6 − 0.6² = 0.24。"""
    ps = (0.6, 0.3, 0.1)
    rows = [{"race_id": "r", "p_market": p, "S": s, "logit_p_market": math.log(p / (1 - p))}
            for p, s in zip(ps, (1.0, 0.0, 0.0))]
    out = pw.fisher_se_at_null(rows + [{**r, "race_id": "q", "S": 1.0 - r["S"]} for r in rows])
    assert out["info"][1][1] == pytest.approx(0.24 + (0.4 - 0.4 ** 2))      # 2 レース目は S = (0, 1, 1)



def test_returned_columns_must_match_the_allow_list_exactly(tmp_path, monkeypatch):
    path = _db(tmp_path)
    assert pw.TARGET_COLUMNS == ("race_year", "race_month_day", "track_code", "kaiji", "nichiji", "race_num",
                                 "track_type_code", "distance", "horse_num", "blood_register_num", "is_refunded", "win_odds")
    # 文字列の検査を通り抜けた SQL (余分な列を 1 つ返す) を差し込んでも、返る列の完全一致で止まる
    leaky = ("SELECT h.race_year, h.race_month_day, h.track_code, h.kaiji, h.nichiji, h.race_num, r.track_type_code, "
             "r.distance, h.horse_num, h.blood_register_num, 0, h.win_odds, h.abnormal_code FROM horse_races h JOIN races r "
             "USING (race_year, race_month_day, track_code, kaiji, nichiji, race_num) WHERE h.race_year = ?")
    monkeypatch.setattr(pw, "target_sql", lambda: leaky)
    with pytest.raises(pw.PowerError, match="allow-list と違う"):
        pw.load_target_fields(2025, path)


def test_outcome_blind_rows_do_not_change_when_target_results_change(tmp_path):
    """植え込み試験: 対象レースの着順・時計・上がり・中止の異常コードを書き換えても、検出力の行は 1 ビットも変わらない。"""
    import json
    path = _db(tmp_path)
    before = json.dumps(pw.outcome_blind_rows(pw.load_target_fields(2025, path), {}, Counter()), sort_keys=True)
    con = sqlite3.connect(path)
    con.execute("UPDATE horse_races SET confirmed_order = 9, finish_time = 9999, final_3f = 999 WHERE race_year = '2025'")
    con.execute("UPDATE horse_races SET abnormal_code = '5' WHERE abnormal_code = '4'")      # 中止 → 失格 (どちらも返還でない)
    con.commit()
    con.close()
    after = json.dumps(pw.outcome_blind_rows(pw.load_target_fields(2025, path), {}, Counter()), sort_keys=True)
    assert before == after


def test_fisher_reports_the_within_race_correlation():
    lo = pw.fisher_se_at_null([{k: v for k, v in r.items() if k != "won"} for r in _null_world(3, rho=0.0)])
    hi = pw.fisher_se_at_null([{k: v for k, v in r.items() if k != "won"} for r in _null_world(3, rho=0.8)])
    assert abs(lo["rho_within_race_market_weighted"]) < 0.15 < 0.5 < hi["rho_within_race_market_weighted"]
