"""C′ の仮説の直接の診断 (学習期 2022-2024 だけ、2025 は読まない。仕様の変更には使わない)。2026-10-06、凍結の前の 4 名レビュー (ddc12b6) の
prediction-logic の must-fix 2 を受けて、事前登録 §2 C の反証の条件と脚質の推定の精度を記録する。

1. pace_pressure の三分位 × 前 (逃・先) / 後 (差・追) ごとの 実勝利数 / Σ P_market (市場が校正されていれば 1)
2. 過去走から推定した脚質と、対象レース自身の実際の脚質コードの一致 (対象レースの値は **この診断にだけ** 使う)
3. レース内の相関: style_x_pace_fit と脚質の指示 (前 −1 / 後 +1)、2 成分の間
4. 脚質が不明の馬の 365 日以内の出走数と、実勝利数 / Σ P_market

usage (worktree の root で):
    .venv64/Scripts/python.exe data/backtest/c_prime_20261006/diag/hypothesis_diagnostics.py <out.json> --db <keiba.db>
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

from scripts import c_prime as cp  # noqa: E402

YEARS = (2022, 2023, 2024)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--db", required=True)
    a = ap.parse_args()
    races, _ = cp.load_races(2024, min_year=2021, db_path=a.db)
    history, experience = cp.style_history(races), cp.experience_index(races)
    c, ex = Counter(), []
    rows = cp.target_rows(races, YEARS, history, experience, c, ex)
    actual = {(r.race_id, x.horse_num): x.leg for r in races.values() for x in r.runs}

    # レースごとの pace_pressure (既知の馬から)
    by = defaultdict(list)
    for r in rows:
        by[r["race_id"]].append(r)
    pace = {}
    for rid, rs in by.items():
        known = [r["style"] for r in rs if r["style"]]
        if known:
            pace[rid] = (sum(s == "1" for s in known) + 0.5 * sum(s == "2" for s in known)) / len(known)
    q1, q2 = np.quantile(list(pace.values()), [1 / 3, 2 / 3])

    def tercile(p):
        return "low" if p <= q1 else ("mid" if p <= q2 else "high")

    cal = defaultdict(lambda: [0, 0.0, 0])
    for r in rows:
        if not r["style"] or r["race_id"] not in pace:
            continue
        t = tercile(pace[r["race_id"]])
        side = "front" if r["style"] in cp.FRONT else "back"
        for key in (f"{t}|{side}", f"{t}|style{r['style']}"):
            cal[key][0] += r["won"]
            cal[key][1] += r["p_market"]
            cal[key][2] += 1
    calibration = {k: {"wins": v[0], "sum_p_market": v[1], "n": v[2], "ratio": v[0] / v[1] if v[1] else None}
                   for k, v in sorted(cal.items())}

    # 推定した脚質と実際の脚質
    pairs = [(r["style"], actual.get((r["race_id"], r["horse_num"]), "")) for r in rows if r["style"]]
    pairs = [(e, t) for e, t in pairs if t in cp.STYLE_CODES]
    n = len(pairs)
    agree4 = sum(e == t for e, t in pairs) / n
    bin_e = [e in cp.FRONT for e, _ in pairs]
    bin_t = [t in cp.FRONT for _, t in pairs]
    agree2 = sum(x == y for x, y in zip(bin_e, bin_t)) / n
    base2 = max(sum(bin_t), n - sum(bin_t)) / n
    pe = (sum(bin_e) / n) * (sum(bin_t) / n) + (1 - sum(bin_e) / n) * (1 - sum(bin_t) / n)
    kappa2 = (agree2 - pe) / (1 - pe)
    confusion = Counter((e, t) for e, t in pairs)
    recall_nige = confusion[("1", "1")] / sum(v for (e, t), v in confusion.items() if t == "1")
    precision_nige = confusion[("1", "1")] / sum(v for (e, t), v in confusion.items() if e == "1")

    # レース内の相関
    comp = cp.fit_composite(rows)
    srows = cp.apply_composite(rows, comp)
    for r in srows:
        r["style_indicator"] = -1.0 if r["style"] in cp.FRONT else (1.0 if r["style"] in cp.BACK else 0.0)
    corr = {"pace_fit_std__style_indicator": cp.within_race_corr(srows, "style_x_pace_fit_std", "style_indicator"),
            "front_comp_std__style_indicator": cp.within_race_corr(srows, "front_competition_signed_std", "style_indicator"),
            "pace_fit_std__front_comp_std": cp.within_race_corr(srows, "style_x_pace_fit_std", "front_competition_signed_std"),
            "S__style_indicator": cp.within_race_corr(srows, "S", "style_indicator")}
    ind_fit = cp.clogit_with_se(srows, ["style_indicator"])
    joint = cp.clogit_with_se(srows, ["style_indicator", "S"])
    pooled = cp.clogit_with_se(srows, ["S"])

    unknown = [r for r in rows if not r["style"]]
    known = [r for r in rows if r["style"]]
    out = {"purpose": "C′ の仮説の直接の診断 (学習期 2022-2024、仕様の変更に使わない)", "years": list(YEARS),
           "n_rows": len(rows), "pace_terciles": [float(q1), float(q2)],
           "calibration_wins_over_sum_p_market": calibration,
           "style_estimate_vs_actual": {"n": n, "agree_4class": agree4, "agree_front_back": agree2,
                                        "baseline_majority_front_back": base2, "kappa_front_back": kappa2,
                                        "nige_recall": recall_nige, "nige_precision": precision_nige,
                                        "confusion": {f"est{e}|act{t}": v for (e, t), v in sorted(confusion.items())}},
           "within_race_corr": corr,
           "pooled_2022_2024_in_sample": {"composite_weights": comp["weights"], "component_z_max": comp["component_z_max"],
                                          "single_component_fits": comp["single_component_fits"],
                                          "S": {"beta": pooled["beta"][1], "se": pooled["se"][1], "z": pooled["z"][1]},
                                          "style_indicator_only": {"beta": ind_fit["beta"][1], "z": ind_fit["z"][1]},
                                          "joint_indicator_and_S": {"beta_indicator": joint["beta"][1], "z_indicator": joint["z"][1],
                                                                    "beta_S": joint["beta"][2], "z_S": joint["z"][2]}},
           "unknown_style": {"n": len(unknown), "share_no_runs_365": sum(r["n_runs_365"] == 0 for r in unknown) / len(unknown),
                             "wins_over_sum_p": sum(r["won"] for r in unknown) / sum(r["p_market"] for r in unknown),
                             "known_wins_over_sum_p": sum(r["won"] for r in known) / sum(r["p_market"] for r in known)}}
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("style_estimate_vs_actual", "within_race_corr", "pooled_2022_2024_in_sample")},
                     ensure_ascii=False, indent=1)[:3000])
    print({k: round(v["ratio"], 3) for k, v in calibration.items()})


if __name__ == "__main__":
    main()
