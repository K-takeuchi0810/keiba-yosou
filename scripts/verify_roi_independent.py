"""回収率の独立再計算 (外部検証、2026-09-04)。

`scripts/backtest.py` とは **別の実装** で同じ数字を出し、71.5% という値が
実装バグではないことを確認する。予想ロジック (predictor) は共有せざるを
得ないが、**集計・払戻突合・母数の決定を一切共有しない**ことで、
「集計側のバグで数字が良く/悪く出ている」可能性を潰す。

backtest.py と意図的に変えている点:
  - 払戻を payouts テーブルの tan_horse_num1..3 から直接引く
    (backtest は get_payout_with_presence を経由)
  - 母数を races テーブルから独立に SQL で決める
    (backtest は list_races を経由)
  - 的中判定を payouts の的中馬番との一致で行う
    (backtest は払戻額 > 0 で判定)
  - 予想は prediction_log ではなく predict_race を都度呼ぶが、
    ◎ の抽出は rank/mark に依存せず「最大 score の馬」を独立に選ぶ
    (印付けロジックのバグを迂回する)

usage:
    python -m scripts.verify_roi_independent --from 20260101 --to 20260816
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import DB_PATH, PROJECT_ROOT, SQL_VALID_HORSE_NUM  # noqa: E402
from predictor.pit_view import mask_post_race  # noqa: E402
from predictor.rules import predict_race  # noqa: E402


def independent_payout(conn: sqlite3.Connection, keys: tuple, horse_num: str) -> int:
    """payouts から単勝払戻を直接引く (backtest の get_payout を使わない)。

    的中馬番が一致した口だけを足す。同着で最大 3 口ある。
    """
    row = conn.execute(
        """SELECT tan_horse_num1, tan_payout1, tan_horse_num2, tan_payout2,
                  tan_horse_num3, tan_payout3
             FROM payouts
            WHERE race_year=? AND race_month_day=? AND track_code=?
              AND kaiji=? AND nichiji=? AND race_num=?""",
        keys,
    ).fetchone()
    if row is None:
        return -1  # 払戻データ欠損は -1 で区別 (0 = 外れ とは別)
    want = str(horse_num).strip().lstrip("0")
    total = 0
    for i in (0, 2, 4):
        num = str(row[i] or "").strip().lstrip("0")
        pay = row[i + 1] or 0
        if num and num == want and pay > 0:
            total += pay
    return total


def run(from_date: str, to_date: str, db_path: str | None = None,
        require_market: bool = False, limit: int | None = None) -> dict:
    conn = sqlite3.connect(f"file:{db_path or DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    # 母数を独立に決める: JRA 中央 + 期間 + 確定勝ち馬が居るレース
    races = conn.execute(
        f"""
        SELECT r.* FROM races r
         WHERE r.race_year || r.race_month_day BETWEEN ? AND ?
           AND r.track_code BETWEEN '01' AND '10'
           AND EXISTS (
                SELECT 1 FROM horse_races h
                 WHERE h.race_year=r.race_year AND h.race_month_day=r.race_month_day
                   AND h.track_code=r.track_code AND h.kaiji=r.kaiji
                   AND h.nichiji=r.nichiji AND h.race_num=r.race_num
                   AND CAST(h.confirmed_order AS INTEGER)=1
                   AND {SQL_VALID_HORSE_NUM}
           )
         ORDER BY r.race_year, r.race_month_day, r.track_code, r.race_num
        """,
        (from_date, to_date),
    ).fetchall()
    if limit:
        races = races[:limit]

    n_races = len(races)
    bets = hits = 0
    stake = payout_total = 0
    missing_payout = 0
    skipped_no_market = 0
    skipped_no_horses = 0
    cache: dict = {}
    per_race: list[dict] = []

    for r in races:
        race = dict(r)
        keys = (race["race_year"], race["race_month_day"], race["track_code"],
                race["kaiji"], race["nichiji"], race["race_num"])
        horses = [dict(h) for h in conn.execute(
            f"""SELECT * FROM horse_races
                 WHERE race_year=? AND race_month_day=? AND track_code=?
                   AND kaiji=? AND nichiji=? AND race_num=?
                   AND {SQL_VALID_HORSE_NUM}""", keys).fetchall()]
        if not horses:
            skipped_no_horses += 1
            continue

        # 予想入力は発走後列を落とす (backtest と同じ規律、ただし別経路で適用)
        pred_input = [mask_post_race(h) for h in horses]
        if require_market and not any((h.get("win_odds") or 0) > 0 for h in pred_input):
            skipped_no_market += 1
            continue

        preds = predict_race(pred_input, conn=conn, race=race, cache=cache)
        if not preds:
            skipped_no_horses += 1
            continue
        # ◎ を rank/mark に頼らず「最大 score」で独立に選ぶ
        top = max(preds, key=lambda p: (p.score, -int(p.horse_num or "99")))

        pay = independent_payout(conn, keys, top.horse_num)
        if pay < 0:
            missing_payout += 1
            continue
        bets += 1
        stake += 100
        payout_total += pay
        if pay > 0:
            hits += 1
        per_race.append({"race": "-".join(keys), "pick": top.horse_num, "payout": pay})

    conn.close()
    meta = {"db_path": str(db_path or DB_PATH)}
    try:
        meta["git_sha"] = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
            cwd=PROJECT_ROOT, check=True).stdout.strip()
    except Exception:
        meta["git_sha"] = None

    return {
        "meta": meta,
        "from_date": from_date,
        "to_date": to_date,
        "require_market": require_market,
        "races_scanned": n_races,
        "bets": bets,
        "hits": hits,
        "hit_rate": round(hits / bets, 4) if bets else None,
        "stake": stake,
        "payout": payout_total,
        "return_rate": round(payout_total / stake, 4) if stake else None,
        "balance": payout_total - stake,
        "skipped": {"no_market": skipped_no_market, "no_horses": skipped_no_horses,
                    "missing_payout": missing_payout},
        "per_race_count": len(per_race),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="from_date", required=True)
    ap.add_argument("--to", dest="to_date", required=True)
    ap.add_argument("--db", default=None)
    ap.add_argument("--require-market", action="store_true")
    ap.add_argument("--limit", type=int, default=None,
                    help="先頭 N レースだけ (動作確認用)")
    ap.add_argument("--save", action="store_true")
    args = ap.parse_args()

    started = datetime.now()
    out = run(args.from_date, args.to_date, db_path=args.db,
              require_market=args.require_market, limit=args.limit)
    out["elapsed_sec"] = round((datetime.now() - started).total_seconds(), 1)
    print(json.dumps(out, ensure_ascii=False, indent=1))

    if args.save:
        d = PROJECT_ROOT / "data" / "backtest"
        d.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = "_require" if args.require_market else ""
        p = d / f"{ts}_independent_roi_{args.from_date}_{args.to_date}{suffix}.json"
        p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"saved: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
