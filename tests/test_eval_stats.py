"""評価統計の契約テスト (`predictor/eval_stats.py`)。

## なぜ要るか

2026-09-19 に条件付きロジットが実データで発散し、係数 −2.7×10⁹ / 区間
10²¹ オーダーを返した。最初に書いた回帰テストは **旧コードでも通ってしまい**
(レビューで mutation により実証)、再発を検出できなかった。

原因は、当初「4 桁のスケール差で条件数が跳ねた」と診断して合成データを
スケール差で作ったこと。Newton 法は **アフィン不変** なので、スケール差だけ
では発散しない。成分分離で実測した真因は **初期ステップの過大 (減衰なし)**。

そこで発散を実際に再現するデータで固定する。
"""
from __future__ import annotations

import math
import random

import numpy as np
import pytest

from predictor.eval_stats import (
    MIN_BUYS_FOR_MONEY,
    band_calibration,
    block_boot,
    conditional_logit,
    flat_bet_roi,
)


def _diverging_sample(n_races: int = 600, seed: int = 3) -> list[dict]:
    """旧実装 (減衰なし Newton) が発散するデータ。

    実データの構造を写す: レース内確率を softmax から作り、`logit(p)` の
    2 乗・3 乗 (絶対値が大きい) と、極小スケールの列を同時に入れる。
    """
    rng = random.Random(seed)
    out: list[dict] = []
    for i in range(n_races):
        n = rng.randint(8, 16)
        u = [rng.gauss(0, 1.5) for _ in range(n)]
        m = max(u)
        w = [math.exp(x - m) for x in u]
        tot = sum(w)
        p = [x / tot for x in w]
        r = rng.random()
        acc, winner = 0.0, n - 1
        for j, pj in enumerate(p):
            acc += pj
            if r <= acc:
                winner = j
                break
        for j in range(n):
            z = math.log(max(p[j], 1e-9) / max(1 - p[j], 1e-9))
            out.append({"race_id": f"r{i}", "won": 1 if j == winner else 0,
                        "z": z, "z2": z * z, "z3": z ** 3,
                        "tiny": rng.gauss(0, 0.05)})
    return out


def _undamped(samples, cols):
    """減衰を外した旧実装 (対照)。これが発散することを確かめる。"""
    from collections import defaultdict

    by = defaultdict(list)
    for s in samples:
        by[s["race_id"]].append(s)
    races = []
    for rows in by.values():
        y = np.array([r["won"] for r in rows], dtype=float)
        if y.sum() <= 0:
            continue
        races.append((np.array([[r[c] for c in cols] for r in rows],
                               dtype=float), y))
    beta = np.zeros(len(cols))
    for _ in range(100):
        g = np.zeros(len(cols))
        h = np.zeros((len(cols), len(cols)))
        for X, y in races:
            u = X @ beta
            u -= u.max()
            w = np.exp(u)
            w /= w.sum()
            g += X.T @ (y - w * y.sum())
            h -= y.sum() * (X.T @ (np.diag(w) - np.outer(w, w)) @ X)
        try:
            step = np.linalg.solve(h, g)
        except np.linalg.LinAlgError:
            return None
        beta = beta - step
        if not np.all(np.isfinite(beta)):
            return None
        if np.abs(step).max() < 1e-9:
            break
    return [float(b) for b in beta]


def test_the_control_really_diverges():
    """**対照が本当に壊れること**を先に確かめる。

    これが無いと、下のテストが「たまたま通っている」のか
    「本当に守っている」のか区別できない。
    """
    bad = _undamped(_diverging_sample(), ["z", "z2", "z3", "tiny"])

    assert bad is None or max(abs(b) for b in bad) > 1e4, (
        f"対照が発散していない = このデータでは再発を検出できない: {bad}")


def test_conditional_logit_stays_finite_where_the_old_one_diverged():
    """同じデータで現行実装は有限に収束すること。"""
    beta, converged = conditional_logit(
        _diverging_sample(), ["z", "z2", "z3", "tiny"], with_status=True)

    assert converged, "収束しなかった"
    assert all(abs(b) < 1e3 for b in beta), f"係数が爆発している: {beta}"


def test_non_convergence_is_reported_not_hidden():
    """収束しなかったら NaN を返し、黙って値を返さないこと。"""
    beta, converged = conditional_logit(
        [], ["z"], with_status=True)

    assert not converged
    assert all(math.isnan(b) for b in beta)


def test_block_boot_drops_failed_fits():
    """当てはめに失敗した再抽出を区間に混ぜないこと。"""
    samples = [{"race_id": f"r{i}", "won": i % 3 == 0, "v": i}
               for i in range(90)]
    calls = {"n": 0}

    def flaky(draw):
        calls["n"] += 1
        return None if calls["n"] % 2 else 1.0

    lo, hi = block_boot(samples, flaky, n_boot=100)

    assert lo == 1.0 and hi == 1.0, (lo, hi)


def test_money_is_untestable_below_the_minimum():
    """少数の的中で「金額合格」が静かに立たないこと。

    3 点全勝 (1.5 倍) なら区間が [1.5, 1.5] に潰れ、区間下限 > 100% が
    成立してしまう。件数の下限が無いとこれを合格と読む。
    """
    three = [{"race_id": f"r{i}", "won": 1, "payout_odds": 1.5}
             for i in range(3)]

    r = flat_bet_roi(three)

    assert r["testable"] is False
    assert r["n_bets"] == 3
    assert math.isnan(r["roi_ci95"][0])
    assert r["min_bets_required"] == MIN_BUYS_FOR_MONEY


def test_money_is_testable_above_the_minimum():
    enough = [{"race_id": f"r{i // 8}", "won": i % 10 == 0, "payout_odds": 9.0}
              for i in range(MIN_BUYS_FOR_MONEY + 20)]

    r = flat_bet_roi(enough)

    assert r["testable"] is True
    assert not math.isnan(r["roi_ci95"][0])


def test_band_calibration_reports_z_for_multiple_comparison():
    """帯ごとに z を出すこと。区間は 95% のままで Bonferroni とは呼ばない。"""
    rng = random.Random(5)
    samples = [{"race_id": f"r{i // 10}", "won": 1 if rng.random() < 0.03 else 0,
                "p": 0.03} for i in range(3000)]

    rows = band_calibration(samples, "p", n_boot=200)

    assert rows and rows[0]["band"] == "0-5%"
    assert "z" in rows[0] and not math.isnan(rows[0]["z"])



# --- 2026-10-04: 水準を明示する区間と、Phase 0.5-5 の主検定の区間 -----------------------------------

def _seq_stat():
    """呼ばれるたびに 1, 2, 3, ... を返す統計量 (標本と無関係。昇順にすると i 番目 = i + 1 になる)。"""
    state = {"i": 0}

    def stat(draw):
        state["i"] += 1
        return float(state["i"])

    return stat


def _samples(n_races: int = 20):
    return [{"race_id": f"r{i}", "won": i % 2 == 0, "v": i} for i in range(n_races)]


def test_block_boot_ci_takes_the_requested_quantiles():
    from predictor.eval_stats import block_boot_ci

    out = block_boot_ci(_samples(), _seq_stat(), level=0.99, n_boot=5000, seed=1, max_discard_frac=0.01)
    # 値は 1..5000。0.5% と 99.5% の分位は int(0.005·5000)=25 番目 (値 26) と int(0.995·5000)=4975 番目 (値 4976)
    assert (out["lo"], out["hi"]) == (26.0, 4976.0) and out["valid"] is True
    assert (out["lower_quantile"], out["upper_quantile"]) == (pytest.approx(0.005), pytest.approx(0.995))
    out95 = block_boot_ci(_samples(), _seq_stat(), level=0.95, n_boot=1000, seed=1, max_discard_frac=0.01)
    assert (out95["lo"], out95["hi"]) == (26.0, 976.0)     # int(0.025·1000)=25, int(0.975·1000)=975


def test_block_boot_ci_is_deterministic_for_a_seed():
    from predictor.eval_stats import block_boot_ci

    samples = [{"race_id": f"r{i % 30}", "won": i % 7 == 0, "v": i} for i in range(300)]

    def mean_v(draw):
        return sum(d["v"] for d in draw) / len(draw)

    a = block_boot_ci(samples, mean_v, level=0.99, n_boot=200, seed=7, max_discard_frac=0.01)
    b = block_boot_ci(samples, mean_v, level=0.99, n_boot=200, seed=7, max_discard_frac=0.01)
    c = block_boot_ci(samples, mean_v, level=0.99, n_boot=200, seed=8, max_discard_frac=0.01)
    assert (a["lo"], a["hi"]) == (b["lo"], b["hi"]) and (a["lo"], a["hi"]) != (c["lo"], c["hi"])


@pytest.mark.parametrize("kwargs", [
    {"level": 0.0}, {"level": 1.0}, {"level": 1.5}, {"level": 99}, {"level": "0.99"},
    {"n_boot": 0}, {"n_boot": 50}, {"n_boot": 1000.0}, {"n_boot": True},
    {"seed": None}, {"max_discard_frac": 0.5}, {"max_discard_frac": -0.1},
])
def test_block_boot_ci_rejects_invalid_arguments(kwargs):
    from predictor.eval_stats import block_boot_ci

    args = {"level": 0.99, "n_boot": 1000, "seed": 1, "max_discard_frac": 0.01, **kwargs}
    with pytest.raises(ValueError):
        block_boot_ci(_samples(), _seq_stat(), **args)


def test_block_boot_ci_is_invalid_when_too_many_resamples_fail():
    from predictor.eval_stats import block_boot_ci

    calls = {"n": 0}

    def flaky(draw):
        calls["n"] += 1
        return None if calls["n"] <= 11 else 1.0          # 1000 回中 11 回失敗 (上限 1% = 10 回を超える)

    out = block_boot_ci(_samples(), flaky, level=0.99, n_boot=1000, seed=1, max_discard_frac=0.01)
    assert out["valid"] is False and math.isnan(out["lo"]) and out["n_discarded"] == 11
    calls["n"] = 1                                         # 今度は 10 回だけ失敗 → 有効
    out = block_boot_ci(_samples(), flaky, level=0.99, n_boot=1000, seed=1, max_discard_frac=0.01)
    assert out["valid"] is True and out["n_discarded"] == 10


def test_primary_ci_requires_an_explicit_99_percent_and_fixed_settings():
    from predictor import eval_stats as es

    with pytest.raises(TypeError):
        es.primary_block_ci(_samples(), _seq_stat())               # 水準を書かない呼び出しは許さない
    for bad in (0.95, 0.999, 0.9):
        with pytest.raises(ValueError, match="99%"):
            es.primary_block_ci(_samples(), _seq_stat(), level=bad)
    out = es.primary_block_ci(_samples(), _seq_stat(), level=0.99)
    assert (out["level"], out["n_boot"], out["seed"], out["max_discard"]) == (0.99, 5000, 20261004, 50)
    assert (out["lo"], out["hi"]) == (26.0, 4976.0)


def test_legacy_block_boot_is_unchanged():
    """従来の 95% の block_boot の挙動 (端点の位置・半分を超えて捨てたら NaN) は変えない。"""
    lo, hi = block_boot(_samples(), _seq_stat(), n_boot=1000, seed=1)
    assert (lo, hi) == (26.0, 976.0)
    calls = {"n": 0}

    def mostly_fail(draw):
        calls["n"] += 1
        return None if calls["n"] <= 501 else 1.0

    lo, hi = block_boot(_samples(), mostly_fail, n_boot=1000, seed=1)
    assert math.isnan(lo) and math.isnan(hi)
