"""指定期間のレースで予想を実行し、的中率・回収率を計算する。

usage:
    python -m scripts.backtest --from 20240101 --to 20241231
    python -m scripts.backtest --from 20240101 --to 20241231 --bet fuku

買い目戦略:
    tan  : ◎ (印 1 位) を単勝 100 円
    fuku : ◎ (印 1 位) を複勝 100 円
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import open_db
from predictor.calibration import calibration_report, fit_bin_calibrator
from predictor.rules import is_tentative, predict_race


def buy_filter_from_generator() -> dict:
    from web.generator import BET_MAX_ODDS, BET_MIN_EV, BET_MIN_ODDS, BET_MIN_VALUE

    return {
        "min_odds": BET_MIN_ODDS,
        "max_odds": BET_MAX_ODDS,
        "min_value": BET_MIN_VALUE,
        "min_ev": BET_MIN_EV,
    }


def distance_bucket_label(distance: int | None) -> str:
    """RA.distance を 4 バケットに集約 (predictor/_distance_bucket と揃える)。"""
    d = distance or 0
    if d <= 1400:
        return "sprint"
    if d <= 1800:
        return "mile"
    if d <= 2200:
        return "middle"
    return "long"


def race_class_label(grade_code: str | None) -> str:
    """RA.grade_code をバックテスト集計用クラスにマップ。

    JV-Data 2003 グレードコード:
      A=G1, B=G2, C=G3, D=重賞以外, E=リステッド/OP特別, F=重賞,
      G=J·G1, H=J·G2, I=J·G3, L=リステッド (新)
    今回は予想精度の弱点 (OP/重賞) を切り出すために以下に集約:
      graded  : A,B,C,F (中央平地重賞)
      jraded  : G,H,I (障害重賞)
      op      : D,E,L (リステッド/オープン特別)
      cond    : それ以外 (条件戦・未勝利・新馬・1 勝クラス〜3 勝クラス)
    """
    g = (grade_code or "").strip()
    if g in ("A", "B", "C", "F"):
        return "graded"
    if g in ("G", "H", "I"):
        return "jraded"
    if g in ("D", "E", "L"):
        return "op"
    return "cond"


def list_races(conn, from_date: str, to_date: str, jra_only: bool = True) -> list[dict]:
    """jra_only=True なら中央場 (track_code 01-10) のみ。
    地方場と海外は JV-Data の RACE dataspec で払戻が来ないので除外しないと
    回収率が引きずり落とされる。
    """
    sql = """
        SELECT * FROM races
        WHERE (race_year || race_month_day) BETWEEN ? AND ?
    """
    if jra_only:
        sql += " AND CAST(track_code AS INTEGER) BETWEEN 1 AND 10 "
    sql += " ORDER BY race_year, race_month_day, track_code, race_num "
    return [dict(r) for r in conn.execute(sql, (from_date, to_date)).fetchall()]


def horses_for_race(conn, race: dict) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            """
            SELECT * FROM horse_races
            WHERE race_year=? AND race_month_day=? AND track_code=?
              AND kaiji=? AND nichiji=? AND race_num=?
            ORDER BY CAST(horse_num AS INTEGER)
            """,
            (
                race["race_year"], race["race_month_day"], race["track_code"],
                race["kaiji"], race["nichiji"], race["race_num"],
            ),
        ).fetchall()
    ]


def get_payout(conn, race: dict, horse_num: str, bet_type: str) -> int:
    """馬番が的中していれば払戻金を返す、外れなら 0。

    payouts テーブルは 1 レース 1 行で、同着考慮で配当 1〜3 (単勝) / 1〜5 (複勝) を持つ。
    horse_num の払戻があるかを順に照合する。
    """
    row = conn.execute(
        """
        SELECT * FROM payouts
        WHERE race_year=? AND race_month_day=? AND track_code=?
          AND kaiji=? AND nichiji=? AND race_num=?
        """,
        (
            race["race_year"], race["race_month_day"], race["track_code"],
            race["kaiji"], race["nichiji"], race["race_num"],
        ),
    ).fetchone()
    if not row:
        return 0
    row = dict(row)
    if bet_type == "tan":
        for i in (1, 2, 3):
            if row.get(f"tan_horse_num{i}") == horse_num:
                return row.get(f"tan_payout{i}") or 0
    elif bet_type == "fuku":
        for i in (1, 2, 3, 4, 5):
            if row.get(f"fuku_horse_num{i}") == horse_num:
                return row.get(f"fuku_payout{i}") or 0
    return 0


def _empty_bet_stats() -> dict:
    return {"bets": 0, "hits": 0, "bet_total": 0, "return_total": 0}


def _add_bet(stats: dict, payout: int) -> None:
    stats["bets"] += 1
    stats["bet_total"] += 100
    if payout > 0:
        stats["hits"] += 1
        stats["return_total"] += payout


def _finish_bet_stats(stats: dict) -> dict:
    bets = stats["bets"]
    bet_total = stats["bet_total"]
    return {
        **stats,
        "hit_rate": (stats["hits"] / bets) if bets else 0,
        "return_rate": (stats["return_total"] / bet_total) if bet_total else 0,
        "profit": stats["return_total"] - bet_total,
    }


def _matches_buy_filter(pred, horse: dict, tentative: bool, spec: dict | None) -> bool:
    if not spec:
        return False
    odds = (horse.get("win_odds") or 0) / 10.0
    if tentative:
        return False
    if pred.rank != 1:
        return False
    if pred.confidence in ("暫定", "混戦", "接戦"):
        return False
    if pred.value_score < spec.get("min_value", 0.0):
        return False
    if pred.expected_value < spec.get("min_ev", 0.0):
        return False
    if pred.kelly_fraction <= 0:
        return False
    min_odds = spec.get("min_odds")
    max_odds = spec.get("max_odds")
    if min_odds is not None and (odds <= 0 or odds < min_odds):
        return False
    if max_odds is not None and (odds <= 0 or odds > max_odds):
        return False
    return True


def run_backtest(
    from_date: str,
    to_date: str,
    bet_type: str = "tan",
    skip_tentative: bool = True,
    jra_only: bool = True,
    min_odds: float | None = None,
    max_odds: float | None = None,
    min_popularity: int | None = None,
    max_popularity: int | None = None,
    filter_from_config: bool = False,
    min_value: float | None = None,
    min_ev: float | None = None,
    db_path: str | Path | None = None,
    progress_every: int = 200,
) -> dict:
    started = time.time()
    buy_filter = buy_filter_from_generator() if filter_from_config else None
    if buy_filter is not None:
        if min_odds is not None:
            buy_filter["min_odds"] = min_odds
        if max_odds is not None:
            buy_filter["max_odds"] = max_odds
        if min_value is not None:
            buy_filter["min_value"] = min_value
        if min_ev is not None:
            buy_filter["min_ev"] = min_ev
    with open_db(db_path) if db_path else open_db() as conn:
        races = list_races(conn, from_date, to_date, jra_only=jra_only)

        n_total_races = len(races)
        n_no_horses = 0
        n_no_pick = 0
        n_filtered = 0
        n_tentative_skipped = 0
        n_bet = 0
        n_hit = 0
        total_bet = 0
        total_return = 0
        all_stats = _empty_bet_stats()
        buy_only_stats = _empty_bet_stats()
        calibration_records: list[dict] = []
        confidence_stats: dict[str, dict] = defaultdict(_empty_bet_stats)
        # 会場別ブレイクダウン (track_code → [bet, return, hits])
        track_stats: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
        # グレード別 (graded/op/cond/jraded) ブレイクダウン
        class_stats: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
        # 距離バケット別 (sprint/mile/middle/long) ブレイクダウン
        bucket_stats: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
        feature_cache: dict = {}

        for i, race in enumerate(races, 1):
            if progress_every and i % progress_every == 0:
                elapsed = time.time() - started
                rate = i / elapsed if elapsed > 0 else 0
                print(
                    f"  [{i}/{n_total_races}] {rate:.1f} races/s ...",
                    file=sys.stderr,
                    flush=True,
                )

            horses = horses_for_race(conn, race)
            if not horses:
                n_no_horses += 1
                continue

            preds = predict_race(horses, conn=conn, race=race, cache=feature_cache)
            tentative = is_tentative(preds)
            if skip_tentative and tentative:
                n_tentative_skipped += 1
                continue

            top = next((p for p in preds if p.rank == 1 and p.mark), None)
            if not top:
                n_no_pick += 1
                continue

            top_horse = next((h for h in horses if h.get("horse_num") == top.horse_num), None)
            if not top_horse:
                n_no_pick += 1
                continue
            horse_by_num = {h.get("horse_num"): h for h in horses}
            for pred in preds:
                horse = horse_by_num.get(pred.horse_num)
                if not horse:
                    continue
                calibration_records.append(
                    {
                        "probability": pred.win_probability,
                        "actual": 1 if horse.get("confirmed_order") == 1 else 0,
                        "confidence": pred.confidence,
                    }
                )
            payout = get_payout(conn, race, top.horse_num, bet_type)
            _add_bet(all_stats, payout)
            _add_bet(confidence_stats[top.confidence], payout)
            if _matches_buy_filter(top, top_horse, tentative, buy_filter):
                _add_bet(buy_only_stats, payout)
            if top_horse:
                odds = (top_horse.get("win_odds") or 0) / 10.0
                popularity = top_horse.get("win_popularity") or 0
                if min_odds is not None and (odds <= 0 or odds < min_odds):
                    n_filtered += 1
                    continue
                if max_odds is not None and (odds <= 0 or odds > max_odds):
                    n_filtered += 1
                    continue
                if min_popularity is not None and (popularity <= 0 or popularity < min_popularity):
                    n_filtered += 1
                    continue
                if max_popularity is not None and (popularity <= 0 or popularity > max_popularity):
                    n_filtered += 1
                    continue

            n_bet += 1
            total_bet += 100
            tcode = race["track_code"]
            cclass = race_class_label(race.get("grade_code"))
            bucket = distance_bucket_label(race.get("distance"))
            track_stats[tcode][0] += 100
            class_stats[cclass][0] += 100
            bucket_stats[bucket][0] += 100
            if payout > 0:
                n_hit += 1
                total_return += payout
                track_stats[tcode][1] += payout
                track_stats[tcode][2] += 1
                class_stats[cclass][1] += payout
                class_stats[cclass][2] += 1
                bucket_stats[bucket][1] += payout
                bucket_stats[bucket][2] += 1

    elapsed = time.time() - started
    all_stats = _finish_bet_stats(all_stats)
    buy_only_stats = _finish_bet_stats(buy_only_stats)
    by_confidence = {
        k: _finish_bet_stats(v)
        for k, v in sorted(confidence_stats.items())
    }
    return {
        "from_date": from_date,
        "to_date": to_date,
        "bet_type": bet_type,
        "elapsed_sec": round(elapsed, 1),
        "races_total": n_total_races,
        "races_no_horses": n_no_horses,
        "races_no_pick": n_no_pick,
        "races_filtered": n_filtered,
        "races_tentative_skipped": n_tentative_skipped,
        "races_bet": n_bet,
        "hits": n_hit,
        "hit_rate": (n_hit / n_bet) if n_bet else 0,
        "bet_total": total_bet,
        "return_total": total_return,
        "return_rate": (total_return / total_bet) if total_bet else 0,
        "all_bets": all_stats["bets"],
        "all_hits": all_stats["hits"],
        "all_hit_rate": all_stats["hit_rate"],
        "all_return_total": all_stats["return_total"],
        "all_return_rate": all_stats["return_rate"],
        "buy_only_bets": buy_only_stats["bets"],
        "buy_only_hits": buy_only_stats["hits"],
        "buy_only_hit_rate": buy_only_stats["hit_rate"],
        "buy_only_return_total": buy_only_stats["return_total"],
        "buy_only_return_rate": buy_only_stats["return_rate"],
        "calibration": calibration_report(calibration_records),
        "calibrator": fit_bin_calibrator(calibration_records),
        "by_confidence": by_confidence,
        "filters": {
            "min_odds": min_odds,
            "max_odds": max_odds,
            "min_popularity": min_popularity,
            "max_popularity": max_popularity,
        },
        "buy_filter": buy_filter,
        "by_track": {
            tc: {
                "bet": v[0],
                "return": v[1],
                "hits": v[2],
                "return_rate": (v[1] / v[0]) if v[0] else 0,
            }
            for tc, v in sorted(track_stats.items())
        },
        "by_class": {
            cc: {
                "bet": v[0],
                "return": v[1],
                "hits": v[2],
                "return_rate": (v[1] / v[0]) if v[0] else 0,
            }
            for cc, v in sorted(class_stats.items())
        },
        "by_bucket": {
            b: {
                "bet": v[0],
                "return": v[1],
                "hits": v[2],
                "return_rate": (v[1] / v[0]) if v[0] else 0,
            }
            for b, v in sorted(bucket_stats.items())
        },
    }


def format_report(r: dict) -> str:
    lines = []
    lines.append("==== バックテスト結果 ====")
    lines.append(f"期間:           {r['from_date']} 〜 {r['to_date']}")
    lines.append(f"買い目:         ◎{r['bet_type']} 100 円固定")
    lines.append(f"処理時間:       {r['elapsed_sec']} 秒")
    lines.append("")
    lines.append(f"対象レース:     {r['races_total']:,}")
    lines.append(f"  出走馬不足:   {r['races_no_horses']:,}")
    lines.append(f"  暫定スキップ: {r['races_tentative_skipped']:,}")
    lines.append(f"  ◎付かず:      {r['races_no_pick']:,}")
    lines.append(f"  条件外:        {r.get('races_filtered', 0):,}")
    lines.append(f"  実際に賭けた: {r['races_bet']:,}")
    lines.append("")
    lines.append(f"的中数:         {r['hits']:,}")
    lines.append(f"的中率:         {r['hit_rate'] * 100:.1f} %")
    lines.append(f"投資総額:       {r['bet_total']:,} 円")
    lines.append(f"払戻総額:       {r['return_total']:,} 円")
    lines.append(f"回収率:         {r['return_rate'] * 100:.1f} %")
    lines.append(f"収支:           {r['return_total'] - r['bet_total']:+,} 円")
    lines.append("")
    lines.append("運用別:")
    lines.append(
        f"  ベタ買い:   {r.get('all_bets', 0):,} 点  的中 {r.get('all_hits', 0):,}  "
        f"回収率 {r.get('all_return_rate', 0) * 100:.1f}%"
    )
    lines.append(
        f"  絞り運用:   {r.get('buy_only_bets', 0):,} 点  的中 {r.get('buy_only_hits', 0):,}  "
        f"回収率 {r.get('buy_only_return_rate', 0) * 100:.1f}%"
    )
    cal = r.get("calibration") or {}
    if cal.get("count"):
        lines.append("")
        lines.append(
            f"確率校正:       Brier {cal.get('brier_score')}  LogLoss {cal.get('log_loss')}  "
            f"n={cal.get('count'):,}"
        )
    if r.get("by_confidence"):
        lines.append("")
        lines.append("confidence別:")
        for name, v in r["by_confidence"].items():
            lines.append(
                f"  {name}: {v['bets']:,} 点  的中 {v['hits']:,} "
                f"({v['hit_rate'] * 100:.1f}%)  回収率 {v['return_rate'] * 100:.1f}%"
            )
    if r["by_track"]:
        lines.append("")
        lines.append("会場別:")
        for tc, v in r["by_track"].items():
            n_bet = v["bet"] // 100
            hit_rate = (v["hits"] / n_bet) if n_bet else 0
            lines.append(
                f"  場{tc}: {n_bet:,} 戦  的中 {v['hits']:,} ({hit_rate * 100:.1f}%)  "
                f"回収率 {v['return_rate'] * 100:.1f}%"
            )
    if r.get("by_class"):
        labels = {
            "graded": "G1/G2/G3",
            "op":     "L/OP特",
            "jraded": "障害重賞",
            "cond":   "条件戦等",
        }
        lines.append("")
        lines.append("クラス別:")
        for cc, v in r["by_class"].items():
            n_bet = v["bet"] // 100
            hit_rate = (v["hits"] / n_bet) if n_bet else 0
            label = labels.get(cc, cc)
            lines.append(
                f"  {label:<10} {n_bet:>5,} 戦  的中 {v['hits']:>4,} ({hit_rate * 100:5.1f}%)  "
                f"回収率 {v['return_rate'] * 100:5.1f}%"
            )
    if r.get("by_bucket"):
        bucket_labels = {
            "sprint": "短距離 <=1400",
            "mile":   "マイル <=1800",
            "middle": "中距離 <=2200",
            "long":   "長距離 >2200",
        }
        order = ["sprint", "mile", "middle", "long"]
        lines.append("")
        lines.append("距離別:")
        for b in order:
            v = r["by_bucket"].get(b)
            if not v:
                continue
            n_bet = v["bet"] // 100
            hit_rate = (v["hits"] / n_bet) if n_bet else 0
            label = bucket_labels.get(b, b)
            lines.append(
                f"  {label:<14} {n_bet:>5,} 戦  的中 {v['hits']:>4,} ({hit_rate * 100:5.1f}%)  "
                f"回収率 {v['return_rate'] * 100:5.1f}%"
            )
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_date", required=True, help="YYYYMMDD")
    ap.add_argument("--to", dest="to_date", required=True, help="YYYYMMDD")
    ap.add_argument("--bet", default="tan", choices=["tan", "fuku"])
    ap.add_argument(
        "--include-tentative", action="store_true",
        help="暫定（予想根拠不足）レースもベット対象にする",
    )
    ap.add_argument(
        "--all-tracks", action="store_true",
        help="地方場・海外含めて評価（payouts 未取得分は外れ扱いになるので注意）",
    )
    ap.add_argument("--min-odds", type=float, default=None)
    ap.add_argument("--max-odds", type=float, default=None)
    ap.add_argument(
        "--filter-from-config",
        action="store_true",
        help="web/generator.py の BET_MIN_* で買い候補だけの成績も保存する",
    )
    ap.add_argument("--min-value", type=float, default=None)
    ap.add_argument("--min-ev", type=float, default=None)
    ap.add_argument("--min-popularity", type=int, default=None)
    ap.add_argument("--max-popularity", type=int, default=None)
    ap.add_argument("--db", default=None, help="SQLite DB path")
    ap.add_argument(
        "--save", action="store_true",
        help="data/backtest/<timestamp>.json に結果を保存",
    )
    ap.add_argument("--save-calibrator", action="store_true")
    ap.add_argument(
        "--rule-version", default="v1",
        help="保存時のルールバージョン名 (例: v1, v2-track-condition)",
    )
    args = ap.parse_args()

    result = run_backtest(
        args.from_date, args.to_date, args.bet,
        skip_tentative=not args.include_tentative,
        jra_only=not args.all_tracks,
        min_odds=args.min_odds,
        max_odds=args.max_odds,
        min_popularity=args.min_popularity,
        max_popularity=args.max_popularity,
        filter_from_config=args.filter_from_config,
        min_value=args.min_value,
        min_ev=args.min_ev,
        db_path=args.db,
    )
    print(format_report(result))

    if args.save:
        out_dir = Path(__file__).resolve().parent.parent / "data" / "backtest"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = "-filtered" if args.filter_from_config else "-all"
        out = out_dir / f"{ts}_{args.bet}_{args.rule_version}{suffix}.json"
        out.write_text(
            json.dumps({"rule_version": args.rule_version, **result},
                       indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\nsaved: {out}")
    if args.save_calibrator:
        out = Path(__file__).resolve().parent.parent / "predictor" / "calibrator.json"
        out.write_text(
            json.dumps(result["calibrator"], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"calibrator saved: {out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
