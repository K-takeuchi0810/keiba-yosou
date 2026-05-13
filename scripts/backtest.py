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
from predictor.calibration import (
    calibration_report,
    fit_bin_calibrator,
    fit_isotonic_calibrator,
)
from predictor.rules import is_tentative, predict_race


def buy_filter_from_generator() -> dict:
    """買い目フィルタの既定値を取得する。

    出典は `config.BUY_FILTER_DEFAULT` 単一。`min_ev` `min_value` は
    None (= 制約なし) を許容するため、float 変換時に None を温存する。
    """
    from config import BUY_FILTER_DEFAULT

    def _maybe_float(v):
        return float(v) if v is not None else None

    return {
        "min_odds": float(BUY_FILTER_DEFAULT["min_odds"]),
        "max_odds": float(BUY_FILTER_DEFAULT["max_odds"]),
        "min_value": _maybe_float(BUY_FILTER_DEFAULT.get("min_value")),
        "min_ev": _maybe_float(BUY_FILTER_DEFAULT.get("min_ev")),
        "min_popularity": BUY_FILTER_DEFAULT.get("min_popularity"),
        "max_popularity": BUY_FILTER_DEFAULT.get("max_popularity"),
        "exclude_confidence": list(BUY_FILTER_DEFAULT.get("exclude_confidence") or []),
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
    """1 レースの出走馬を返す。horse_num が空 / "00" のプレースホルダ行は除外。

    JV-Data 上で出馬表確定前は SE レコードに馬番が入らない / "00" のことが
    あるが、表示・予想・回収率計算のいずれにも有害なので根元で弾く。
    """
    return [
        dict(r)
        for r in conn.execute(
            """
            SELECT * FROM horse_races
            WHERE race_year=? AND race_month_day=? AND track_code=?
              AND kaiji=? AND nichiji=? AND race_num=?
              AND horse_num IS NOT NULL
              AND TRIM(horse_num) != ''
              AND horse_num != '00'
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
    return {
        "bets": 0,
        "hits": 0,
        "bet_total": 0,
        "return_total": 0,
        "_payouts": [],
        "_stakes": [],
    }


def _add_bet(stats: dict, payout: int) -> None:
    stats["bets"] += 1
    stats["bet_total"] += 100
    stats["_stakes"].append(100)
    stats["_payouts"].append(payout if payout > 0 else 0)
    if payout > 0:
        stats["hits"] += 1
        stats["return_total"] += payout


def _finish_bet_stats(stats: dict) -> dict:
    """終了処理: hit_rate / return_rate / profit + Phase 4 (2026-05-13) CI を計算。

    n=41 戦 4 ヒット (旧 wl_odds_8_20 採用判断) の点推定 116.1% は CI 下限が
    8% / 上限 224% と幅広く、本番投入判断に不適。Wilson 95% CI と
    bootstrap return rate CI を必ず添えるようにする。
    """
    from predictor.stats import wilson_ci, bootstrap_return_rate
    bets = stats["bets"]
    bet_total = stats["bet_total"]
    payouts = stats.pop("_payouts", []) or []
    stakes = stats.pop("_stakes", []) or []
    hit_lo, hit_hi = wilson_ci(stats["hits"], bets) if bets else (0.0, 0.0)
    if bets and payouts and stakes:
        ret_point, ret_lo, ret_hi = bootstrap_return_rate(payouts, stakes, n_resample=1000)
    else:
        ret_point, ret_lo, ret_hi = (0.0, 0.0, 0.0)
    return {
        **stats,
        "hit_rate": (stats["hits"] / bets) if bets else 0,
        "return_rate": (stats["return_total"] / bet_total) if bet_total else 0,
        "profit": stats["return_total"] - bet_total,
        "hit_rate_ci95": [round(hit_lo, 4), round(hit_hi, 4)],
        "return_rate_ci95": [round(ret_lo, 4), round(ret_hi, 4)],
    }


def _matches_buy_filter(
    pred,
    horse: dict,
    tentative: bool,
    spec: dict | None,
    race: dict | None = None,
) -> bool:
    """買い目フィルタ判定。

    spec は config.BUY_FILTER_DEFAULT 由来の dict で、以下キーを参照する:
        min_ev / min_value / min_odds / max_odds / min_popularity /
        max_popularity / exclude_confidence (list).
    `Kelly > 0` の固定条件は撤廃した (現行モデルで Kelly が正になる候補が
    存在しなかったため死フィルタになっていた)。重賞ホワイトリストは race を
    渡したときだけ評価。
    """
    if not spec:
        return False
    from config import is_whitelisted_race  # 関数スコープ import で循環回避
    if race is not None and not is_whitelisted_race(race):
        return False
    odds = (horse.get("win_odds") or 0) / 10.0
    popularity = horse.get("win_popularity") or 0
    if tentative or pred.rank != 1:
        return False
    exclude_conf = spec.get("exclude_confidence", ["暫定", "混戦", "接戦"])
    if pred.confidence in exclude_conf:
        return False
    min_value = spec.get("min_value")
    if min_value is not None and pred.value_score < min_value:
        return False
    min_ev = spec.get("min_ev")
    if min_ev is not None and pred.expected_value < min_ev:
        return False
    min_odds = spec.get("min_odds")
    max_odds = spec.get("max_odds")
    if min_odds is not None and (odds <= 0 or odds < min_odds):
        return False
    if max_odds is not None and (odds <= 0 or odds > max_odds):
        return False
    min_pop = spec.get("min_popularity")
    max_pop = spec.get("max_popularity")
    if popularity:
        if min_pop is not None and popularity < min_pop:
            return False
        if max_pop is not None and popularity > max_pop:
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
        # 重賞ホワイトリスト単独 (EV/Odds フィルタ無視) で◎単勝ベタ買いした
        # 場合の集計。「whitelist だけで控除率超えるか」を測るための指標。
        whitelist_only_stats = _empty_bet_stats()
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
            if _matches_buy_filter(top, top_horse, tentative, buy_filter, race=race):
                _add_bet(buy_only_stats, payout)
            # 重賞ホワイトリスト単独 (EV/Odds 等のフィルタ無視) でのベタ買い結果。
            # 暫定だけは除外。BET_WHITELIST=0 のときは is_whitelisted_race が
            # 常に True を返すので、この集計は all_stats と同等になる。
            from config import is_whitelisted_race  # 循環回避のため局所 import
            if not tentative and is_whitelisted_race(race):
                _add_bet(whitelist_only_stats, payout)
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
    whitelist_only_stats = _finish_bet_stats(whitelist_only_stats)
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
        "all_hit_rate_ci95": all_stats.get("hit_rate_ci95"),
        "all_return_rate_ci95": all_stats.get("return_rate_ci95"),
        "buy_only_bets": buy_only_stats["bets"],
        "buy_only_hits": buy_only_stats["hits"],
        "buy_only_hit_rate": buy_only_stats["hit_rate"],
        "buy_only_return_total": buy_only_stats["return_total"],
        "buy_only_return_rate": buy_only_stats["return_rate"],
        # Phase 4 (2026-05-13): Wilson hit_rate / bootstrap return_rate の 95% CI。
        # n が小さいほど CI 広く、点推定だけでの本番投入判断を防ぐ。
        "buy_only_hit_rate_ci95": buy_only_stats.get("hit_rate_ci95"),
        "buy_only_return_rate_ci95": buy_only_stats.get("return_rate_ci95"),
        # ホワイトリスト単独 (EV/Odds フィルタ無視) で◎単勝ベタ買いの結果。
        # config.BUY_FILTER_DEFAULT.whitelist_tracks の場 (現 07=中京 / 09=阪神)
        # で重賞のみ買ったときの結果。「特定 2 場の重賞ベタ買いで勝てるか」の指標。
        "whitelist_only_bets": whitelist_only_stats["bets"],
        "whitelist_only_hits": whitelist_only_stats["hits"],
        "whitelist_only_hit_rate": whitelist_only_stats["hit_rate"],
        "whitelist_only_return_total": whitelist_only_stats["return_total"],
        "whitelist_only_return_rate": whitelist_only_stats["return_rate"],
        "whitelist_only_hit_rate_ci95": whitelist_only_stats.get("hit_rate_ci95"),
        "whitelist_only_return_rate_ci95": whitelist_only_stats.get("return_rate_ci95"),
        "calibration": calibration_report(calibration_records),
        "calibrator": fit_bin_calibrator(calibration_records),
        "_calibration_records": calibration_records,  # 内部用 (--save 時には除外したい)
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
    lines.append(
        f"  WL単独:     {r.get('whitelist_only_bets', 0):,} 点  的中 {r.get('whitelist_only_hits', 0):,}  "
        f"回収率 {r.get('whitelist_only_return_rate', 0) * 100:.1f}%  (重賞+WL場ベタ買い)"
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
        "--no-filter-from-config",
        action="store_true",
        help="buy_only_* の集計を無効化する (P0-4 以降は config の買い目フィルタが既定 ON)",
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
        "--calibrator-type", choices=["bin", "isotonic"], default="bin",
        help="--save-calibrator 時の校正アルゴリズム。isotonic は単調制約付き "
             "(Phase 3 / 2026-05-13 追加、scikit-learn 必須)",
    )
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
        filter_from_config=not args.no_filter_from_config,
        min_value=args.min_value,
        min_ev=args.min_ev,
        db_path=args.db,
    )
    print(format_report(result))

    if args.save:
        out_dir = Path(__file__).resolve().parent.parent / "data" / "backtest"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = "-all" if args.no_filter_from_config else "-filtered"
        out = out_dir / f"{ts}_{args.bet}_{args.rule_version}{suffix}.json"
        # 巨大な _calibration_records (10 万行レベル) は JSON 保存対象外
        saveable = {k: v for k, v in result.items() if not k.startswith("_")}
        out.write_text(
            json.dumps({"rule_version": args.rule_version, **saveable},
                       indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"\nsaved: {out}")
    if args.save_calibrator:
        out = Path(__file__).resolve().parent.parent / "predictor" / "calibrator.json"
        # 後追い監査用に「いつ・何のデータで fit したか」を必ず記録する
        # (2026-05-12 まで欠落、再現性不能だったため)
        if args.calibrator_type == "isotonic":
            calib_obj = fit_isotonic_calibrator(result["_calibration_records"])
        else:
            calib_obj = result["calibrator"]
        calib_with_meta = {
            **calib_obj,
            "trained_from": args.from_date,
            "trained_to": args.to_date,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "rule_version": args.rule_version,
            "calibrator_type": args.calibrator_type,
        }
        out.write_text(
            json.dumps(calib_with_meta, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(
            f"calibrator saved: {out} type={args.calibrator_type} "
            f"trained {args.from_date}-{args.to_date}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
