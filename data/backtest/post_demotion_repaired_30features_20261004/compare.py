"""凍結 4B (repaired 31-feature) と post-demotion repaired 30-feature の比較 (2026-10-04)。

受理の判定は docs/PHASE05_RESULTS.md「post-demotion repaired 30-feature の学習 — 事前固定」の 2 条件だけ:
  (a) β₂ の 95% 区間が 4B の区間と重なる
  (b) 30 特徴それぞれ・validation と strategy_dev それぞれで、域外率が 4B の値 + 0.5pt 以下
それ以外の数値は比較のために記録するだけで、判定には使わない。

DB には触れない (評価 JSON・サンプル CSV・域外監査 JSON だけを読む)。

usage (worktree の根で):
    .venv64/Scripts/python.exe data/backtest/post_demotion_repaired_30features_20261004/compare.py
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BT = HERE.parent
FROZEN = BT / "frozen_4b_repaired_31features_20260919"
SRC = {
    "4b": {"eval": FROZEN / "20260919_phase05_4B_market_offset.json",
           "samples": FROZEN / "20260919_phase05_4B_samples.csv",
           "domain": BT / "20260919_feature_domain_after.json"},
    "30": {"eval": HERE / "post_demotion_market_offset_eval.json",
           "samples": HERE / "post_demotion_market_offset_samples.csv",
           "domain": HERE / "feature_domain_post_demotion.json"},
}
DOMAIN_TOLERANCE = 0.005            # 事前固定: 4B + 0.5pt
MAX_LEAD_MINUTES = 30.0             # 主分析 (鮮度内) の定義。評価 JSON の meta と照合する
BUY_EDGE = 0.05                     # 購入条件 (5pt 超)。評価 JSON の meta と照合する
N_BOOT = 2000
SEED = 20261004


def load_samples(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in ("won", "lead_min", "p_t10", "p_offset", "edge"):
            r[k] = float(r[k])
    return rows


def ll(rows: list[dict], key: str) -> float:
    return -float(np.mean([math.log(r[key]) if r["won"] else math.log(1 - r[key]) for r in rows]))


def race_bootstrap(rows: list[dict], stat, n: int = N_BOOT, seed: int = SEED) -> list[float]:
    """レース単位の再抽選で stat(rows) の 95% 区間。"""
    by_race = defaultdict(list)
    for r in rows:
        by_race[r["race_id"]].append(r)
    races = sorted(by_race)
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n):
        pick = rng.integers(0, len(races), len(races))
        vals.append(stat([r for i in pick for r in by_race[races[i]]]))
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]


def describe(rows: list[dict]) -> dict:
    ratio = np.array([r["p_offset"] / r["p_t10"] for r in rows])
    by_race = defaultdict(list)
    for r in rows:
        by_race[r["race_id"]].append(r)
    same_top = [max(rs, key=lambda r: r["p_offset"]) is max(rs, key=lambda r: r["p_t10"]) for rs in by_race.values()]
    d_ll = ll(rows, "p_offset") - ll(rows, "p_t10")
    return {
        "n_races": len(by_race), "n_horses": len(rows),
        "log_loss_offset": ll(rows, "p_offset"), "log_loss_t10": ll(rows, "p_t10"),
        "delta_log_loss_offset_minus_t10": d_ll,
        "delta_log_loss_ci95": race_bootstrap(rows, lambda rs: ll(rs, "p_offset") - ll(rs, "p_t10")),
        "abs_correction_mean_pt": float(np.mean([abs(r["p_offset"] - r["p_t10"]) for r in rows]) * 100),
        "abs_correction_max_pt": float(np.max([abs(r["p_offset"] - r["p_t10"]) for r in rows]) * 100),
        "ratio_max": float(ratio.max()), "ratio_p95": float(np.percentile(ratio, 95)),
        "ratio_p99": float(np.percentile(ratio, 99)), "log_ratio_sd": float(np.log(ratio).std()),
        "n_ratio_ge_1_25": int((ratio >= 1.25).sum()), "n_ratio_ge_1_75": int((ratio >= 1.75).sum()),
        "n_purchase_condition": int(sum(r["edge"] > BUY_EDGE for r in rows)),
        "share_top1_equals_market_favourite": float(np.mean(same_top)),
    }


def domain_check(dom4b: dict, dom30: dict) -> dict:
    rates4b = {f["feature"]: f["out_of_train_range"] for f in dom4b["features"]}
    rows, fails = [], []
    for f in dom30["features"]:
        if f.get("audit_only"):
            continue
        for split in ("validation", "strategy_dev"):
            new, old = f["out_of_train_range"][split], rates4b[f["feature"]][split]
            ok = new <= old + DOMAIN_TOLERANCE
            rows.append({"feature": f["feature"], "split": split, "rate_4b": old, "rate_30": new, "ok": ok})
            if not ok:
                fails.append(rows[-1])
    n_features = len({r["feature"] for r in rows})
    return {"n_features_checked": n_features, "tolerance": DOMAIN_TOLERANCE, "pass": not fails and n_features == 30,
            "failures": fails,
            "max_rate": {s: max((r for r in rows if r["split"] == s), key=lambda r: r["rate_30"]) for s in
                         ("validation", "strategy_dev")},
            "rows": rows}


def main() -> int:
    ev = {k: json.loads(v["eval"].read_text(encoding="utf-8")) for k, v in SRC.items()}
    for k in ev:
        assert ev[k]["meta"]["max_lead_minutes"] == MAX_LEAD_MINUTES, k
        assert ev[k]["meta"]["buy_edge_pt"] == BUY_EDGE, k
        assert (ev[k]["meta"]["from_date"], ev[k]["meta"]["to_date"]) == ("20260509", "20260831"), k
    samples = {k: load_samples(v["samples"]) for k, v in SRC.items()}
    fresh = {k: [r for r in rows if r["lead_min"] <= MAX_LEAD_MINUTES] for k, rows in samples.items()}

    p4b, p30 = ev["4b"]["primary_conditional_logit"], ev["30"]["primary_conditional_logit"]
    lo4, hi4 = p4b["coef_correction_ci95"]
    lo3, hi3 = p30["coef_correction_ci95"]
    cond_a = max(lo4, lo3) <= min(hi4, hi3)

    dom = domain_check(json.loads(SRC["4b"]["domain"].read_text(encoding="utf-8")),
                       json.loads(SRC["30"]["domain"].read_text(encoding="utf-8")))

    # 同じ評価集合か (馬の集合が一致するか)。一致する馬で 4B ↔ 30 の補正の相関と LogLoss の対差を出す
    key = lambda r: (r["race_id"], r["horse_num"])  # noqa: E731
    f4 = {key(r): r for r in fresh["4b"]}
    f3 = {key(r): r for r in fresh["30"]}
    common = sorted(set(f4) & set(f3))
    lr4 = np.array([math.log(f4[k]["p_offset"] / f4[k]["p_t10"]) for k in common])
    lr3 = np.array([math.log(f3[k]["p_offset"] / f3[k]["p_t10"]) for k in common])
    t10_same = all(abs(f4[k]["p_t10"] - f3[k]["p_t10"]) < 1e-12 for k in common)
    paired_rows = [{"race_id": k[0], "won": f4[k]["won"], "a": f4[k]["p_offset"], "b": f3[k]["p_offset"]} for k in common]
    paired_d = ll([{**r, "p": r["b"]} for r in paired_rows], "p") - ll([{**r, "p": r["a"]} for r in paired_rows], "p")
    paired_ci = race_bootstrap(paired_rows, lambda rs: ll([{**r, "p": r["b"]} for r in rs], "p")
                               - ll([{**r, "p": r["a"]} for r in rs], "p"))

    out = {
        "acceptance": {
            "a_beta2_ci_overlaps_4b": {"pass": cond_a, "ci_4b": [lo4, hi4], "ci_30": [lo3, hi3]},
            "b_domain_not_worse": {k: v for k, v in dom.items() if k != "rows"},
            "accepted": bool(cond_a and dom["pass"]),
        },
        "comparison_not_used_for_decision": {
            "beta2": {"4b": p4b["coef_correction"], "30": p30["coef_correction"]},
            "beta_market": {"4b": p4b["coef_market"], "30": p30["coef_market"]},
            "verdict": {"4b": ev["4b"]["verdict"], "30": ev["30"]["verdict"]},
            "sets": {"4b": ev["4b"]["sets"], "30": ev["30"]["sets"]},
            "fresh_t10": {"4b": describe(fresh["4b"]), "30": describe(fresh["30"])},
            "paired": {"n_common_horses": len(common), "n_only_4b": len(set(f4) - set(f3)),
                       "n_only_30": len(set(f3) - set(f4)), "t10_market_identical": t10_same,
                       "corr_log_ratio_4b_vs_30": float(np.corrcoef(lr4, lr3)[0, 1]),
                       "log_loss_30_minus_4b": paired_d, "log_loss_30_minus_4b_ci95": paired_ci},
            "audit_rates_eval_rows_30": ev["30"]["meta"].get("audit_rates_eval_rows"),
            "audit_rates_by_year_eval_rows_30": ev["30"]["meta"].get("audit_rates_by_year_eval_rows"),
            "model_feature_schema_30": {k: ev["30"]["meta"]["model_feature_schema"].get(k) for k in
                                        ("schema_source", "n_features", "matches_current_features",
                                         "model_sha256", "model_meta")},
            "domain_audit_rates_30": json.loads(SRC["30"]["domain"].read_text(encoding="utf-8"))["meta"].get(
                "audit_rates_by_year"),
        },
        "notes": [
            "判定は acceptance の 2 条件だけ (事前固定)。comparison の数値は判定に使わない",
            "β₂ が良くなっても新しい信号とは見なさない (打ち切りの情報は他の特徴から部分的に復元できる = 希釈)",
            f"区間はレース単位の再抽選 n={N_BOOT} seed={SEED}。4B の評価 JSON の β₂ の区間は n_boot=300",
        ],
        "inputs": {k: {n: str(p.relative_to(BT)) for n, p in v.items()} for k, v in SRC.items()},
    }
    (HERE / "comparison_4b_vs_30.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    a = out["acceptance"]
    print(f"(a) β₂ CI 4B [{lo4:+.3f}, {hi4:+.3f}] / 30 [{lo3:+.3f}, {hi3:+.3f}] -> {'PASS' if cond_a else 'FAIL'}")
    print(f"(b) 域外率 (4B + 0.5pt 以下、{dom['n_features_checked']} 特徴) -> {'PASS' if dom['pass'] else 'FAIL'}"
          f" 失敗 {len(dom['failures'])} 件")
    print(f"受理: {a['accepted']}")
    print(json.dumps(out["comparison_not_used_for_decision"]["fresh_t10"], ensure_ascii=False, indent=1))
    print(json.dumps(out["comparison_not_used_for_decision"]["paired"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
