"""次の世代の候補 A″ の探索 (学習期 2022-2024 の中だけ)。台帳: `docs/A_DOUBLE_PRIME_EXPLORATION.md`。

- e0: 構造の量 (結果の列を使わない)。2022-2023 で補正テーブル・合成を当てはめ、2024 の行で S と前走の着順の分位・log P_market の関係を測る
- e1: 2022 ⇄ 2023 の交差。各向きで推定期間の年だけで補正テーブル・σ_within・合成を作り、もう一方の年で β_S の z を記録する (選択しない)
- e2: 2022-2023 で推定 → 2024 で通す (dry run。証拠にしない)
- gate: 最終の 2022-2024 pooled の当てはめの β_S と、2024 の行 (合成は 2022-2023) でのレース内の分散・結果を読まない検出力・件数の見込み・比 r。
  候補の門の判定は台帳 A2-1 の規則で行う (`gate_verdict`)

    python -m scripts.group_a2_explore --mode e0 --out-dir data/backtest/group_a2_20261006/e0 --db <keiba.db>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from db import sql_evaluable_race  # noqa: E402
from predictor import race_market as rm  # noqa: E402
from predictor import eval_stats as es  # noqa: E402
from predictor import market_clogit as mc  # noqa: E402
from scripts import c_prime as cp  # noqa: E402
from scripts import group_a as ga  # noqa: E402
from scripts import group_a2 as a2  # noqa: E402
from scripts import group_a_stats as st  # noqa: E402
from scripts import prereg_runner as pr  # noqa: E402
from scripts import research_window  # noqa: E402

MODES = ("e0", "e1", "e2", "gate", "verdict")
E1_DIRECTIONS = [((2022,), (2023,)), ((2023,), (2022,))]
E2_DIRECTION = ((2022, 2023), (2024,))
POOLED_YEARS = (2022, 2023, 2024)
GATE_YEAR = 2024
BOOT_N, BOOT_SEED, BOOT_MAX_DISCARD_FRAC = 1000, 20261004, 0.01
# 候補の門 (台帳 A2-1、A″ を見る前に固定)
CONSTRUCT_R2_MAX = 0.80
WITHIN_VAR_MIN = 0.50
N_CALENDAR_MAX = 6800
MONEY_RACES_MAX = 17000
DEPENDENCIES = ("scripts/group_a2.py", "scripts/group_a2_explore.py", "scripts/group_a.py", "scripts/c_prime.py",
                "scripts/research_window.py", "scripts/prereg_runner.py", "scripts/group_a_stats.py", "predictor/market_clogit.py",
                "predictor/race_market.py", "predictor/eval_stats.py", "config.py", "db.py", "docs/A_DOUBLE_PRIME_PREREG.md",
                "docs/A_DOUBLE_PRIME_EXPLORATION.md", "data/backtest/group_a_class_20261005/class_table.csv")


def prepare(races: dict, fit_years: tuple[int, ...], row_years: tuple[tuple[int, ...], ...]) -> tuple[dict, dict, dict]:
    """推定期間の年で補正テーブルを作り、行の年ごとの標本 (成分は未標準化) と件数を返す。"""
    tables = ga.fit_tables(races, a2.SPEC, fit_years)
    ratings, rate_stats = ga.rate_runs(races, tables)
    finishes = a2.finish_history(races)
    rows, summary = {}, {}
    for ys in row_years:
        c, ex = Counter(), []
        rows[ys] = a2.target_rows(races, ys, ratings, finishes, c, ex)
        n = len(rows[ys])
        summary["-".join(map(str, ys))] = {
            "n_rows": n, "n_races": len({r["race_id"] for r in rows[ys]}), "counts": dict(c), "exclusions": ex,
            "component_observed_rate": {k: sum(not math.isnan(r[k]) for r in rows[ys]) / n for k in a2.COMPONENTS} if n else {},
            "last_finish_observed_rate": sum(not math.isnan(r["last_finish_pct"]) for r in rows[ys]) / n if n else math.nan}
    return rows, summary, {"unrated_runs": rate_stats.get("unrated_runs", 0), "rated_runs": rate_stats.get("rated_runs", 0)}


def evaluate(fit_rows: list[dict], eval_rows: list[dict]) -> dict:
    comp = a2.fit_composite(fit_rows)
    ev = a2.apply_composite(eval_rows, comp)
    res = cp.clogit_with_se(ev, ["S"])
    return {"composite": comp, "beta_market": res["beta"][0], "beta_S": res["beta"][1], "se_S": res["se"][1], "z_S": res["z"][1],
            "S_variance_decomposition_eval": cp.variance_decomposition(ev, "S")}


def train_boot_se(rows_s: list[dict]) -> dict:
    """凍結した S での [market_feature, S] の β_S の、レースを単位にしたブートストラップの SE (§8-7b と同じ設定)。"""
    rows_m = mc.add_market_feature(rows_s)
    packed = st.pack(rows_m, [mc.MARKET_COL, "S"])
    t0 = time.time()
    vals, discarded = es._block_resample(rows_m, st.make_beta_stat(packed, "S"), BOOT_N, BOOT_SEED)
    max_discard = math.floor(BOOT_MAX_DISCARD_FRAC * BOOT_N + 1e-9)
    se = float(np.std(vals, ddof=1)) if discarded <= max_discard and len(vals) > 1 else None
    return {"n_boot": BOOT_N, "seed": BOOT_SEED, "n_valid": len(vals), "n_discarded": discarded, "max_discard": max_discard,
            "se": se, "n_races": len({r["race_id"] for r in rows_s}), "seconds": round(time.time() - t0, 1)}


def confirmed_flat_jra_races(db_path: Path, year: int) -> int:
    """その年の確定の平地の JRA レース数 (結果の列は読まない。比 r の分母)。"""
    research_window.check(f"{year}0101", f"{year}1231", purpose="development", context="group_a2_explore.confirmed_flat_jra_races")
    conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    try:
        (n,) = conn.execute(
            f"SELECT COUNT(*) FROM races r WHERE r.race_year = ? AND {research_window.JRA_TRACK_SQL} "
            f"AND r.data_div = '{research_window.CONFIRMED_DATA_DIV}' "
            f"AND CAST(r.track_type_code AS INTEGER) < {research_window.OBSTACLE_FROM} AND {sql_evaluable_race('r.data_div')}",
            (str(year),)).fetchone()
    finally:
        conn.close()
    return int(n)


def money_state(n_buys: int, n_races: int) -> dict:
    """金額の試験の成熟 (reject しない)。最低点数は race_market.MIN_BUYS_FOR_MONEY_PASS (1,500)。"""
    min_buys = rm.MIN_BUYS_FOR_MONEY_PASS
    if n_buys == 0:
        return {"state": "MONEY_UNTESTABLE_NO_EXPECTED_BUYS", "min_buys": min_buys, "races_for_min_buys": None}
    races_for = min_buys * n_races / n_buys
    return {"state": "MONEY_MATURABLE" if races_for <= MONEY_RACES_MAX else "MONEY_UNTESTABLE_WITHIN_5Y", "min_buys": min_buys,
            "races_for_min_buys": races_for}


def gate_verdict(construct_r2: float, e_betas: list[tuple[float, float]], pooled_beta: float, within_var: float,
                 n_calendar: int) -> dict:
    """台帳 A2-1 の 4 本の門 (金額は reject しない)。e_betas は E1 の 2 向きと E2 の (β_S, z)。"""
    reasons = []
    if not construct_r2 < CONSTRUCT_R2_MAX:
        reasons.append("STRUCTURAL_REJECT")
    if (sum(b > 0 for b, _ in e_betas) < 2 or any(z <= -2 for _, z in e_betas) or not pooled_beta > 0 or len(e_betas) != 3):
        reasons.append("SIGN_INSTABILITY_REJECT")
    if not within_var >= WITHIN_VAR_MIN:
        reasons.append("INSUFFICIENT_WITHIN_RACE_VARIATION")
    if not n_calendar <= N_CALENDAR_MAX:
        reasons.append("PRIMARY_INFEASIBLE")
    return {"passed": not reasons, "reasons": reasons}


def verdict_from_results(results_dir: Path) -> dict:
    """e0 / e1 / e2 / gate の成果物を読み、台帳 A2-1 の門を 1 回だけ判定する (入力と各ファイルの sha256 を同梱)。欠けた入力は KeyError で止まる。"""
    paths = {m: results_dir / m / f"{m}_result.json" for m in ("e0", "e1", "e2", "gate")}
    res = {m: json.loads(p.read_text(encoding="utf-8")) for m, p in paths.items()}
    e_betas = [(d["beta_S"], d["z_S"]) for d in res["e1"]["directions"] + res["e2"]["directions"]]
    inputs = {"construct_r2": res["e0"]["structural"]["within_race_r2_S_on_finish_only"]["r2"], "e_betas": e_betas,
              "pooled_beta": res["gate"]["pooled_in_sample"]["beta_S"], "within_var": res["gate"]["within_var_gate_value"],
              "n_calendar": res["gate"]["n_calendar_required"]}
    return {"inputs": inputs, "verdict": gate_verdict(**inputs), "money": res["gate"]["purchase_projection"],
            "sources": {m: {"path": pr.rel(ROOT, p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                            "git_sha": res[m]["provenance"]["git_sha"], "git_dirty": res[m]["provenance"]["git_dirty"]}
                        for m, p in paths.items()}}


def run(mode: str, out_dir: Path, db_path: Path) -> dict:
    if mode == "verdict":
        out = {"mode": mode, **verdict_from_results(out_dir.parent)}
        out["provenance"] = pr.provenance(ROOT, DEPENDENCIES, db_path, sys.argv, own_output=pr.rel(ROOT, out_dir))
        out_dir.mkdir(parents=True, exist_ok=True)
        pr.write_json(out_dir / "verdict_result.json", out)
        return out
    races, load_stats = ga.load_races(2024, min_year=2021, db_path=db_path)
    out: dict = {"mode": mode, "load_stats": dict(load_stats)}
    if mode == "e0":
        fit_years, (ev_year,) = E2_DIRECTION
        rows, summary, rate = prepare(races, fit_years, (fit_years, (ev_year,)))
        comp = a2.fit_composite(rows[fit_years])
        ev = a2.rows_without_outcome(a2.apply_composite(rows[(ev_year,)], comp))
        out.update({"fit_years": list(fit_years), "eval_year": ev_year, "years": summary, "rating_stats": rate,
                    "weights": comp["weights"], "zeroed": comp["zeroed"], "structural": a2.structural(ev),
                    "note": "結果の列を使わない (2024 の行から won を除いてから測る)。合成の当てはめは 2022-2023 の結果を使う"})
    elif mode in ("e1", "e2"):
        out["directions"] = []
        for fit_years, ev_years in (E1_DIRECTIONS if mode == "e1" else [E2_DIRECTION]):
            rows, summary, rate = prepare(races, fit_years, (fit_years, ev_years))
            d = {"fit_years": list(fit_years), "eval_years": list(ev_years), "years": summary, "rating_stats": rate,
                 **evaluate(rows[fit_years], rows[ev_years])}
            out["directions"].append(d)
    else:
        fit_years, (ev_year,) = E2_DIRECTION
        rows, summary, _ = prepare(races, fit_years, (fit_years, (ev_year,)))
        comp = a2.fit_composite(rows[fit_years])
        ev = a2.apply_composite(rows[(ev_year,)], comp)
        boot = train_boot_se(a2.apply_composite(rows[fit_years], comp))
        power = a2.outcome_blind_power(ev, pr.BETA_TARGET, pr.CRITICAL_MULTIPLIER, boot["se"], boot["n_races"])
        se_scaled, sigma1, n_primary = power["se_train_scaled"], power["sigma_per_race"], power["n_primary_required"]
        n_flat = confirmed_flat_jra_races(db_path, ev_year)
        r = power["n_races"] / n_flat
        buys = len(mc.ratio_buys_at(a2.rows_without_outcome(ev), 1.0, pr.BETA_TARGET, s_col="S"))
        pooled_rows, _, _ = prepare(races, POOLED_YEARS, (POOLED_YEARS,))
        pooled = evaluate(pooled_rows[POOLED_YEARS], pooled_rows[POOLED_YEARS])
        vd = cp.variance_decomposition(ev, "S")
        out.update({"years": summary, "variance_decomposition_2024": vd,
                    "within_var_gate_value": vd["market_weighted_within_var_per_race"],
                    "power": power, "train_bootstrap": boot, "se_train_scaled": se_scaled, "sigma_per_race_fixed": sigma1,
                    "n_primary_required": n_primary, "confirmed_flat_jra_races_2024": n_flat, "r": r,
                    "n_calendar_required": math.ceil(n_primary / r),
                    "purchase_projection": {"n_buys_2024": buys, "n_races_2024": power["n_races"],
                                            "per_100_races": 100 * buys / power["n_races"], **money_state(buys, power["n_races"])},
                    "pooled_in_sample": {k: pooled[k] for k in ("beta_market", "beta_S", "se_S", "z_S")},
                    "pooled_composite": pooled["composite"]})
    out["provenance"] = pr.provenance(ROOT, DEPENDENCIES, db_path, sys.argv, own_output=pr.rel(ROOT, out_dir))
    out_dir.mkdir(parents=True, exist_ok=True)
    pr.write_json(out_dir / f"{mode}_result.json", out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=MODES, required=True)
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
    if a.mode == "e0":
        s = out["structural"]
        print(f"construct R2 (S ~ finish) {s['within_race_r2_S_on_finish_only']['r2']:.3f} / "
              f"R2 (S ~ finish + logP) {s['within_race_r2_S_on_finish_and_market']['r2']:.3f} / corr(S, logP) {s['within_race_corr_S_log_p']:.3f}")
    elif a.mode in ("e1", "e2"):
        for d in out["directions"]:
            print(f"{d['fit_years']} -> {d['eval_years']}: beta_S {d['beta_S']:+.4f} z {d['z_S']:+.2f} / beta_market {d['beta_market']:.3f}")
    elif a.mode == "verdict":
        print(f"verdict {out['verdict']} / money {out['money']['state']}")
    else:
        print(f"within var {out['within_var_gate_value']:.3f} / N_primary {out['n_primary_required']} / r {out['r']:.3f} / "
              f"N_calendar {out['n_calendar_required']} / pooled beta_S {out['pooled_in_sample']['beta_S']:+.4f} / "
              f"money {out['purchase_projection']['state']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
