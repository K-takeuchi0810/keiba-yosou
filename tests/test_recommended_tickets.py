from predictor.tickets import build_recommended_tickets


def _pick(num, *, buy=False, odds=4.2, p=0.0, ev=0.0, confidence="標準"):
    return {
        "num": str(num),
        "name": f"テスト{num}",
        "ticket": f"単勝 {num}番",
        "bet_candidate": buy,
        "odds": odds,
        "win_probability": p,
        "expected_value": ev,
        "confidence": confidence,
    }


def test_build_recommended_tickets_settles_final_results():
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
        "umaren_combo1": "0307",
        "umaren_payout1": 1420,
        "sanrenpuku_combo1": "030711",
        "sanrenpuku_payout1": 4420,
    }
    tickets = build_recommended_tickets(
        [_pick(3, buy=True, odds=8.8), _pick(7), _pick(11), _pick(1)],
        row,
    )

    assert [t["bet_type"] for t in tickets] == ["単勝", "複勝", "馬連", "三連複"]
    assert tickets[0]["hit"] is True
    assert tickets[0]["payout_yen"] == 880
    assert tickets[0]["final_odds"] == 8.8
    assert tickets[2]["hit"] is True
    assert tickets[2]["stake_units"] == 1
    assert tickets[2]["hit_combo"] == "3-7"
    assert tickets[3]["hit"] is True
    assert tickets[3]["stake_units"] == 1
    assert tickets[3]["hit_combo"] == "3-7-11"


def test_build_recommended_tickets_keeps_unsettled_future_races():
    tickets = build_recommended_tickets([_pick(8, buy=True), _pick(11), _pick(13)], None)

    assert len(tickets) == 4
    assert all(t["settled"] is False for t in tickets)
    assert all(t["result_label"] == "結果未確定" for t in tickets)
    assert tickets[0]["final_odds"] is None


def test_build_recommended_tickets_uses_payout_for_final_odds_only_when_hit():
    row = {
        "tan_horse_num1": "05",
        "tan_payout1": 620,
    }
    hit = build_recommended_tickets([_pick(5, buy=True, odds=2.1)], row, max_stake_yen=100)
    miss = build_recommended_tickets([_pick(3, buy=True, odds=9.9)], row, max_stake_yen=100)

    assert hit[0]["final_odds"] == 6.2
    assert miss[0]["final_odds"] is None


def test_build_recommended_tickets_respects_race_budget():
    tickets = build_recommended_tickets(
        [_pick(3, buy=True, p=0.24, ev=1.8), _pick(1), _pick(10), _pick(2)],
        None,
        max_stake_yen=300,
    )

    assert [t["bet_type"] for t in tickets] == ["単勝", "複勝"]
    assert sum(t["stake_yen"] for t in tickets) == 300
    assert tickets[0]["stake_units"] == 2


def test_build_recommended_tickets_adds_exotics_only_when_budget_allows():
    tickets = build_recommended_tickets(
        [_pick(13, buy=True), _pick(3), _pick(10), _pick(12)],
        None,
        max_stake_yen=400,
    )

    assert [t["bet_type"] for t in tickets] == ["単勝", "複勝", "馬連", "三連複"]
    assert sum(t["stake_yen"] for t in tickets) == 400
