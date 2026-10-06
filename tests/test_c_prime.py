"""Phase 0.5-5 Group C′ の計算の契約 (`scripts/c_prime.py`、事前登録 §8-4c / §8-4c-2、台帳 C′-0)。

最重要: **対象レース自身の `leg_quality_code` がどの経路からも混入しない** (レース後に確定する値)。対象レースの値を極端な値に
変えても全成分が変わらないことを行動テストで固定する。同じ日の他のレースも履歴に入れない (PIT)。
"""
from __future__ import annotations

import math
import random
import sqlite3
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

from predictor import race_market as rm
from scripts import c_prime as cp

ROOT = Path(__file__).resolve().parents[1]


# --- 一時 DB --------------------------------------------------------------------------------------

def _make_db(path: Path, races: list[dict]) -> Path:
    """races: [{"ymd", "track", "rn", "tt", "data_div", "runs": [(horse_num, horse, abnormal, finish, odds, leg)]}]"""
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE races (race_year TEXT, race_month_day TEXT, track_code TEXT, kaiji TEXT, nichiji TEXT, "
                 "race_num TEXT, track_type_code TEXT, data_div TEXT)")
    conn.execute("CREATE TABLE horse_races (race_year TEXT, race_month_day TEXT, track_code TEXT, kaiji TEXT, nichiji TEXT, "
                 "race_num TEXT, horse_num TEXT, blood_register_num TEXT, abnormal_code TEXT, confirmed_order TEXT, "
                 "win_odds INTEGER, leg_quality_code TEXT)")
    for r in races:
        key = (r["ymd"][:4], r["ymd"][4:], r.get("track", "05"), "01", "01", r.get("rn", "01"))
        conn.execute("INSERT INTO races VALUES (?,?,?,?,?,?,?,?)", (*key, r.get("tt", "23"), r.get("data_div", "7")))
        for hn, horse, abn, fin, odds, leg in r["runs"]:
            conn.execute("INSERT INTO horse_races VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                         (*key, hn, horse, abn, str(fin), int(round(odds * 10)), leg))
    conn.commit()
    conn.close()
    return path


def _d(ymd: str, days: int) -> str:
    x = date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:])) + timedelta(days=days)
    return x.strftime("%Y%m%d")


TARGET = "20230610"


def _scenario(target_legs=("1", "1", "1", "1"), same_day_leg="4"):
    """対象レース (2023-06-10、4 頭) と、各馬の過去走。H1 は同じ日の別のレース (第 5 レース) にも出ている (使ってはいけない)。"""
    hist = [
        # H1: 先行 (2) が多い。対象日の 365 日前ちょうどの走は窓に入る
        {"ymd": _d(TARGET, -365), "rn": "03", "runs": [("01", "H1", "0", 1, 3.0, "2"), ("02", "X1", "0", 2, 3.0, "4")]},
        {"ymd": _d(TARGET, -30), "rn": "03", "runs": [("01", "H1", "0", 1, 3.0, "2"), ("02", "X2", "0", 2, 3.0, "4")]},
        # H2: 逃 (1)
        {"ymd": _d(TARGET, -60), "rn": "04", "runs": [("01", "H2", "0", 1, 3.0, "1"), ("02", "X3", "0", 2, 3.0, "3")]},
        # H3: 差 (3)。366 日前の走 (窓の外) は逃 (1)
        {"ymd": _d(TARGET, -366), "rn": "04", "runs": [("01", "H3", "0", 1, 3.0, "1"), ("02", "X4", "0", 2, 3.0, "3")]},
        {"ymd": _d(TARGET, -10), "rn": "05", "runs": [("01", "H3", "0", 1, 3.0, "3"), ("02", "X5", "0", 2, 3.0, "4")]},
        # H4: 履歴なし (不明)
        # 同じ日の別のレース (第 2 レース、対象より前の時刻) に H1 が出走 — 使ってはいけない
        {"ymd": TARGET, "rn": "02", "runs": [("01", "H1", "0", 1, 3.0, same_day_leg), ("02", "X6", "0", 2, 3.0, "1")]},
    ]
    target = {"ymd": TARGET, "rn": "11", "runs": [
        ("01", "H1", "0", 1, 2.5, target_legs[0]), ("02", "H2", "0", 2, 4.0, target_legs[1]),
        ("03", "H3", "0", 3, 5.0, target_legs[2]), ("04", "H4", "0", 4, 9.0, target_legs[3])]}
    return hist + [target]


def _rows(tmp_path, name, races):
    db = _make_db(tmp_path / name, races)
    loaded, _ = cp.load_races(2024, min_year=2021, db_path=db)
    c, ex = Counter(), []
    rows = cp.target_rows(loaded, (2023,), cp.style_history(loaded), cp.experience_index(loaded), c, ex)
    return [r for r in rows if r["race_id"].startswith(TARGET) and r["race_id"].endswith("_11")], c, ex


# --- 対象レース自身の脚質コードが混入しない ---------------------------------------------------------------

def test_target_race_own_leg_codes_never_reach_any_component(tmp_path):
    base, _, _ = _rows(tmp_path, "a.db", _scenario(target_legs=("1", "1", "1", "1")))
    alt, _, _ = _rows(tmp_path, "b.db", _scenario(target_legs=("4", "3", "2", "1")))
    blank, _, _ = _rows(tmp_path, "c.db", _scenario(target_legs=("", "", "", "")))
    keys = ("style", *cp.COMPONENTS)
    for a, b, c in zip(base, alt, blank):
        for k in keys:
            assert (a[k] == b[k] == c[k]) or (math.isnan(a[k]) and math.isnan(b[k]) and math.isnan(c[k])), k


def test_same_day_other_races_are_not_history(tmp_path):
    a, _, _ = _rows(tmp_path, "a.db", _scenario(same_day_leg="4"))
    b, _, _ = _rows(tmp_path, "b.db", _scenario(same_day_leg="1"))
    assert [r["style"] for r in a] == [r["style"] for r in b]
    assert a[0]["style"] == "2"                         # H1 は過去の 2 走 (先) から。同じ日の走 (4 / 1) は数えない


def test_styles_and_components_of_the_scenario(tmp_path):
    rows, counts, ex = _rows(tmp_path, "a.db", _scenario())
    assert [r["style"] for r in rows] == ["2", "1", "3", ""]          # H3 の 366 日前の逃は窓の外、H4 は不明
    pace = (1 + 0.5 * 1) / 3
    assert rows[0]["style_x_pace_fit"] == pytest.approx(-pace)        # 先
    assert rows[1]["style_x_pace_fit"] == pytest.approx(-pace)        # 逃
    assert rows[2]["style_x_pace_fit"] == pytest.approx(+pace)        # 差
    assert math.isnan(rows[3]["style_x_pace_fit"]) and math.isnan(rows[3]["front_competition_signed"])
    assert [r["front_competition_signed"] for r in rows[:3]] == [0.0, 0.0, 0.0]     # 同じ脚質の他馬なし / 差は 0
    assert sum(r["p_market"] for r in rows) == pytest.approx(1.0)
    assert ex == []


# --- 窓・直近 5 走・同数の規則 -------------------------------------------------------------------------

def _h(*pairs):
    return [(o, f"r{o}", leg) for o, leg in pairs]


def test_window_edges_are_365_days_back_and_the_day_before():
    t = 1000
    assert cp.style_of(_h((t - 365, "3")), t) == "3"
    assert cp.style_of(_h((t - 366, "3")), t) is None
    assert cp.style_of(_h((t, "3")), t) is None                     # 対象日 (同じ日) は使わない
    assert cp.style_of(_h((t - 1, "4")), t) == "4"


def test_only_the_five_most_recent_runs_count():
    t = 1000
    hist = _h((t - 70, "1"), (t - 60, "1"), (t - 50, "1"), (t - 40, "3"), (t - 30, "3"), (t - 20, "2"))
    # 直近 5 走 = 1, 1, 3, 3, 2 → 最頻値 {1, 3} の同数 → 新しい方の 3。6 走を数えると 1 が 3 回で 1 になる
    assert cp.style_of(hist, t) == "3"


def test_ties_go_to_the_mode_seen_most_recently():
    t = 1000
    assert cp.style_of(_h((t - 50, "1"), (t - 40, "3"), (t - 30, "1"), (t - 20, "3")), t) == "3"
    # 最も新しい走 (2) が最頻値でないとき、最頻値 {1, 3} の中で最も新しい走の値 (3)
    assert cp.style_of(_h((t - 50, "1"), (t - 40, "1"), (t - 30, "3"), (t - 20, "3"), (t - 10, "2")), t) == "3"


def test_style_history_only_keeps_codes_one_to_four(tmp_path):
    races = [{"ymd": "20230101", "runs": [("01", "H1", "0", 1, 3.0, "1"), ("02", "H2", "4", 0, 3.0, ""),
                                          ("03", "H3", "0", 2, 3.0, "9")]}]
    loaded, _ = cp.load_races(2024, min_year=2021, db_path=_make_db(tmp_path / "s.db", races))
    hist = cp.style_history(loaded)
    assert set(hist) == {"H1"}


# --- 読み込み ------------------------------------------------------------------------------------------

def test_exploration_refuses_the_primary_year(tmp_path):
    db = _make_db(tmp_path / "e.db", [])
    with pytest.raises(cp.CPrimeError, match="2025"):
        cp.load_races(2025, db_path=db)
    with pytest.raises(cp.CPrimeError, match="目的"):
        cp.load_races(2025, db_path=db, allow_primary_year=True)


def test_obstacles_are_skipped_and_unknown_flat_codes_stop(tmp_path):
    db = _make_db(tmp_path / "o.db", [{"ymd": "20230101", "tt": "53", "runs": [("01", "H1", "0", 1, 3.0, "1")]}])
    races, stats = cp.load_races(2024, db_path=db)
    assert races == {} and stats["skip_obstacle_rows"] == 1
    db2 = _make_db(tmp_path / "u.db", [{"ymd": "20230101", "tt": "31", "runs": [("01", "H1", "0", 1, 3.0, "1")]}])
    with pytest.raises(cp.CPrimeError, match="未知"):
        cp.load_races(2024, db_path=db2)


# --- 選択集合 (§8-6) ------------------------------------------------------------------------------------

def test_refunded_runner_is_not_in_the_member_set_and_unpriced_runner_excludes_the_race(tmp_path):
    hist = [{"ymd": "20230101", "rn": "01", "runs": [("01", "A", "0", 1, 3.0, "1"), ("02", "B", "0", 2, 3.0, "1"),
                                                      ("03", "C", "0", 3, 3.0, "3")]}]
    target_ok = {"ymd": "20230601", "rn": "05", "runs": [("01", "A", "0", 1, 2.0, "1"), ("02", "B", "3", 0, 0.0, ""),
                                                          ("03", "C", "0", 2, 3.0, "3")]}
    target_bad = {"ymd": "20230602", "rn": "05", "runs": [("01", "A", "0", 1, 2.0, "1"), ("03", "C", "0", 2, 0.0, "3")]}
    loaded, _ = cp.load_races(2024, db_path=_make_db(tmp_path / "m.db", hist + [target_ok, target_bad]))
    c, ex = Counter(), []
    rows = cp.target_rows(loaded, (2023,), cp.style_history(loaded), cp.experience_index(loaded), c, ex)
    ok = [r for r in rows if r["race_id"].startswith("20230601")]
    assert [r["horse_num"] for r in ok] == ["01", "03"]                    # 競走除外の B は母集団に入らない
    assert ok[0]["style_x_pace_fit"] == pytest.approx(-0.5)               # 逃 1 頭 / 既知 2 頭 (B の逃は数えない)
    assert ok[0]["front_competition_signed"] == 0.0
    assert ex == [{"race_id": "20230602_05_01_01_05", "reason": "nonrefund_runner_without_price:final", "horses": ["03"]}]
    assert c["excluded:nonrefund_runner_without_price:final"] == 1


def test_dead_heats_are_dropped_and_counted(tmp_path):
    races = [{"ymd": "20230601", "runs": [("01", "A", "0", 1, 2.0, "1"), ("02", "B", "0", 1, 3.0, "3")]}]
    loaded, _ = cp.load_races(2024, db_path=_make_db(tmp_path / "d.db", races))
    c, ex = Counter(), []
    assert cp.target_rows(loaded, (2023,), {}, {}, c, ex) == [] and c["drop_dead_heat_or_no_winner"] == 1


# --- 成分 ---------------------------------------------------------------------------------------------

def test_race_components_by_hand():
    out = cp.race_components({"01": "1", "02": "1", "03": "2", "04": "3", "05": "4", "06": None})
    pace = (2 + 0.5 * 1) / 5
    assert out["01"]["style_x_pace_fit"] == pytest.approx(-pace)
    assert out["04"]["style_x_pace_fit"] == pytest.approx(pace)
    assert out["01"]["front_competition_signed"] == -1.0          # 他の逃 1 頭
    assert out["03"]["front_competition_signed"] == 0.0           # 他の先 0 頭
    assert out["05"]["front_competition_signed"] == 0.0           # 追は 0
    assert math.isnan(out["06"]["style_x_pace_fit"])
    allnan = cp.race_components({"01": None, "02": None})
    assert all(math.isnan(v) for d in allnan.values() for v in d.values())


# --- 標準化 (§8-4c-2) -----------------------------------------------------------------------------------

def _r(race, x):
    return {"race_id": race, "x": x}


def test_within_sd_is_equal_race_ddof0_and_keeps_zero_variance_races():
    rows = [_r("A", 0.0), _r("A", 2.0),                      # v = 1
            _r("B", 5.0), _r("B", 5.0), _r("B", 5.0),        # v = 0 (含める)
            _r("C", 7.0),                                     # 1 頭 → v = 0 (含める)
            _r("D", math.nan), _r("D", math.nan)]             # 欠損だけ → 数えない
    got = cp.within_sd(rows, "x")
    assert got["sd"] == pytest.approx(math.sqrt(1 / 3)) and got["n_races"] == 3 and got["n_races_zero_variance"] == 2
    # 1 レース 1 票: 大きなレース (分散 4 の 10 頭) が小さなレース (分散 0) と同じ重み
    rows2 = [_r("A", -2.0 if i % 2 else 2.0) for i in range(10)] + [_r("B", 1.0), _r("B", 1.0)]
    assert cp.within_sd(rows2, "x")["sd"] == pytest.approx(math.sqrt(2.0))


def test_within_sd_zero_everywhere_stops():
    with pytest.raises(cp.CPrimeError, match="0"):
        cp.within_sd([_r("A", 1.0), _r("A", 1.0)], "x")


def test_standardize_divides_only_and_fills_missing_with_the_race_mean():
    rows = [_r("A", 1.0), _r("A", 3.0), _r("A", math.nan), _r("B", math.nan), _r("B", math.nan), _r("C", 4.0)]
    cp.standardize(rows, "x", 2.0, "xs")
    assert [r["xs"] for r in rows] == [0.5, 1.5, 1.0, 0.0, 0.0, 2.0]      # 中心化しない / 欠損はレース内の平均 / 全欠損は 0


def test_within_share_is_anova_type():
    rows = [_r("A", 0.0), _r("A", 2.0), _r("B", 4.0), _r("B", 6.0)]
    # 全体平均 3: 総平方和 9+1+1+9 = 20、レース内 1+1+1+1 = 4
    assert cp.within_share(rows, "x") == pytest.approx(4 / 20)


# --- 合成 ---------------------------------------------------------------------------------------------

def _synthetic_rows(n_races=1500, seed=0, b1=0.5, b2=-0.4, year=2022):
    rng = random.Random(seed)
    rows = []
    for i in range(n_races):
        k = 8
        raw = [rng.random() + 0.1 for _ in range(k)]
        tot = sum(raw)
        p = [x / tot for x in raw]
        c1 = [rng.gauss(0, 1) for _ in range(k)]
        c2 = [rng.gauss(0, 1) for _ in range(k)]
        w = [p[j] * math.exp(b1 * c1[j] + b2 * c2[j]) for j in range(k)]
        u, acc, win = rng.random() * sum(w), 0.0, k - 1
        for j in range(k):
            acc += w[j]
            if u <= acc:
                win = j
                break
        for j in range(k):
            rows.append({"race_id": f"{year}-{i}", "year": year, "horse_num": f"{j + 1:02d}", "won": int(j == win),
                         "p_market": p[j], "style": "1", "n_runs_365": j,
                         "style_x_pace_fit": c1[j], "front_competition_signed": c2[j]})
    return rows


def test_reverse_signed_component_gets_zero_weight():
    comp = cp.fit_composite(_synthetic_rows(b1=0.5, b2=-0.4))
    assert comp["weights"]["style_x_pace_fit"] > 0.3
    assert comp["weights"]["front_competition_signed"] == 0.0
    assert comp["raw_coefficients"]["front_competition_signed"] < 0
    assert comp["fit"]["cols"][0] == "market_feature"


def test_all_reverse_signed_components_stop_the_composite():
    with pytest.raises(cp.CPrimeError, match="逆の符号"):
        cp.fit_composite(_synthetic_rows(b1=-0.5, b2=-0.4, seed=1))


def test_fit_refuses_primary_year_rows():
    with pytest.raises(cp.CPrimeError, match="2025"):
        cp.fit_composite(_synthetic_rows(n_races=50, year=2025))


def test_apply_composite_uses_the_frozen_scales_and_s_has_unit_within_sd_on_fit_rows():
    fit_rows = _synthetic_rows(b1=0.5, b2=0.3, seed=2)
    comp = cp.fit_composite(fit_rows)
    s_fit = cp.apply_composite(fit_rows, comp)
    assert cp.within_sd(s_fit, "S")["sd"] == pytest.approx(1.0, rel=1e-9)
    other = _synthetic_rows(n_races=200, b1=0.5, b2=0.3, seed=3, year=2023)
    for r in other:
        r["style_x_pace_fit"] *= 3.0                        # 尺度の違う年でも、凍結した σ で割る (推定し直さない)
    s_other = cp.apply_composite(other, comp)
    r0 = s_other[0]
    want = (comp["weights"]["style_x_pace_fit"] * r0["style_x_pace_fit"] / comp["component_sd"]["style_x_pace_fit"]["sd"]
            + comp["weights"]["front_competition_signed"] * r0["front_competition_signed"]
            / comp["component_sd"]["front_competition_signed"]["sd"]) / comp["s_sd"]["sd"]
    assert r0["S"] == pytest.approx(want)
    assert other[0].get("S") is None                        # 入力の行は変えない


def test_clogit_goes_through_market_feature(monkeypatch):
    calls = {"n": 0}
    real = rm.market_feature
    monkeypatch.setattr(rm, "market_feature", lambda p: calls.__setitem__("n", calls["n"] + 1) or real(p))
    rows = _synthetic_rows(n_races=100, seed=4)
    cp.clogit_with_se(rows, ["style_x_pace_fit"])
    assert calls["n"] >= len(rows)


def test_clogit_se_matches_the_information_of_the_log_model():
    rows = _synthetic_rows(n_races=400, seed=5, b1=0.5, b2=0.0)
    got = cp.clogit_with_se(rows, ["style_x_pace_fit"])
    assert got["cols"] == ["market_feature", "style_x_pace_fit"]
    assert abs(got["beta"][0] - 1.0) < 0.2 and abs(got["beta"][1] - 0.5) < 0.15
    assert all(s > 0 for s in got["se"])


# --- 診断 ---------------------------------------------------------------------------------------------

def test_variance_decomposition_by_hand():
    rows = [{"race_id": "A", "S": 0.0, "p_market": 0.5}, {"race_id": "A", "S": 2.0, "p_market": 0.5},
            {"race_id": "B", "S": 4.0, "p_market": 0.25}, {"race_id": "B", "S": 6.0, "p_market": 0.75}]
    d = cp.variance_decomposition(rows)
    assert d["total_var"] == pytest.approx(5.0)
    assert d["within_var"] == pytest.approx(1.0) and d["between_var"] == pytest.approx(4.0)
    assert d["within_share"] == pytest.approx(0.2)
    # 市場で重み付けたレース内の分散: A 0.5·1+0.5·1 = 1、B 0.25·(4−5.5)²+0.75·(6−5.5)² = 0.75 → 平均 0.875
    assert d["market_weighted_within_var_per_race"] == pytest.approx(0.875)


def test_runs_in_window_edges():
    assert cp.runs_in_window([634, 635, 636, 999, 1000], 1000) == 3   # 366 日前と当日は外、365 日前ちょうど (635)・前日 (999) は内


# --- 来歴・静的な検査 ---------------------------------------------------------------------------------

def test_blob_sha_matches_git_and_ignores_crlf(tmp_path):
    p = tmp_path / "a.txt"
    p.write_bytes(b"hello\n")
    assert cp.blob_sha(p) == "ce013625030ba8dba906f756967f9e9ca394464a"
    p.write_bytes(b"hello\r\n")
    assert cp.blob_sha(p) == "ce013625030ba8dba906f756967f9e9ca394464a"


@pytest.mark.parametrize("path", ["scripts/c_prime.py", "scripts/c_prime_explore.py"])
def test_c_prime_code_does_not_use_group_a_market_functions_or_raw_logs(path):
    """§8-6b の runner の前提条件: Group A (logit の仕様) の市場の関数を使わず、市場の列に log を直接書かない。"""
    src = (ROOT / path).read_text(encoding="utf-8")
    # 汎用の推定 (scripts/group_a_stats.py、市場の変換を持たない) は依存として許す。Group A の市場・特徴のコードは使わない
    for bad in ("group_a_power", "scripts/group_a.py", "from scripts import group_a\n", "import group_a\n", "logit_p_market",
                "add_market_logit", "math.log(", "np.log(", "estimate_leg_code"):
        assert bad not in src, bad


def test_singular_information_in_clogit_is_a_c_prime_error(monkeypatch):
    """特異な情報行列は CPrimeError (leave-one-year-out の記録が except CPrimeError で続けられるように)。"""
    rows = _synthetic_rows(n_races=80, seed=6)

    def singular(_):
        raise np.linalg.LinAlgError("singular")
    monkeypatch.setattr(cp.np.linalg, "inv", singular)
    with pytest.raises(cp.CPrimeError, match="特異"):
        cp.clogit_with_se(rows, ["style_x_pace_fit"])


def test_history_only_load_nulls_primary_year_results_in_sql(tmp_path):
    races = [{"ymd": "20241201", "runs": [("01", "A", "0", 1, 2.0, "1"), ("02", "B", "0", 2, 3.0, "3")]},
             {"ymd": "20250105", "runs": [("01", "A", "0", 1, 2.0, "2"), ("02", "B", "0", 2, 3.0, "4")]}]
    db = _make_db(tmp_path / "h.db", races)
    loaded, _ = cp.load_races(2025, db_path=db, allow_primary_year=True, primary_purpose="test", primary_year_history_only=True)
    r25 = [x for r in loaded.values() if r.ymd.startswith("2025") for x in r.runs]
    r24 = [x for r in loaded.values() if r.ymd.startswith("2024") for x in r.runs]
    assert [(x.finish, x.win_odds, x.leg) for x in r25] == [(0, 0.0, "2"), (0, 0.0, "4")]
    assert [(x.finish, x.win_odds) for x in r24] == [(1, 2.0), (2, 3.0)]
