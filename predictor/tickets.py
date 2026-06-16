"""Recommended ticket display and historical settlement helpers."""

from __future__ import annotations

from typing import Any

BASE_STAKE_YEN = 100
DEFAULT_PLAN_BUDGET_UNITS = 4


def horse_num(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return f"{int(text):02d}"
    except ValueError:
        return text.zfill(2)


def display_num(value: Any) -> str:
    text = horse_num(value)
    return text.lstrip("0") or "0"


def payout_row_for_race(conn, race: dict) -> dict | None:
    row = conn.execute(
        """
        SELECT * FROM payouts
        WHERE race_year=? AND race_month_day=? AND track_code=?
          AND kaiji=? AND nichiji=? AND race_num=?
        """,
        (
            race["race_year"], race["race_month_day"], race["track_code"],
            race["kaiji"], race["nichiji"], race["race_num"],
        ),
    ).fetchone()
    return dict(row) if row else None


def _pick_num(pick: dict) -> str:
    return horse_num(pick.get("num") or pick.get("horse_num"))


def _combo_key(nums: list[str]) -> str:
    normalized = sorted((horse_num(n) for n in nums), key=lambda n: int(n or "0"))
    return "".join(normalized)


def _combo_label(nums: list[str]) -> str:
    normalized = sorted((horse_num(n) for n in nums), key=lambda n: int(n or "0"))
    return "-".join(display_num(n) for n in normalized)


def _single_payout(row: dict | None, prefix: str, num: str) -> tuple[int, str | None]:
    if not row:
        return 0, None
    target = horse_num(num)
    limit = 3 if prefix == "tan" else 5
    for i in range(1, limit + 1):
        if horse_num(row.get(f"{prefix}_horse_num{i}")) == target:
            return int(row.get(f"{prefix}_payout{i}") or 0), display_num(target)
    return 0, None


def _combo_payout(row: dict | None, prefix: str, nums: list[str]) -> tuple[int, str | None]:
    if not row:
        return 0, None
    target = _combo_key(nums)
    for i in range(1, 4):
        combo = str(row.get(f"{prefix}_combo{i}") or "").strip()
        if combo == target:
            return int(row.get(f"{prefix}_payout{i}") or 0), _combo_label(nums)
    return 0, None


def ticket_stake_yen(tickets: list[dict]) -> int:
    """Return the actual total stake represented by a ticket plan."""
    return sum(int(t.get("stake_yen") or 0) for t in tickets)


def _settled(
    row: dict | None,
    payout: int,
    hit_combo: str | None,
    stake_units: int,
    payout_units: int = 1,
) -> dict:
    stake = stake_units * BASE_STAKE_YEN
    if row is None:
        return {
            "settled": False,
            "hit": None,
            "result_label": "結果未確定",
            "payout_yen": None,
            "stake_yen": stake,
            "return_pct": None,
            "hit_combo": None,
        }
    payout_total = payout * payout_units if payout > 0 else 0
    return {
        "settled": True,
        "hit": payout_total > 0,
        "result_label": f"的中 払戻 {payout_total:,}円" if payout_total > 0 else "不的中",
        "payout_yen": payout_total,
        "stake_yen": stake,
        "return_pct": round(payout_total / stake * 100, 1) if stake else None,
        "hit_combo": hit_combo,
    }


def _ticket(
    *,
    category: str,
    bet_type: str,
    ticket: str,
    nums: list[str],
    stake_units: int,
    row: dict | None,
    payout: int,
    hit_combo: str | None = None,
    final_odds: float | None = None,
    payout_units: int = 1,
) -> dict:
    stake_label_unit = "口" if bet_type in {"単勝", "複勝"} else "点"
    return {
        "category": category,
        "bet_type": bet_type,
        "ticket": ticket,
        "nums": [display_num(n) for n in nums],
        "stake_units": stake_units,
        "stake_label": f"{stake_units}{stake_label_unit}",
        "final_odds": final_odds,
        **_settled(row, payout, hit_combo, stake_units, payout_units=payout_units),
    }


def _available_units(max_stake_yen: int | None, unit_yen: int) -> int:
    unit = unit_yen if unit_yen > 0 else BASE_STAKE_YEN
    if max_stake_yen is None:
        return DEFAULT_PLAN_BUDGET_UNITS
    return max(int(max_stake_yen or 0) // unit, 0)


def build_recommended_tickets(
    candidate_picks: list[dict],
    payout_row: dict | None = None,
    *,
    max_stake_yen: int | None = None,
    unit_yen: int = BASE_STAKE_YEN,
) -> list[dict]:
    """Build recommended tickets from the visible 3-5 horse candidate set.

    The tickets are intended for verification/display.  They do not alter the
    core buy filter and they settle only when final payout data is available.
    """
    ordered: list[dict] = []
    seen: set[str] = set()
    for pick in candidate_picks:
        num = _pick_num(pick)
        if not num or num in seen:
            continue
        seen.add(num)
        ordered.append(pick)
    if not ordered:
        return []

    main = next((p for p in ordered if p.get("bet_candidate") or p.get("buy")), ordered[0])
    ordered = [main] + [p for p in ordered if p is not main]
    main_num = _pick_num(main)
    opponents = [_pick_num(p) for p in ordered[1:]]
    second = opponents[0] if opponents else None
    third = opponents[1] if len(opponents) >= 2 else None
    units = _available_units(max_stake_yen, unit_yen)
    if units <= 0:
        return []
    tickets: list[dict] = []

    tan_payout, tan_hit = _single_payout(payout_row, "tan", main_num)
    win_probability = float(main.get("win_probability") or main.get("probability") or 0.0)
    if win_probability > 1.0:
        win_probability /= 100.0
    expected_value = float(main.get("expected_value") or main.get("ev") or 0.0)
    confidence = str(main.get("confidence") or "")
    is_strong = win_probability >= 0.20 and expected_value >= 1.25 and "混戦" not in confidence
    tan_units = 2 if is_strong and units >= 3 else 1
    if units == 1:
        tan_units = 1
    tickets.append(_ticket(
        category="本線",
        bet_type="単勝",
        ticket=f"単勝 {display_num(main_num)}番",
        nums=[main_num],
        stake_units=tan_units,
        row=payout_row,
        payout=tan_payout,
        hit_combo=tan_hit,
        final_odds=(
            round(tan_payout / BASE_STAKE_YEN, 1)
            if payout_row is not None and tan_payout > 0 else None
        ),
        payout_units=tan_units,
    ))
    used_units = tan_units

    if used_units >= units:
        return tickets

    fuku_payout, fuku_hit = _single_payout(payout_row, "fuku", main_num)
    tickets.append(_ticket(
        category="保険",
        bet_type="複勝",
        ticket=f"複勝 {display_num(main_num)}番",
        nums=[main_num],
        stake_units=1,
        row=payout_row,
        payout=fuku_payout,
        hit_combo=fuku_hit,
    ))
    used_units += 1

    if second and used_units < units:
        payout, hit_combo = _combo_payout(payout_row, "umaren", [main_num, second])
        tickets.append(_ticket(
            category="相手",
            bet_type="馬連",
            ticket=f"馬連 {display_num(main_num)}-{display_num(second)}",
            nums=[main_num, second],
            stake_units=1,
            row=payout_row,
            payout=payout,
            hit_combo=hit_combo,
            final_odds=(round(payout / BASE_STAKE_YEN, 1) if payout > 0 else None),
        ))
        used_units += 1

    if third and used_units < units:
        nums = [main_num, second, third]
        payout, hit_combo = _combo_payout(payout_row, "sanrenpuku", nums)
        tickets.append(_ticket(
            category="押さえ",
            bet_type="三連複",
            ticket=f"三連複 {display_num(main_num)}-{display_num(second)}-{display_num(third)}",
            nums=nums,
            stake_units=1,
            row=payout_row,
            payout=payout,
            hit_combo=hit_combo,
            final_odds=(round(payout / BASE_STAKE_YEN, 1) if payout > 0 else None),
        ))

    return tickets
