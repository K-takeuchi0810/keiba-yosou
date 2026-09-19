"""評価の統計部品。DB にもモデルにも依存しない純関数だけを置く。

`scripts/fundamental_eval.py` に置いていたものを移した。CLI スクリプトを
ライブラリ扱いすると `sys.path` 操作と DB import を巻き込むうえ、
privatename (`_block_boot` 等) を外から呼ぶことになる。消費者が 2 本になり
(0.5-5 で 3 本目が確実) テストも付いた時点で切り出すのが最も安い。
"""
from __future__ import annotations

import math
import random
from collections import defaultdict

import numpy as np

# 「市場 10%、AI 20% だから買う」と判断するには、**AI の 20% が信用できないと
# 意味がない**。分位ではなく確率の固定帯で較正を見る (憲法 Phase 0.5-3)。
BANDS: tuple[tuple[float, float, str], ...] = (
    (0.00, 0.05, "0-5%"), (0.05, 0.10, "5-10%"), (0.10, 0.20, "10-20%"),
    (0.20, 0.30, "20-30%"), (0.30, 1.01, "30%+"),
)
N_BOOT = 1000
SEED = 20260918

# 金額の判定に必要な最低件数。これ未満は「不合格」ではなく **判定不能**。
# 2026-09-19 のレビューで、3 点全勝なら区間が [1.5, 1.5] になり
# 「回収率の区間下限 > 100%」が静かに成立してしまうことが実証された。
MIN_BUYS_FOR_MONEY = 100


def logit(p) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), 1e-9, 1 - 1e-9)
    return np.log(p / (1 - p))


def normalise(d: dict[str, float]) -> dict[str, float]:
    tot = sum(d.values())
    return {k: v / tot for k, v in d.items()} if tot > 0 else {}


def block_boot(samples: list[dict], stat, n_boot: int = N_BOOT,
               seed: int = SEED) -> tuple[float, float]:
    """レースを塊として再抽出した 95% 区間。

    同一レースの馬は「1 頭しか勝たない」ので独立ではない。馬単位で再抽出すると
    区間が狭く出て、無い差を有ると言ってしまう。

    `stat` が `None` / NaN を返した再抽出は捨てる。**収束しなかった当てはめを
    区間に混ぜない**ため (旧実装では発散値 1e21 が区間に入っていた)。
    """
    blocks: dict[str, list[dict]] = defaultdict(list)
    for s in samples:
        blocks[s["race_id"]].append(s)
    bl = list(blocks.values())
    rng = random.Random(seed)
    vals: list[float] = []
    for _ in range(n_boot):
        draw: list[dict] = []
        for _ in range(len(bl)):
            draw.extend(bl[rng.randrange(len(bl))])
        v = stat(draw)
        if v is None or (isinstance(v, float) and math.isnan(v)):
            continue
        vals.append(float(v))
    if len(vals) < n_boot // 2:
        return float("nan"), float("nan")
    vals.sort()
    return vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals))]


def conditional_logit(samples: list[dict], cols: list[str],
                      with_status: bool = False):
    """レース内で 1 頭だけ勝つ構造を使った条件付きロジット (Benter 型)。

    `P(i が勝つ) = exp(x_i·β) / Σ_j exp(x_j·β)` を最尤で解く。

    「AI の意見が市場の値動きと相関するか」ではなく **「市場の価格を与えた上で、
    AI の意見が結果を説明するか」** を直接測る。レース内正規化・価格水準・
    レース固有効果はすべて構造に吸収される。

    ## 発散する条件と、実際に効いている対策 (2026-09-19 に成分分離で実測)

    素の Newton 法は **初期ステップが過大** なときに発散する。実データ
    (626 レース、`logit(P_T10)` の 3 次項が −227 まで、補正が 0.06 程度) で
    係数 −2.7×10⁹、100 反復で 1e21 を返していた。

    成分ごとに外して測った結果:

    | 実装 | margin 係数 | 反復 |
    |---|---|---|
    | ステップ制限あり | +0.4015 | 8-9 |
    | **ステップ制限なし** | **−4.5×10¹¹** | 100 (打切り) |
    | 標準化なし (制限あり) | +0.4015 | 8 |
    | リッジなし (制限あり) | +0.4015 | 9 |

    **効いているのはステップ制限 (damped Newton) だけ**。Newton 法は
    アフィン不変なので、列の標準化は収束性を変えない。当初「4 桁のスケール差で
    条件数が跳ねた」と書いたのは **誤診断**だった。標準化は係数の可読性のために
    残すが、発散対策ではない。

    `with_status=True` なら `(beta, converged)` を返す。**100 反復で打ち切った
    結果を黙って返さない**ため。
    """
    by_race: dict[str, list[dict]] = defaultdict(list)
    for s in samples:
        by_race[s["race_id"]].append(s)
    races = []
    for rows in by_race.values():
        y = np.array([r["won"] for r in rows], dtype=float)
        if y.sum() <= 0:
            continue
        races.append((np.array([[r[c] for c in cols] for r in rows],
                               dtype=float), y))
    nan = [float("nan")] * len(cols)
    if not races:
        return (nan, False) if with_status else nan

    scale = np.concatenate([X for X, _ in races]).std(axis=0)
    scale[scale <= 0] = 1.0
    races = [(X / scale, y) for X, y in races]

    beta = np.zeros(len(cols))
    converged = False
    for _ in range(100):
        grad = np.zeros(len(cols))
        hess = np.zeros((len(cols), len(cols)))
        for X, y in races:
            u = X @ beta
            u -= u.max()
            w = np.exp(u)
            w /= w.sum()
            grad += X.T @ (y - w * y.sum())
            hess -= y.sum() * (X.T @ (np.diag(w) - np.outer(w, w)) @ X)
        try:
            step = np.linalg.solve(hess, grad)
        except np.linalg.LinAlgError:
            return (nan, False) if with_status else nan
        # **これが発散対策の本体** (damped Newton)。1 歩を 2 標準偏差に制限する。
        big = np.abs(step).max()
        if big > 2.0:
            step = step * (2.0 / big)
        beta = beta - step
        if not np.all(np.isfinite(beta)):
            return (nan, False) if with_status else nan
        if np.abs(step).max() < 1e-9:
            converged = True
            break
    out = [float(b) for b in beta / scale]
    if not converged:
        out = nan
    return (out, converged) if with_status else out


def coefficient_ci(samples: list[dict], cols: list[str], index: int,
                   n_boot: int = N_BOOT, seed: int = SEED) -> tuple[float, float]:
    """条件付きロジットの係数 1 本のレース単位ブートストラップ区間。

    収束しなかった当てはめは `block_boot` 側で捨てられる。
    """
    def stat(draw):
        beta, ok = conditional_logit(draw, cols, with_status=True)
        return beta[index] if ok else None

    return block_boot(samples, stat, n_boot=n_boot, seed=seed)


def band_calibration(samples: list[dict], key: str,
                     n_boot: int = N_BOOT) -> list[dict]:
    """固定帯ごとの予測確率 vs 実勝率。区間はレース単位ブートストラップ。

    `z` は「ずれ / 標準誤差」。多重比較の閾値 (例 Bonferroni 0.05/6 の 2.64) と
    読み手が直接比べられるように出す。**区間そのものは 95% のまま**なので、
    区間に Bonferroni の名前を付けない。
    """
    out: list[dict] = []
    for lo, hi, label in BANDS:
        sel = [s for s in samples if lo <= s[key] < hi]
        if not sel:
            continue

        def gap(draw, lo=lo, hi=hi, key=key):
            d = [r for r in draw if lo <= r[key] < hi]
            if len(d) < 20:
                return None
            return (sum(r["won"] for r in d) / len(d)
                    - sum(r[key] for r in d) / len(d))

        lo_ci, hi_ci = block_boot(samples, gap, n_boot=n_boot)
        pred = sum(s[key] for s in sel) / len(sel)
        act = sum(s["won"] for s in sel) / len(sel)
        se = (hi_ci - lo_ci) / (2 * 1.959964) if hi_ci == hi_ci else float("nan")
        out.append({"band": label, "n": len(sel), "predicted": pred,
                    "actual": act, "gap": act - pred,
                    "gap_ci95": [lo_ci, hi_ci],
                    "z": (act - pred) / se if se and se == se and se > 0
                         else float("nan")})
    return out


def metrics(samples: list[dict], key: str) -> dict:
    from predictor.evaluation import brier, expected_calibration_error, log_loss

    y = [s["won"] for s in samples]
    p = [s[key] for s in samples]
    return {"n_races": len({s["race_id"] for s in samples}), "n_horses": len(p),
            "log_loss": log_loss(y, p), "brier": brier(y, p),
            "calibration_error": expected_calibration_error(y, p)}


def flat_bet_roi(samples: list[dict], n_boot: int = N_BOOT) -> dict:
    """100 円均等で買ったときの回収率。**払戻は確定値から取る**。

    件数が `MIN_BUYS_FOR_MONEY` 未満なら `testable=False` を返す。
    **少数の的中で区間が潰れて「合格」が立つのを防ぐ**。
    """
    def roi(draw):
        if not draw:
            return None
        ret = sum(100.0 * s["payout_odds"] for s in draw if s["won"] == 1)
        return ret / (100.0 * len(draw))

    point = roi(samples)
    testable = len(samples) >= MIN_BUYS_FOR_MONEY
    lo, hi = (block_boot(samples, roi, n_boot=n_boot) if testable
              else (float("nan"), float("nan")))
    return {"n_bets": len(samples),
            "roi": float("nan") if point is None else point,
            "roi_ci95": [lo, hi], "testable": testable,
            "min_bets_required": MIN_BUYS_FOR_MONEY}
