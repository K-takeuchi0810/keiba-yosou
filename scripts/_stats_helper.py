"""Shared statistical helpers for diagnostic scripts.

The functions in this module are intentionally small and explicit.  They make
scorecard-facing assumptions visible: family size, multiple-comparison
correction, z-test definition, and power calculation inputs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class MultipleComparisonResult:
    """Per-test correction values for one p-value."""

    p_value: float
    bonferroni_p: float
    bh_q: float


@dataclass(frozen=True)
class WelchPowerResult:
    """Observed-power approximation for a Welch two-sample t-test."""

    alpha: float
    target_power: float
    n_a: int
    n_b: int
    std_a: float
    std_b: float
    effect_delta: float
    se: float
    df: float
    ncp: float
    critical_t: float
    observed_power: float
    target_power_delta: float


def normal_cdf(x: float) -> float:
    """Standard normal CDF."""

    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def normal_two_sided_p_from_z(z_value: float) -> float:
    """Two-sided p-value from a normal z statistic."""

    return math.erfc(abs(z_value) / math.sqrt(2.0))


def inverse_normal_cdf(p: float) -> float:
    """Inverse CDF for standard normal, Acklam approximation."""

    if p <= 0.0 or p >= 1.0:
        raise ValueError(f"p out of range: {p}")
    a = [
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    ]
    b = [
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    ]
    c = [
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    ]
    d = [
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e00,
        3.754408661907416e00,
    ]
    p_low = 0.02425
    p_high = 1.0 - p_low
    if p < p_low:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    if p > p_high:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(
            (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5])
            / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
        )
    q = p - 0.5
    r = q * q
    return (
        (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5])
        * q
        / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)
    )


def bonferroni_alpha(alpha: float, family_size: int) -> float:
    """Bonferroni per-test alpha."""

    if family_size <= 0:
        raise ValueError(f"family_size must be positive: {family_size}")
    return alpha / family_size


def bonferroni_z_threshold(alpha: float, family_size: int, *, two_sided: bool = True) -> float:
    """Normal |z| threshold after Bonferroni correction."""

    per_test = bonferroni_alpha(alpha, family_size)
    tail = per_test / 2.0 if two_sided else per_test
    return inverse_normal_cdf(1.0 - tail)


def apply_bonferroni(p_values: list[float], family_size: int | None = None) -> list[float]:
    """Return Bonferroni-adjusted p-values."""

    n = len(p_values) if family_size is None else family_size
    if n <= 0:
        return []
    return [min(max(p, 0.0) * n, 1.0) for p in p_values]


def apply_bh_fdr(p_values: list[float]) -> list[float]:
    """Return Benjamini-Hochberg q-values in original input order."""

    n = len(p_values)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda idx: p_values[idx])
    q_values = [1.0] * n
    running_min = 1.0
    for reverse_rank, idx in enumerate(reversed(order), start=1):
        rank = n - reverse_rank + 1
        adjusted = max(p_values[idx], 0.0) * n / rank
        running_min = min(running_min, adjusted)
        q_values[idx] = min(running_min, 1.0)
    return q_values


def multiple_comparison_results(p_values: list[float]) -> list[MultipleComparisonResult]:
    """Return Bonferroni and BH-FDR values for each p-value."""

    bonferroni = apply_bonferroni(p_values)
    bh = apply_bh_fdr(p_values)
    return [
        MultipleComparisonResult(p_value=p, bonferroni_p=bp, bh_q=q)
        for p, bp, q in zip(p_values, bonferroni, bh)
    ]


def two_proportion_z_test(
    hits_a: int,
    n_a: int,
    hits_b: int,
    n_b: int,
    *,
    method: str = "pooled",
) -> dict[str, float]:
    """Two-proportion z-test for delta = p_b - p_a.

    method="pooled" uses the null-hypothesis pooled SE.  method="unpooled"
    keeps the older Wald-style diagnostic behavior.
    """

    if n_a <= 0 or n_b <= 0:
        raise ValueError(f"n_a and n_b must be positive: n_a={n_a}, n_b={n_b}")
    p_a = hits_a / n_a
    p_b = hits_b / n_b
    delta = p_b - p_a
    if method == "pooled":
        pooled = (hits_a + hits_b) / (n_a + n_b)
        se = math.sqrt(pooled * (1.0 - pooled) * (1.0 / n_a + 1.0 / n_b))
    elif method == "unpooled":
        se = math.sqrt(p_a * (1.0 - p_a) / n_a + p_b * (1.0 - p_b) / n_b)
    else:
        raise ValueError(f"unknown z-test method: {method}")
    z_value = delta / se if se > 0.0 else 0.0
    return {
        "p_a": p_a,
        "p_b": p_b,
        "delta": delta,
        "se": se,
        "z": z_value,
        "p_two_sided": normal_two_sided_p_from_z(z_value),
    }


def welch_df(std_a: float, n_a: int, std_b: float, n_b: int) -> float:
    """Welch-Satterthwaite degrees of freedom."""

    if n_a <= 1 or n_b <= 1:
        return 0.0
    var_a = std_a * std_a
    var_b = std_b * std_b
    term_a = var_a / n_a
    term_b = var_b / n_b
    numerator = (term_a + term_b) ** 2
    denominator = (term_a * term_a) / (n_a - 1) + (term_b * term_b) / (n_b - 1)
    return numerator / denominator if denominator > 0.0 else 0.0


def welch_power_two_sided(
    *,
    effect_delta: float,
    std_a: float,
    n_a: int,
    std_b: float,
    n_b: int,
    alpha: float = 0.05,
    target_power: float = 0.80,
) -> WelchPowerResult:
    """Approximate two-sided Welch-test power using a noncentral t distribution."""

    from scipy import stats  # type: ignore[import-not-found]

    se = math.sqrt(std_a * std_a / n_a + std_b * std_b / n_b)
    df = welch_df(std_a, n_a, std_b, n_b)
    if se <= 0.0 or df <= 0.0:
        raise ValueError("cannot compute Welch power with zero SE/df")
    ncp = effect_delta / se
    critical_t = float(stats.t.ppf(1.0 - alpha / 2.0, df))
    observed_power = float(stats.nct.sf(critical_t, df, ncp) + stats.nct.cdf(-critical_t, df, ncp))
    target_delta = _minimum_delta_for_power(
        std_a=std_a,
        n_a=n_a,
        std_b=std_b,
        n_b=n_b,
        alpha=alpha,
        target_power=target_power,
    )
    return WelchPowerResult(
        alpha=alpha,
        target_power=target_power,
        n_a=n_a,
        n_b=n_b,
        std_a=std_a,
        std_b=std_b,
        effect_delta=effect_delta,
        se=se,
        df=df,
        ncp=ncp,
        critical_t=critical_t,
        observed_power=observed_power,
        target_power_delta=target_delta,
    )


def _minimum_delta_for_power(
    *,
    std_a: float,
    n_a: int,
    std_b: float,
    n_b: int,
    alpha: float,
    target_power: float,
) -> float:
    """Small bisection search for the positive delta that reaches target power."""

    from scipy import stats  # type: ignore[import-not-found]

    se = math.sqrt(std_a * std_a / n_a + std_b * std_b / n_b)
    df = welch_df(std_a, n_a, std_b, n_b)
    critical_t = float(stats.t.ppf(1.0 - alpha / 2.0, df))

    def power_for_delta(delta: float) -> float:
        ncp = delta / se
        return float(stats.nct.sf(critical_t, df, ncp) + stats.nct.cdf(-critical_t, df, ncp))

    lo = 0.0
    hi = max(se, abs(std_a), abs(std_b), 1e-9)
    while power_for_delta(hi) < target_power:
        hi *= 2.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if power_for_delta(mid) >= target_power:
            hi = mid
        else:
            lo = mid
    return hi
