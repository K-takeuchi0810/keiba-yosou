from __future__ import annotations

import os

from scripts.backtest import (
    _add_market_snapshot_race,
    _empty_market_snapshot_stats,
    _finish_market_snapshot_stats,
    _popularity_config,
    _snapshot_meta,
    _snapshot_age_min,
    payout_from_row,
)


RACE = {
    "race_year": "2026",
    "race_month_day": "0607",
    "track_code": "05",
    "start_time": "1230",
}


def cfg(**over) -> dict:
    base = {
        "min_field": 3,
        "max_snapshot_age_min": 30,
        "first": 7,
        "second": 4,
        "third": 2,
        "config_error": None,
    }
    base.update(over)
    return base


def horse(num: str, pop: int, fetched_at: str | None, *, odds: int = 80) -> dict:
    return {
        "horse_num": num,
        "win_popularity": pop,
        "win_odds": odds,
        "odds_fetched_at": fetched_at,
    }


def finish(horses: list[dict], pop_cfg: dict | None = None) -> dict:
    pop_cfg = pop_cfg or cfg()
    stats = _empty_market_snapshot_stats(pop_cfg)
    _add_market_snapshot_race(stats, RACE, horses, pop_cfg)
    return _finish_market_snapshot_stats(stats)


def test_snapshot_age_boundaries():
    assert _snapshot_age_min(horse("01", 1, "2026-06-07T12:00:00"), RACE) == 30
    assert _snapshot_age_min(horse("01", 1, "2026-06-07T11:59:00"), RACE) == 31
    assert _snapshot_age_min(horse("01", 1, "2026-06-07T12:31:00"), RACE) == -1
    assert _snapshot_age_min(horse("01", 1, None), RACE) is None


def test_market_snapshot_counts_fresh_stale_unknown_and_bonus_candidates():
    res = finish([
        horse("01", 1, "2026-06-07T12:00:00"),
        horse("02", 2, "2026-06-07T11:59:00"),
        horse("03", 3, None),
        horse("04", 1, "2026-06-07T12:31:00"),
    ])

    assert res["scope"] == "races_with_horses_before_tentative_filter"
    assert res["clean_market_races"] == 1
    assert res["fresh_horses"] == 1
    assert res["stale_horses"] == 1
    assert res["unknown_horses"] == 1
    assert res["post_start_horses"] == 1
    assert res["pop1_3_horses"] == 4
    assert res["popularity_bonus_candidate_horses"] == 1
    assert res["races_with_popularity_bonus_candidate"] == 1
    assert res["snapshot_age_min"] == {
        "count": 2,
        "min": 30,
        "p50": 30,
        "p90": 30,
        "max": 31,
    }


def test_market_snapshot_bonus_requires_min_field_and_enabled_weights():
    fresh_pop1 = horse("01", 1, "2026-06-07T12:10:00")
    fresh_pop2 = horse("02", 2, "2026-06-07T12:10:00")

    small_field = finish([fresh_pop1, fresh_pop2], cfg(min_field=3))
    assert small_field["popularity_bonus_candidate_horses"] == 0

    disabled_weights = finish(
        [fresh_pop1, fresh_pop2, horse("03", 3, "2026-06-07T12:10:00")],
        cfg(first=0, second=0, third=0),
    )
    assert disabled_weights["popularity_bonus_candidate_horses"] == 0

    only_third_weight = finish(
        [fresh_pop1, fresh_pop2, horse("03", 3, "2026-06-07T12:10:00")],
        cfg(first=0, second=0, third=2),
    )
    assert only_third_weight["popularity_bonus_candidate_horses"] == 1


def test_market_snapshot_clean_race_requires_odds_and_popularity():
    res = finish([
        horse("01", 1, "2026-06-07T12:10:00"),
        horse("02", 0, "2026-06-07T12:10:00"),
        horse("03", 3, "2026-06-07T12:10:00", odds=0),
    ])

    assert res["clean_market_races"] == 0
    assert res["horses_with_market_odds"] == 1


def test_popularity_config_respects_env_overrides_for_snapshot_conditions():
    keys = [
        "PRED_W_popularity_min_field",
        "PRED_W_popularity_max_snapshot_age_min",
        "PRED_W_popularity_first",
        "PRED_W_popularity_second",
        "PRED_W_popularity_third",
    ]
    old = {k: os.environ.get(k) for k in keys}
    try:
        os.environ["PRED_W_popularity_min_field"] = "9"
        os.environ["PRED_W_popularity_max_snapshot_age_min"] = "12"
        os.environ["PRED_W_popularity_first"] = "1"
        os.environ["PRED_W_popularity_second"] = "0"
        os.environ["PRED_W_popularity_third"] = "0"
        cfg_ = _popularity_config()
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    assert cfg_["min_field"] == 9
    assert cfg_["max_snapshot_age_min"] == 12
    assert cfg_["first"] == 1
    assert cfg_["second"] == 0
    assert cfg_["third"] == 0


def test_payout_from_row_distinguishes_missing_row_from_losing_ticket():
    row = {
        "tan_horse_num1": "03",
        "tan_payout1": 880,
        "tan_horse_num2": None,
        "tan_payout2": None,
        "tan_horse_num3": None,
        "tan_payout3": None,
        "fuku_horse_num1": "03",
        "fuku_payout1": 220,
        "fuku_horse_num2": "07",
        "fuku_payout2": 180,
        "fuku_horse_num3": "11",
        "fuku_payout3": 310,
        "fuku_horse_num4": None,
        "fuku_payout4": None,
        "fuku_horse_num5": None,
        "fuku_payout5": None,
    }

    assert payout_from_row(row, "03", "tan") == 880
    assert payout_from_row(row, "07", "fuku") == 180
    assert payout_from_row(row, "01", "tan") == 0
    assert payout_from_row(None, "03", "tan") == 0


def test_snapshot_meta_records_any_pred_w_env_override():
    key = "PRED_W_custom_namespace_probe"
    old = os.environ.get(key)
    try:
        os.environ[key] = "123"
        meta = _snapshot_meta()
    finally:
        if old is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = old

    assert meta["env_overrides"].get(key) == "123" or meta["env_overrides"][key.upper()] == "123"
