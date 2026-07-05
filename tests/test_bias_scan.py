"""scripts/bias_scan.py の純粋関数 (セグメントキー導出・集計・有意判定) のテスト。

DB 不要。境界値 (min_n ゲート、開催進行の early/mid 境界、馬場サーフェス依存、
subject=all のレース内相関補正) を固定する。
"""

from __future__ import annotations

import scripts.bias_scan as b


# --- セグメントキー導出 -------------------------------------------------------
def test_surface_key():
    assert b.surface_key({"track_type_code": "11"}) == "turf"
    assert b.surface_key({"track_type_code": "24"}) == "dirt"
    assert b.surface_key({"track_type_code": "51"}) == "jump"
    assert b.surface_key({"track_type_code": None}) == "other"
    assert b.surface_key({}) == "other"


def test_condition_key_surface_dependent():
    # 芝レースは turf_condition を見る
    turf = {"turf_condition": "4", "dirt_condition": "0"}
    assert b.condition_key(turf, "turf") == "soft"
    # ダートレースは dirt_condition を見る
    dirt = {"turf_condition": "0", "dirt_condition": "2"}
    assert b.condition_key(dirt, "dirt") == "good"
    # 障害は populated な方をフォールバック
    jump = {"turf_condition": "0", "dirt_condition": "3"}
    assert b.condition_key(jump, "jump") == "yielding"
    # 欠損/0 は unknown
    assert b.condition_key({"turf_condition": "0"}, "turf") == "unknown"
    assert b.condition_key({}, "turf") == "unknown"


def test_weather_keys():
    assert b.weather_key({"weather_code": "4"}) == "rain"
    assert b.weather_key({"weather_code": " 3 "}) == "light_rain"  # strip
    assert b.weather_key({"weather_code": "9"}) == "unknown"
    assert b.weather_wet_key({"weather_code": "1"}) == "dry"
    assert b.weather_wet_key({"weather_code": "4"}) == "wet"
    assert b.weather_wet_key({"weather_code": "0"}) == "unknown"


def test_meet_progress_boundaries():
    # nichiji 1-2 = early, 3-5 = mid, 6+ = late
    assert b.meet_progress_key({"nichiji": "01"}) == "early"
    assert b.meet_progress_key({"nichiji": "02"}) == "early"
    assert b.meet_progress_key({"nichiji": "03"}) == "mid"
    assert b.meet_progress_key({"nichiji": "05"}) == "mid"
    assert b.meet_progress_key({"nichiji": "06"}) == "late"
    assert b.meet_progress_key({"nichiji": "0"}) == "unknown"
    assert b.meet_progress_key({"nichiji": "xx"}) == "unknown"
    assert b.meet_progress_key({}) == "unknown"


def test_season_key():
    assert b.season_key({"race_month_day": "0415"}) == "spring"
    assert b.season_key({"race_month_day": "1220"}) == "winter"
    assert b.season_key({"race_month_day": "0701"}) == "summer"
    assert b.season_key({"race_month_day": "1003"}) == "autumn"
    assert b.season_key({}) == "unknown"


# --- セル集計 / ゲート / 有意判定 --------------------------------------------
def _cell(probs, actuals, *, n_races=None, field=12, trusted=True, payout_win=300):
    c = b.Cell()
    nr = n_races if n_races is not None else len(probs)
    for _ in range(nr):
        c.add_race(field)
    for p, a in zip(probs, actuals):
        c.add(p, a, bool(a), payout_win if a else 0, trusted)
    return c


def test_min_n_gate_pick():
    # n=49 < min_n=50 -> insufficient, bias_severity=None
    c = _cell([0.3] * 49, [0] * 49)
    st = b.summarize_cell(c, min_n=50, subject="pick")
    assert st["status"] == "insufficient"
    assert st["bias_severity"] is None
    # n=50 -> ok
    c2 = _cell([0.3] * 50, [0] * 50)
    st2 = b.summarize_cell(c2, min_n=50, subject="pick")
    assert st2["status"] == "ok"
    assert st2["bias_severity"] is not None


def test_overconfidence_significant():
    # pred 0.35 vs actual 0.10 (n=120) -> over-confident, mean_pred > Wilson hi
    actuals = [1 if i % 10 == 0 else 0 for i in range(120)]  # 12% actual
    c = _cell([0.35] * 120, actuals)
    st = b.summarize_cell(c, min_n=50, subject="pick")
    assert st["calibration_gap"] > 0
    assert st["gap_significant"] is True
    assert b.severity_tag(st) == "SIG*"  # gap >= MATERIAL_GAP


def test_subject_all_suppresses_significance_and_return():
    # all モード: 有効 n=レース数、有意判定は None、return も None
    # 600 馬行 / 50 レース (1 レース 12 頭) を模す
    c = b.Cell()
    for _ in range(50):
        c.add_race(12)
    for i in range(600):
        c.add(0.08, 1 if i % 12 == 0 else 0, False, 0, True)
    st = b.summarize_cell(c, min_n=50, subject="all")
    assert st["gap_significant"] is None          # 有意判定を出さない
    assert st["return_pct"] is None               # return は出さない
    assert st["effective_n"] == 50                # 有効 n はレース数
    assert st["n"] == 600
    # effective_n(50) >= min_n(50) なので ok
    assert st["status"] == "ok"
    # min_n=51 だと effective_n(50) で insufficient になる
    st2 = b.summarize_cell(c, min_n=51, subject="all")
    assert st2["status"] == "insufficient"


def test_avg_field():
    c = b.Cell()
    c.add_race(10)
    c.add_race(16)
    st = b.summarize_cell(c, min_n=0, subject="pick")
    assert st["avg_field"] == 13.0


def test_streaming_brier_golden():
    """streaming 集計の brier/mean_pred が手計算と一致する golden (無音回帰防止)。"""
    probs = [0.35, 0.10, 0.62, 0.05]
    actuals = [1, 0, 0, 1]
    c = _cell(probs, actuals)
    st = b.summarize_cell(c, min_n=0, subject="pick")
    expect_brier = round(sum((p - y) ** 2 for p, y in zip(probs, actuals)) / len(probs), 6)
    assert st["brier"] == expect_brier
    assert st["mean_pred"] == round(sum(probs) / len(probs), 4)
    assert st["actual_rate"] == round(sum(actuals) / len(actuals), 4)


def test_warn_counter():
    c = b.Cell()
    c.add_race(10)
    c.add(0.2, 0, False, 0, True, has_warning=True)
    c.add(0.2, 1, True, 300, True)  # 既定 False
    st = b.summarize_cell(c, min_n=0, subject="pick")
    assert st["warn_n"] == 1
    assert st["warn_pct"] == 50.0


def test_severity_tag_levels():
    base = {"gap_significant": True, "calibration_gap": 0.05}
    assert b.severity_tag(base) == "SIG*"
    assert b.severity_tag({"gap_significant": True, "calibration_gap": 0.01}) == "sig"
    assert b.severity_tag({"gap_significant": False, "calibration_gap": 0.2}) == ""
    assert b.severity_tag({"gap_significant": None, "calibration_gap": 0.2}) == ""
