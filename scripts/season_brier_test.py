"""H3-2: 同季節 Brier 悪化の Welch t-test + bootstrap CI.

P19 B1-S0 Step 2: v4 §1.1 N1 月次 Brier 表から 2025-01〜05 と 2026-01〜05 の
5 ペアを抽出し、Welch (= unpaired, equal_var=False) t-test と paired t-test、
さらに 10000 回 bootstrap CI で delta = mean(2026) - mean(2025) の不確実性を
評価する。

Gate-2 (a) 判定: Welch p < 0.05 → 「弱く棄却」以上 = Gate-2 (a) PASS。

実行: python -m scripts.season_brier_test
出力: data/h3_2_season_brier_test.log
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy import stats


# v4 §1.1 N1 月次 Brier 表 (p_win Brier) からハードコード
# (n は month sample size、Brier は p_win Brier)
MONTHLY_BRIER_2025 = {
    "2025-01": {"n": 240, "brier": 0.0996},
    "2025-02": {"n": 300, "brier": 0.0922},
    "2025-03": {"n": 336, "brier": 0.0914},
    "2025-04": {"n": 264, "brier": 0.0712},
    "2025-05": {"n": 312, "brier": 0.0906},
}
MONTHLY_BRIER_2026 = {
    "2026-01": {"n": 276, "brier": 0.0601},
    "2026-02": {"n": 324, "brier": 0.0791},
    "2026-03": {"n": 300, "brier": 0.0807},
    "2026-04": {"n": 264, "brier": 0.1167},
    "2026-05": {"n": 144, "brier": 0.1250},
}


def bootstrap_delta_ci(
    arr2025: np.ndarray,
    arr2026: np.ndarray,
    n_resample: int = 10000,
    ci_level: float = 0.95,
    rng_seed: int = 20260524,
) -> dict:
    """Resample monthly Brier values with replacement, compute delta = mean(2026) - mean(2025)."""
    rng = np.random.default_rng(rng_seed)
    n25 = len(arr2025)
    n26 = len(arr2026)
    deltas = np.empty(n_resample, dtype=np.float64)
    for i in range(n_resample):
        s25 = rng.choice(arr2025, size=n25, replace=True)
        s26 = rng.choice(arr2026, size=n26, replace=True)
        deltas[i] = s26.mean() - s25.mean()
    alpha = (1.0 - ci_level) / 2.0
    lo = float(np.quantile(deltas, alpha))
    hi = float(np.quantile(deltas, 1.0 - alpha))
    median = float(np.median(deltas))
    p_pos = float(np.mean(deltas > 0.0))  # P(delta > 0 | bootstrap)
    return {
        "n_resample": n_resample,
        "ci_level": ci_level,
        "lo": lo,
        "median": median,
        "hi": hi,
        "p_delta_gt_0": p_pos,
        "observed_delta": float(arr2026.mean() - arr2025.mean()),
    }


def run_tests(arr2025: np.ndarray, arr2026: np.ndarray, label: str) -> dict:
    """Run Welch (unpaired, equal_var=False) + paired t-test on monthly Brier arrays."""
    welch = stats.ttest_ind(arr2026, arr2025, equal_var=False)
    paired = stats.ttest_rel(arr2026, arr2025)

    boot = bootstrap_delta_ci(arr2025, arr2026, n_resample=10000)

    return {
        "label": label,
        "n_2025": int(len(arr2025)),
        "n_2026": int(len(arr2026)),
        "mean_2025": float(arr2025.mean()),
        "mean_2026": float(arr2026.mean()),
        "std_2025": float(arr2025.std(ddof=1)) if len(arr2025) > 1 else 0.0,
        "std_2026": float(arr2026.std(ddof=1)) if len(arr2026) > 1 else 0.0,
        "delta": float(arr2026.mean() - arr2025.mean()),
        "welch_t": float(welch.statistic),
        "welch_p_two_sided": float(welch.pvalue),
        "welch_p_one_sided_greater": float(welch.pvalue) / 2.0
        if welch.statistic > 0
        else 1.0 - float(welch.pvalue) / 2.0,
        "paired_t": float(paired.statistic),
        "paired_p_two_sided": float(paired.pvalue),
        "paired_p_one_sided_greater": float(paired.pvalue) / 2.0
        if paired.statistic > 0
        else 1.0 - float(paired.pvalue) / 2.0,
        "bootstrap": boot,
    }


def gate2a_verdict(p_two_sided: float) -> str:
    """v4 §0.1 rubric 適用"""
    if p_two_sided < 0.01:
        return "確定的に棄却 (p<0.01) = Gate-2 (a) PASS (strong)"
    elif p_two_sided < 0.05:
        return "強く棄却 (0.01<=p<0.05) = Gate-2 (a) PASS"
    elif p_two_sided < 0.10:
        return "弱く棄却 (0.05<=p<0.10) = Gate-2 (a) PASS (weakest)"
    elif p_two_sided < 0.20:
        return "border zone (0.10<=p<0.20) = Gate-2 (a) FAIL"
    else:
        return "弱く支持 (p>=0.20) = Gate-2 (a) FAIL"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default="data/h3_2_season_brier_test.log",
        help="Output log path",
    )
    args = parser.parse_args()

    arr_2025_full = np.array(
        [v["brier"] for v in MONTHLY_BRIER_2025.values()], dtype=np.float64
    )
    arr_2026_full = np.array(
        [v["brier"] for v in MONTHLY_BRIER_2026.values()], dtype=np.float64
    )
    arr_2025_aprmay = arr_2025_full[3:5]  # Apr-May 2025
    arr_2026_aprmay = arr_2026_full[3:5]  # Apr-May 2026

    out_lines = []
    out_lines.append("H3-2: 同季節 Brier 悪化 Welch + paired t-test + bootstrap CI")
    out_lines.append("=" * 70)
    out_lines.append("")
    out_lines.append("Input data (v4 §1.1 N1 月次 Brier 表 由来、p_win Brier):")
    out_lines.append("")
    out_lines.append("  2025:")
    for k, v in MONTHLY_BRIER_2025.items():
        out_lines.append(f"    {k}: brier={v['brier']:.4f} (n={v['n']})")
    out_lines.append("  2026:")
    for k, v in MONTHLY_BRIER_2026.items():
        out_lines.append(f"    {k}: brier={v['brier']:.4f} (n={v['n']})")
    out_lines.append("")

    # メイン test 1: Jan-May 5 pairs
    test_full = run_tests(arr_2025_full, arr_2026_full, "Jan-May 5 pairs")
    # メイン test 2: Apr-May subset (2 pairs)
    test_aprmay = run_tests(arr_2025_aprmay, arr_2026_aprmay, "Apr-May 2 pairs (subset)")

    for test_result in (test_full, test_aprmay):
        out_lines.append("-" * 70)
        out_lines.append(f"Test: {test_result['label']}")
        out_lines.append("-" * 70)
        out_lines.append(
            f"  n_2025={test_result['n_2025']}, n_2026={test_result['n_2026']}"
        )
        out_lines.append(
            f"  mean_2025={test_result['mean_2025']:.4f}, "
            f"std_2025={test_result['std_2025']:.4f}"
        )
        out_lines.append(
            f"  mean_2026={test_result['mean_2026']:.4f}, "
            f"std_2026={test_result['std_2026']:.4f}"
        )
        out_lines.append(
            f"  delta = mean(2026) - mean(2025) = {test_result['delta']:+.4f}"
        )
        out_lines.append("")
        out_lines.append(
            f"  Welch (unpaired, equal_var=False): t={test_result['welch_t']:+.3f}, "
            f"p_two_sided={test_result['welch_p_two_sided']:.4f}, "
            f"p_one_sided_greater={test_result['welch_p_one_sided_greater']:.4f}"
        )
        out_lines.append(
            f"  Paired (ttest_rel):                t={test_result['paired_t']:+.3f}, "
            f"p_two_sided={test_result['paired_p_two_sided']:.4f}, "
            f"p_one_sided_greater={test_result['paired_p_one_sided_greater']:.4f}"
        )
        out_lines.append("")
        boot = test_result["bootstrap"]
        out_lines.append(
            f"  Bootstrap CI (n_resample={boot['n_resample']}, "
            f"ci={boot['ci_level']:.2f}):"
        )
        out_lines.append(
            f"    observed delta = {boot['observed_delta']:+.4f}"
        )
        out_lines.append(
            f"    bootstrap median = {boot['median']:+.4f}, "
            f"95% CI = [{boot['lo']:+.4f}, {boot['hi']:+.4f}]"
        )
        out_lines.append(
            f"    P(delta > 0 | bootstrap) = {boot['p_delta_gt_0']:.4f}"
        )
        out_lines.append("")

    # v4 §0.1 rubric 適用 for Jan-May (= primary Gate-2 (a) verdict)
    out_lines.append("=" * 70)
    out_lines.append("Gate-2 (a) verdict")
    out_lines.append("=" * 70)
    out_lines.append("")
    out_lines.append("primary test: Jan-May 5 pairs (= handoff §「事前予想」が想定)")
    out_lines.append("")
    primary_p = test_full["welch_p_two_sided"]
    out_lines.append(
        f"  Welch p_two_sided = {primary_p:.4f} → {gate2a_verdict(primary_p)}"
    )
    out_lines.append("")
    paired_p = test_full["paired_p_two_sided"]
    out_lines.append(
        f"  Paired p_two_sided = {paired_p:.4f} → {gate2a_verdict(paired_p)} (補助)"
    )
    out_lines.append("")
    out_lines.append("secondary test: Apr-May 2 pairs (= v4 §1.1 +3.3σ 観察の正面検定)")
    out_lines.append("")
    secondary_p = test_aprmay["welch_p_two_sided"]
    out_lines.append(
        f"  Welch p_two_sided = {secondary_p:.4f} → {gate2a_verdict(secondary_p)} "
        "(n=2 vs 2 で power 極小、参考値)"
    )
    out_lines.append("")
    out_lines.append("-" * 70)
    out_lines.append("総合判定:")
    out_lines.append("-" * 70)
    out_lines.append("")
    out_lines.append(
        f"  primary (Jan-May Welch p={primary_p:.4f}) を **公式 Gate-2 (a) 判定** とする。"
    )
    out_lines.append(
        "  bootstrap CI の P(delta > 0) と paired test の方向で補強。"
    )
    out_lines.append("")
    out_lines.append("  Welch 採択理由: handoff §「事前予想」が ttest_ind を指定。")
    out_lines.append("  paired を補助で見る理由: 同月同曜日 (Jan-Jan, Feb-Feb, ...) は")
    out_lines.append("    競馬週ごとの schedule 差で paired より independent に近い。")
    out_lines.append("    両 test の verdict が一致するかが robustness の検証になる。")

    # JSON 形式の生数値も出力 (= 機械可読、次 step で参照)
    out_lines.append("")
    out_lines.append("=" * 70)
    out_lines.append("Raw numbers (JSON)")
    out_lines.append("=" * 70)
    out_lines.append("")
    out_lines.append(json.dumps({"jan_may": test_full, "apr_may": test_aprmay}, indent=2))

    out_text = "\n".join(out_lines) + "\n"
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(out_text, encoding="utf-8")

    # stdout にも summary を出す
    print(out_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
