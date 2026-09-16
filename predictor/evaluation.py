"""憲法 (docs/CHARTER_2026_09_17.md) が要求する評価バッテリー。

## なぜ 1 本にまとめるか

方針 3 は「Accuracy・的中率・AUC を最終目的関数にしない」と定め、代わりに
LogLoss / Brier / Calibration / 市場に対する情報利得 / 期待値 / 実回収率 /
最大ドローダウン / 購入件数 / 利益の再現性 を要求する。
方針 9 は「最大払戻上位 1・5・10 件を除外した回収率も報告」を要求する。
方針 10 は Bootstrap 信頼区間・最大ドローダウン・連敗数を要求する。

呼ぶたびに書き直していると、報告のたびに項目が抜ける。実際 2026-09-15 には
「回収率 112%」と報告したあとで大口 3 件依存が判明した。
**合否に関わる数字は必ずここを通す。**

## 使い方

    from predictor.evaluation import evaluate_probabilities, evaluate_bets

    prob = evaluate_probabilities(y, p_model, p_market)   # 確率の良さ
    bets = evaluate_bets(payouts, dates=..., race_ids=...)  # 購入した結果

的中率と AUC も返すが **診断用** であり、合否に使ってはいけない (方針 3)。
"""
from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass, field
from typing import Sequence

EPS = 1e-9


def _clip(p: float) -> float:
    return min(max(p, EPS), 1.0 - EPS)


def _check_pair(y: Sequence, p: Sequence) -> None:
    """長さ違いを黙って切り詰めさせない。

    `zip` は短いほうに合わせて切るので、長さがずれていると **半分のデータで
    計算した値が正常に見える**。実際 log_loss([1,0,1,0], [0.9,0.1]) が
    正しい値の半分を返していた (2026-09-17 コード品質レビューで再現)。
    """
    if len(y) != len(p):
        raise ValueError(
            f"長さが違う: 実績 {len(y)} 件 vs 予測 {len(p)} 件。"
            "zip で切り詰めると誤った値が正常に見えるので拒否する")


def log_loss(y: Sequence[int], p: Sequence[float]) -> float:
    _check_pair(y, p)
    n = len(y)
    if n == 0:
        return float("nan")
    return -sum(
        (yi * math.log(_clip(pi)) + (1 - yi) * math.log(1 - _clip(pi)))
        for yi, pi in zip(y, p)
    ) / n


def brier(y: Sequence[int], p: Sequence[float]) -> float:
    _check_pair(y, p)
    n = len(y)
    return sum((pi - yi) ** 2 for yi, pi in zip(y, p)) / n if n else float("nan")


def auc(y: Sequence[int], p: Sequence[float]) -> float:
    """順位の良さ。**診断用**であり合否には使わない (方針 3)。"""
    _check_pair(y, p)
    n_pos = sum(1 for yi in y if yi)
    n_neg = len(y) - n_pos
    if not n_pos or not n_neg:
        return float("nan")
    order = sorted(range(len(p)), key=lambda i: p[i])
    ranks = [0.0] * len(p)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and p[order[j + 1]] == p[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    rsum = sum(r for r, yi in zip(ranks, y) if yi)
    return (rsum - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def calibration_table(y: Sequence[int], p: Sequence[float],
                      bins: int = 10) -> list[dict]:
    """予測確率の帯ごとに、実際の発生率と比べる (方針 3 の Calibration)。"""
    rows: list[dict] = []
    order = sorted(range(len(p)), key=lambda i: p[i])
    if not order:
        return rows
    size = max(len(order) // bins, 1)
    for b in range(0, len(order), size):
        idx = order[b:b + size]
        if len(idx) < 5:
            continue
        pred = sum(p[i] for i in idx) / len(idx)
        act = sum(y[i] for i in idx) / len(idx)
        rows.append({"n": len(idx), "predicted": round(pred, 5),
                     "actual": round(act, 5), "gap": round(act - pred, 5)})
    return rows


def expected_calibration_error(y: Sequence[int], p: Sequence[float],
                               bins: int = 10) -> float:
    """較正誤差。**測れないときは 0 ではなく nan を返す**。

    以前は全 bin が最小件数に満たないと 0.0 を返しており、
    件数不足を「完璧な較正」と偽装していた (2026-09-17 レビューで再現)。
    """
    _check_pair(y, p)
    tbl = calibration_table(y, p, bins)
    n = sum(r["n"] for r in tbl)
    if n == 0:
        return float("nan")
    return sum(r["n"] * abs(r["gap"]) for r in tbl) / n


@dataclass
class ProbabilityReport:
    """確率の良さ。**主指標は市場に対する情報利得** (方針 3)。"""

    n: int
    log_loss: float
    brier: float
    calibration_error: float
    market_log_loss: float | None = None
    information_gain_vs_market: float | None = None
    auc_diagnostic: float = float("nan")          # 診断用。合否に使わない
    market_auc_diagnostic: float | None = None    # 同上
    calibration: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def evaluate_probabilities(y: Sequence[int], p_model: Sequence[float],
                           p_market: Sequence[float] | None = None,
                           bins: int = 10) -> ProbabilityReport:
    rep = ProbabilityReport(
        n=len(y), log_loss=log_loss(y, p_model), brier=brier(y, p_model),
        calibration_error=expected_calibration_error(y, p_model, bins),
        auc_diagnostic=auc(y, p_model),
        calibration=calibration_table(y, p_model, bins),
    )
    if p_market is not None:
        rep.market_log_loss = log_loss(y, p_market)
        rep.information_gain_vs_market = rep.market_log_loss - rep.log_loss
        rep.market_auc_diagnostic = auc(y, p_market)
    return rep


@dataclass
class BetReport:
    """購入結果。**回収率単独では合否にしない** (方針 9/10)。"""

    n_bets: int
    n_hits: int
    hit_rate: float
    stake: float
    payout: float
    return_rate: float
    balance: float
    # 方針 9: 大当たり依存性
    return_rate_excl_top1: float
    return_rate_excl_top5: float
    return_rate_excl_top10: float
    top_payouts: list[float]
    # 方針 10: 不確実性
    ci95_low: float
    ci95_high: float
    max_drawdown: float
    max_losing_streak: int
    # 方針 9: 再現性
    n_days: int
    n_months: int
    monthly_return_rates: dict[str, float]
    profitable_month_ratio: float
    # 探索の健全性 (方針 15): 何通り試した中の 1 つか。
    # Phase 1 の交互作用探索では何百通りも試すので、素の区間だけを見ると
    # 「探して一番良かったもの」を実力と誤認する。
    n_hypotheses: int = 1
    ci_adjusted_low: float = float("nan")
    # 出所 (方針 7/8/15)。これが無いと「どの期間・どのオッズ・どのコードで
    # 出した数字か」が成果物から分からず、後から検証できない。
    meta: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return asdict(self)


def _z_for_one_sided(alpha: float) -> float:
    """片側 alpha に対応する z 値 (二分探索)。多重比較補正で使う。"""
    lo, hi = 0.0, 10.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if 0.5 * math.erfc(mid / math.sqrt(2)) > alpha:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _bootstrap_ci(values: Sequence[float], groups: Sequence | None,
                  iters: int = 2000, seed: int = 20260917) -> tuple[float, float]:
    """回収率の信頼区間。

    **計算は predictor.stats.bootstrap_return_rate に委譲する。**
    同じ数字を出す実装を 2 つ持つと、同じ購入列に対して 2 つの区間が出て
    「どちらが正しいのか」が決まらない (2026-09-17 レビュー指摘)。

    groups を渡すとその単位 (レース / 開催日) で再抽出する。同一レース内の
    相関を壊さないため、購入が 1 レース複数点になる場合は必ず渡すこと。
    """
    if len(values) < 2:
        return (float("nan"), float("nan"))
    from predictor.stats import bootstrap_return_rate

    # payouts は「1 単位賭けたときの倍率」なので、stake は全件 1 とする。
    # 整数化はしない (倍率は小数)。bootstrap_return_rate は合計比を取るだけなので
    # 小数でも正しく動く。
    _, lo, hi = bootstrap_return_rate(
        list(values), [1.0] * len(values), n_resample=iters, seed=seed,
        groups=list(groups) if groups is not None else None)
    return (lo, hi)


def _check_dates(dates: Sequence[str], n: int) -> None:
    """日付が YYYYMMDD であること。

    ハイフン付き ("2026-05-10") を渡すと月キーが "2026-0" になり、月数が
    1 と出る。同じ事故を 2026-09-14 に config 側で直したのに、新しいモジュールで
    再発させた (2026-09-17 レビューで再現)。
    """
    if len(dates) != n:
        raise ValueError(f"dates の長さ {len(dates)} が購入 {n} 件と違う")
    bad = [d for d in dates if not (len(str(d)) == 8 and str(d).isdigit())]
    if bad:
        raise ValueError(
            f"dates は YYYYMMDD で渡すこと (例: {bad[0]!r})。"
            "ハイフン付きだと月別集計が壊れる")


ODDS_SOURCES = ("T-10", "final", "unknown")


def evaluate_bets(payouts: Sequence[float],
                  dates: Sequence[str] | None = None,
                  race_ids: Sequence | None = None,
                  bootstrap_iters: int = 2000,
                  n_hypotheses: int = 1,
                  odds_source: str = "unknown",
                  window: tuple[str, str] | None = None,
                  split_name: str | None = None,
                  extra_meta: dict | None = None) -> BetReport:
    """購入 1 件 = **1 単位賭けたときの払戻倍率** (外れは 0.0) の列を渡す。

    金額ではなく倍率で統一する。以前は `stake_each` を受け取っていたが、
    払戻を倍率・賭け金を金額として扱っていたため、`stake_each=100` にすると
    収支が桁違いになっていた (2026-09-17 レビューで再現)。単位を 1 本にして
    混ざりようをなくす。

    dates を渡すと月別の再現性・連敗・ドローダウンを時系列順で計算する。
    race_ids を渡すとブートストラップをレース単位で行う。
    n_hypotheses に「何通り試した中の 1 つか」を渡すと多重比較補正後の
    区間下限も出す (Phase 1 の交互作用探索で必須)。
    """
    n = len(payouts)
    if n == 0:
        raise ValueError(
            "購入が 0 件。評価する対象がない。"
            "(方針 13 により 0 件は正常な結果だが、回収率は定義できない)")
    if dates is not None:
        _check_dates(dates, n)
    if race_ids is None and n > 1:
        # 1 レース複数点買う戦略では、レース内の結果が連動するため
        # 1 件ずつ独立に再抽出すると区間が不当に狭くなる。省略を黙って
        # 許すと、狭すぎる区間で「有意」と誤認する (2026-09-17 検証レビュー指摘)。
        raise ValueError(
            "race_ids が必要。1 レース 1 点でも `race_ids=list(range(n))` を "
            "明示すること (省略すると馬単位の再抽出になり区間が不当に狭くなる)")
    if race_ids is not None and len(race_ids) != n:
        raise ValueError(f"race_ids の長さ {len(race_ids)} が購入 {n} 件と違う")
    if odds_source not in ODDS_SOURCES:
        raise ValueError(
            f"odds_source は {ODDS_SOURCES} のいずれか (got {odds_source!r})。"
            "T-10 と確定オッズを混ぜた数字は比較できない")
    stake_each = 1.0
    hits = sum(1 for x in payouts if x > 0)
    total = float(sum(payouts))
    srt = sorted(payouts, reverse=True)

    def excl(k: int) -> float:
        rest = srt[k:]
        return (sum(rest) / len(rest)) if rest else float("nan")

    order = list(range(n))
    if dates is not None:
        order.sort(key=lambda i: dates[i])
    cum = peak = dd = 0.0
    streak = worst_streak = 0
    for i in order:
        cum += payouts[i] - stake_each
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
        if payouts[i] > 0:
            streak = 0
        else:
            streak += 1
            worst_streak = max(worst_streak, streak)

    monthly: dict[str, list[float]] = {}
    if dates is not None:
        for x, d in zip(payouts, dates):
            monthly.setdefault(str(d)[:6], []).append(x)
    m_rr = {k: sum(v) / len(v) for k, v in sorted(monthly.items())}
    prof = (sum(1 for v in m_rr.values() if v >= 1.0) / len(m_rr)
            if m_rr else float("nan"))

    lo, hi = _bootstrap_ci(list(payouts), race_ids, iters=bootstrap_iters)
    # 多重比較補正: n_hypotheses 通り試したなら片側 α を割る (ボンフェローニ)。
    # Phase 1 の交互作用探索では何百通りも試すので、素の区間だけを見ると
    # 「探して一番良かったもの」を実力と誤認する。
    adj_low = lo
    if n_hypotheses > 1 and hi > lo:
        se = (hi - lo) / (2 * 1.96)
        adj_low = (total / n) - _z_for_one_sided(0.05 / n_hypotheses) * se
    return BetReport(
        n_bets=n, n_hits=hits, hit_rate=hits / n,
        stake=n * stake_each, payout=total, return_rate=total / n,
        balance=total - n * stake_each,
        return_rate_excl_top1=excl(1), return_rate_excl_top5=excl(5),
        return_rate_excl_top10=excl(10),
        top_payouts=[round(float(x), 1) for x in srt[:10]],
        ci95_low=lo, ci95_high=hi, max_drawdown=dd,
        max_losing_streak=worst_streak,
        n_days=len(set(dates)) if dates is not None else 0,
        n_months=len(m_rr),
        monthly_return_rates={k: round(v, 4) for k, v in m_rr.items()},
        profitable_month_ratio=prof,
        n_hypotheses=n_hypotheses, ci_adjusted_low=adj_low,
        meta=_build_meta(odds_source, window, split_name, dates, extra_meta),
    )


def _build_meta(odds_source: str, window: tuple[str, str] | None,
                split_name: str | None, dates: Sequence[str] | None,
                extra: dict | None) -> dict:
    """成果物が自分について説明できるようにする (方針 7/8/15)。"""
    import subprocess
    from datetime import datetime

    meta: dict = {
        "evaluated_at": datetime.now().isoformat(timespec="seconds"),
        "odds_source": odds_source,
        "split_name": split_name,
        "window": list(window) if window else (
            [min(dates), max(dates)] if dates else None),
    }
    try:
        from config import PROJECT_ROOT
        meta["git_sha"] = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
            cwd=PROJECT_ROOT, check=True).stdout.strip()
    except Exception:
        meta["git_sha"] = None
    if extra:
        meta.update(extra)
    return meta


MIN_BETS_FOR_JUDGEMENT = 100


def format_bet_report(r: BetReport, target: float = 1.40) -> str:
    """人が読む形。

    **合否は点推定ではなく信頼区間の下限で決める。**
    憲法の合格条件は「140% を統計的に確認できないモデルは本番投入しない」。
    点推定が目標を超えただけで「達成」と書くと、憲法が禁じる誤読を
    報告様式そのものが誘発する (2026-09-17 収益性レビュー指摘)。
    """
    if r.n_bets < MIN_BETS_FOR_JUDGEMENT:
        head = (f"判定不能: 購入 {r.n_bets} 件は {MIN_BETS_FOR_JUDGEMENT} 件未満。"
                "区間が広すぎて合否を言えない")
    else:
        ok_target = r.ci95_low >= target          # 点推定ではなく下限で見る
        ok_break_even = r.ci95_low > 1.0
        ok_robust = r.return_rate_excl_top5 >= 1.0
        head = (
            f"判定: 目標 {target * 100:.0f}% "
            f"{'達成 (区間下限が目標超)' if ok_target else '未達'} / "
            f"区間下限>100% {'○' if ok_break_even else '×'} / "
            f"大当たり非依存 {'○' if ok_robust else '×'}"
        )
    lines = [
        f"購入 {r.n_bets:,} 件 / 的中 {r.n_hits:,} ({r.hit_rate * 100:.1f}%)",
        f"回収率 (点推定) {r.return_rate * 100:.1f}%  95%区間 "
        f"[{r.ci95_low * 100:.1f}%, {r.ci95_high * 100:.1f}%]  "
        f"収支 {r.balance:+,.1f} 単位",
        f"大当たり依存: 上位1件除外 {r.return_rate_excl_top1 * 100:.1f}% / "
        f"5件除外 {r.return_rate_excl_top5 * 100:.1f}% / "
        f"10件除外 {r.return_rate_excl_top10 * 100:.1f}%",
        f"最大ドローダウン {r.max_drawdown:.1f} 単位 / 最大連敗 {r.max_losing_streak} / "
        f"{r.n_days} 日 {r.n_months} ヶ月 / 黒字月 "
        f"{r.profitable_month_ratio * 100:.0f}%",
    ]
    if r.n_hypotheses > 1:
        lines.append(
            f"多重比較: {r.n_hypotheses} 通り試した中の 1 つ。"
            f"補正後の区間下限 {r.ci_adjusted_low * 100:.1f}% "
            "(これを見ないと『探して一番良かったもの』を実力と誤認する)")
    lines.append(head)
    return "\n".join(lines)
