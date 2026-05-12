"""Compare simple betting filters using one prediction pass.

usage:
    python -m scripts.filter_sweep --from 20240101 --to 20241231 --bet tan
    python -m scripts.filter_sweep --walk-forward  # 2 期間並列 sweep
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import BUY_FILTER_DEFAULT
from db import open_db
from predictor.rules import is_tentative, predict_race
from scripts.backtest import get_payout, horses_for_race, list_races

WHITELIST_GRADES = frozenset(BUY_FILTER_DEFAULT["whitelist_grades"])
WHITELIST_TRACKS = frozenset(BUY_FILTER_DEFAULT["whitelist_tracks"])


@dataclass
class Pick:
    track_code: str
    grade_code: str          # 重賞判定用 (A/B/C/F = graded)
    ev: float                # 予想 EV
    odds: float
    popularity: int
    confidence: str          # 信頼度ラベル
    tan_payout: int
    fuku_payout: int

    @property
    def is_whitelisted(self) -> bool:
        if self.grade_code and self.grade_code in WHITELIST_GRADES:
            return True
        if self.track_code and self.track_code in WHITELIST_TRACKS:
            return True
        return False


def collect_picks(
    from_date: str,
    to_date: str,
    skip_tentative: bool = True,
    db_path: str | Path | None = None,
) -> list[Pick]:
    picks: list[Pick] = []
    with open_db(db_path) if db_path else open_db() as conn:
        races = list_races(conn, from_date, to_date, jra_only=True)
        feature_cache: dict = {}
        for race in races:
            horses = horses_for_race(conn, race)
            if not horses:
                continue
            preds = predict_race(horses, conn=conn, race=race, cache=feature_cache)
            if skip_tentative and is_tentative(preds):
                continue
            top = next((p for p in preds if p.rank == 1 and p.mark), None)
            if not top:
                continue
            horse = next((h for h in horses if h.get("horse_num") == top.horse_num), None)
            if not horse:
                continue
            picks.append(
                Pick(
                    track_code=race["track_code"],
                    grade_code=(race.get("grade_code") or "").strip(),
                    ev=float(top.expected_value or 0),
                    odds=(horse.get("win_odds") or 0) / 10.0,
                    popularity=horse.get("win_popularity") or 0,
                    confidence=top.confidence,
                    tan_payout=get_payout(conn, race, top.horse_num, "tan"),
                    fuku_payout=get_payout(conn, race, top.horse_num, "fuku"),
                )
            )
    return picks


def match_filter(p: Pick, spec: dict) -> bool:
    if "min_odds" in spec and (p.odds <= 0 or p.odds < spec["min_odds"]):
        return False
    if "max_odds" in spec and (p.odds <= 0 or p.odds > spec["max_odds"]):
        return False
    if "min_pop" in spec and (p.popularity <= 0 or p.popularity < spec["min_pop"]):
        return False
    if "max_pop" in spec and (p.popularity <= 0 or p.popularity > spec["max_pop"]):
        return False
    if "min_ev" in spec and p.ev < spec["min_ev"]:
        return False
    if "tracks" in spec and p.track_code not in spec["tracks"]:
        return False
    if spec.get("whitelist") and not p.is_whitelisted:
        return False
    if "exclude_conf" in spec and p.confidence in spec["exclude_conf"]:
        return False
    return True


def summarize(picks: list[Pick], bet: str, spec: dict) -> dict:
    payout_attr = f"{bet}_payout"
    selected = [p for p in picks if match_filter_extended(p, spec)]
    bet_total = len(selected) * 100
    returns = sum(getattr(p, payout_attr) for p in selected)
    hits = sum(1 for p in selected if getattr(p, payout_attr) > 0)
    return {
        "bets": len(selected),
        "hits": hits,
        "hit_rate": hits / len(selected) if selected else 0,
        "return_rate": returns / bet_total if bet_total else 0,
        "profit": returns - bet_total,
    }


FILTERS = [
    # ベースライン
    ("all", {}),
    ("whitelist_only", {"whitelist": True}),
    # whitelist 内 odds 帯
    ("wl_odds_2_5", {"whitelist": True, "min_odds": 2.0, "max_odds": 5.0}),
    ("wl_odds_5_10", {"whitelist": True, "min_odds": 5.0, "max_odds": 10.0}),
    ("wl_odds_10_20", {"whitelist": True, "min_odds": 10.0, "max_odds": 20.0}),
    ("wl_odds_20_50", {"whitelist": True, "min_odds": 20.0, "max_odds": 50.0}),
    ("wl_odds_5_15", {"whitelist": True, "min_odds": 5.0, "max_odds": 15.0}),
    ("wl_odds_8_20", {"whitelist": True, "min_odds": 8.0, "max_odds": 20.0}),
    # whitelist 内 popularity 帯
    ("wl_pop_1_2", {"whitelist": True, "min_pop": 1, "max_pop": 2}),
    ("wl_pop_1_3", {"whitelist": True, "min_pop": 1, "max_pop": 3}),
    ("wl_pop_4_6", {"whitelist": True, "min_pop": 4, "max_pop": 6}),
    ("wl_pop_4_8", {"whitelist": True, "min_pop": 4, "max_pop": 8}),
    ("wl_pop_7_plus", {"whitelist": True, "min_pop": 7}),
    # whitelist + 信頼度
    ("wl_ex_tentative", {"whitelist": True, "exclude_conf": ["暫定"]}),
    ("wl_ex_unsure", {"whitelist": True, "exclude_conf": ["暫定", "混戦", "接戦"]}),
    # whitelist + 複合
    ("wl_odds_5_15_pop_1_4", {"whitelist": True, "min_odds": 5.0, "max_odds": 15.0, "min_pop": 1, "max_pop": 4}),
    ("wl_odds_2_8_pop_1_3", {"whitelist": True, "min_odds": 2.0, "max_odds": 8.0, "min_pop": 1, "max_pop": 3}),
    ("wl_ex_unsure_pop_1_4", {"whitelist": True, "exclude_conf": ["暫定", "混戦", "接戦"], "min_pop": 1, "max_pop": 4}),
    # wl_odds_8_20 路線の +100% 追求 (2026-05-12 追加, project-state 高インパクト #3)
    # 隣接 odds 帯を試して戦数増の可能性を見る
    ("wl_odds_6_20", {"whitelist": True, "min_odds": 6.0, "max_odds": 20.0}),
    ("wl_odds_7_22", {"whitelist": True, "min_odds": 7.0, "max_odds": 22.0}),
    ("wl_odds_8_25", {"whitelist": True, "min_odds": 8.0, "max_odds": 25.0}),
    ("wl_odds_9_25", {"whitelist": True, "min_odds": 9.0, "max_odds": 25.0}),
    # 8-20 + 信頼度フィルタ重ね掛け (戦数減 / 回収率上振れ狙い)
    ("wl_odds_8_20_ex_unsure", {"whitelist": True, "min_odds": 8.0, "max_odds": 20.0, "exclude_conf": ["暫定", "混戦", "接戦"]}),
    ("wl_odds_8_20_ex_tentative", {"whitelist": True, "min_odds": 8.0, "max_odds": 20.0, "exclude_conf": ["暫定"]}),
    # 8-20 + 人気帯 (中穴 4-8 が wl_pop_4_8 単体で eval 122.1% を出したため)
    ("wl_odds_8_20_pop_4_8", {"whitelist": True, "min_odds": 8.0, "max_odds": 20.0, "min_pop": 4, "max_pop": 8}),
    # wl_pop_4_8 の安定化候補
    ("wl_pop_4_10", {"whitelist": True, "min_pop": 4, "max_pop": 10}),
    ("wl_pop_5_9_ex_unsure", {"whitelist": True, "min_pop": 5, "max_pop": 9, "exclude_conf": ["暫定", "混戦", "接戦"]}),
    # whitelist 外 (= 控除率の低い領域)
    ("non_wl", {"whitelist": False}),
    # 旧バリアント (参考)
    ("odds_2_5", {"min_odds": 2.0, "max_odds": 5.0}),
    ("odds_10_20", {"min_odds": 10.0, "max_odds": 20.0}),
]


# 「whitelist 外」を分離してマッチさせる - whitelist=False は spec 側で扱わないので
# match_filter 内では何もせず、ここでは spec が `whitelist=False` キー持ちのとき
# 「whitelist 外を残す」を意味する。
def _adjust_spec_for_non_whitelist(spec: dict) -> dict:
    """spec で whitelist=False を渡したら「whitelist 外のみ」のマッチを返す用に解釈変更。"""
    return spec  # match_filter で whitelist True のときだけ判定するので互換


# match_filter を whitelist=False の場合に「whitelist 外」と読むよう拡張
def match_filter_extended(p: Pick, spec: dict) -> bool:
    if not match_filter(p, {k: v for k, v in spec.items() if k != "whitelist" or v is True}):
        return False
    if spec.get("whitelist") is False and p.is_whitelisted:
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_date", default=None)
    ap.add_argument("--to", dest="to_date", default=None)
    ap.add_argument("--bet", choices=["tan", "fuku"], default="tan")
    ap.add_argument("--by-year", action="store_true")
    ap.add_argument(
        "--walk-forward",
        action="store_true",
        help="2 期間並列 sweep (design=2025/06-12, eval=2026/01-04)。"
        "両期間とも 80%+ かを比較表示。",
    )
    ap.add_argument("--db", default=None, help="SQLite DB path")
    args = ap.parse_args()

    started = time.time()

    if args.walk_forward:
        periods = [
            ("design", "20250601", "20251231"),
            ("eval", "20260101", "20260430"),
        ]
        period_picks: dict[str, list[Pick]] = {}
        for name, fr, to in periods:
            period_picks[name] = collect_picks(fr, to, db_path=args.db)
            print(
                f"  collected {name} ({fr}-{to}): {len(period_picks[name])} picks",
                file=sys.stderr,
            )
        # 両期間で summarize を集計し並列表示
        print("filter,d_bets,d_hit_rate,d_return_rate,e_bets,e_hit_rate,e_return_rate,robust")
        rows: list[tuple[str, dict, dict]] = []
        for name, spec in FILTERS:
            d = summarize(period_picks["design"], args.bet, spec)
            e = summarize(period_picks["eval"], args.bet, spec)
            rows.append((name, d, e))
        # ソート: 両期間とも >=80% (= robust) を上位、次に min(return) で
        rows.sort(
            key=lambda x: (
                x[1]["return_rate"] >= 0.80 and x[2]["return_rate"] >= 0.80,
                min(x[1]["return_rate"], x[2]["return_rate"]),
            ),
            reverse=True,
        )
        for name, d, e in rows:
            robust = "Y" if d["return_rate"] >= 0.80 and e["return_rate"] >= 0.80 else "n"
            print(
                f"{name},{d['bets']},{d['hit_rate']*100:.1f},{d['return_rate']*100:.1f},"
                f"{e['bets']},{e['hit_rate']*100:.1f},{e['return_rate']*100:.1f},{robust}"
            )
        print(f"sec,{time.time() - started:.1f}", file=sys.stderr)
        return 0

    if not args.from_date or not args.to_date:
        ap.error("--from と --to が必要 (または --walk-forward)")

    print("filter,bets,hits,hit_rate,return_rate,profit")

    if args.by_year:
        start_year = int(args.from_date[:4])
        end_year = int(args.to_date[:4])
        for year in range(start_year, end_year + 1):
            from_date = max(args.from_date, f"{year}0101")
            to_date = min(args.to_date, f"{year}1231")
            picks = collect_picks(from_date, to_date, db_path=args.db)
            for name, spec in FILTERS:
                r = summarize(picks, args.bet, spec)
                print(
                    f"{year}:{name},{r['bets']},{r['hits']},"
                    f"{r['hit_rate'] * 100:.1f},{r['return_rate'] * 100:.1f},{r['profit']}"
                )
    else:
        picks = collect_picks(args.from_date, args.to_date, db_path=args.db)
        rows = [(name, summarize(picks, args.bet, spec)) for name, spec in FILTERS]
        rows.sort(key=lambda x: (x[1]["return_rate"], x[1]["bets"]), reverse=True)
        for name, r in rows:
            print(
                f"{name},{r['bets']},{r['hits']},"
                f"{r['hit_rate'] * 100:.1f},{r['return_rate'] * 100:.1f},{r['profit']}"
            )
    print(f"sec,{time.time() - started:.1f}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
