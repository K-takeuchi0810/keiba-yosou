"""1 レースの「選択集合」と市場の確率・P_new・購入条件を、評価の全経路で同じ規則で作る (事前登録 0.5-5 §8-6 / §8-6b)。

## 返還の対象と、それ以外の扱い (§8-6)

| 異常コード | 金額 (回収率) | 尤度 (条件付きロジットの選択集合) |
|---|---|---|
| 1 出走取消 / 2 発走除外 / 3 競走除外 | 返還: 賭けに数えない | 集合から除く |
| 4 競走中止 / 5 失格 / 7 降着 | 返還しない (4・5 は外れ、7 は確定着順どおり) | 集合に残す |

- 返還の対象 (`db.REFUNDED_ABNORMAL_CODES`) を除いてから、**残った馬だけで** 市場の確率を正規化し直す。除いた馬の確率ぶん、
  edge と比が系統的に正に寄るのを防ぐ
- 返還の対象に価格が無い (`win_odds = 0`) ことは、レースを落とす理由にしない (旧実装は `runner_set_mismatch` で黙って落とした。
  除外が発走後に分かる情報なので、後知恵の選択になる)
- **返還の対象でない馬に価格が無い** レースは、市場の確率を作れないので除く。理由・馬番・レースを成果物に残す (黙って落とさない)

## P_new の唯一の定義 (§8-6b)

`P_new(i) = exp(β_market·log P_market(i) + β_S·S(i)) / Σ_j exp(β_market·log P_market(j) + β_S·S(j))`

- 市場の項は **log P_market** (logit ではない)。β_market = 1・β_S = 0 で P_new が P_market に **ちょうど** 一致する。
  logit で入れると、β_market = 1 でも `p / (1 − p)` の正規化になり、市場そのものにならない (本命ほど過大)
- 尤度 (条件付きロジット) の列と、金額の側の確率の変換は、この関数の同じ係数で作る (別のモデルにしない)
"""
from __future__ import annotations

import math
import numbers
from dataclasses import dataclass, field

from collections import defaultdict

from db import is_refunded  # noqa: F401  (返還の対象の判定の単一の出典は db。ここでは再公開するだけ)
from predictor.eval_stats import MIN_BUYS_FOR_MONEY, N_BOOT, block_boot, flat_bet_roi

# 金額の対照と区分 (下の関数) は predictor/eval_stats.py に置かない: eval_stats.py と db.py は Group A の主検定の錠
# (data/backtest/group_a_20261005/final/PRIMARY_LOCK.json の pinned) が sha256 を固定したファイルで、変えると Group A の
# 固定のファイルの照合が通らなくなる

#: 購入条件 (事前登録 §4-5・§8-8): `P_new / P_market ≥ 1.25`。結果を見て変えない。
RATIO_BUY = 1.25
#: 140% 級の目安 (観察の記録だけ。購入条件ではない)。
RATIO_140 = 1.75
#: 金額の合格を主張してよい最低点数 (事前登録 §4-5 の検出力の表・§8-7 の区分)。100〜1,499 点は MONEY_UNDERPOWERED。
MIN_BUYS_FOR_MONEY_PASS = 1500


@dataclass(frozen=True)
class ChoiceSet:
    """返還の対象を除いた出走馬 (尤度と金額の対象) と、その中で正規化し直した市場の確率。"""
    choice: tuple[str, ...]
    refunded: tuple[str, ...]
    #: 市場の名前 → {馬番: 選択集合の中で和 1 の確率}
    implied: dict[str, dict[str, float]]
    #: 市場の名前 → 価格があった返還の対象の馬番 (診断: 旧実装はこれを外れの賭けに数えた)
    refunded_priced: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class Excluded:
    """尤度から除くレース。理由と、原因になった馬番を成果物に残す。"""
    reason: str
    horses: tuple[str, ...]


def build_choice_set(abnormal: dict[str, object], markets: dict[str, dict[str, float]]) -> ChoiceSet | Excluded:
    """1 レースの選択集合を作る。

    abnormal: そのレースの **全出走登録馬** (取消を含む) の 馬番 → 異常コード (正常は '0' や '')
    markets: 市場の名前 → {馬番: オッズ}。オッズ ≤ 0 や欠けは「価格なし」
    """
    refunded = tuple(sorted(h for h, c in abnormal.items() if is_refunded(c)))
    choice = tuple(sorted(h for h, c in abnormal.items() if not is_refunded(c)))
    if not choice:
        return Excluded("no_runner_after_refund", refunded)
    implied: dict[str, dict[str, float]] = {}
    refunded_priced: dict[str, tuple[str, ...]] = {}
    for name, odds in markets.items():
        unknown = tuple(sorted(h for h in odds if h not in abnormal))
        if unknown:
            return Excluded(f"market_runner_not_registered:{name}", unknown)
        unpriced = tuple(h for h in choice if not odds.get(h, 0.0) > 0.0)
        if unpriced:
            return Excluded(f"nonrefund_runner_without_price:{name}", unpriced)
        inv = {h: 1.0 / odds[h] for h in choice}
        total = sum(inv.values())
        implied[name] = {h: v / total for h, v in inv.items()}
        refunded_priced[name] = tuple(h for h in refunded if odds.get(h, 0.0) > 0.0)
    return ChoiceSet(choice=choice, refunded=refunded, implied=implied, refunded_priced=refunded_priced)


class MarketFeatureError(ValueError):
    """市場の確率が条件付きロジットの市場の列を作れない値 (0 以下・1 超・NaN・非有限)。"""


def market_feature(p: float) -> float:
    """条件付きロジットの市場の列の **唯一の** 変換 (§8-6b)。`log P_market` (logit ではない)。

    C′ 以降の尤度の列・検出力の Fisher 情報・P_new・金額の評価はすべてこれを通す (`predictor/market_clogit.py`)。
    `p` は §8-6 の選択集合の中で正規化し直した P_market。0 以下・1 超・NaN・非有限は **止める** (epsilon で丸めない。
    丸めると、価格の欠けたデータが黙って極端な本命・人気薄の値として尤度に入る)。実数 (numpy の浮動小数を含む) だけを受け、
    bool と文字列は拒否する。例外の文は ASCII の記号だけにする (cp932 のコンソールで表示に失敗して理由が隠れないように)。
    """
    if isinstance(p, bool) or not isinstance(p, numbers.Real) or not math.isfinite(p) or not 0.0 < p <= 1.0:
        raise MarketFeatureError(f"market probability out of range: {p!r} (need finite 0 < p <= 1)")
    return math.log(float(p))


def p_new(p_market: dict[str, float], s: dict[str, float], beta_market: float, beta_s: float) -> dict[str, float]:
    """§8-6b の P_new。`p_market` は選択集合の中で和 1 (build_choice_set の implied)。

    C′ の尤度・検出力・購入の件数の見込みは `predictor/market_clogit.py` からこれと `market_feature` を通す (事前登録 §8-6b)。
    """
    if set(p_market) != set(s):
        raise ValueError(f"P_market と S の馬の集合が違う: {sorted(set(p_market) ^ set(s))}")
    u = {h: beta_market * market_feature(p) + beta_s * s[h] for h, p in p_market.items()}
    m = max(u.values())
    e = {h: math.exp(v - m) for h, v in u.items()}
    total = sum(e.values())
    return {h: v / total for h, v in e.items()}


def ratio_buys(p_model: dict[str, float], p_market: dict[str, float],
               threshold: float = RATIO_BUY) -> list[str]:
    """購入条件 `P_new / P_market ≥ threshold` を満たす馬番 (同じ選択集合の、正規化し直した市場に対して)。"""
    if set(p_model) != set(p_market):
        raise ValueError(f"比を取る 2 つの確率の馬の集合が違う: {sorted(set(p_model) ^ set(p_market))}")
    return sorted(h for h in p_model if p_model[h] >= threshold * p_market[h])


def ratio_set(rows: list[dict], model_key: str, threshold: float = RATIO_BUY,
              market_key: str = "p_t10") -> list[dict]:
    """標本の行 (複数レース) から、レースごとに `rows[model_key] / rows[market_key] ≥ threshold` の行を返す。"""
    by_race: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_race[r["race_id"]].append(r)
    out = []
    for race_rows in by_race.values():
        hit = set(ratio_buys({r["horse_num"]: r[model_key] for r in race_rows},
                             {r["horse_num"]: r[market_key] for r in race_rows}, threshold))
        out.extend(r for r in race_rows if r["horse_num"] in hit)
    return out


def choice_rows(rows: list[dict], abnormal: dict[str, object],
                markets: dict[str, dict[str, float]]) -> tuple[ChoiceSet, list[dict]] | Excluded:
    """評価の標本の行 (1 レースぶん、`horse_num` と `won` を持つ) を選択集合に絞る。

    標本の行は返還の対象 (2・3) を敗者として含みうる (`build_dataset` の包含規則は変えない、§8-6)。ここで除く。
    """
    cs = build_choice_set(abnormal, markets)
    if isinstance(cs, Excluded):
        return cs
    have = {r["horse_num"] for r in rows}
    extra = tuple(sorted(have - set(abnormal)))
    if extra:
        return Excluded("sample_row_not_registered", extra)
    missing = tuple(h for h in cs.choice if h not in have)
    if missing:
        return Excluded("choice_runner_without_sample_row", missing)
    keep = set(cs.choice)
    refunded_winner = tuple(sorted(r["horse_num"] for r in rows if r["won"] == 1 and r["horse_num"] not in keep))
    if refunded_winner:
        return Excluded("winner_is_refunded", refunded_winner)
    return cs, [r for r in rows if r["horse_num"] in keep]


# --- 金額の対照 (事前登録 §4-5) ------------------------------------------------------------


def market_proportional_roi(samples: list[dict], p_key: str = "p_t10", n_boot: int = N_BOOT) -> dict:
    """事前登録 §4-5 の対照 1: 1 レースに 100 円を **市場の確率に比例して** 配る (`stake ∝ 1/odds`)。

    `p_key` は選択集合の中で和 1 に正規化し直した市場の確率 (`predictor.race_market.build_choice_set`)。
    返還の対象は標本に居ないので、賭け金も払戻も 0 (事前登録 §8-6)。
    """
    def roi(draw):
        if not draw:
            return None
        stake = sum(100.0 * s[p_key] for s in draw)
        ret = sum(100.0 * s[p_key] * s["payout_odds"] for s in draw if s["won"] == 1)
        return ret / stake if stake > 0 else None

    point = roi(samples)
    n_races = len({s["race_id"] for s in samples})
    lo, hi = block_boot(samples, roi, n_boot=n_boot) if samples else (float("nan"), float("nan"))
    return {"n_races": n_races, "roi": float("nan") if point is None else point, "roi_ci95": [lo, hi]}


def favourite_flat_roi(samples: list[dict], odds_key: str = "odds_t10", n_boot: int = N_BOOT) -> dict:
    """事前登録 §4-5 の対照 2: 各レースのオッズ最小の 1 頭に 100 円 (同値は馬番の小さい方、数値で比べる)。返還の対象は標本に居ない。"""
    by_race: dict[str, list[dict]] = defaultdict(list)
    for s in samples:
        by_race[s["race_id"]].append(s)
    picks = [min(rows, key=lambda s: (s[odds_key], int(s["horse_num"]))) for rows in by_race.values()]
    return flat_bet_roi(picks, n_boot=n_boot)


def tail_calibration(samples: list[dict], new_key: str, market_key: str) -> dict:
    """購入集合の「実勝利数 / Σ P_new / Σ P_market」(事前登録 §4-5 の観察の記録。判定には使わない)。"""
    return {"n": len(samples), "wins": int(sum(s["won"] for s in samples)),
            "sum_p_new": float(sum(s[new_key] for s in samples)),
            "sum_p_market": float(sum(s[market_key] for s in samples))}


def money_class(flat: dict) -> str:
    """金額の区分 (事前登録 §4-5・§8-7)。**合格を主張してよいのは MONEY_PASS だけ**。

    - MONEY_UNTESTABLE: 100 点未満 (区間を定義しない)
    - MONEY_UNDERPOWERED: 100〜1,499 点 (区間は記録するが、下限が 100% を超えても合格を主張しない)
    - MONEY_PASS: 1,500 点以上かつ回収率の 95% 区間の下限 > 100% (点推定ではなく区間の下限で判定する)
    - MONEY_NOT_PASSED: 1,500 点以上で、下限が 100% 以下か区間が無効
    """
    n = flat["n_bets"]
    if n < MIN_BUYS_FOR_MONEY:
        return "MONEY_UNTESTABLE"
    if n < MIN_BUYS_FOR_MONEY_PASS:
        return "MONEY_UNDERPOWERED"
    lo = flat["roi_ci95"][0]
    return "MONEY_PASS" if lo == lo and lo > 1.0 else "MONEY_NOT_PASSED"

