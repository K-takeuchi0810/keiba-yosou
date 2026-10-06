"""事前登録 0.5-5 §8-6b の表の再現: 学習期 2022-2024 だけで、市場の項を logit(P) と log(P) で入れたときの β_market (2025 は読まない)。

対象の定義は Group A の `target_samples` と同じ (JRA・確定・平地、勝ち馬 1 頭、返還の対象 1/2/3 を除き、残りの全馬に価格、
残りで和 1 に正規化し直す)。市場だけの条件付きロジット (`predictor.eval_stats.conditional_logit`) と、β = 1 に固定したときの
1 レースあたりの平均対数尤度を出す。

usage (worktree の root で):
    .venv64/Scripts/python.exe data/backtest/eval_refund_20261006/market_term_table.py <out.json> [--db <keiba.db>]
"""
import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from predictor.eval_stats import conditional_logit  # noqa: E402
from predictor.provenance import git_dirty, git_sha  # noqa: E402
from scripts import group_a as ga  # noqa: E402


def year_rows(races, year):
    rows = []
    for r in races.values():
        if int(r.ymd[:4]) != year:
            continue
        winners = [x for x in r.runs if x.finish == 1]
        if len(winners) != 1:
            continue
        choice = [x for x in r.runs if x.abnormal not in ga.REFUNDED]
        if any(x.win_odds <= 0 for x in choice) or winners[0] not in choice:
            continue
        inv = [1 / x.win_odds for x in choice]
        t = sum(inv)
        for x, q in zip(choice, inv):
            p = q / t
            rows.append({"race_id": r.race_id, "won": int(x.finish == 1),
                         "z_logit": math.log(p / (1 - p)), "z_log": math.log(p)})
    return rows


def mean_ll_at_one(rows, key):
    by = defaultdict(list)
    for x in rows:
        by[x["race_id"]].append(x)
    s = 0.0
    for rs in by.values():
        m = max(x[key] for x in rs)
        den = sum(math.exp(x[key] - m) for x in rs)
        w = [x for x in rs if x["won"]][0]
        s += w[key] - m - math.log(den)
    return s / len(by), len(by)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--db", default=None)
    a = ap.parse_args()
    kw = {"db_path": a.db} if a.db else {}
    races, _ = ga.load_races(2024, min_year=2022, **kw)     # 2025 は load_races が拒否する (allow_primary_year なし)
    out = {"purpose": "prereg 0.5-5 §8-6b table (training years only, 2025 not read)",
           "git_sha": git_sha(), "git_dirty": bool(git_dirty()), "years": {}}
    for year in (2022, 2023, 2024):
        rows = year_rows(races, year)
        b_logit, ok1 = conditional_logit(rows, ["z_logit"], with_status=True)
        b_log, ok2 = conditional_logit(rows, ["z_log"], with_status=True)
        ll_logit, n = mean_ll_at_one(rows, "z_logit")
        ll_log, _ = mean_ll_at_one(rows, "z_log")
        out["years"][str(year)] = {"races": n, "horses": len(rows),
                                   "beta_market_logit": b_logit[0], "converged_logit": ok1,
                                   "beta_market_log": b_log[0], "converged_log": ok2,
                                   "mean_loglik_at_beta1_logit": ll_logit, "mean_loglik_at_beta1_log": ll_log}
        print(year, out["years"][str(year)])
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
