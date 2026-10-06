"""Phase 0.5-5 Group D の探索 (学習期 2022-2024 の中だけ、2025 は読まない)。台帳: `docs/PHASE05_5_EXPLORATION.md` の D-2。

- e1: 2022 ⇄ 2023 の交差。各向きで推定期間の年だけで補正テーブル・σ_within を作り、もう一方の年で β_S の z を記録する (候補なし、選択しない)
- e2: 2022-2023 で推定 → 2024 で通す (dry run。証拠にしない)

    python -m scripts.group_d_explore --mode e1 --out-dir data/backtest/group_d_20261006/e1 --db <keiba.db>
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import c_prime as cp  # noqa: E402
from scripts import group_a as ga  # noqa: E402
from scripts import group_d as gd  # noqa: E402
from scripts import prereg_runner as pr  # noqa: E402

MODES = {"e1": [((2022,), (2023,)), ((2023,), (2022,))], "e2": [((2022, 2023), (2024,))]}
DEPENDENCIES = ("scripts/group_d.py", "scripts/group_d_explore.py", "scripts/group_a.py", "scripts/c_prime.py", "scripts/research_window.py",
                "scripts/prereg_runner.py", "predictor/market_clogit.py", "predictor/race_market.py", "predictor/eval_stats.py",
                "config.py", "db.py", "docs/PHASE05_5_PREREG.md", "docs/PHASE05_5_EXPLORATION.md",
                "data/backtest/group_a_class_20261005/class_table.csv")


def year_summary(rows: list[dict], counts: dict, exclusions: list) -> dict:
    n = len(rows)
    return {"n_rows": n, "n_races": len({r["race_id"] for r in rows}),
            "has_prev_rate": sum(r["has_prev"] for r in rows) / n if n else math.nan,
            "observed_rate": sum(not math.isnan(r["S_raw"]) for r in rows) / n if n else math.nan,
            "class_move_dist": dict(sorted(Counter(int(r["class_move"]) for r in rows if not math.isnan(r["class_move"])).items())),
            "counts": counts, "exclusions": exclusions}


def direction(races, fit_years, eval_years) -> dict:
    tables = ga.fit_tables(races, gd.SPEC, fit_years)
    history = gd.run_ratings(races, tables)
    req = gd.Requirements(races, gd.winner_ratings(races, history))
    out = {"fit_years": list(fit_years), "eval_years": list(eval_years), "years": {}}
    rows_by = {}
    for ys in (fit_years, eval_years):
        c, ex = Counter(), []
        rows_by[ys] = gd.target_rows(races, ys, history, req, c, ex)
        out["years"]["-".join(map(str, ys))] = year_summary(rows_by[ys], dict(c), ex)
    scale = gd.fit_scale(rows_by[fit_years])
    fit_s = gd.standardize_and_fill(rows_by[fit_years], scale["sd"])
    ev = gd.standardize_and_fill(rows_by[eval_years], scale["sd"])
    fit_c, ev_c = gd.clogit(fit_s), gd.clogit(ev)
    for r in ev:
        r["S_x_move"] = r["S_std"] * r["class_move_filled"]
    inter = cp.clogit_with_se(ev, ["class_move_filled", "S_std", "S_x_move"])
    out.update({"S_scale": scale, "fit_in_sample": fit_c, "eval": ev_c, "beta_S": ev_c["beta"][2], "z_S": ev_c["z"][2],
                "beta_move": ev_c["beta"][1], "z_move": ev_c["z"][1], "beta_market": ev_c["beta"][0],
                "S_within_share_eval": cp.within_share([r for r in rows_by[eval_years] if not math.isnan(r["S_raw"])], "S_raw"),
                "S_variance_decomposition_eval": cp.variance_decomposition(ev, "S_std"),
                "S_vs_class_move_within_corr_eval": cp.within_race_corr(ev, "S_std", "class_move_filled"),
                "diag_S_x_move_eval": {"beta": inter["beta"][3], "z": inter["z"][3]},
                "diag_gap_equivalence_eval": gd.gap_equivalence(rows_by[eval_years], scale["sd"])})
    return out


def run(mode: str, out_dir: Path, db_path: Path) -> dict:
    races, load_stats = ga.load_races(2024, min_year=2021, db_path=db_path)
    out = {"mode": mode, "load_stats": dict(load_stats), "directions": [direction(races, f, e) for f, e in MODES[mode]]}
    if mode == "e1":
        zs = [d["z_S"] for d in out["directions"]]
        out["e1_summary"] = {"z_S": zs, "mean_z_S": sum(zs) / len(zs), "note": "D は候補を持たないので選択しない (台帳 D-1)"}
    out["provenance"] = pr.provenance(ROOT, DEPENDENCIES, db_path, own_output=pr.rel(ROOT, out_dir))
    out_dir.mkdir(parents=True, exist_ok=True)
    pr.write_json(out_dir / f"{mode}_result.json", out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=sorted(MODES), required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--db", default=str(ga.DB_PATH))
    a = ap.parse_args()
    out_dir = Path(a.out_dir)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    if out_dir.exists() and any(out_dir.iterdir()):
        raise SystemExit(f"出力先が空でない (上書きしない): {out_dir}")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    out = run(a.mode, out_dir, Path(a.db))
    for d in out["directions"]:
        print(f"{d['fit_years']} -> {d['eval_years']}: beta_S {d['beta_S']:+.4f} z {d['z_S']:+.2f} / beta_move {d['beta_move']:+.4f} "
              f"z {d['z_move']:+.2f} / beta_market {d['beta_market']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
