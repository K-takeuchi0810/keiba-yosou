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
from collections import defaultdict

import numpy as np

from predictor import race_market as rm
from predictor.eval_stats import conditional_logit

#: 条件付きロジットの市場の列の名前。
MARKET_COL = "market_feature"
#: レースごとの P_market の和が 1 から離れてよい幅 (選択集合の中で正規化し直していない行を止める)。
SUM_TOL = 1e-9


class MarketClogitError(ValueError):
    pass


def _by_race(rows: list[dict]) -> dict[str, list[dict]]:
    by: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by[r["race_id"]].append(r)
    return by


def check_canonical(rows: list[dict], p_key: str = "p_market") -> None:
    """P_market が §8-6 の canonical (選択集合の中で和 1) であることを確かめる。外れたら止める (黙って正規化し直さない)。"""
    for rid, rs in _by_race(rows).items():
        total = sum(r[p_key] for r in rs)
        if not abs(total - 1.0) <= SUM_TOL:
            raise MarketClogitError(f"{rid}: P_market の和が 1 でない ({total!r})。§8-6 の選択集合の中で正規化し直した値を渡す")


def add_market_feature(rows: list[dict], p_key: str = "p_market") -> None:
    """各行に市場の列 `MARKET_COL = market_feature(P_market)` を足す (canonical を確かめてから)。"""
    check_canonical(rows, p_key)
    for r in rows:
        r[MARKET_COL] = rm.market_feature(r[p_key])


def fit_clogit(rows: list[dict], s_col: str = "S", p_key: str = "p_market") -> dict:
    """主検定の当てはめ: `P(i 勝ち) ∝ exp(β_market·market_feature(P_market) + β_S·S)`。(β_market, β_S) の組を返す。

    金額の試験の P_new は、この組をそのまま `p_new` に渡して作る (T−10 で β_market を推定し直して差し替えない、§8-6b)。
    """
    add_market_feature(rows, p_key)
    beta, ok = conditional_logit(rows, [MARKET_COL, s_col], with_status=True)
    return {"beta_market": float(beta[0]), "beta_s": float(beta[1]), "converged": bool(ok),
            "columns": [MARKET_COL, s_col], "market_transform": "log P_market (predictor.race_market.market_feature)"}


def fisher_se_at_null(rows: list[dict], s_col: str = "S", p_key: str = "p_market") -> dict:
    """β_market = 1・β_S = 0 の仮定での S の係数の SE (シューア補元の Fisher 情報)。**勝ちの列は読まない**。

    市場の列は log なので、この仮定でのモデルの勝つ確率は P_market そのもの (`p_new(p, S, 1, 0) == p`)。重みもそれを使う。
    x = (market_feature, S) のレース内の確率重み付きの共分散を足し合わせた情報行列の逆行列の S の対角から SE を出す。
    """
    if any("won" in r for r in rows):
        raise MarketClogitError("検出力の計算の行に勝ちの列がある (結果を読まない経路のはず)")
    check_canonical(rows, p_key)
    info = np.zeros((2, 2))
    for rs in _by_race(rows).values():
        p_market = {r["horse_num"]: r[p_key] for r in rs}
        s = {r["horse_num"]: r[s_col] for r in rs}
        p_null = rm.p_new(p_market, s, 1.0, 0.0)            # 仮定でのモデルの確率 (= P_market、恒等性のテストで固定)
        p = np.array([p_null[r["horse_num"]] for r in rs])
        X = np.array([[rm.market_feature(r[p_key]), r[s_col]] for r in rs], dtype=float)
        m = p @ X
        info += (X * p[:, None]).T @ X - np.outer(m, m)
    inv = np.linalg.inv(info)
    var_s = float(info[1, 1])
    return {"se": float(math.sqrt(inv[1, 1])), "n_races": len(_by_race(rows)), "info": info.tolist(),
            "var_s_within": var_s, "schur_complement": float(info[1, 1] - info[0, 1] ** 2 / info[0, 0]),
            "rho_within_race_market_weighted": float(info[0, 1] / math.sqrt(info[0, 0] * info[1, 1])),
            "assumption": "beta_market=1, beta_S=0 (win probability = renormalised market probability, log market term)"}


def ratio_buys_at(rows: list[dict], beta_market: float, beta_s: float, s_col: str = "S", p_key: str = "p_market",
                  threshold: float = rm.RATIO_BUY) -> list[tuple[str, str]]:
    """係数の組 (β_market, β_S) で作った P_new に対し、`P_new / P_market ≥ threshold` の (race_id, 馬番)。

    主検定の前の件数の見込み (§8-8) は仮定値 (1, β_target) を、金額の試験は主検定の (β̂_market, β̂_S) を渡す。
    診断の 3 集合 (full / market-recalibration only / S-correction only) もこの関数に係数を変えて渡す。
    比は exp(β_S·S) ではなく、レース内で正規化した P_new で取る。
    """
    check_canonical(rows, p_key)
    out = []
    for rid, rs in _by_race(rows).items():
        p_market = {r["horse_num"]: r[p_key] for r in rs}
        pn = rm.p_new(p_market, {r["horse_num"]: r[s_col] for r in rs}, beta_market, beta_s)
        out.extend((rid, h) for h in rm.ratio_buys(pn, p_market, threshold))
    return sorted(out)


def diagnostic_sets(rows: list[dict], beta_market_hat: float, beta_s_hat: float, s_col: str = "S",
                    p_key: str = "p_market") -> dict:
    """金額の試験の診断 (§8-6b、判定には使わない): 3 つの係数の組の比 ≥ 1.25 の集合の件数と Jaccard。

    - full: (β̂_market, β̂_S)
    - market_recalibration_only: (β̂_market, 0) — 市場の再校正だけで出る買い目
    - s_correction_only: (1, β̂_S) — 市場は恒等の校正のまま、S の補正だけで出る買い目
    """
    sets = {"full": set(ratio_buys_at(rows, beta_market_hat, beta_s_hat, s_col, p_key)),
            "market_recalibration_only": set(ratio_buys_at(rows, beta_market_hat, 0.0, s_col, p_key)),
            "s_correction_only": set(ratio_buys_at(rows, 1.0, beta_s_hat, s_col, p_key))}

    def jaccard(a, b):
        return len(a & b) / len(a | b) if a | b else float("nan")

    names = list(sets)
    return {"n": {k: len(v) for k, v in sets.items()},
            "jaccard": {f"{a}|{b}": jaccard(sets[a], sets[b]) for i, a in enumerate(names) for b in names[i + 1:]},
            "coefficients": {"full": [beta_market_hat, beta_s_hat], "market_recalibration_only": [beta_market_hat, 0.0],
                             "s_correction_only": [1.0, beta_s_hat]}}
