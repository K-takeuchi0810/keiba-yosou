"""統計ヘルパ。Phase 4 (2026-05-13)。

backtest の点推定 (回収率 116%) だけで意思決定するとサンプル少時に誤判断する。
Wilson CI と bootstrap で信頼区間を計算し、buy_only stats に必ず付与する。

純 Python (numpy 不要)。32-bit / 64-bit どちらでも動作。
"""

from __future__ import annotations

import math
import random


def wilson_ci(wins: int, total: int, alpha: float = 0.05) -> tuple[float, float]:
    """Wilson score confidence interval for binomial proportion.

    通常の正規近似 (wins/total ± 1.96 * sqrt(p(1-p)/n)) は n が小さいと
    確率域 [0,1] を逸脱する。Wilson は二次方程式を解いて補正する標準手法。

    戻り: (lower, upper) ∈ [0, 1].
    """
    if total <= 0:
        return (0.0, 0.0)
    z = _inverse_normal_cdf(1.0 - alpha / 2.0)
    p_hat = wins / total
    n = total
    denom = 1.0 + z * z / n
    center = (p_hat + z * z / (2 * n)) / denom
    half_width = (z * math.sqrt(p_hat * (1 - p_hat) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, center - half_width), min(1.0, center + half_width))


def _inverse_normal_cdf(p: float) -> float:
    """Beasley-Springer-Moro による正規分布の逆 CDF (n=1.96 を α=0.025 等で得る)。

    SciPy なしで Wilson CI を動かすため。精度は ±1e-6。
    """
    if p <= 0.0 or p >= 1.0:
        raise ValueError(f"p out of range: {p}")
    a = [
        -3.969683028665376e+01, 2.209460984245205e+02,
        -2.759285104469687e+02, 1.383577518672690e+02,
        -3.066479806614716e+01, 2.506628277459239e+00,
    ]
    b = [
        -5.447609879822406e+01, 1.615858368580409e+02,
        -1.556989798598866e+02, 6.680131188771972e+01,
        -1.328068155288572e+01,
    ]
    c = [
        -7.784894002430293e-03, -3.223964580411365e-01,
        -2.400758277161838e+00, -2.549732539343734e+00,
        4.374664141464968e+00, 2.938163982698783e+00,
    ]
    d = [
        7.784695709041462e-03, 3.224671290700398e-01,
        2.445134137142996e+00, 3.754408661907416e+00,
    ]
    p_low = 0.02425
    p_high = 1.0 - p_low
    if p < p_low:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
        )
    if p > p_high:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(
            (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5])
            / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
        )
    q = p - 0.5
    r = q * q
    return (
        ((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]
    ) * q / (
        ((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1
    )


def bootstrap_return_rate(
    payouts: list[int],
    stakes: list[int],
    n_resample: int = 1000,
    seed: int = 42,
    alpha: float = 0.05,
) -> tuple[float, float, float]:
    """各賭けの (stake, payout) ペアから return rate の bootstrap CI を計算。

    戻り: (point_estimate, lo_quantile, hi_quantile)
    既定 α=0.05 で 95% CI。
    """
    if not payouts or not stakes or len(payouts) != len(stakes):
        return (0.0, 0.0, 0.0)
    total_stake = sum(stakes)
    total_return = sum(payouts)
    point = total_return / total_stake if total_stake else 0.0
    rng = random.Random(seed)
    n = len(payouts)
    samples: list[float] = []
    for _ in range(n_resample):
        idxs = [rng.randrange(n) for _ in range(n)]
        s = sum(stakes[i] for i in idxs)
        r = sum(payouts[i] for i in idxs)
        samples.append(r / s if s else 0.0)
    samples.sort()
    lo_idx = max(0, int(n_resample * alpha / 2))
    hi_idx = min(n_resample - 1, int(n_resample * (1 - alpha / 2)))
    return (point, samples[lo_idx], samples[hi_idx])
