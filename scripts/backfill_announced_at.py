"""既存の odds_snapshots に、提供元が示す発表時刻 (announced_at) を遡及で埋める。

## なぜ要るか

憲法 Phase 0.5-1 は 3 種類の時刻を分けて持つことを要求する:

  (1) レース予定発走時刻
  (2) 情報を取得した時刻   = odds_snapshots.fetched_at (我々のローカル時計)
  (3) 提供元が示す観測時刻 = O1 レコードの announced_at

(3) は今まで parse されていたのに保存されていなかった。PIT 監査で
「受信時刻より後に発表されたオッズを使っていないか」を確かめるのに要る。

## スナップショット 1 枚ずつ正確に紐付ける

初版は (レース, 馬) 単位で埋めたため、**51 枚のスナップ全部に同じ発表時刻**が
入り、14:58 のオッズが「08:43 発表」になっていた。それでは監査が自明に通り、
違反 0 件という嘘の結果が出る。

生ファイル名の末尾のエポックが受信時刻 (fetched_at) と一致することを実測で
確認したので、**(レース, 馬, 受信時刻)** で紐付ける。

    0B31_2026091309040412_1789256703.jvd → 1789256703 → 2026-09-13T08:45:03
    DB の fetched_at                                   = 2026-09-13T08:45:03

usage:
    .venv64/Scripts/python.exe -m scripts.backfill_announced_at [--limit N] [--dry-run] [--reset]
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db import open_db  # noqa: E402
from jvlink_client.parser import O1_LENGTH, _split_fixed, parse_o1  # noqa: E402

RAW_DIRS = ("0B31", "0B30", "0B11", "0B12")
EPOCH_RE = re.compile(r"_(\d{9,11})\.jvd$", re.IGNORECASE)


def received_at_from_name(path: Path) -> str | None:
    """ファイル名末尾のエポックを受信時刻 (ISO8601) にする。

    実測で DB の fetched_at と一致することを確認済み。一致しないファイル名は
    None を返し、**推測で埋めない** (間違った紐付けは監査を嘘にする)。
    """
    m = EPOCH_RE.search(path.name)
    if not m:
        return None
    try:
        return datetime.fromtimestamp(int(m.group(1))).isoformat(timespec="seconds")
    except (ValueError, OverflowError, OSError):
        return None


def iter_o1_files(limit: int | None = None):
    root = Path(__file__).resolve().parent.parent / "data" / "raw"
    seen = 0
    for d in RAW_DIRS:
        base = root / d
        if not base.is_dir():
            continue
        for p in sorted(base.glob("*.jvd")):
            yield p
            seen += 1
            if limit and seen >= limit:
                return


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None, help="先頭 N ファイルだけ")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reset", action="store_true",
                    help="既存の announced_at を消してから入れ直す")
    args = ap.parse_args()

    stats = Counter()
    updates: list[tuple] = []
    for path in iter_o1_files(args.limit):
        stats["files"] += 1
        received_at = received_at_from_name(path)
        if received_at is None:
            stats["no_epoch_in_name"] += 1
            continue
        try:
            data = path.read_bytes()
        except OSError:
            stats["unreadable"] += 1
            continue
        if len(data) < O1_LENGTH:
            continue
        for rec in _split_fixed(data, O1_LENGTH):
            try:
                o1 = parse_o1(rec)
            except Exception:
                stats["parse_error"] += 1
                continue
            if o1.record_type != "O1" or not o1.announced_at.strip():
                continue
            stats["records"] += 1
            for horse_num, _odds, _pop in o1.win_odds:
                updates.append((o1.announced_at, o1.year, o1.month_day,
                                o1.track_code, o1.kaiji, o1.nichiji,
                                o1.race_num, horse_num, received_at))
        if stats["files"] % 2000 == 0:
            print(f"  {stats['files']} ファイル走査 / 候補 {len(updates):,} 行",
                  flush=True)

    print(f"走査 {stats['files']:,} ファイル / O1 レコード {stats['records']:,} / "
          f"更新候補 {len(updates):,} 行 / エポック無し {stats['no_epoch_in_name']:,}")
    if args.dry_run:
        return 0

    with open_db() as conn:
        if args.reset:
            n = conn.execute(
                "UPDATE odds_snapshots SET announced_at=NULL").rowcount
            print(f"  既存の発表時刻を消去: {n:,} 行")
        conn.executemany(
            "UPDATE odds_snapshots SET announced_at=? "
            " WHERE race_year=? AND race_month_day=? AND track_code=? "
            "   AND kaiji=? AND nichiji=? AND race_num=? AND horse_num=? "
            "   AND fetched_at=?",
            updates,
        )
        conn.commit()
        row = conn.execute(
            "SELECT COUNT(*), SUM(CASE WHEN announced_at IS NOT NULL THEN 1 ELSE 0 END)"
            " FROM odds_snapshots").fetchone()
        # 紐付けが 1 枚ずつになっているかの自己検査
        chk = conn.execute(
            """SELECT AVG(d) FROM (
                 SELECT COUNT(DISTINCT announced_at) d FROM odds_snapshots
                  WHERE announced_at IS NOT NULL
                  GROUP BY race_year, race_month_day, track_code, kaiji,
                           nichiji, race_num, horse_num
                  HAVING COUNT(*) > 5)""").fetchone()
    print(f"完了: {row[0]:,} 行中 {row[1]:,} 行に発表時刻あり "
          f"({row[1] / row[0] * 100:.1f}%)")
    print(f"  6 枚以上ある馬の平均『発表時刻の種類数』: {chk[0]:.1f} "
          f"(1.0 なら紐付け失敗、スナップ数に近いほど正しい)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
