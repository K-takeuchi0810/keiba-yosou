"""Display policy for race-level buy candidate horses."""

from __future__ import annotations

BUY_CANDIDATE_MIN = 3
BUY_CANDIDATE_MAX = 5


def _pick_num(pick: dict | None) -> str:
    if not pick:
        return ""
    return str(pick.get("num") or pick.get("horse_num") or "")


def select_buy_candidate_picks(picks: list[dict]) -> list[dict]:
    """Return 3-5 display candidates when enough horses are available.

    A race can occasionally have fewer than three scored horses after data
    quality filtering; in that case we show every available pick instead of
    inventing a placeholder.
    """
    if len(picks) < BUY_CANDIDATE_MIN:
        return picks[:]
    return picks[:BUY_CANDIDATE_MAX]


def select_race_buy_pick(picks: list[dict]) -> dict | None:
    """Return the single representative buy pick for a race."""
    return next((p for p in picks if p.get("bet_candidate") or p.get("buy")), None)


def mark_single_race_buy_pick(picks: list[dict], race_buy_pick: dict | None) -> list[dict]:
    """Return display copies where only the race representative is marked buy."""
    target = _pick_num(race_buy_pick)
    marked = []
    for pick in picks:
        item = dict(pick)
        is_target = bool(target and _pick_num(item) == target)
        if "bet_candidate" in item:
            item["bet_candidate"] = is_target
        if "buy" in item:
            item["buy"] = is_target
        marked.append(item)
    return marked
