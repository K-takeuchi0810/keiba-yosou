"""prediction_log (発行時点の予想) と確定結果を突合し live 的中率・回収率を出す。

F4 答え合わせ (2026-07-15)。web.generator --log-predictions が貯めた「実際に配信した
予想」を confirmed_order / payouts.tan_payout1 と JOIN する。backtest (再構築) と違い
**発行時点で凍結された予想**なのでハインドサイトが無い。同一レースに複数 generated_at が
あるときは最新スナップショットを採用 (発走に最も近い予想)。

使い方:
  .venv64/Scripts/python.exe -m scripts.prediction_accuracy [--from YYYYMMDD --to YYYYMMDD] [--mark ◎]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import guard_analysis_window, sealed_notice  # noqa: E402
from db import open_db  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_date", default="00000000")
    ap.add_argument("--to", dest="to_date", default="99999999")
    ap.add_argument("--mark", default="◎", help="集計対象の印 (既定 ◎)")
    ap.add_argument(
        "--allow-sealed", action="store_true",
        help="F3 封印窓 (2026-10-01〜) も集計する。意図的な封印破りとして"
             "監査ログに記録される。12 月の判定材料には使えなくなる",
    )
    args = ap.parse_args()

    # F3 封印ホールドアウト。既定の集計窓が全期間 (00000000〜99999999) なので、
    # 10/01 を過ぎると無引数実行がそのまま封印窓を読みに行く。ここで打ち切る。
    from_date, to_date, sealed_info = guard_analysis_window(
        args.from_date, args.to_date, allow_sealed=args.allow_sealed,
        context="prediction_accuracy")
    notice = sealed_notice(sealed_info)
    if notice:
        print(notice)
    if sealed_info.get("fully_sealed"):
        return 0

    with open_db() as conn:
        # レース×馬ごとに最新 generated_at のスナップショットのみ採用。
        rows = conn.execute(
            """
            WITH latest AS (
                SELECT pl.*,
                       ROW_NUMBER() OVER (
                         PARTITION BY race_year, race_month_day, track_code, kaiji,
                                      nichiji, race_num, horse_num
                         ORDER BY generated_at DESC) AS rn
                  FROM prediction_log pl
                 WHERE (race_year || race_month_day) BETWEEN ? AND ?
                   AND mark = ?
            )
            SELECT l.race_year, l.race_month_day, l.track_code, l.kaiji, l.nichiji,
                   l.race_num, l.horse_num, l.win_odds, l.model_version,
                   hr.confirmed_order, p.tan_payout1, p.tan_horse_num1
              FROM latest l
              JOIN horse_races hr
                ON hr.race_year=l.race_year AND hr.race_month_day=l.race_month_day
               AND hr.track_code=l.track_code AND hr.kaiji=l.kaiji
               AND hr.nichiji=l.nichiji AND hr.race_num=l.race_num
               AND hr.horse_num=l.horse_num
              LEFT JOIN payouts p
                ON p.race_year=l.race_year AND p.race_month_day=l.race_month_day
               AND p.track_code=l.track_code AND p.kaiji=l.kaiji
               AND p.nichiji=l.nichiji AND p.race_num=l.race_num
             WHERE l.rn = 1 AND hr.confirmed_order > 0
            """,
            (from_date, to_date, args.mark),   # 封印窓で打ち切った窓を使う
        ).fetchall()

    n = len(rows)
    if n == 0:
        print(f"prediction_log に該当データなし (mark={args.mark}, {args.from_date}-{args.to_date})。"
              "web.generator --log-predictions で蓄積が始まる。")
        return 0
    wins = sum(1 for r in rows if r["confirmed_order"] == 1)
    # 単勝フラット: 的中時は tan_payout1 (該当馬が1着=payout対象) を回収。100円賭け。
    ret = sum((r["tan_payout1"] or 0) for r in rows
              if r["confirmed_order"] == 1 and r["tan_payout1"])
    staked = n * 100
    # 要求した窓ではなく **実際に集計した窓** を出す (封印で打ち切られた場合に
    # 見出しだけ全期間のままだと、範囲を誤認したまま数字を読むことになる)。
    print(f"=== {args.mark} live 答え合わせ ({from_date}-{to_date}) ===")
    print(f"  対象レース(確定): {n}")
    print(f"  的中(1着): {wins} = {100*wins/n:.1f}%")
    print(f"  単勝フラット回収率: {100*ret/staked:.1f}% (賭 {staked:,}円 / 戻 {ret:,}円)")
    models = sorted({r["model_version"] for r in rows if r["model_version"]})
    print(f"  モデル版: {models}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
