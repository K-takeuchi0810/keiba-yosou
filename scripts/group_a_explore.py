"""Phase 0.5-5 Group A の探索 (学習期の中だけ): 2022 ⇄ 2023 の交差で 12 候補を比べ、規則で 1 つ選ぶ (2026-10-05)。

仕様: `docs/PHASE05_5_EXPLORATION.md` の A-2 / A-3。**2024 年以前だけを読む** (`group_a.load_races` が 2025 を拒む)。
2024 の dry run は、交差の結果と選んだ候補を台帳にコミットしてから、`--mode dryrun --spec <名前>` で別に走らせる。

usage (worktree の根で):
    python -m scripts.group_a_explore --db <keiba.db> --mode cross --out <dir>
    python -m scripts.group_a_explore --db <keiba.db> --mode dryrun --spec S1V1W0 --out <dir>
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime
from bisect import bisect_left
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from scripts import group_a as g

SPECS = [g.Spec(s, v, w) for s in ("S1", "S2") for v in ("V0", "V1", "V2") for w in ("W0", "W1")]
FOLDS = [((2022,), (2023,)), ((2023,), (2022,))]
TIE_MARGIN = 0.25
DEFAULTS = {"V": "V0", "W": "W0", "S": "S1"}


def within_race_corr(rows: list[dict], a: str, b: str) -> float:
    """レース内で平均を引いた 2 変数の相関 (レース固定効果を除いた相関)。"""
    by: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if not (math.isnan(r[a]) or math.isnan(r[b])):
            by[r["race_id"]].append(r)
    xs, ys = [], []
    for rs in by.values():
        if len(rs) < 2:
            continue
        ma = sum(r[a] for r in rs) / len(rs)
        mb = sum(r[b] for r in rs) / len(rs)
        xs += [r[a] - ma for r in rs]
        ys += [r[b] - mb for r in rs]
    x, y = np.array(xs), np.array(ys)
    if len(x) < 3 or x.std() == 0 or y.std() == 0:
        return math.nan
    return float(np.corrcoef(x, y)[0, 1])


def past_field_size(races: dict[str, g.Race]) -> dict[str, list[tuple[int, int]]]:
    """{馬: [(日の通し番号, その走の選択集合の頭数)]} (診断用。頭数の多い・少ない過去走の偏り)。"""
    out: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for r in sorted(races.values(), key=lambda x: x.ymd):
        n = sum(x.abnormal not in g.REFUNDED for x in r.runs)
        for x in r.runs:
            if x.abnormal not in g.REFUNDED and x.horse:
                out[x.horse].append((x.ordinal, n))
    return out


def add_field_size(rows: list[dict], races: dict[str, g.Race], fs: dict) -> None:
    for row in rows:
        t = g.day_ordinal(row["race_id"][:8])
        hist = fs.get(row["horse"], [])
        lo = bisect_left(hist, (t - g.WINDOW_DAYS, -1))
        hi = bisect_left(hist, (t, -1))
        vals = [n for _, n in hist[lo:hi]]
        row["past_field_size"] = float(np.mean(vals)) if vals else math.nan


def missing_rates(rows: list[dict]) -> dict:
    return {c: float(np.mean([math.isnan(r[c]) for r in rows])) for c in g.COMPONENTS} if rows else {}


def evaluate(races: dict, spec: g.Spec, est: tuple, ev: tuple, fs: dict) -> dict:
    t0 = time.time()
    tables = g.fit_tables(races, spec, est)
    ratings, rstats = g.rate_runs(races, tables)
    c_fit, c_ev = Counter(), Counter()
    fit_rows = g.target_samples(races, est, ratings, c_fit)
    ev_rows = g.target_samples(races, ev, ratings, c_ev)
    for rows in (fit_rows, ev_rows):
        g.add_market_logit(rows)
    comp = g.fit_composite(fit_rows)
    g.apply_composite(ev_rows, comp)
    res = g.clogit_with_se(ev_rows, ["logit_p_market", "S"])
    beta, se = res["beta"][1], res["se"][1]
    add_field_size(ev_rows, races, fs)
    return {
        "spec": spec.name, "est_years": list(est), "eval_years": list(ev),
        "z": beta / se if res["converged"] and se > 0 else math.nan, "beta_S": beta, "se_S": se,
        "beta_market": res["beta"][0], "converged": res["converged"],
        "w1": tables.weight_fit, "w_used": tables.w,
        "raw_weights": comp["raw_weights"], "weights": comp["weights"], "zeroed": comp["zeroed"],
        "fit_component_z": dict(zip(["logit_p_market"] + list(g.COMPONENTS),
                                    [b / s if s > 0 else math.nan for b, s in zip(comp["fit_clogit"]["beta"],
                                                                                   comp["fit_clogit"]["se"])])),
        "par_counts": tables.par.counts, "n_variants": len(tables.variants), "rating_stats": dict(rstats),
        "missing_rates_eval": missing_rates(ev_rows), "missing_rates_fit": missing_rates(fit_rows),
        "counts_fit": dict(c_fit), "counts_eval": dict(c_ev), "n_eval_rows": len(ev_rows),
        "corr_S_market_within_race": within_race_corr(ev_rows, "S", "logit_p_market"),
        "corr_S_past_field_size_within_race": within_race_corr(ev_rows, "S", "past_field_size"),
        "seconds": round(time.time() - t0, 1),
    }


def complexity_key(name: str) -> tuple:
    s, v, w = name[:2], name[2:4], name[4:6]
    nondefault = (v != DEFAULTS["V"]) + (w != DEFAULTS["W"]) + (s != DEFAULTS["S"])
    return (nondefault, ["V0", "V1", "V2"].index(v), ["W0", "W1"].index(w), ["S1", "S2"].index(s))


def select(results: list[dict]) -> dict:
    """探索台帳 A-3 の規則: z の平均が最大 → 差 0.25 未満の集合 → 補正の少ない順の全順序。W1 が片方でも無効なら外す。"""
    by: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        by[r["spec"]].append(r)
    table, excluded = [], []
    for name, rs in by.items():
        if name.endswith("W1") and any(not (r["w1"] or {}).get("valid") for r in rs):
            excluded.append(name)
            continue
        zs = [r["z"] for r in rs]
        if len(zs) != len(FOLDS) or any(math.isnan(z) for z in zs):
            excluded.append(name)
            continue
        table.append((name, float(np.mean(zs))))
    if not table:
        return {"selected": None, "excluded": excluded, "ranking": []}
    best = max(z for _, z in table)
    near = [n for n, z in table if best - z < TIE_MARGIN]
    chosen = min(near, key=complexity_key)
    return {"selected": chosen, "best_mean_z": best, "tie_set": sorted(near, key=complexity_key),
            "ranking": sorted(table, key=lambda t: -t[1]), "excluded": excluded}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--mode", choices=["cross", "dryrun"], required=True)
    ap.add_argument("--spec")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    started = datetime.now().astimezone().isoformat(timespec="seconds")
    races, load_stats = g.load_races(2024, db_path=a.db)
    fs = past_field_size(races)
    meta = {"mode": a.mode, "started_at": started, "provenance": g.provenance(a.db, ["group_a_explore", *(argv or sys.argv[1:])]),
            "load_stats": dict(load_stats),
            "years_loaded": sorted({int(r.ymd[:4]) for r in races.values()})}
    assert max(meta["years_loaded"]) <= 2024, "探索で 2025 が読み込まれた"
    if a.mode == "cross":
        results = []
        for spec in SPECS:
            for est, ev in FOLDS:
                r = evaluate(races, spec, est, ev, fs)
                print(f"{r['spec']} est={est} eval={ev} z={r['z']:.3f} beta={r['beta_S']:.4f} "
                      f"zeroed={r['zeroed']} w={r['w_used']:.4f} ({r['seconds']}s)", flush=True)
                results.append(r)
        sel = select(results)
        payload = {**meta, "results": results, "selection": sel, "seconds": round(time.time() - t0, 1),
                   "ended_at": datetime.now().astimezone().isoformat(timespec="seconds")}
        (out / "cross_results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print(json.dumps(sel, ensure_ascii=False, indent=1))
        return 0
    if not a.spec:
        ap.error("dryrun には --spec が要る")
    spec = next((s for s in SPECS if s.name == a.spec), None)
    if spec is None:
        ap.error(f"未知の候補: {a.spec} (候補: {', '.join(s.name for s in SPECS)})")
    r = evaluate(races, spec, (2022, 2023), (2024,), fs)
    payload = {**meta, "dryrun": r, "seconds": round(time.time() - t0, 1),
               "ended_at": datetime.now().astimezone().isoformat(timespec="seconds")}
    (out / f"dryrun_2024_{spec.name}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: r[k] for k in ("spec", "z", "beta_S", "se_S", "zeroed", "w_used")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
