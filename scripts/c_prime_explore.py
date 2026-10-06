"""Phase 0.5-5 Group C′ の探索 (学習期 2022-2024 の中だけ、2025 は読まない)。台帳: `docs/PHASE05_5_EXPLORATION.md` の C′-2。

- e1: 2022 ⇄ 2023 の交差。各向きで推定期間の年だけで σ_within・合成の重みを作り、もう一方の年で S の z を記録する
  (C′ は候補を持たないので **選択はしない**。点検と安定性の記録)
- e2: 2022-2023 で推定 → 2024 で通す (dry run。証拠にしない)

    python -m scripts.c_prime_explore --mode e1 --out-dir data/backtest/c_prime_20261006/e1
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import c_prime as cp  # noqa: E402

MODES = {"e1": [((2022,), (2023,)), ((2023,), (2022,))],
         "e2": [((2022, 2023), (2024,))]}


def known_count_distribution(rows: list[dict]) -> dict:
    by = defaultdict(int)
    races = set()
    for r in rows:
        races.add(r["race_id"])
        if r["style"]:
            by[r["race_id"]] += 1
    dist = Counter(by.get(rid, 0) for rid in races)
    return {"n_races": len(races), "n_races_known_zero": dist.get(0, 0),
            "distribution": {str(k): v for k, v in sorted(dist.items())}}


def year_summary(rows: list[dict]) -> dict:
    n = len(rows)
    unknown = sum(not r["style"] for r in rows)
    return {"n_rows": n, "n_races": len({r["race_id"] for r in rows}),
            "style_unknown_rate": unknown / n if n else float("nan"),
            "style_counts": dict(sorted(Counter(r["style"] or "unknown" for r in rows).items())),
            "known_count": known_count_distribution(rows),
            "component_within_share": {c: cp.within_share(rows, c) for c in cp.COMPONENTS}}


def direction(rows_by_year: dict[int, list[dict]], fit_years: tuple[int, ...], eval_years: tuple[int, ...]) -> dict:
    fit_rows = [r for y in fit_years for r in rows_by_year[y]]
    eval_rows = [r for y in eval_years for r in rows_by_year[y]]
    comp = cp.fit_composite(fit_rows)
    fit_s = cp.apply_composite(fit_rows, comp)
    ev = cp.apply_composite(eval_rows, comp)
    z = cp.clogit_with_se(ev, ["S"])
    return {"fit_years": list(fit_years), "eval_years": list(eval_years), "composite": comp,
            "eval_clogit": z, "beta_S": z["beta"][1], "z_S": z["z"][1],
            "S_within_share_fit": cp.within_share(fit_s, "S"), "S_within_share_eval": cp.within_share(ev, "S"),
            "S_variance_decomposition_eval": cp.variance_decomposition(ev, "S"),
            "S_vs_n_runs_365_within_corr_eval": cp.within_race_corr(ev, "S", "n_runs_365")}


def run(mode: str, out_dir: Path, db_path: Path) -> dict:
    races, load_stats = cp.load_races(2024, min_year=2021, db_path=db_path)
    history = cp.style_history(races)
    experience = cp.experience_index(races)
    years = sorted({y for pair in MODES[mode] for part in pair for y in part})
    rows_by_year, counts_by_year, excl_by_year = {}, {}, {}
    for y in years:
        c, ex = Counter(), []
        rows_by_year[y] = cp.target_rows(races, (y,), history, experience, c, ex)
        counts_by_year[y], excl_by_year[y] = dict(c), ex
    out = {"mode": mode, "load_stats": dict(load_stats),
           "years": {str(y): {**year_summary(rows_by_year[y]), "counts": counts_by_year[y],
                              "exclusions": excl_by_year[y]} for y in years},
           "directions": [direction(rows_by_year, f, e) for f, e in MODES[mode]]}
    if mode == "e1":
        zs = [d["z_S"] for d in out["directions"]]
        out["e1_summary"] = {"z_S": zs, "mean_z_S": sum(zs) / len(zs),
                             "note": "C′ は候補を持たないので選択しない (台帳 C′-1)。点検と安定性の記録"}
    out["provenance"] = cp.provenance(db_path, own_output=str(out_dir.relative_to(ROOT)).replace("\\", "/")
                                      if out_dir.is_absolute() and out_dir.is_relative_to(ROOT) else str(out_dir).replace("\\", "/"))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{mode}_result.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=sorted(MODES), required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--db", default=str(cp.DB_PATH))
    a = ap.parse_args()
    out_dir = Path(a.out_dir)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    if out_dir.exists() and any(out_dir.iterdir()):
        raise SystemExit(f"出力先が空でない (上書きしない): {out_dir}")
    out = run(a.mode, out_dir, Path(a.db))
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    for d in out["directions"]:
        print(f"{d['fit_years']} -> {d['eval_years']}: beta_S {d['beta_S']:+.4f} z {d['z_S']:+.2f} "
              f"weights {d['composite']['weights']} zmax {d['composite']['component_z_max']:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
