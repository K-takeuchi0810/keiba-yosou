"""scripts.analyze_cross_pool の Harville 数式の不変量テスト。

棄却判断 (経路2、2026-08-22) を支える数式なので、確率測度としての整合を固定する
(コード品質監査の指摘)。F3 で Harville を再利用する際の土台。
"""
from __future__ import annotations

import random

from scripts.analyze_cross_pool import harville_top2_prob, harville_top3_prob


def _random_probs(n: int, seed: int) -> dict[str, float]:
    rng = random.Random(seed)
    raw = {f"{i:02d}": rng.random() + 0.01 for i in range(1, n + 1)}
    total = sum(raw.values())
    return {k: v / total for k, v in raw.items()}


def test_top2_probs_sum_to_one():
    """全ペアの「1-2 着独占」確率の総和は 1 (Harville は完全な確率測度)。"""
    for seed in (1, 7, 42):
        p = _random_probs(10, seed)
        nums = sorted(p)
        total = sum(
            harville_top2_prob(p, a, b)
            for i, a in enumerate(nums) for b in nums[i + 1:]
        )
        assert abs(total - 1.0) < 1e-9


def test_top3_probs_sum_to_one():
    for seed in (1, 7, 42):
        p = _random_probs(10, seed)
        nums = sorted(p)
        total = 0.0
        for i, a in enumerate(nums):
            for j in range(i + 1, len(nums)):
                for k in range(j + 1, len(nums)):
                    total += harville_top3_prob(p, (a, nums[j], nums[k]))
        assert abs(total - 1.0) < 1e-9


def test_top2_symmetry():
    p = _random_probs(8, 3)
    assert harville_top2_prob(p, "01", "02") == harville_top2_prob(p, "02", "01")
