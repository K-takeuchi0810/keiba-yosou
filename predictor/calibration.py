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


def fit_bin_calibrator(records: list[dict], bin_size: float = 0.05, min_count: int = 20) -> dict:
    report = calibration_report(records, bin_size=bin_size)
    bins = []
    for b in report.get("bins", []):
        if b["count"] >= min_count:
            calibrated = b["actual_win_rate"]
        else:
            calibrated = b["avg_probability"]
        bins.append(
            {
                "lower": b["lower"],
                "upper": b["upper"],
                "count": b["count"],
                "avg_probability": b["avg_probability"],
                "calibrated_probability": round(calibrated, 4),
            }
        )
    return {
        "type": "bin",
        "bin_size": bin_size,
        "min_count": min_count,
        "source_count": report.get("count", 0),
        "brier_score": report.get("brier_score"),
        "log_loss": report.get("log_loss"),
        "bins": bins,
    }


def fit_isotonic_calibrator(records: list[dict]) -> dict:
    """Isotonic regression による単調校正器 (Phase 3 / 2026-05-13)。

    bin calibrator は隣接 bin 間で非単調になり得る (例: 0.10 bin が 0.08、
    0.15 bin が 0.18) ため、odds × calibrated_prob の EV が段差で暴れる。
    Isotonic は単調制約付きで滑らかな写像を学習し、点推定の信頼性を上げる。

    依存: scikit-learn (.venv64)。未 install 時は ModuleNotFoundError → caller で
    fit_bin_calibrator にフォールバック想定。
    """
    try:
        from sklearn.isotonic import IsotonicRegression  # type: ignore[import-not-found]
    except ModuleNotFoundError as e:
        raise RuntimeError(
            "fit_isotonic_calibrator requires scikit-learn. Run from .venv64."
        ) from e
    ps: list[float] = []
    ys: list[int] = []
    for r in records:
        try:
            p = max(0.0, min(1.0, float(r.get("probability", 0.0))))
        except (TypeError, ValueError):
            continue
        ps.append(p)
        ys.append(1 if r.get("actual") else 0)
    if not ps:
        return {
            "type": "isotonic",
            "x_knots": [],
            "y_knots": [],
            "source_count": 0,
            "brier_score": None,
            "log_loss": None,
        }
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(ps, ys)
    base_report = calibration_report(records)
    x_knots = iso.X_thresholds_.tolist() if hasattr(iso, "X_thresholds_") else []
    y_knots = iso.y_thresholds_.tolist() if hasattr(iso, "y_thresholds_") else []
    return {
        "type": "isotonic",
        "x_knots": x_knots,
        "y_knots": y_knots,
        "source_count": len(ps),
        "brier_score": base_report.get("brier_score"),
        "log_loss": base_report.get("log_loss"),
    }


def apply_isotonic(calibrator: dict, prob: float) -> float:
    """Isotonic calibrator の x_knots / y_knots を線形補間で適用。

    rules.py:_apply_calibrator から呼ばれる純 Python 実装 (numpy 不要)。
    32-bit / 64-bit どちらでも動作。
    """
    xs = calibrator.get("x_knots") or []
    ys = calibrator.get("y_knots") or []
    if not xs or not ys:
        return prob
    p = max(0.0, min(1.0, float(prob)))
    if p <= xs[0]:
        return float(ys[0])
    if p >= xs[-1]:
        return float(ys[-1])
    for i in range(len(xs) - 1):
        if xs[i] <= p <= xs[i + 1]:
            x0, x1 = xs[i], xs[i + 1]
            y0, y1 = ys[i], ys[i + 1]
            if x1 == x0:
                return float(y0)
            return float(y0 + (y1 - y0) * (p - x0) / (x1 - x0))
    return float(ys[-1])
