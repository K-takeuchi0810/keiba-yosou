"""Probability calibration metrics for prediction backtests."""

from __future__ import annotations

import math


def calibration_report(records: list[dict], bin_size: float = 0.05) -> dict:
    """Return Brier/log-loss and reliability-bin data.

    records must contain ``probability`` in [0, 1] and ``actual`` as 0/1.
    """
    clean = [
        (max(0.0, min(1.0, float(r.get("probability", 0.0)))), 1 if r.get("actual") else 0)
        for r in records
    ]
    n = len(clean)
    if not n:
        return {"count": 0, "brier_score": None, "log_loss": None, "bins": []}

    eps = 1e-15
    brier = sum((p - y) ** 2 for p, y in clean) / n
    log_loss = -sum(y * math.log(max(p, eps)) + (1 - y) * math.log(max(1 - p, eps)) for p, y in clean) / n

    bin_count = int(round(1.0 / bin_size))
    buckets = [
        {"lower": i * bin_size, "upper": (i + 1) * bin_size, "count": 0, "prob_sum": 0.0, "wins": 0}
        for i in range(bin_count)
    ]
    for p, y in clean:
        idx = min(int(p / bin_size), bin_count - 1)
        buckets[idx]["count"] += 1
        buckets[idx]["prob_sum"] += p
        buckets[idx]["wins"] += y

    bins = []
    for b in buckets:
        count = b["count"]
        avg_prob = b["prob_sum"] / count if count else 0.0
        actual_rate = b["wins"] / count if count else 0.0
        bins.append(
            {
                "lower": round(b["lower"], 2),
                "upper": round(b["upper"], 2),
                "count": count,
                "avg_probability": round(avg_prob, 4),
                "actual_win_rate": round(actual_rate, 4),
                "wins": b["wins"],
            }
        )

    return {
        "count": n,
        "brier_score": round(brier, 6),
        "log_loss": round(log_loss, 6),
        "bins": bins,
    }
