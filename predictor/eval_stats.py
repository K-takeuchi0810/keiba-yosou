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


def _block_resample(samples: list[dict], stat, n_boot: int, seed: int) -> tuple[list[float], int]:
    """レースを塊として n_boot 回再抽出し、(昇順の統計量の値, 捨てた回数) を返す。

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
    discarded = 0
    for _ in range(n_boot):
        draw: list[dict] = []
        for _ in range(len(bl)):
            draw.extend(bl[rng.randrange(len(bl))])
        v = stat(draw)
        if v is None or (isinstance(v, float) and math.isnan(v)):
            discarded += 1
            continue
        vals.append(float(v))
    vals.sort()
    return vals, discarded


def block_boot(samples: list[dict], stat, n_boot: int = N_BOOT,
               seed: int = SEED) -> tuple[float, float]:
    """レースを塊として再抽出した 95% 区間 (従来の呼び出し元のための関数。挙動は 2026-10-04 以前と同じ)。

    捨てた再抽出が半分を超えたら (NaN, NaN)。Phase 0.5-5 の主検定には使わない (`primary_block_ci` を使う)。
    """
    vals, _ = _block_resample(samples, stat, n_boot, seed)
    if len(vals) < n_boot // 2:
        return float("nan"), float("nan")
    return vals[int(0.025 * len(vals))], vals[int(0.975 * len(vals))]


def block_boot_ci(samples: list[dict], stat, *, level: float, n_boot: int, seed: int,
                  max_discard_frac: float) -> dict:
    """水準・回数・seed・捨てる上限をすべて明示して求める、レース単位のパーセンタイル区間 (2026-10-04)。

    両側 `level` の区間の端点は、昇順の値の `int(a·n)` 番目と `int((1 − a)·n)` 番目 (a = (1 − level) / 2、
    n = 有効な再抽出の数。従来の `block_boot` と同じ切り捨て)。不正な引数は止める (黙って 95% などに戻らない)。
    捨てた再抽出が `max_discard_frac × n_boot` を超えたら区間は無効 (lo / hi は NaN、`valid` は False)。
    捨てた再抽出は無作為ではない (収束しないのは極端な再抽出に偏る) ので、`n_discarded` を必ず成果物に残す。

    **再現性の前提**: ブロックの並びは `samples` の中の race_id の初出の順なので、同じ seed でも `samples` の並びが
    違えば区間は変わる。呼び出し側は決定的な順序 (race_id → 馬番) で渡し、入力の sha256 を成果物に残すこと。
    引数は組み込みの int / float だけ (numpy の型は拒否する)。下限 n_boot ≥ 100 と上限 max_discard_frac < 0.5 は、
    それより少ない再抽出や、半分以上を捨てた区間は意味を持たないため。
    """
    if not samples:
        raise ValueError("標本が空")
    if not isinstance(level, float) or not (0.5 <= level < 1.0):
        raise ValueError(f"区間の水準が不正: {level!r} (0.5 以上 1 未満の float)")
    if not isinstance(n_boot, int) or isinstance(n_boot, bool) or n_boot < 100:
        raise ValueError(f"再抽出の回数が不正: {n_boot!r} (100 以上の int)")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError(f"seed が不正: {seed!r}")
    if isinstance(max_discard_frac, bool) or not isinstance(max_discard_frac, (int, float)) \
            or not (0.0 <= max_discard_frac < 0.5):
        raise ValueError(f"捨てる上限が不正: {max_discard_frac!r}")
    vals, discarded = _block_resample(samples, stat, n_boot, seed)
    alpha = (1.0 - level) / 2.0
    out = {"level": level, "n_boot": n_boot, "seed": seed, "n_valid": len(vals), "n_discarded": discarded,
           "max_discard": math.floor(max_discard_frac * n_boot + 1e-9),   # 浮動小数の 7.000000000000001 などで 1 ずれないように
           "lower_quantile": alpha, "upper_quantile": 1.0 - alpha}
    if discarded > out["max_discard"] or not vals:
        return {**out, "lo": float("nan"), "hi": float("nan"), "valid": False}
    n = len(vals)
    return {**out, "lo": vals[int(alpha * n)], "hi": vals[int((1.0 - alpha) * n)], "valid": True}


# Phase 0.5-5 の主検定の区間 (docs/PHASE05_5_PREREG.md §8-4。事前登録で固定)
PRIMARY_CI_LEVEL = 0.99
PRIMARY_N_BOOT = 5000
PRIMARY_SEED = 20261004
PRIMARY_MAX_DISCARD_FRAC = 0.01


def primary_block_ci(samples: list[dict], stat, *, level: float) -> dict:
    """Phase 0.5-5 の主検定の区間。水準は呼び出し側で **99% を明示** させ、それ以外は止める。

    回数 5000・seed 20261004・捨てる上限 1% は事前登録の値に固定 (呼び出し側から変えられない)。
    区間が無効 (`valid` False) なら判定は PRIMARY_INCONCLUSIVE (事前登録 §8-4)。判定するコードは `valid` を先に見ること
    (`float("nan") > 0` は False なので、`lo > 0` だけで判定すると無効な区間が PRIMARY_FAIL に化ける)。
    戻り値の dict (水準・回数・seed・捨てた回数を含む) は丸ごと成果物に残す。主検定のコードは
    `block_boot` / `coefficient_ci` (95%) を使わず、この関数だけを使う。
    """
    if level != PRIMARY_CI_LEVEL:
        raise ValueError(f"Phase 0.5-5 の主検定の区間は 99% に固定 (渡された水準: {level!r})")
    return block_boot_ci(samples, stat, level=PRIMARY_CI_LEVEL, n_boot=PRIMARY_N_BOOT, seed=PRIMARY_SEED,
                         max_discard_frac=PRIMARY_MAX_DISCARD_FRAC)


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
