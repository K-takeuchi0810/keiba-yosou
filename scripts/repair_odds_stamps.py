"""horse_races.odds_fetched_at の post-start 刻印を修復する。

背景 (2026-08-22 検出):
  発走後に走る ingest (毎分実行の外部 live 取得 / 20:00 傾向収集バッチ) が
  realtime O1 を取り込むたびに `odds_fetched_at` へ発走後の時刻を刻印し、
  `scripts.backtest.race_odds_untrusted` がそのレースを「post-start snapshot
  あり」として検証母数から除外していた。実害は 2026 年 1-6 月の適格レースが
  1,568 → 1,135 に縮小 (同じ期間・同じモデルでも再実行するたびに母数が減る)。

  書き込み側は `db.update_win_odds` の post-start ガードで恒久対処済み。本
  スクリプトは **既に刻印されてしまった行** を後追いで修復する。

修復方針 (1 行ごと):
  (a) odds_snapshots に発走前 (fetched_at < 発走時刻) の snapshot がある
      → その最新値を horse_races に復元する (PIT として最も正しい値)。
  (b) 発走前 snapshot が無い
      → win_odds は残したまま odds_fetched_at を NULL にする。発走後の
        オッズは締切後で動かないため確定オッズと等価であり、NULL
        (= 確定・信頼。ただし PIT 特徴には使用禁止) が正しい意味づけ。

既定は dry-run。実際に書くときだけ `--apply` を付ける。実行結果は
`data/runtime/repair_odds_stamps_<ts>.json` に監査ログとして残す。

usage:
    python -m scripts.repair_odds_stamps --from 20260101 --to 20260822
    python -m scripts.repair_odds_stamps --from 20260101 --to 20260822 --apply
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import DB_PATH, open_db  # noqa: E402

ROOT_DIR = Path(__file__).resolve().parent.parent

# 発走時刻 (races.start_time, "HHMM") を ISO8601 に組み立てる SQL 断片。
# horse_races.odds_fetched_at と辞書順比較できる形にそろえる。
START_ISO_SQL = (
    "r.race_year || '-' || substr(r.race_month_day, 1, 2) || '-' "
    "|| substr(r.race_month_day, 3, 2) || 'T' "
    "|| substr(r.start_time, 1, 2) || ':' || substr(r.start_time, 3, 2) || ':00'"
)


def find_post_start_rows(
    conn: sqlite3.Connection, from_date: str, to_date: str, jra_only: bool
) -> list[dict]:
    """post-start 刻印されている horse_races 行を列挙する。"""
    track_filter = "AND r.track_code BETWEEN '01' AND '10'" if jra_only else ""
    rows = conn.execute(
        f"""
        SELECT h.race_year, h.race_month_day, h.track_code, h.kaiji, h.nichiji,
               h.race_num, h.horse_num, h.win_odds, h.win_popularity,
               h.odds_fetched_at, h.odds_dataspec, {START_ISO_SQL} AS start_iso
          FROM horse_races h
          JOIN races r USING (race_year, race_month_day, track_code,
                              kaiji, nichiji, race_num)
         WHERE h.race_year || h.race_month_day BETWEEN ? AND ?
           AND h.odds_fetched_at IS NOT NULL
           AND length(trim(coalesce(r.start_time, ''))) = 4
           AND h.odds_fetched_at >= {START_ISO_SQL}
           {track_filter}
        """,
        (from_date, to_date),
    ).fetchall()
    return [dict(r) for r in rows]


def newest_pre_start_snapshot(
    conn: sqlite3.Connection, row: dict
) -> dict | None:
    """その馬の「発走前」snapshot のうち最新のものを返す。無ければ None。"""
    snap = conn.execute(
        """
        SELECT fetched_at, win_odds, win_popularity, source
          FROM odds_snapshots
         WHERE race_year=? AND race_month_day=? AND track_code=?
           AND kaiji=? AND nichiji=? AND race_num=? AND horse_num=?
           AND fetched_at < ?
         ORDER BY fetched_at DESC
         LIMIT 1
        """,
        (
            row["race_year"], row["race_month_day"], row["track_code"],
            row["kaiji"], row["nichiji"], row["race_num"], row["horse_num"],
            row["start_iso"],
        ),
    ).fetchone()
    return dict(snap) if snap else None


def repair(
    conn: sqlite3.Connection,
    from_date: str,
    to_date: str,
    *,
    jra_only: bool = True,
    apply: bool = False,
) -> dict:
    rows = find_post_start_rows(conn, from_date, to_date, jra_only)
    restored = cleared = 0
    affected_races: set[tuple] = set()
    # 巻き戻し用に、変更前の値をそのまま監査ログへ残す (改ざん防止と
    # 「何を書き換えたか後から言える」ことの担保。7 千行規模なので JSON で足りる)。
    before_rows: list[dict] = []
    for row in rows:
        affected_races.add((
            row["race_year"], row["race_month_day"], row["track_code"],
            row["kaiji"], row["nichiji"], row["race_num"],
        ))
        keys = (
            row["race_year"], row["race_month_day"], row["track_code"],
            row["kaiji"], row["nichiji"], row["race_num"], row["horse_num"],
        )
        snap = newest_pre_start_snapshot(conn, row)
        before_rows.append({
            "keys": list(keys),
            "win_odds": row["win_odds"],
            "win_popularity": row["win_popularity"],
            "odds_fetched_at": row["odds_fetched_at"],
            "odds_dataspec": row["odds_dataspec"],
            "action": "restore" if snap is not None else "clear",
        })
        if snap is not None:
            restored += 1
            if apply:
                conn.execute(
                    """
                    UPDATE horse_races
                       SET win_odds = ?, win_popularity = ?,
                           odds_fetched_at = ?, odds_dataspec = ?
                     WHERE race_year=? AND race_month_day=? AND track_code=?
                       AND kaiji=? AND nichiji=? AND race_num=? AND horse_num=?
                    """,
                    (
                        snap["win_odds"], snap["win_popularity"],
                        snap["fetched_at"],
                        # odds_dataspec は "0B31" 等の dataspec コードのドメイン。
                        # odds_snapshots.source は "0B31" だけでなく "morning" /
                        # "backfill_0B31" 等の運用ラベルも入るため、そのまま書くと
                        # GUI/HTML の dataspec 表示にラベルが漏れる (2026-08-22
                        # コード品質監査指摘)。元の値を保つ。
                        row["odds_dataspec"],
                        *keys,
                    ),
                )
        else:
            cleared += 1
            if apply:
                conn.execute(
                    """
                    UPDATE horse_races
                       SET odds_fetched_at = NULL
                     WHERE race_year=? AND race_month_day=? AND track_code=?
                       AND kaiji=? AND nichiji=? AND race_num=? AND horse_num=?
                    """,
                    keys,
                )
    if apply:
        conn.commit()
    return {
        "before_rows": before_rows,
        "from_date": from_date,
        "to_date": to_date,
        "jra_only": jra_only,
        "applied": apply,
        "post_start_rows": len(rows),
        "restored_from_snapshot": restored,
        "cleared_to_null": cleared,
        "affected_races": len(affected_races),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="from_date", required=True, help="YYYYMMDD")
    ap.add_argument("--to", dest="to_date", required=True, help="YYYYMMDD")
    ap.add_argument("--db", default=None, help="SQLite DB path")
    ap.add_argument(
        "--all-tracks", action="store_true",
        help="地方・海外も対象にする (既定は JRA 中央 01-10 のみ)",
    )
    ap.add_argument(
        "--apply", action="store_true",
        help="実際に UPDATE する (既定は dry-run で件数だけ出す)",
    )
    args = ap.parse_args()

    db_path = args.db or DB_PATH
    with open_db(db_path) as conn:
        conn.row_factory = sqlite3.Row
        summary = repair(
            conn, args.from_date, args.to_date,
            jra_only=not args.all_tracks, apply=args.apply,
        )

    before_rows = summary.pop("before_rows", [])
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    out_dir = ROOT_DIR / "data" / "runtime"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = out_dir / f"repair_odds_stamps_{stamp}.json"
    out.write_text(
        json.dumps(
            {"run_at": stamp, **summary, "before_rows": before_rows},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"audit: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
