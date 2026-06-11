"""買い候補の日単位ポートフォリオ集計 (P20-3 / 2026-06-07)。

web/generator.py と gui/app.py で同型再実装されていた
「開催日ごとに recommended_kelly を合算し、1 日あたり上限
(config.BET_PORTFOLIO_MAX_PCT) を超えた日は超過分を按分 scale する」
ロジックの **単一出典**。CLAUDE.md が警告する「単一出典乖離クラス」を解消する。

bankroll は 1 開催日ごとに区切られる前提なので **日単位** で集計する。
多日窓の買い候補を全件合算すると誤って巨大化するため、日をまたぐ集計はしない。

config への一方向依存のみ (predictor.risk は import しない)。recommended_kelly は
呼び出し側 (web/generator.py:277, gui/app.py:671) が risk.recommended_fraction で
既に算出済みの fraction を渡す前提なので、本モジュールは合算と按分のみを担う。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from config import BET_KELLY_MAX_PCT, BET_KELLY_MODE, BET_PORTFOLIO_MAX_PCT


def compute_day_portfolio(
    candidates: Iterable[Mapping],
    *,
    portfolio_cap: float | None = None,
    per_bet_cap: float | None = None,
    kelly_mode: str | None = None,
) -> dict:
    """買い候補を開催日ごとに集計し、ポートフォリオ rollup を単一契約で返す。

    引数:
        candidates: 買い候補 dict の列。各 dict の契約:
            date              : 開催日 "YYYY-MM-DD" (None なら "?" に丸める)
            recommended_kelly : 推奨投資率 fraction 0-1
                                (= 1/4 Kelly + per-bet cap 済)
            expected_value    : EV。想定回収率 (推奨賭金加重平均 EV) に使用。
                                後方互換として "ev" キーも許容する
                                (gui/app.py の item は "ev" を使うため)。
        portfolio_cap: 1 日あたり投資率上限 (fraction)。None なら
            config.BET_PORTFOLIO_MAX_PCT。
        per_bet_cap: 1 点あたり上限 (fraction)。表示メタ用。None なら
            config.BET_KELLY_MAX_PCT。
        kelly_mode: "full"/"half"/"quarter"。表示メタ用。None なら
            config.BET_KELLY_MODE。

    戻り (単一契約。web の portfolio_info / gui の buy_portfolio を統一):
        count           : 候補総数
        days            : [{date, count, total_pct, over_cap, scale}, ...]
                          (date 昇順。total_pct は ×100 済、scale は超過日のみ <1.0)
        max_day_pct     : 全日の total_pct の最大 (空なら 0.0)
        any_over_cap    : いずれかの日が 1 日上限を超過したか
        exp_return_pct  : 推奨賭金加重平均 EV ×100 (候補ゼロ/加重ゼロなら None)
        multi_day       : 集計対象日が 2 日以上か
        cap_pct         : portfolio_cap ×100 (表示メタ)
        per_bet_cap_pct : per_bet_cap ×100 (表示メタ)
        kelly_mode      : kelly_mode 文字列 (表示メタ)
    """
    cap = portfolio_cap if portfolio_cap is not None else BET_PORTFOLIO_MAX_PCT
    per_bet = per_bet_cap if per_bet_cap is not None else BET_KELLY_MAX_PCT
    mode = kelly_mode if kelly_mode is not None else BET_KELLY_MODE

    candidates = list(candidates)

    by_day_total: dict[str, float] = {}
    by_day_count: dict[str, int] = {}
    weighted_ev_num = 0.0
    weighted_ev_den = 0.0
    for c in candidates:
        day = c.get("date") or "?"
        rec = c.get("recommended_kelly") or 0.0
        ev = c.get("expected_value")
        if ev is None:
            ev = c.get("ev")  # gui/app.py item の旧フィールド名後方互換
        ev = ev or 0.0
        by_day_total[day] = by_day_total.get(day, 0.0) + rec
        by_day_count[day] = by_day_count.get(day, 0) + 1
        weighted_ev_num += rec * ev
        weighted_ev_den += rec

    days = []
    for day in sorted(by_day_total):
        tot = by_day_total[day]
        over = tot > cap
        days.append({
            "date": day,
            "count": by_day_count[day],
            "total_pct": round(tot * 100, 2),
            "over_cap": over,
            "scale": (cap / tot if over and tot > 0 else 1.0),
        })

    return {
        "count": len(candidates),
        "days": days,
        "max_day_pct": round(max((d["total_pct"] for d in days), default=0.0), 2),
        "any_over_cap": any(d["over_cap"] for d in days),
        "exp_return_pct": (
            round(weighted_ev_num / weighted_ev_den * 100, 1)
            if weighted_ev_den else None
        ),
        "multi_day": len(by_day_total) > 1,
        "cap_pct": round(cap * 100, 1),
        "per_bet_cap_pct": round(per_bet * 100, 1),
        "kelly_mode": mode,
    }
