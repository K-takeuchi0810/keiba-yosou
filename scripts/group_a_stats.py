"""Phase 0.5-5 Group A の推定の部品: 条件付きロジットを配列にまとめて解く (2026-10-06)。

`predictor.eval_stats.conditional_logit` と **同じアルゴリズム** (列の標準化 = 勝ち馬のいるレースの全行の母標準偏差、
β = 0 から始める減衰付きの Newton 法、1 歩を 2 (標準化の単位) に制限、`max|step| < 1e-9` で収束、上限 100 反復、
収束しなければ NaN) を、レースを同じ長さに詰めた配列でまとめて計算する。再抽出 (主検定の 5000 回、学習期の SE の 1000 回) を
現実的な時間で回すため。`conditional_logit` と数値が一致することをテストで固定する (tests/test_group_a_stats.py)。

主検定の区間は `predictor.eval_stats.primary_block_ci` で求め、その統計量の関数 (`make_beta_stat`) だけをここで作る。
再抽出のやり方 (レースの塊・seed・回数) は `eval_stats._block_resample` のまま。
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

MAX_ITER = 100
TOL = 1e-9
STEP_CAP = 2.0


@dataclass
class Packed:
    X: np.ndarray        # (R, M, k)
    y: np.ndarray        # (R, M)
    mask: np.ndarray     # (R, M) 実在する行なら 1
    race_ids: list
    cols: list


def pack(samples: list[dict], cols: list[str]) -> Packed:
    """標本をレースごとに詰める。各行に `_ri` (レースの番号) と `_first` (そのレースの最初の行か) を書き込む。

    レースの順は `samples` の中の初出の順 (`eval_stats._block_resample` の塊の順と同じ)。
    """
    order: dict[str, int] = {}
    groups: list[list[dict]] = []
    for s in samples:
        ri = order.get(s["race_id"])
        if ri is None:
            ri = order[s["race_id"]] = len(groups)
            groups.append([])
        s["_ri"] = ri
        s["_first"] = not groups[ri]
        groups[ri].append(s)
    R, M, k = len(groups), max((len(g) for g in groups), default=0), len(cols)
    X = np.zeros((R, M, k))
    y = np.zeros((R, M))
    mask = np.zeros((R, M))
    for ri, rows in enumerate(groups):
        for j, r in enumerate(rows):
            X[ri, j] = [r[c] for c in cols]
            y[ri, j] = r["won"]
            mask[ri, j] = 1.0
    return Packed(X, y, mask, list(order), list(cols))


def clogit_packed(p: Packed, idx: np.ndarray | None = None) -> tuple[list[float], bool]:
    """`conditional_logit(samples, cols, with_status=True)` と同じ答えを返す。`idx` はレースの番号 (重複可) の並び。"""
    X, y, mask = (p.X, p.y, p.mask) if idx is None else (p.X[idx], p.y[idx], p.mask[idx])
    ysum = y.sum(axis=1)
    keep = ysum > 0
    X, y, mask, ysum = X[keep], y[keep], mask[keep], ysum[keep]
    k = X.shape[2]
    nan = [float("nan")] * k
    if X.shape[0] == 0:
        return nan, False
    n = mask.sum()
    mean = (X * mask[:, :, None]).sum(axis=(0, 1)) / n
    var = (((X - mean) ** 2) * mask[:, :, None]).sum(axis=(0, 1)) / n
    scale = np.sqrt(var)
    scale[scale <= 0] = 1.0
    Xs = X / scale
    beta = np.zeros(k)
    neg = np.where(mask > 0, 0.0, -np.inf)
    converged = False
    for _ in range(MAX_ITER):
        u = Xs @ beta + neg
        u = u - u.max(axis=1, keepdims=True)
        w = np.exp(u)
        w = w / w.sum(axis=1, keepdims=True)
        resid = y - w * ysum[:, None]
        grad = np.einsum("rmk,rm->k", Xs, resid)
        m = np.einsum("rmk,rm->rk", Xs, w)
        second = np.einsum("rmk,rml,rm->rkl", Xs, Xs, w) - np.einsum("rk,rl->rkl", m, m)
        hess = -np.einsum("r,rkl->kl", ysum, second)
        try:
            step = np.linalg.solve(hess, grad)
        except np.linalg.LinAlgError:
            return nan, False
        big = np.abs(step).max()
        if big > STEP_CAP:
            step = step * (STEP_CAP / big)
        beta = beta - step
        if not np.all(np.isfinite(beta)):
            return nan, False
        if np.abs(step).max() < TOL:
            converged = True
            break
    if not converged:
        return nan, False
    return [float(b) for b in beta / scale], True


def races_of_draw(draw: list[dict]) -> np.ndarray:
    """再抽出の標本 (レースの塊を連結した行の並び) から、レースの番号の並びを取り出す (`pack` が付けた `_ri` / `_first`)。"""
    return np.array([r["_ri"] for r in draw if r["_first"]], dtype=int)


def make_beta_stat(p: Packed, col: str):
    """`primary_block_ci` / `_block_resample` に渡す統計量: 再抽出の標本での β[col]。収束しなければ None (捨てる)。"""
    j = p.cols.index(col)

    def stat(draw: list[dict]):
        beta, ok = clogit_packed(p, races_of_draw(draw))
        return beta[j] if ok and math.isfinite(beta[j]) else None

    return stat
