"""Measure F3 PIT snapshot coverage in the development window.

This audit is read-only. It does not train a model or implement features.
All market snapshot eligibility decisions go through predictor.pit_gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from statistics import median

from config import PIT_GATE_MINUTES, PROJECT_ROOT
from db import open_db_readonly
from predictor.pit_gate import pit_cutoff, usable_snapshots


DEV_FROM = "20260704"
SEALED_START = "20261001"
NEAR_T10_MAX_LEAD_MIN = 25.0
PROJECTION_WEEKS = 4
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "f3_phase1_readiness" / "dev_odds_coverage.json"
DEFAULT_REPORT = PROJECT_ROOT / "docs" / "F3_phase1_readiness.md"
PRODUCTION_ARTIFACTS = (
    PROJECT_ROOT / "predictor" / "lgbm_model.txt",
    PROJECT_ROOT / "predictor" / "lgbm_features.json",
    PROJECT_ROOT / "predictor" / "lgbm_meta.json",
    PROJECT_ROOT / "predictor" / "calibrator.json",
)


def _validate_window(from_date: str, to_date: str) -> None:
    for label, value in (("from_date", from_date), ("to_date", to_date)):
        if len(value) != 8 or not value.isdigit():
            raise ValueError(f"{label} must be YYYYMMDD")
        datetime.strptime(value, "%Y%m%d")
    if from_date > to_date:
        raise ValueError("from_date must not be after to_date")
    if to_date >= SEALED_START:
        raise ValueError(f"sealed holdout access denied: to_date must be before {SEALED_START}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_hashes() -> dict[str, str]:
    return {
        str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"): _sha256(path)
        for path in PRODUCTION_ARTIFACTS
    }


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _race_id(race: dict) -> str:
    return "_".join(
        str(race.get(name) or "")
        for name in (
            "race_year",
            "race_month_day",
            "track_code",
            "kaiji",
            "nichiji",
            "race_num",
        )
    )


def _start_datetime(race: dict) -> datetime | None:
    race_date = f"{race.get('race_year', '')}{race.get('race_month_day', '')}"
    raw = str(race.get("start_time") or "").strip()
    if pit_cutoff(race_date, raw) is None:
        return None
    try:
        return datetime.strptime(race_date + raw.zfill(4), "%Y%m%d%H%M")
    except ValueError:
        return None


def _post_time_band(race: dict) -> str:
    start = _start_datetime(race)
    if start is None:
        return "unknown"
    return "morning" if start.hour < 12 else "afternoon"


def analyze_race(conn, race: dict) -> dict:
    """Measure one race using the canonical PIT gate and distinct timestamps."""
    start = _start_datetime(race)
    rows = usable_snapshots(conn, race)
    timestamps: dict[str, datetime] = {}
    for row in rows:
        raw = str(row.get("fetched_at") or "")
        if not raw:
            continue
        fetched = datetime.fromisoformat(raw)
        timestamps[raw] = fetched

    lead_by_timestamp: dict[str, float] = {}
    if start is not None:
        for raw, fetched in timestamps.items():
            comparable_start = start
            if fetched.tzinfo is not None:
                comparable_start = start.replace(tzinfo=fetched.tzinfo)
            lead = (comparable_start - fetched).total_seconds() / 60.0
            if lead + 1e-9 < PIT_GATE_MINUTES:
                raise RuntimeError("canonical PIT gate returned a post-cutoff snapshot")
            lead_by_timestamp[raw] = lead

    leads = list(lead_by_timestamp.values())
    n_usable = len(leads)
    earliest = max(leads) if leads else None
    latest = min(leads) if leads else None
    drift_computable = n_usable >= 2
    wide_drift = bool(
        drift_computable
        and earliest is not None
        and earliest >= 60.0
        and latest is not None
        and latest <= NEAR_T10_MAX_LEAD_MIN
    )
    ordered_times = sorted(lead_by_timestamp)
    return {
        "race_id": _race_id(race),
        "race_date": f"{race.get('race_year', '')}{race.get('race_month_day', '')}",
        "track_code": race.get("track_code"),
        "race_num": race.get("race_num"),
        "start_time": race.get("start_time"),
        "post_time_band": _post_time_band(race),
        "n_usable": n_usable,
        "earliest_fetched_at": ordered_times[0] if ordered_times else None,
        "latest_fetched_at": ordered_times[-1] if ordered_times else None,
        "earliest_lead_min": round(earliest, 6) if earliest is not None else None,
        "latest_lead_min": round(latest, 6) if latest is not None else None,
        "drift_computable": drift_computable,
        "wide_drift": wide_drift,
    }


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(float(ordered[lower]), 6)
    weight = position - lower
    result = ordered[lower] * (1.0 - weight) + ordered[upper] * weight
    return round(float(result), 6)


def _distribution(values: list[float]) -> dict:
    return {
        "n": len(values),
        "min": round(min(values), 6) if values else None,
        "p25": _percentile(values, 0.25),
        "median": round(float(median(values)), 6) if values else None,
        "p75": _percentile(values, 0.75),
        "p90": _percentile(values, 0.90),
        "max": round(max(values), 6) if values else None,
    }


def _safe_rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 8) if denominator else None


def _daily_trend(daily: list[dict]) -> dict:
    usable_days = [item for item in daily if item["races_with_entries"]]
    rates = [float(item["drift_computable_rate"] or 0.0) for item in usable_days]
    midpoint = len(rates) // 2
    first_rates = rates[:midpoint]
    second_rates = rates[midpoint:]
    first = sum(first_rates) / len(first_rates) if first_rates else 0.0
    second = sum(second_rates) / len(second_rates) if second_rates else 0.0

    slope_per_week = 0.0
    if len(usable_days) >= 2:
        x = [datetime.strptime(item["date"], "%Y%m%d").toordinal() for item in usable_days]
        x_mean = sum(x) / len(x)
        y_mean = sum(rates) / len(rates)
        denominator = sum((value - x_mean) ** 2 for value in x)
        if denominator:
            slope_per_day = sum(
                (x_value - x_mean) * (y_value - y_mean)
                for x_value, y_value in zip(x, rates)
            ) / denominator
            slope_per_week = slope_per_day * 7.0
    return {
        "race_days": len(usable_days),
        "first_half_mean_rate": round(first, 8),
        "second_half_mean_rate": round(second, 8),
        "second_half_minus_first_half": round(second - first, 8),
        "linear_slope_rate_per_calendar_week": round(slope_per_week, 8),
        "improving": second > first,
    }


def _build_summary(all_races: list[dict], measurements: list[dict]) -> tuple[list[dict], dict]:
    race_dates = sorted({
        f"{race.get('race_year', '')}{race.get('race_month_day', '')}"
        for race in all_races
    })
    races_by_date: dict[str, list[dict]] = defaultdict(list)
    for item in all_races:
        races_by_date[f"{item.get('race_year', '')}{item.get('race_month_day', '')}"].append(item)
    measured_by_date: dict[str, list[dict]] = defaultdict(list)
    for item in measurements:
        measured_by_date[item["race_date"]].append(item)

    daily = []
    for race_date in race_dates:
        rows = measured_by_date[race_date]
        with_usable = sum(item["n_usable"] >= 1 for item in rows)
        drift = sum(item["drift_computable"] for item in rows)
        wide = sum(item["wide_drift"] for item in rows)
        daily.append({
            "date": race_date,
            "total_races": len(races_by_date[race_date]),
            "races_with_entries": len(rows),
            "races_with_usable": with_usable,
            "usable_rate": _safe_rate(with_usable, len(rows)),
            "drift_computable": drift,
            "drift_computable_rate": _safe_rate(drift, len(rows)),
            "wide_drift": wide,
            "wide_drift_rate": _safe_rate(wide, len(rows)),
        })

    n_entries = len(measurements)
    n_usable = sum(item["n_usable"] >= 1 for item in measurements)
    n_drift = sum(item["drift_computable"] for item in measurements)
    n_wide = sum(item["wide_drift"] for item in measurements)
    bands = {}
    for band in ("morning", "afternoon", "unknown"):
        rows = [item for item in measurements if item["post_time_band"] == band]
        leads = [float(item["earliest_lead_min"]) for item in rows if item["earliest_lead_min"] is not None]
        bands[band] = {
            "races_with_entries": len(rows),
            "races_with_usable": sum(item["n_usable"] >= 1 for item in rows),
            "drift_computable": sum(item["drift_computable"] for item in rows),
            "wide_drift": sum(item["wide_drift"] for item in rows),
            "earliest_lead_min": _distribution(leads),
        }
    all_leads = [
        float(item["earliest_lead_min"])
        for item in measurements
        if item["earliest_lead_min"] is not None
    ]
    active_days = [item for item in daily if item["races_with_usable"] > 0]
    mean_drift_active_day = (
        sum(item["drift_computable"] for item in active_days) / len(active_days)
        if active_days else 0.0
    )
    projection = {
        "weeks": PROJECTION_WEEKS,
        "assumption": "two comparable JRA race days per week at the observed active-day mean",
        "active_race_days_observed": len(active_days),
        "mean_drift_computable_per_active_race_day": round(mean_drift_active_day, 6),
        "projected_additional_drift_computable": round(
            mean_drift_active_day * 2 * PROJECTION_WEEKS
        ),
    }
    summary = {
        "total_races": len(all_races),
        "races_with_entries": n_entries,
        "races_with_usable": n_usable,
        "usable_rate": _safe_rate(n_usable, n_entries),
        "drift_computable": n_drift,
        "drift_computable_rate": _safe_rate(n_drift, n_entries),
        "wide_drift": n_wide,
        "wide_drift_rate": _safe_rate(n_wide, n_entries),
        "earliest_lead_min": _distribution(all_leads),
        "by_post_time_band": bands,
        "daily_trend": _daily_trend(daily),
        "rough_projection": projection,
    }
    return daily, summary


def _list_races(conn, from_date: str, to_date: str) -> list[dict]:
    _validate_window(from_date, to_date)
    rows = conn.execute(
        """
        SELECT r.*,
               EXISTS (
                   SELECT 1 FROM horse_races h
                    WHERE h.race_year=r.race_year
                      AND h.race_month_day=r.race_month_day
                      AND h.track_code=r.track_code
                      AND h.kaiji=r.kaiji
                      AND h.nichiji=r.nichiji
                      AND h.race_num=r.race_num
               ) AS has_entries
          FROM races r
         WHERE (r.race_year || r.race_month_day) BETWEEN ? AND ?
         ORDER BY r.race_year, r.race_month_day, r.track_code,
                  r.kaiji, r.nichiji, CAST(r.race_num AS INTEGER)
        """,
        (from_date, to_date),
    ).fetchall()
    return [dict(row) for row in rows]


def _latest_dev_date(conn) -> str:
    upper = min(date.today().strftime("%Y%m%d"), "20260930")
    row = conn.execute(
        """
        SELECT MAX(race_year || race_month_day) AS latest
          FROM races
         WHERE (race_year || race_month_day) BETWEEN ? AND ?
        """,
        (DEV_FROM, upper),
    ).fetchone()
    latest = str(row["latest"] or "")
    if not latest:
        raise RuntimeError("no development-window races are available")
    _validate_window(DEV_FROM, latest)
    return latest


def collect(from_date: str, to_date: str | None = None) -> dict:
    production_before = _artifact_hashes()
    with open_db_readonly() as conn:
        if int(conn.execute("PRAGMA query_only").fetchone()[0]) != 1:
            raise RuntimeError("database connection is not query_only")
        effective_to = to_date or _latest_dev_date(conn)
        _validate_window(from_date, effective_to)
        all_races = _list_races(conn, from_date, effective_to)
        measurements = [
            analyze_race(conn, race)
            for race in all_races
            if bool(race.get("has_entries"))
        ]

    daily, summary = _build_summary(all_races, measurements)
    production_after = _artifact_hashes()
    if production_before != production_after:
        raise RuntimeError("production artifacts changed during readiness audit")
    git_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True
    ).strip()
    return {
        "experiment_id": "f3_phase1_readiness",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "git_sha": git_sha,
        "window": {"from_date": from_date, "to_date": effective_to},
        "gate": {
            "function": "predictor.pit_gate.usable_snapshots",
            "cutoff_function": "predictor.pit_gate.pit_cutoff",
            "pit_gate_minutes": PIT_GATE_MINUTES,
            "near_t10_max_lead_min": NEAR_T10_MAX_LEAD_MIN,
            "wide_drift_definition": (
                "at least two distinct eligible timestamps, earliest lead >= 60, "
                "latest lead <= 25"
            ),
            "near_t10_basis": "existing fresh-odds collection window T-25 through T-10",
        },
        "database": {"open_mode": "read_only", "pragma_query_only": True},
        "sealed_holdout_accessed": False,
        "production_artifacts_before": production_before,
        "production_artifacts_after": production_after,
        "production_artifacts_unchanged": True,
        "races": measurements,
        "daily": daily,
        "summary": summary,
    }


def render_report(payload: dict) -> str:
    summary = payload["summary"]
    bands = summary["by_post_time_band"]
    trend = summary["daily_trend"]
    projection = summary["rough_projection"]

    def pct(value: float | None) -> str:
        return "n/a" if value is None else f"{value:.1%}"

    def minutes(value: float | None) -> str:
        return "n/a" if value is None else f"{value:.1f} min"

    scale_statement = (
        f"The observed corpus has {summary['drift_computable']} drift-computable races; "
        "this is below a hundreds-of-races corpus."
        if summary["drift_computable"] < 100
        else f"The observed corpus has {summary['drift_computable']} drift-computable races."
    )
    trend_word = "improving" if trend["improving"] else "not improving"
    return "\n".join([
        "# F3 Phase 1 readiness: development PIT odds coverage",
        "",
        f"Window: `{payload['window']['from_date']}` through `{payload['window']['to_date']}`. ",
        f"Gate: `usable_snapshots`, T-{payload['gate']['pit_gate_minutes']}. ",
        "Measurement only; no model or feature was created.",
        "",
        "## Coverage",
        "",
        "| Metric | Count | Rate of races with entries |",
        "|---|---:|---:|",
        f"| Total races | {summary['total_races']} | - |",
        f"| Races with entries | {summary['races_with_entries']} | 100.0% |",
        f"| At least one usable timestamp | {summary['races_with_usable']} | {pct(summary['usable_rate'])} |",
        f"| Drift computable (at least 2 distinct times) | {summary['drift_computable']} | {pct(summary['drift_computable_rate'])} |",
        f"| Wide drift | {summary['wide_drift']} | {pct(summary['wide_drift_rate'])} |",
        "",
        "Wide drift is a measurement label: earliest lead >= 60 minutes and the latest "
        "eligible point is in the existing T-25 through T-10 collection window.",
        "",
        "## Earliest lead by post time",
        "",
        "| Band | Races with entries | Races with usable PIT | Earliest lead median |",
        "|---|---:|---:|---:|",
        f"| Morning (<12:00) | {bands['morning']['races_with_entries']} | {bands['morning']['races_with_usable']} | {minutes(bands['morning']['earliest_lead_min']['median'])} |",
        f"| Afternoon (>=12:00) | {bands['afternoon']['races_with_entries']} | {bands['afternoon']['races_with_usable']} | {minutes(bands['afternoon']['earliest_lead_min']['median'])} |",
        f"| Overall | {summary['races_with_entries']} | {summary['races_with_usable']} | {minutes(summary['earliest_lead_min']['median'])} |",
        "",
        "## Trend and readiness material",
        "",
        f"Daily drift coverage is **{trend_word}** by the first-half versus second-half "
        f"descriptive comparison ({pct(trend['first_half_mean_rate'])} to "
        f"{pct(trend['second_half_mean_rate'])}); slope is "
        f"{trend['linear_slope_rate_per_calendar_week']:+.3f} rate/week.",
        f"{scale_statement} This is the factual sample-size input for the human Phase 1 "
        "seven-model readiness decision; this audit does not change the design.",
        f"Wide-drift coverage is {summary['wide_drift']} / {summary['races_with_entries']} "
        f"({pct(summary['wide_drift_rate'])}). Morning and afternoon lead medians above are "
        "the input for deciding whether a 09:30 anchor task is needed; no task was registered.",
        f"Reference-only four-week extrapolation: +{projection['projected_additional_drift_computable']} "
        "drift-computable races, assuming two comparable race days/week at the observed "
        f"active-day mean ({projection['active_race_days_observed']} active days observed).",
        "",
        "## Invariants",
        "",
        "Sealed holdout not accessed. Database opened read-only with query_only enabled. "
        "Production artifacts unchanged. F3 frozen design document unchanged.",
        "",
    ])


def run(from_date: str = DEV_FROM, to_date: str | None = None) -> dict:
    payload = collect(from_date, to_date)
    _atomic_write(DEFAULT_OUTPUT, json.dumps(payload, indent=2, ensure_ascii=True) + "\n")
    _atomic_write(DEFAULT_REPORT, render_report(payload))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-date", default=DEV_FROM)
    parser.add_argument("--to-date")
    args = parser.parse_args()
    result = run(args.from_date, args.to_date)
    print(json.dumps(result["summary"], indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
