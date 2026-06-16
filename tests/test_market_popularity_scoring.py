from __future__ import annotations

import predictor.rules as rules
from predictor.rules import _score_one, _w


def test_market_popularity_bonus_is_active_for_large_fields():
    """P24 以降、市場人気は買い候補だけでなく◎決定前のスコアにも反映する。"""
    feat = {
        "current_starter_count": 16,
        "current_race_date": "20260607",
        "current_start_time": "1230",
    }
    fresh = {"odds_fetched_at": "2026-06-07T12:05:00"}

    score_pop1, reasons_pop1 = _score_one({"win_popularity": 1, **fresh}, feat)
    score_pop2, reasons_pop2 = _score_one({"win_popularity": 2, **fresh}, feat)
    score_pop3, reasons_pop3 = _score_one({"win_popularity": 3, **fresh}, feat)
    score_pop4, reasons_pop4 = _score_one({"win_popularity": 4, **fresh}, feat)

    assert score_pop1 - score_pop4 == _w("popularity.first", 7)
    assert score_pop2 - score_pop4 == _w("popularity.second", 4)
    assert score_pop3 - score_pop4 == _w("popularity.third", 2)
    assert "市場1人気" in reasons_pop1
    assert "市場2人気" in reasons_pop2
    assert "市場3人気" in reasons_pop3
    assert not any("市場" in r for r in reasons_pop4)


def test_market_popularity_bonus_is_disabled_for_small_fields():
    feat = {
        "current_starter_count": 10,
        "current_race_date": "20260607",
        "current_start_time": "1230",
    }
    fresh = {"odds_fetched_at": "2026-06-07T12:05:00"}

    score_pop1, reasons_pop1 = _score_one({"win_popularity": 1, **fresh}, feat)
    score_pop4, _ = _score_one({"win_popularity": 4, **fresh}, feat)

    assert score_pop1 == score_pop4
    assert "市場1人気" not in reasons_pop1


def test_market_popularity_bonus_requires_fresh_snapshot():
    feat = {
        "current_starter_count": 16,
        "current_race_date": "20260607",
        "current_start_time": "1230",
    }

    score_fresh, reasons_fresh = _score_one(
        {"win_popularity": 1, "odds_fetched_at": "2026-06-07T12:05:00"}, feat)
    score_stale, reasons_stale = _score_one(
        {"win_popularity": 1, "odds_fetched_at": "2026-06-07T11:45:00"}, feat)
    score_missing, reasons_missing = _score_one({"win_popularity": 1}, feat)
    score_post_start, _ = _score_one(
        {"win_popularity": 1, "odds_fetched_at": "2026-06-07T12:31:00"}, feat)

    assert score_fresh - score_stale == _w("popularity.first", 7)
    assert score_missing == score_stale
    assert score_post_start == score_stale
    assert "市場1人気" in reasons_fresh
    assert "市場1人気" not in reasons_stale
    assert "市場1人気" not in reasons_missing


def test_market_popularity_can_change_predict_race_mark_order():
    orig_compute_features = rules.compute_features

    def fake_compute_features(conn, horse, race, cache=None):
        return {
            "current_starter_count": 16,
            "current_race_date": "20260607",
            "current_start_time": "1230",
        }

    try:
        rules.compute_features = fake_compute_features
        horses = [
            {"horse_num": "01", "win_popularity": 4, "win_odds": 80, "odds_fetched_at": "2026-06-07T12:05:00"},
            {"horse_num": "02", "win_popularity": 1, "win_odds": 30, "odds_fetched_at": "2026-06-07T12:05:00"},
        ]
        preds = rules.predict_race(horses, conn=object(), race={"race_year": "2026", "race_month_day": "0607"})
    finally:
        rules.compute_features = orig_compute_features

    assert preds[0].horse_num == "02"
    assert preds[0].mark == "◎"
    assert "市場1人気" in preds[0].rationale


def test_market_popularity_layer_a_can_be_ablated_via_env(monkeypatch):
    """二重取り込みリスク監査: 層 (A) _market_score の人気ボーナスを ablation
    したいときは PRED_W_popularity_first/second/third=0 で完全無効化できる。

    これにより層 (A) を切ったまま層 (B) _investment_probability の market_blend
    だけを単体評価でき、A/B 両方が同方向に作用しているか実測で確認できる。
    """
    monkeypatch.setenv("PRED_W_popularity_first", "0")
    monkeypatch.setenv("PRED_W_popularity_second", "0")
    monkeypatch.setenv("PRED_W_popularity_third", "0")
    feat = {
        "current_starter_count": 16,
        "current_race_date": "20260607",
        "current_start_time": "1230",
    }
    fresh = {"odds_fetched_at": "2026-06-07T12:05:00"}
    score_pop1, reasons_pop1 = _score_one({"win_popularity": 1, **fresh}, feat)
    score_pop4, _ = _score_one({"win_popularity": 4, **fresh}, feat)
    assert score_pop1 == score_pop4, "weight=0 のとき 1 人気と 4 人気のスコア差は無くなる"
    assert not any("市場" in r for r in reasons_pop1), \
        "weight=0 のとき rationale に '市場N人気' を出さない (虚偽表示防止)"
