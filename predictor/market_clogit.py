"""C′ 以降の主検定の部品: 市場の列・条件付きロジット・結果を読まない Fisher 情報・購入の件数の見込み (事前登録 0.5-5 §8-6b)。

**市場の変換は `predictor.race_market.market_feature` (log P_market) だけ** を通す。尤度の列・検出力の Fisher 情報・P_new・
金額の評価が別の変換を使うと、尤度で推定した係数と金額の側の確率が別のモデルになる (Group A で β_market 0.867 と
「β_market = 1 の仮定」が食い違った原因、§8-6b)。ここの関数は `rm.market_feature` を **モジュールの属性として** 呼ぶ
(テストが差し替えて、全経路が同じ関数を通ることを確かめる)。

Group A のコード (`scripts/group_a.py::add_market_logit`・`scripts/group_a_power.py::fisher_se_at_null`) は logit の仕様のまま
凍結した歴史的な成果物で、ここから呼ばない・書き換えない。

入力の行は 1 頭 1 行で `race_id` と、§8-6 の選択集合の中で和 1 に正規化し直した市場の確率 (既定の列 `p_market`) を持つ。
"""
from __future__ import annotations

import math
import numbers
from collections import defaultdict

import numpy as np

from predictor import race_market as rm
from predictor.eval_stats import conditional_logit

#: 条件付きロジットの市場の列の名前。
MARKET_COL = "market_feature"
#: レースごとの P_market の和が 1 から離れてよい幅 (選択集合の中で正規化し直していない行を止める)。
SUM_TOL = 1e-9


#: Group A (logit の仕様) の行が持つ市場の列。C′ の部品に混ざったら止める (旧い行ビルダの再利用を防ぐ)。
FORBIDDEN_LEGACY_COLS = ("logit_p_market",)


class MarketClogitError(ValueError):
    """C′ の部品に渡した行・係数が契約を満たさない (canonical でない・馬番の重複・空・非有限の係数・不収束・特異な情報行列)。"""


def _by_race(rows: list[dict]) -> dict[str, list[dict]]:
    by: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by[r["race_id"]].append(r)
    return by


def check_canonical(rows: list[dict], p_key: str = "p_market") -> dict[str, list[dict]]:
    """行が C′ の契約を満たすことを確かめ、レースごとに分けて返す。外れたら止める (黙って正規化し直さない)。

    - 空でない / Group A の logit の列を持たない / レース内で馬番が重複しない (重複すると尤度と P_new が別の集合になる)
    - P_market が §8-6 の canonical (選択集合の中で和 1、許容 `SUM_TOL`)。中間の成果物で P_market を丸めて保存すると
      ここで止まる (丸めずに保存するか、選択集合から作り直す)
    """
    if not rows:
        raise MarketClogitError("rows が空")
    legacy = sorted({c for r in rows for c in FORBIDDEN_LEGACY_COLS if c in r})
    if legacy:
        raise MarketClogitError(f"Group A (logit の仕様) の列がある: {legacy}。C′ の行は market_feature だけで作る")
    by = _by_race(rows)
    for rid, rs in by.items():
        horses = [r["horse_num"] for r in rs]
        if len(set(horses)) != len(horses):
            raise MarketClogitError(f"{rid}: 馬番が重複している {sorted(h for h in set(horses) if horses.count(h) > 1)}")
        total = sum(r[p_key] for r in rs)
        if not abs(total - 1.0) <= SUM_TOL:
            raise MarketClogitError(f"{rid}: P_market の和が 1 でない ({total!r})。§8-6 の選択集合の中で正規化し直した値を渡す")
    return by


def _check_coefficients(*betas: float) -> None:
    if not all(isinstance(b, numbers.Real) and math.isfinite(b) for b in betas):
        raise MarketClogitError(f"係数が有限でない {betas!r} (収束しなかった当てはめの値を渡していないか)")


def add_market_feature(rows: list[dict], p_key: str = "p_market") -> list[dict]:
    """市場の列 `MARKET_COL = market_feature(P_market)` を足した **行のコピー** を返す (入力の行は変えない)。"""
    check_canonical(rows, p_key)
    return [{**r, MARKET_COL: rm.market_feature(r[p_key])} for r in rows]


def fit_clogit(rows: list[dict], s_col: str = "S", p_key: str = "p_market") -> dict:
    """主検定の当てはめ: `P(i 勝ち) ∝ exp(β_market·market_feature(P_market) + β_S·S)`。(β_market, β_S) の組を返す。

    金額の試験の P_new は、この組をそのまま `p_new` / `ratio_buys_at` に渡して作る (T−10 で β_market を推定し直して
    差し替えない、§8-6b)。収束しなければ止める (NaN の係数が後段で「購入 0 件」に化けるのを防ぐ)。入力の行は変えない。
    """
    data = add_market_feature(rows, p_key)
    beta, ok = conditional_logit(data, [MARKET_COL, s_col], with_status=True)
    if not ok:
        raise MarketClogitError(f"条件付きロジットが収束しなかった (beta={list(beta)!r})")
    _check_coefficients(*beta)
    return {"beta_market": float(beta[0]), "beta_s": float(beta[1]), "converged": True,
            "columns": [MARKET_COL, s_col], "market_transform": "log P_market (predictor.race_market.market_feature)"}


def fit_s_given_unit_market(rows: list[dict], s_col: str = "S", p_key: str = "p_market",
                            max_iter: int = 100, tol: float = 1e-10, step_cap: float = 2.0) -> dict:
    """β_market = 1 に固定した当てはめ (市場の列をオフセットにして β_S だけを推定、診断用)。

    `P(i 勝ち) ∝ P_market(i)·exp(β_S·S(i))`。S-correction only の正統な係数 (β_S | β_market = 1)。1 次元の減衰付き Newton 法。
    """
    by = check_canonical(rows, p_key)
    races = []
    for rs in by.values():
        if sum(r["won"] for r in rs) != 1:
            continue
        off = np.array([rm.market_feature(r[p_key]) for r in rs])
        s = np.array([r[s_col] for r in rs], dtype=float)
        y = np.array([r["won"] for r in rs], dtype=float)
        races.append((off, s, y))
    if not races:
        raise MarketClogitError("勝ち馬 1 頭のレースが無い")
    b = 0.0
    for _ in range(max_iter):
        g = h = 0.0
        for off, s, y in races:
            u = off + b * s
            w = np.exp(u - u.max())
            w /= w.sum()
            m = float(w @ s)
            g += float(y @ s) - m
            h += float(w @ (s * s)) - m * m
        if not h > 0:
            raise MarketClogitError("情報が 0 (S がレース内で定数か)")
        step = g / h
        step = max(-step_cap, min(step_cap, step))
        b += step
        if abs(step) < tol:
            return {"beta_s_given_unit_market": b, "converged": True, "n_races": len(races)}
    raise MarketClogitError(f"β_S | β_market = 1 の当てはめが収束しなかった (b={b!r})")


def fisher_se_at_null(rows: list[dict], s_col: str = "S", p_key: str = "p_market") -> dict:
    """β_market = 1・β_S = 0 の仮定での S の係数の SE (シューア補元の Fisher 情報)。**勝ちの列は読まない**。

    市場の列は log なので、この仮定でのモデルの勝つ確率は P_market そのもの (`p_new(p, S, 1, 0) == p`)。重みもそれを使う。
    x = (market_feature, S) のレース内の確率重み付きの共分散を足し合わせた情報行列の逆行列の S の対角から SE を出す。
    """
    if any("won" in r for r in rows):
        raise MarketClogitError("検出力の計算の行に勝ちの列がある (結果を読まない経路のはず)")
    by = check_canonical(rows, p_key)
    info = np.zeros((2, 2))
    for rs in by.values():
        p_market = {r["horse_num"]: r[p_key] for r in rs}
        s = {r["horse_num"]: r[s_col] for r in rs}
        p_null = rm.p_new(p_market, s, 1.0, 0.0)            # 仮定でのモデルの確率 (= P_market、恒等性のテストで固定)
        p = np.array([p_null[r["horse_num"]] for r in rs])
        X = np.array([[rm.market_feature(r[p_key]), r[s_col]] for r in rs], dtype=float)
        m = p @ X
        info += (X * p[:, None]).T @ X - np.outer(m, m)
    try:
        inv = np.linalg.inv(info)
    except np.linalg.LinAlgError as e:
        raise MarketClogitError("情報行列が特異 (S がレース内で定数か、市場の列と S が一次従属)") from e
    var_s = float(info[1, 1])
    return {"se": float(math.sqrt(inv[1, 1])), "n_races": len(by), "info": info.tolist(),
            "var_s_within": var_s, "schur_complement": float(info[1, 1] - info[0, 1] ** 2 / info[0, 0]),
            "rho_within_race_market_weighted": float(info[0, 1] / math.sqrt(info[0, 0] * info[1, 1])),
            "assumption": "beta_market=1, beta_S=0 (win probability = renormalised market probability, log market term)"}


def ratio_buys_at(rows: list[dict], beta_market: float, beta_s: float, s_col: str = "S", p_key: str = "p_market",
                  threshold: float = rm.RATIO_BUY) -> list[tuple[str, str]]:
    """係数の組 (β_market, β_S) で作った P_new に対し、`P_new / P_market ≥ threshold` の (race_id, 馬番)。

    主検定の前の件数の見込み (§8-8) は仮定値 (1, β_target) を、金額の試験は主検定の (β̂_market, β̂_S) を渡す。
    診断の 3 集合 (full / market-recalibration only / S-correction only) もこの関数に係数を変えて渡す。
    比は exp(β_S·S) ではなく、レース内で正規化した P_new で取る (§8-8 の「S ≥ 2」の目安は使わない)。
    非有限の係数は止める (収束しなかった当てはめの NaN が「購入 0 件」に化けるのを防ぐ)。
    """
    _check_coefficients(beta_market, beta_s)
    by = check_canonical(rows, p_key)
    out = []
    for rid, rs in by.items():
        p_market = {r["horse_num"]: r[p_key] for r in rs}
        pn = rm.p_new(p_market, {r["horse_num"]: r[s_col] for r in rs}, beta_market, beta_s)
        out.extend((rid, h) for h in rm.ratio_buys(pn, p_market, threshold))
    return sorted(out)


def diagnostic_sets(rows: list[dict], beta_market_hat: float, beta_s_hat: float, s_col: str = "S",
                    p_key: str = "p_market", beta_s_given_unit_market: float | None = None) -> dict:
    """金額の試験の診断 (§8-6b、判定には使わない): 3 つの係数の組の比 ≥ 1.25 の集合の件数と Jaccard。

    - full: (β̂_market, β̂_S)
    - market_recalibration_only: (β̂_market, 0) — 市場の再校正だけで出る買い目
    - s_correction_only: (1, β̂_S) — 市場は恒等の校正のまま、S の補正だけで出る買い目
    - s_correction_given_unit_market (任意): (1, β̂_S | β_market = 1) — β_market = 1 に制約した当てはめの係数
      (`fit_s_given_unit_market`)。S と市場がレース内で相関すると、同時推定の β̂_S は「S だけの補正」の係数として純粋でないため
    """
    _check_coefficients(beta_market_hat, beta_s_hat)
    sets = {"full": set(ratio_buys_at(rows, beta_market_hat, beta_s_hat, s_col, p_key)),
            "market_recalibration_only": set(ratio_buys_at(rows, beta_market_hat, 0.0, s_col, p_key)),
            "s_correction_only": set(ratio_buys_at(rows, 1.0, beta_s_hat, s_col, p_key))}
    coefficients = {"full": [beta_market_hat, beta_s_hat], "market_recalibration_only": [beta_market_hat, 0.0],
                    "s_correction_only": [1.0, beta_s_hat]}
    if beta_s_given_unit_market is not None:
        sets["s_correction_given_unit_market"] = set(ratio_buys_at(rows, 1.0, beta_s_given_unit_market, s_col, p_key))
        coefficients["s_correction_given_unit_market"] = [1.0, beta_s_given_unit_market]

    def jaccard(a, b):
        return len(a & b) / len(a | b) if a | b else float("nan")

    names = list(sets)
    return {"n": {k: len(v) for k, v in sets.items()},
            "jaccard": {f"{a}|{b}": jaccard(sets[a], sets[b]) for i, a in enumerate(names) for b in names[i + 1:]},
            "coefficients": coefficients}
