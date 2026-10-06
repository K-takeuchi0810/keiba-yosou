"""Phase 0.5-5 Group D の計算の契約 (`scripts/group_d.py`、事前登録 §8-4d、台帳 D-0〜D-3)。

外部の指示者の必須の確認項目: 今回のクラスの要求水準を引いた量は、条件付きロジットでは前走の評価値と同じ係数になる (レース内で定数を引くだけ)。
"""
from __future__ import annotations

import math
import random
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from predictor import race_market as rm
from scripts import c_prime as cp
from scripts import group_a as ga
from scripts import group_d as gd
from scripts import prereg_runner as pr

ROOT = Path(__file__).resolve().parents[1]


def _race(rid, ymd, cls, surface="D", runs=()):
    r = ga.Race(race_id=rid, ymd=ymd, track="05", track_type="24" if surface == "D" else "11", surface=surface, distance=1600,
                going=f"{surface}1", weight_type="2", cls=cls, age="3up", runs=[])
    for hn, horse, fin, odds, abn in runs:
        r.runs.append(ga.Run(rid, ymd, ga.day_ordinal(ymd), horse, hn, abn, fin, math.nan, 55.0, odds))
    return r


# --- 前走・要求水準の PIT -------------------------------------------------------------------------

def test_previous_run_uses_only_days_before_the_target_within_365():
    t = 1000
    h = [(t - 366, "r0", 1.0), (t - 365, "r1", 2.0), (t - 10, "r2", 3.0), (t, "rT", 9.0)]
    assert gd.previous_run(h, t) == (t - 10, "r2", 3.0)                 # 同じ日 (rT) は使わない
    assert gd.previous_run(h[:2], t) == (t - 365, "r1", 2.0)            # 365 日前ちょうどは窓の内
    assert gd.previous_run(h[:1], t) is None                            # 366 日前は窓の外
    assert gd.previous_run([], t) is None


def _req_world(n_races=25, day0="20230101", cls="005", surface="D", winner=lambda i: float(i)):
    races = {}
    hist = {}
    d0 = ga.day_ordinal(day0)
    from datetime import date
    for i in range(n_races):
        ymd = date.fromordinal(d0 + i).strftime("%Y%m%d")
        rid = f"R{i:03d}"
        races[rid] = _race(rid, ymd, cls, surface, [("01", f"W{i}", 1, 2.0, "0"), ("02", f"L{i}", 2, 3.0, "0")])
        hist.setdefault(f"W{i}", []).append((d0 + i, rid, winner(i)))
        hist.setdefault(f"L{i}", []).append((d0 + i, rid, -5.0))
    return races, hist, d0


def test_requirement_is_the_median_winner_rating_of_the_window_before_the_day_and_needs_20_races():
    races, hist, d0 = _req_world(n_races=25)
    req = gd.Requirements(races, gd.winner_ratings(races, hist))
    # 日 d0+21: 窓は d0..d0+20 の 21 レース (同じ日の R021 は含まない) → 勝ち馬の評価値 0..20 の中央値 10
    assert req("005", "D", d0 + 21) == 10.0
    assert math.isnan(req("005", "D", d0 + 19))                         # 19 レースしかない → 欠損 (別の水準に寄せない)
    assert req("005", "D", d0 + 20) == pytest.approx(9.5)               # 20 レース (0..19)
    assert math.isnan(req("005", "T", d0 + 21)) and math.isnan(req("010", "D", d0 + 21))
    assert math.isnan(req(None, "D", d0 + 21))


def test_dead_heat_winners_count_as_one_observation_at_their_median():
    r = _race("RX", "20230301", "005", "D", [("01", "A", 1, 2.0, "0"), ("02", "B", 1, 2.0, "0"), ("03", "C", 3, 5.0, "0")])
    hist = {"A": [(1, "RX", 4.0)], "B": [(1, "RX", 6.0)], "C": [(1, "RX", -1.0)]}
    assert gd.winner_ratings({"RX": r}, hist) == {"RX": 5.0}


def test_level_mapping_puts_newcomer_and_maiden_together():
    assert gd.LEVEL == {"701": 0, "703": 0, "005": 1, "010": 2, "016": 3, "999": 4}


# --- 標本 ---------------------------------------------------------------------------------------

def _target_world():
    """要求水準の材料 25 レース (005・ダート) の後に、前走が 005 の馬と前走の無い馬が出る 010 のレース。"""
    races, hist, d0 = _req_world(n_races=25)
    from datetime import date
    prev_day = d0 + 22
    target_day = d0 + 40
    # 前走: X は R_prev (005・ダート、d0+22) で評価値 15、Y は前走なし、Z は前走 (005) で評価値 8
    races["RP"] = _race("RP", date.fromordinal(prev_day).strftime("%Y%m%d"), "005", "D",
                        [("01", "X", 1, 2.0, "0"), ("02", "Z", 2, 3.0, "0")])
    hist["X"] = [(prev_day, "RP", 15.0)]
    hist["Z"] = [(prev_day, "RP", 8.0)]
    races["RT"] = _race("RT", date.fromordinal(target_day).strftime("%Y%m%d"), "010", "D",
                        [("01", "X", 1, 2.0, "0"), ("02", "Y", 2, 4.0, "0"), ("03", "Z", 3, 4.0, "0"), ("04", "Q", 0, 0.0, "3")])
    return races, hist, prev_day, target_day


def test_target_rows_build_surplus_and_class_move_from_the_same_previous_run():
    races, hist, prev_day, _ = _target_world()
    req = gd.Requirements(races, gd.winner_ratings(races, hist))
    c, ex = Counter(), []
    rows = [r for r in gd.target_rows(races, (2023,), hist, req, c, ex) if r["race_id"] == "RT"]
    assert [r["horse_num"] for r in rows] == ["01", "02", "03"]          # 競走除外の Q は選択集合に入らない
    want_req = float(np.median(range(0, 22)))                           # 前走の日 d0+22 の前日までの 22 レース (0..21) → 10.5
    assert rows[0]["S_raw"] == pytest.approx(15.0 - want_req)
    assert rows[2]["S_raw"] == pytest.approx(8.0 - want_req)
    assert rows[0]["class_move"] == 1.0 and rows[2]["class_move"] == 1.0  # 005 → 010
    assert math.isnan(rows[1]["S_raw"]) and math.isnan(rows[1]["class_move"]) and not rows[1]["has_prev"]
    assert sum(r["p_market"] for r in rows) == pytest.approx(1.0)


def test_race_with_no_observed_runner_is_excluded_and_recorded():
    races, hist, _, _ = _target_world()
    for h in ("X", "Z"):
        hist.pop(h)
    req = gd.Requirements(races, gd.winner_ratings(races, hist))
    c, ex = Counter(), []
    rows = gd.target_rows(races, (2023,), hist, req, c, ex)
    assert not [r for r in rows if r["race_id"] == "RT"]
    assert {"race_id": "RT", "reason": gd.EXCLUDE_ALL_MISSING, "horses": ["01", "02", "03"]} in ex
    assert c[f"excluded:{gd.EXCLUDE_ALL_MISSING}"] >= 1


def test_requirement_missing_makes_both_surplus_and_move_missing():
    races, hist, d0 = _req_world(n_races=10)                            # 10 レースしかない → 要求水準は欠損
    from datetime import date
    races["RT"] = _race("RT", date.fromordinal(d0 + 30).strftime("%Y%m%d"), "010", "D", [("01", "W3", 1, 2.0, "0"), ("02", "N", 2, 3.0, "0")])
    req = gd.Requirements(races, gd.winner_ratings(races, hist))
    c, ex = Counter(), []
    gd.target_rows(races, (2023,), hist, req, c, ex)
    assert c["requirement_missing_rows"] >= 1
    assert any(e["race_id"] == "RT" and e["reason"] == gd.EXCLUDE_ALL_MISSING for e in ex)


def test_standardize_divides_and_fills_both_columns_with_the_race_observed_mean():
    rows = [{"race_id": "A", "S_raw": 2.0, "class_move": 1.0}, {"race_id": "A", "S_raw": 4.0, "class_move": 3.0},
            {"race_id": "A", "S_raw": math.nan, "class_move": math.nan}]
    out = gd.standardize_and_fill(rows, 2.0)
    assert [r["S_std"] for r in out] == [1.0, 2.0, 1.5]
    assert [r["class_move_filled"] for r in out] == [1.0, 3.0, 2.0]          # 欠損はレース内の観測の平均 (0 ではない)
    assert math.isnan(rows[2]["S_raw"]) and "S_std" not in rows[0]         # 入力の行は変えない
    with pytest.raises(gd.GroupDError):
        gd.standardize_and_fill([{"race_id": "B", "S_raw": math.nan, "class_move": math.nan}], 1.0)


def test_unknown_class_stops():
    races, hist, _, _ = _target_world()
    races["RT"].cls = "123"
    with pytest.raises(gd.GroupDError, match="canonical class"):
        gd.target_rows(races, (2023,), hist, gd.Requirements(races, gd.winner_ratings(races, hist)), Counter(), [])


def test_fit_scale_refuses_the_primary_year():
    with pytest.raises(gd.GroupDError, match="2025"):
        gd.fit_scale([{"race_id": "A", "year": 2025, "S_raw": 1.0}, {"race_id": "A", "year": 2025, "S_raw": 2.0}])


# --- 必須の確認項目: 今回のクラスの要求水準を引いた量は前走の評価値と同値 ------------------------------------

def _synthetic_rows(n_races=600, seed=0, beta_prev=0.4):
    rng = random.Random(seed)
    rows = []
    for i in range(n_races):
        k = 8
        raw = [rng.random() + 0.2 for _ in range(k)]
        tot = sum(raw)
        p = [x / tot for x in raw]
        prev = [rng.gauss(0, 1) for _ in range(k)]
        move = [float(rng.choice([-1, 0, 0, 1])) for _ in range(k)]
        req_current = rng.gauss(0, 3)                                  # 今回のクラスの要求水準 (レース内で一定)
        w = [p[j] * math.exp(beta_prev * prev[j]) for j in range(k)]
        u, acc, win = rng.random() * sum(w), 0.0, k - 1
        for j in range(k):
            acc += w[j]
            if u <= acc:
                win = j
                break
        for j in range(k):
            rows.append({"race_id": f"R{i}", "year": 2022, "horse_num": f"{j + 1:02d}", "won": int(j == win), "p_market": p[j],
                         "class_move_filled": move[j], "prev_std": prev[j], "gap_std": prev[j] - req_current})
    return rows


def test_gap_to_current_class_is_identical_to_previous_rating_in_conditional_logit():
    rows = _synthetic_rows()
    g = cp.clogit_with_se(rows, ["class_move_filled", "gap_std"])
    p = cp.clogit_with_se(rows, ["class_move_filled", "prev_std"])
    assert g["beta"] == pytest.approx(p["beta"], abs=1e-9) and g["se"] == pytest.approx(p["se"], abs=1e-9)
    assert cp.within_sd(rows, "gap_std")["sd"] == pytest.approx(cp.within_sd(rows, "prev_std")["sd"], rel=1e-12)


def test_primary_clogit_columns_are_market_move_and_s():
    rows = _synthetic_rows(n_races=300, seed=2)
    for r in rows:
        r["S_std"] = r["prev_std"]
    out = gd.clogit(rows)
    assert out["cols"] == ["market_feature", "class_move_filled", "S_std"]
    assert abs(out["beta"][2] - 0.4) < 0.2


def test_group_d_code_uses_only_market_clogit_for_the_market():
    for path in ("scripts/group_d.py", "scripts/group_d_explore.py"):
        src = (ROOT / path).read_text(encoding="utf-8")
        for bad in ("add_market_logit", "logit_p_market", "group_a_power", "math.log(", "np.log(", "fit_composite(",
                    "apply_composite("):
            assert bad not in src, (path, bad)


# --- 共通の部品 (prereg_runner) ------------------------------------------------------------------

def test_prereg_runner_check_pinned_is_fail_closed():
    base = {"a.py": "1"}
    with pytest.raises(pr.RunError, match="git の状態"):
        pr.check_pinned({"git_dirty": None, "git_status": None, "git_sha": "u", "files_blob_sha1": base}, ("a.py",),
                        ("freeze", {"files_blob_sha1": base}))
    with pytest.raises(pr.RunError, match="固定のファイルが無い"):
        pr.check_pinned({"git_dirty": False, "git_status": [], "git_sha": "s", "files_blob_sha1": {}}, ("a.py",),
                        ("freeze", {"files_blob_sha1": base}))
    with pytest.raises(pr.RunError, match="凍結・検出力の時点と違う"):
        pr.check_pinned({"git_dirty": False, "git_status": [], "git_sha": "s", "files_blob_sha1": {"a.py": "2"}}, ("a.py",),
                        ("freeze", {"files_blob_sha1": base}))
    ok = pr.check_pinned({"git_dirty": False, "git_status": [], "git_sha": "s", "files_blob_sha1": base}, ("a.py",),
                         ("freeze", {"files_blob_sha1": base}))
    assert ok["pinned_blob_sha1"] == base


def test_prereg_runner_fixed_power_and_verdict():
    f = pr.fixed_power(0.02, 0.015, 10000, 2500)                       # 換算 0.03 > 解析 0.02 → 大きい方
    assert f["se_fixed"] == pytest.approx(0.03) and f["status_before_primary"] == "PRIMARY_DECIDABLE"
    g = pr.fixed_power(0.04, None, 10000, 2500)
    assert g["inconclusive_by_power"] and g["status_before_primary"] == "PRIMARY_INCONCLUSIVE"
    assert pr.verdict({"valid": True, "lo": 0.0}, {"inconclusive_by_power": False}) == ("PRIMARY_FAIL", "ci_lower_not_above_zero")
    assert pr.verdict({"valid": False, "lo": math.nan}, {"inconclusive_by_power": True})[1] == "mde_above_beta_target+boot_na"
    assert pr.verdict({"valid": True, "lo": 0.01}, {"inconclusive_by_power": False})[0] == "PRIMARY_PASS"


def test_prereg_runner_provenance_excludes_several_own_outputs(tmp_path):
    import subprocess
    repo = tmp_path / "repo"
    (repo / "out").mkdir(parents=True)
    (repo / "frozen").mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    (repo / "a.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "a.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "a"], check=True)
    (repo / "out" / "r.json").write_text("{}", encoding="utf-8")
    (repo / "frozen" / "STARTED.json").write_text("{}", encoding="utf-8")
    prov = pr.provenance(repo, ("a.txt",), tmp_path / "x.db", own_output=["out", "frozen/STARTED.json"])
    assert prov["git_dirty"] is False and prov["files_blob_sha1"]["a.txt"] == pr.blob_sha(repo / "a.txt")
    (repo / "b.txt").write_text("y", encoding="utf-8")
    assert pr.provenance(repo, ("a.txt",), tmp_path / "x.db", own_output=["out"])["git_dirty"] is True


def test_prereg_runner_write_json_is_atomic_and_nan_free(tmp_path):
    p = tmp_path / "x.json"
    pr.write_json(p, {"a": math.nan, "b": [1.0, math.inf]})
    assert p.read_text(encoding="utf-8").count("null") == 2 and not (tmp_path / "x.json.tmp").exists()


def test_requirement_uses_the_median_not_the_mean():
    races, hist, d0 = _req_world(n_races=25, winner=lambda i: float(i) ** 2)
    req = gd.Requirements(races, gd.winner_ratings(races, hist))
    # 窓は 0..20 の 21 レース、勝ち馬の評価値は i² → 中央値 100 (平均は約 136.7)
    assert req("005", "D", d0 + 21) == 100.0

