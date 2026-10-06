"""Group D の構造的な非識別の確認 (学習期 2022-2024 だけ、2025 は読まない。2026-10-06、外部の指示者の決定 (2) の記録のため)。

停止の理由に使う量は、係数の値や符号 (β・z) ではなく、次の **構造の量** だけ:
1. レース内で S_std と前走の評価値 (Group A の last と同じ関数) の相関、S_std を [前走の評価値, class_move] で線形回帰したときの決定係数
   (結果の列を使わない)
2. §2 D の仮説が現れる交互作用 S × class_move の係数の SE (条件付きロジットのヘッセ行列から) を、主検定の年のレース数に換算した MDE
   (SE だけを使う。係数の値は判定に使わない)
3. 件数の見込み (§8-8 / §8-4d と同じ `market_clogit.ratio_buys_at(rows, 1.0, β_target)`、仮定値で数える。結果の列を使わない)。
   学習期の年ごとと 3 年 pooled (2026-10-06 レビューの指摘で追加。文書の「0.6 頭 / 100 レース」の出典)

usage (worktree の root で):
    .venv64/Scripts/python.exe data/backtest/group_d_20261006/structural/structural_check.py <out.json> --db <keiba.db>
"""
import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
import numpy as np  # noqa: E402

from predictor import market_clogit as mc  # noqa: E402
from scripts import c_prime as cp  # noqa: E402
from scripts import group_d_explore as gde  # noqa: E402
from scripts import group_a as ga  # noqa: E402
from scripts import group_d as gd  # noqa: E402
from scripts import prereg_runner as pr  # noqa: E402

YEARS = (2022, 2023, 2024)
DEPENDENCIES = gde.DEPENDENCIES + ("data/backtest/group_d_20261006/structural/structural_check.py",
                                   "data/backtest/group_d_20261006/e2/e2_result.json")
E2_RESULT = ROOT / "data/backtest/group_d_20261006/e2/e2_result.json"


def e2_target_races_2024() -> int:
    """主検定の年のレース数の代わりに使う 2024 の対象レース数 (E2 の成果物から読む。手書きの写しにしない)。"""
    e2 = json.loads(E2_RESULT.read_text(encoding="utf-8"))
    return int(e2["directions"][0]["years"]["2024"]["counts"]["target_races_used"])


def within_r2(rows, y, xs):
    """レース内で中心化した y を、レース内で中心化した xs で最小二乗 (等重み)。決定係数と係数。"""
    by = defaultdict(list)
    for r in rows:
        by[r["race_id"]].append(r)
    Y, X = [], []
    for rs in by.values():
        yy = np.array([r[y] for r in rs], dtype=float)
        xx = np.array([[r[c] for c in xs] for r in rs], dtype=float)
        Y.extend(yy - yy.mean())
        X.extend(xx - xx.mean(axis=0))
    Y, X = np.array(Y), np.array(X)
    coef, *_ = np.linalg.lstsq(X, Y, rcond=None)
    resid = Y - X @ coef
    return {"r2": float(1 - (resid @ resid) / (Y @ Y)), "coef": dict(zip(xs, map(float, coef)))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--db", required=True)
    a = ap.parse_args()
    races, _ = ga.load_races(2024, min_year=2021, db_path=a.db)
    tables = ga.fit_tables(races, gd.SPEC, YEARS)
    history = gd.run_ratings(races, tables)
    req = gd.Requirements(races, gd.winner_ratings(races, history))
    c, ex = Counter(), []
    rows = gd.target_rows(races, YEARS, history, req, c, ex)
    sd_s = gd.fit_scale(rows)["sd"]
    prev_sd = cp.within_sd([r for r in rows if not math.isnan(r["S_raw"])], "prev_rating")["sd"]
    srows = gd.standardize_and_fill(rows, sd_s)
    obs = [r for r in srows if not math.isnan(r["S_raw"])]
    for r in obs:
        r["prev_std"] = r["prev_rating"] / prev_sd
    out = {"purpose": "Group D の構造的な非識別の確認 (学習期だけ、停止の理由に β・z は使わない)", "years": list(YEARS),
           "n_rows_observed": len(obs), "n_races": len({r["race_id"] for r in srows})}
    out["within_race_corr_S_std_prev_std"] = cp.within_race_corr(obs, "S_std", "prev_std")
    out["within_race_r2_S_on_prev_and_move"] = within_r2(obs, "S_std", ["prev_std", "class_move"])
    out["within_race_r2_S_on_prev_only"] = within_r2(obs, "S_std", ["prev_std"])
    # 交互作用の SE → 主検定の年のレース数に換算した MDE (SE だけを使う)
    for r in srows:
        r["S_x_move"] = r["S_std"] * r["class_move_filled"]
    fit = cp.clogit_with_se(srows, ["class_move_filled", "S_std", "S_x_move"])
    n_train = len({r["race_id"] for r in srows})
    n_target_proxy = e2_target_races_2024()                  # 2024 の対象レース数 (E2) を主検定の年の代わりに使う (2025 は読まない)
    se_int = fit["se"][3]
    se_int_target = se_int * math.sqrt(n_train / n_target_proxy)
    out["interaction_S_x_move"] = {"se_train_pooled": se_int, "n_train_races": n_train, "n_target_races_proxy": n_target_proxy,
                                   "se_scaled_to_target": se_int_target, "mde": pr.CRITICAL_MULTIPLIER * se_int_target,
                                   "beta_target": pr.BETA_TARGET,
                                   "note": "SE だけを使う。係数の値は記録もしない (停止の理由に使わないため)"}
    # 交互作用の取り方による違い: S × 1[class_move > 0] (昇級の有無)
    for r in srows:
        r["riser"] = 1.0 if r["class_move_filled"] > 0 else 0.0
        r["S_x_riser"] = r["S_std"] * r["riser"]
    fit2 = cp.clogit_with_se(srows, ["class_move_filled", "S_std", "riser", "S_x_riser"])
    se2 = fit2["se"][4] * math.sqrt(n_train / n_target_proxy)
    out["interaction_S_x_riser"] = {"se_train_pooled": fit2["se"][4], "se_scaled_to_target": se2, "mde": pr.CRITICAL_MULTIPLIER * se2,
                                    "share_risers": sum(r["riser"] for r in srows) / len(srows),
                                    "note": "S × 昇級の有無 (0/1)。係数の値は記録しない"}
    share_risers = out["interaction_S_x_riser"]["share_risers"]
    out["note_interaction_units"] = ("交互作用の MDE は取り方で大きく変わる: S × class_move (整数、-4〜+4) は大きな昇降の行が SE を下げ、"
                                     f"S × 1[昇級] は昇級の行 (約 {share_risers:.1%}) だけで識別する。§2 D の『同じ昇級でも中身が違う』に近いのは後者")
    # 件数の見込み (仮定値 β_market = 1・β_S = β_target、β_move = 0。§8-4d と同じ関数)
    proj = {}
    for label, yrs in [(str(y), (y,)) for y in YEARS] + [("pooled_2022_2024", YEARS)]:
        sub = [r for r in srows if r["year"] in yrs]
        n_r = len({r["race_id"] for r in sub})
        n_b = len(mc.ratio_buys_at(sub, 1.0, pr.BETA_TARGET, s_col="S_std"))
        proj[label] = {"n_races": n_r, "n_buys": n_b, "per_100_races": 100 * n_b / n_r,
                       "races_for_1500": 1500 * n_r / n_b if n_b else None}
    out["purchase_projection_at_beta_target"] = {
        "by_year": proj, "method": "market_clogit.ratio_buys_at(rows, 1.0, BETA_TARGET, s_col='S_std')、尺度は 2022-2024 の pooled within-race SD",
        "note": "仮定値で数える件数の見込み (§8-8)。β̂ は使わない"}
    out["share_class_move_zero"] = sum(r["class_move"] == 0 for r in obs) / len(obs)
    out["provenance"] = pr.provenance(ROOT, DEPENDENCIES, a.db, sys.argv, own_output=pr.rel(ROOT, Path(a.out).resolve()))
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
