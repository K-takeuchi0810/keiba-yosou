from predictor.portfolio import apply_daily_budget, normalize_daily_budget_yen, sync_actual_stakes


def test_normalize_daily_budget_yen():
    assert normalize_daily_budget_yen("10000") == 10000
    assert normalize_daily_budget_yen(2500.9) == 2500
    assert normalize_daily_budget_yen("") is None
    assert normalize_daily_budget_yen("bad") is None
    assert normalize_daily_budget_yen(0) is None


def test_apply_daily_budget_adds_rounded_stakes_without_forcing_full_spend():
    candidates = [
        {"date": "2026/06/13", "recommended_kelly": 0.03, "start_time": "10:00"},
        {"date": "2026/06/13", "recommended_kelly": 0.012, "start_time": "11:00"},
    ]
    info = apply_daily_budget(candidates, 10000)

    assert info["daily_budget_yen"] == 10000
    assert [c["stake_yen"] for c in candidates] == [300, 100]
    assert info["allocated_yen"] == 400
    assert info["total_allocated_yen"] == 400
    assert info["remaining_yen"] == 9600
    assert info["total_remaining_yen"] == 9600


def test_apply_daily_budget_reduces_lower_rank_when_minimum_units_exceed_budget():
    candidates = [
        {"date": "2026/06/13", "recommended_kelly": 0.03, "start_time": "10:00"},
        {"date": "2026/06/13", "recommended_kelly": 0.02, "start_time": "11:00"},
        {"date": "2026/06/13", "recommended_kelly": 0.01, "start_time": "12:00"},
    ]
    info = apply_daily_budget(candidates, 200)

    assert sum(c["stake_yen"] for c in candidates) <= 200
    assert [c["stake_yen"] for c in candidates] == [100, 100, 0]
    assert info["allocated_yen"] == 200


def test_apply_daily_budget_scales_when_portfolio_cap_is_exceeded():
    candidates = [
        {"date": "2026/06/13", "recommended_kelly": 0.20, "start_time": "10:00"},
        {"date": "2026/06/13", "recommended_kelly": 0.20, "start_time": "11:00"},
    ]
    info = apply_daily_budget(candidates, 10000, portfolio_cap=0.25)

    assert [c["stake_yen"] for c in candidates] == [1200, 1200]
    assert info["allocated_yen"] == 2400
    assert info["unit_yen"] == 100
    assert info["budget_days"][0]["budget_scale"] == 0.625


def test_sync_actual_stakes_updates_budget_totals_after_ticket_plan_cap():
    candidates = [
        {"date": "2026/06/13", "recommended_kelly": 0.08},
        {"date": "2026/06/13", "recommended_kelly": 0.02},
    ]
    info = apply_daily_budget(candidates, 10000)
    assert info["allocated_yen"] == 1000

    candidates[0]["stake_yen"] = 400
    candidates[1]["stake_yen"] = 100
    synced = sync_actual_stakes(candidates, info)

    assert synced["allocated_yen"] == 500
    assert synced["total_allocated_yen"] == 500
    assert synced["remaining_yen"] == 9500
    assert synced["budget_days"][0]["allocated_yen"] == 500
