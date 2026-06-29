"""SQLite アクセスレイヤ。

- `init_db(conn)`: schema.sql を流して必要なテーブルを作る
- `upsert_race(conn, RaceInfo)`: RA レコードを INSERT OR REPLACE
- `upsert_horse_race(conn, HorseRaceInfo)`: SE レコードを INSERT OR REPLACE
- `record_ingested_file(...)`: 取り込み済みファイルを記録
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from config import DB_PATH, PROJECT_ROOT
from jvlink_client.parser import (
    BreedingHorse,
    CourseInfo,
    ExoticOdds,
    HorseMaster,
    HorseNameOrigin,
    HorseRaceInfo,
    JockeyMaster,
    Lineage,
    MiningPrediction,
    O1Odds,
    OffspringMaster,
    OwnerMaster,
    Payout,
    ProducerMaster,
    RaceInfo,
    RaceScratch,
    RecordMaster,
    Schedule,
    Scratch,
    SpecialEntry,
    StartTimeChange,
    TrainerMaster,
    TrainingTime,
    VoteCounts,
    WeatherGoing,
    Win5,
)

SCHEMA_PATH = PROJECT_ROOT / "data" / "schema.sql"


def connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    # GUI スレッド + .venv64 subprocess (render) + 外部スクリプトが並走するため、
    # writer 競合時に即 "database is locked" にせず最大 5 秒待つ (2026-06-13)。
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


@contextmanager
def open_db(path: Path | str = DB_PATH):
    conn = connect(path)
    try:
        init_db(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(conn: sqlite3.Connection) -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema)
    _ensure_column(conn, "horse_races", "odds_fetched_at", "TEXT")
    _ensure_column(conn, "horse_races", "odds_dataspec", "TEXT")
    _ensure_column(conn, "training_times", "data_div", "TEXT")
    _ensure_column(conn, "training_times", "data_created", "TEXT")


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, decl: str) -> None:
    cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


# 整合性のために RA/SE の主キーを race_id 構成順に揃えて生成する
_RACE_PK = (
    "race_year",
    "race_month_day",
    "track_code",
    "kaiji",
    "nichiji",
    "race_num",
)


def _ra_to_row(ra: RaceInfo) -> dict:
    d = asdict(ra)
    d["race_year"] = d.pop("year")
    d["race_month_day"] = d.pop("month_day")
    d.pop("record_type", None)  # 種別 ID は固定なのでテーブルに持たない
    return d


def _se_to_row(se: HorseRaceInfo) -> dict:
    d = asdict(se)
    d["race_year"] = d.pop("year")
    d["race_month_day"] = d.pop("month_day")
    d.pop("record_type", None)
    return d


def upsert_race(conn: sqlite3.Connection, ra: RaceInfo) -> None:
    row = _ra_to_row(ra)
    cols = list(row.keys())
    placeholders = ",".join(f":{c}" for c in cols)
    sql = f"INSERT OR REPLACE INTO races ({','.join(cols)}) VALUES ({placeholders})"
    conn.execute(sql, row)


def upsert_horse_race(conn: sqlite3.Connection, se: HorseRaceInfo) -> None:
    row = _se_to_row(se)
    cols = list(row.keys())
    placeholders = ",".join(f":{c}" for c in cols)
    update_exprs = []
    for col in cols:
        if col in {"race_year", "race_month_day", "track_code", "kaiji", "nichiji", "race_num", "horse_num"}:
            continue
        if col in {"mining_time", "mining_predicted_order", "win_odds", "win_popularity"}:
            update_exprs.append(f"{col}=CASE WHEN excluded.{col} > 0 THEN excluded.{col} ELSE horse_races.{col} END")
        else:
            update_exprs.append(f"{col}=excluded.{col}")
    sql = (
        f"INSERT INTO horse_races ({','.join(cols)}) VALUES ({placeholders}) "
        "ON CONFLICT(race_year, race_month_day, track_code, kaiji, nichiji, race_num, horse_num) "
        f"DO UPDATE SET {','.join(update_exprs)}"
    )
    conn.execute(sql, row)


def _hr_to_row(hr: Payout) -> dict:
    d = asdict(hr)
    d["race_year"] = d.pop("year")
    d["race_month_day"] = d.pop("month_day")
    d.pop("record_type", None)
    return d


def upsert_payout(conn: sqlite3.Connection, hr: Payout) -> None:
    row = _hr_to_row(hr)
    cols = list(row.keys())
    placeholders = ",".join(f":{c}" for c in cols)
    sql = f"INSERT OR REPLACE INTO payouts ({','.join(cols)}) VALUES ({placeholders})"
    conn.execute(sql, row)


def update_win_odds(
    conn: sqlite3.Connection,
    o1: O1Odds,
    fetched_at: str | None = None,
    dataspec: str = "0B31",
) -> int:
    updated = 0
    fetched_at = fetched_at or datetime.now().isoformat(timespec="seconds")
    params_base = (
        o1.year,
        o1.month_day,
        o1.track_code,
        o1.kaiji,
        o1.nichiji,
        o1.race_num,
    )
    for horse_num, odds, popularity in o1.win_odds:
        # 古い snapshot で新しい snapshot を上書きしないためのガード
        # (out-of-order / 再取り込み対策)。既存 odds_fetched_at が NULL
        # (= 未設定 or 確定オッズ) の場合は更新を許可し、既存 snapshot が
        # 取り込む fetched_at より新しい場合のみスキップする。
        # ISO8601 文字列は辞書順比較で時刻順と一致する。
        cur = conn.execute(
            """
            UPDATE horse_races
               SET win_odds = ?, win_popularity = ?,
                   odds_fetched_at = ?, odds_dataspec = ?
             WHERE race_year=? AND race_month_day=? AND track_code=?
               AND kaiji=? AND nichiji=? AND race_num=? AND horse_num=?
               AND (odds_fetched_at IS NULL OR odds_fetched_at <= ?)
            """,
            (odds, popularity, fetched_at, dataspec, *params_base, horse_num, fetched_at),
        )
        updated += cur.rowcount
    return updated


def upsert_horse_master(conn: sqlite3.Connection, um: HorseMaster) -> None:
    row = asdict(um)
    row.pop("record_type", None)
    cols = list(row.keys())
    placeholders = ",".join(f":{c}" for c in cols)
    sql = f"INSERT OR REPLACE INTO horse_masters ({','.join(cols)}) VALUES ({placeholders})"
    conn.execute(sql, row)


def _upsert_master(conn: sqlite3.Connection, table: str, obj) -> None:
    """単一キーマスタ (KS/CH/BR/BN 等) の汎用 upsert。record_type は保存しない。"""
    row = asdict(obj)
    row.pop("record_type", None)
    cols = list(row.keys())
    placeholders = ",".join(f":{c}" for c in cols)
    conn.execute(
        f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) VALUES ({placeholders})",
        row,
    )


def upsert_jockey_master(conn: sqlite3.Connection, ks: JockeyMaster) -> None:
    _upsert_master(conn, "jockey_masters", ks)


def upsert_trainer_master(conn: sqlite3.Connection, ch: TrainerMaster) -> None:
    _upsert_master(conn, "trainer_masters", ch)


def upsert_producer_master(conn: sqlite3.Connection, br: ProducerMaster) -> None:
    _upsert_master(conn, "producer_masters", br)


def upsert_owner_master(conn: sqlite3.Connection, bn: OwnerMaster) -> None:
    _upsert_master(conn, "owner_masters", bn)


def is_file_ingested(conn: sqlite3.Connection, filename: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM ingested_files WHERE filename = ?", (filename,)
    )
    return cur.fetchone() is not None


def record_ingested_file(
    conn: sqlite3.Connection,
    filename: str,
    dataspec: str,
    record_count: int,
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO ingested_files "
        "(filename, dataspec, record_count) VALUES (?, ?, ?)",
        (filename, dataspec, record_count),
    )


# ============================================================
# Phase 1 (2026-05-13): JV-Link 未活用 dataspec upsert
# ============================================================


def upsert_mining_prediction(conn: sqlite3.Connection, mp: MiningPrediction) -> None:
    """DM / TM の per-horse 予想 1 件を upsert。"""
    d = asdict(mp)
    d["race_year"] = d.pop("year")
    d["race_month_day"] = d.pop("month_day")
    cols = list(d.keys())
    placeholders = ",".join(f":{c}" for c in cols)
    sql = f"INSERT OR REPLACE INTO mining_predictions ({','.join(cols)}) VALUES ({placeholders})"
    conn.execute(sql, d)
    if mp.predicted_rank > 0:
        if mp.record_type == "DM":
            conn.execute(
                """
                UPDATE horse_races
                   SET mining_predicted_order = ?
                 WHERE race_year = ?
                   AND race_month_day = ?
                   AND track_code = ?
                   AND kaiji = ?
                   AND nichiji = ?
                   AND race_num = ?
                   AND horse_num = ?
                """,
                (
                    mp.predicted_rank,
                    mp.year,
                    mp.month_day,
                    mp.track_code,
                    mp.kaiji,
                    mp.nichiji,
                    mp.race_num,
                    mp.horse_num,
                ),
            )
        else:
            conn.execute(
                """
                UPDATE horse_races
                   SET mining_predicted_order = ?
                 WHERE race_year = ?
                   AND race_month_day = ?
                   AND track_code = ?
                   AND kaiji = ?
                   AND nichiji = ?
                   AND race_num = ?
                   AND horse_num = ?
                   AND COALESCE(mining_predicted_order, 0) = 0
                """,
                (
                    mp.predicted_rank,
                    mp.year,
                    mp.month_day,
                    mp.track_code,
                    mp.kaiji,
                    mp.nichiji,
                    mp.race_num,
                    mp.horse_num,
                ),
            )


def upsert_breeding_horse(conn: sqlite3.Connection, hn: BreedingHorse) -> None:
    """HN (繁殖馬マスタ) 1 件を upsert。"""
    d = asdict(hn)
    d.pop("record_type", None)
    cols = list(d.keys())
    placeholders = ",".join(f":{c}" for c in cols)
    sql = f"INSERT OR REPLACE INTO breeding_horses ({','.join(cols)}) VALUES ({placeholders})"
    conn.execute(sql, d)


def upsert_offspring_master(conn: sqlite3.Connection, sk: OffspringMaster) -> None:
    """SK (産駒マスタ) 1 件を upsert。"""
    d = asdict(sk)
    d.pop("record_type", None)
    cols = list(d.keys())
    placeholders = ",".join(f":{c}" for c in cols)
    sql = f"INSERT OR REPLACE INTO offspring_master ({','.join(cols)}) VALUES ({placeholders})"
    conn.execute(sql, d)


def upsert_training_time(conn: sqlite3.Connection, tt: TrainingTime) -> None:
    """HC / WC (調教タイム) 1 件を upsert。"""
    d = asdict(tt)
    d.pop("record_type", None)
    cols = list(d.keys())
    placeholders = ",".join(f":{c}" for c in cols)
    sql = f"INSERT OR REPLACE INTO training_times ({','.join(cols)}) VALUES ({placeholders})"
    conn.execute(sql, d)


def upsert_special_entry(conn: sqlite3.Connection, se: SpecialEntry) -> None:
    """TK (特別登録) per-horse エントリ 1 件を upsert。"""
    d = asdict(se)
    d["race_year"] = d.pop("year")
    d["race_month_day"] = d.pop("month_day")
    d.pop("record_type", None)
    cols = list(d.keys())
    placeholders = ",".join(f":{c}" for c in cols)
    sql = f"INSERT OR REPLACE INTO special_entries ({','.join(cols)}) VALUES ({placeholders})"
    conn.execute(sql, d)


def upsert_exotic_odds(conn: sqlite3.Connection, odds: ExoticOdds) -> int:
    """O2-O6 の 1 レコード (= 1 レース 1 式別) を組合せ単位で行展開して upsert。

    戻り値は書き込んだ組合せ行数 (取り込み観測性のため)。
    """
    rows = [
        (
            odds.year, odds.month_day, odds.track_code, odds.kaiji, odds.nichiji,
            odds.race_num, odds.bet_type, combo, odds_low, odds_high, pop,
            odds.data_div, odds.data_created, odds.announced_time,
        )
        for combo, odds_low, odds_high, pop in odds.entries
    ]
    if not rows:
        return 0
    conn.executemany(
        "INSERT OR REPLACE INTO exotic_odds "
        "(race_year, race_month_day, track_code, kaiji, nichiji, race_num, "
        " bet_type, combo, odds_low, odds_high, popularity, data_div, data_created, announced_time) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    return len(rows)


def upsert_vote_counts(conn: sqlite3.Connection, vc: VoteCounts) -> int:
    """H1 / H6 の 1 レコードを組合せ単位で行展開して upsert。

    戻り値は書き込んだ行数 (取り込み観測性のため)。
    """
    rows = [
        (
            vc.year, vc.month_day, vc.track_code, vc.kaiji, vc.nichiji,
            vc.race_num, bet_type, combo, votes, pop, vc.data_div, vc.data_created,
        )
        for bet_type, combo, votes, pop in vc.entries
    ]
    if not rows:
        return 0
    conn.executemany(
        "INSERT OR REPLACE INTO vote_counts "
        "(race_year, race_month_day, track_code, kaiji, nichiji, race_num, "
        " bet_type, combo, votes, popularity, data_div, data_created) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    return len(rows)


def upsert_race_scratch(conn: sqlite3.Connection, jg: RaceScratch) -> None:
    """JG (競走馬除外情報) 1 件を upsert。"""
    d = asdict(jg)
    d["race_year"] = d.pop("year")
    d["race_month_day"] = d.pop("month_day")
    d.pop("record_type", None)
    cols = list(d.keys())
    placeholders = ",".join(f":{c}" for c in cols)
    sql = f"INSERT OR REPLACE INTO race_scratches ({','.join(cols)}) VALUES ({placeholders})"
    conn.execute(sql, d)


def _upsert_race_keyed(conn: sqlite3.Connection, table: str, obj) -> None:
    """year/month_day を race_year/race_month_day にリネームして INSERT OR REPLACE する汎用 upsert。"""
    d = asdict(obj)
    if "year" in d:
        d["race_year"] = d.pop("year")
    if "month_day" in d:
        d["race_month_day"] = d.pop("month_day")
    d.pop("record_type", None)
    cols = list(d.keys())
    placeholders = ",".join(f":{c}" for c in cols)
    conn.execute(
        f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) VALUES ({placeholders})", d
    )


def upsert_record_master(conn: sqlite3.Connection, rc: RecordMaster) -> None:
    _upsert_race_keyed(conn, "record_master", rc)


def upsert_course_info(conn: sqlite3.Connection, cs: CourseInfo) -> None:
    _upsert_master(conn, "course_infos", cs)


def upsert_schedule(conn: sqlite3.Connection, ys: Schedule) -> None:
    _upsert_race_keyed(conn, "schedules", ys)


def upsert_lineage(conn: sqlite3.Connection, bt: Lineage) -> None:
    _upsert_master(conn, "horse_lineages", bt)


def upsert_horse_name_origin(conn: sqlite3.Connection, hy: HorseNameOrigin) -> None:
    _upsert_master(conn, "horse_name_origins", hy)


def upsert_weather_going(conn: sqlite3.Connection, we: WeatherGoing) -> None:
    _upsert_race_keyed(conn, "weather_going", we)


def upsert_race_cancellation(conn: sqlite3.Connection, av: Scratch) -> None:
    _upsert_race_keyed(conn, "race_cancellations", av)


def upsert_start_time_change(conn: sqlite3.Connection, tc: StartTimeChange) -> None:
    _upsert_race_keyed(conn, "start_time_changes", tc)


def upsert_win5(conn: sqlite3.Connection, wf: Win5) -> int:
    """WF (WIN5) のヘッダ + 払戻を upsert。戻り値は払戻行数。"""
    conn.execute(
        "INSERT OR REPLACE INTO win5 "
        "(race_year, race_month_day, target_races, sale_votes, carryover_initial, "
        " carryover_remaining, refund_flag, void_flag, established_flag, data_div, data_created) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            wf.year, wf.month_day, wf.target_races, wf.sale_votes, wf.carryover_initial,
            wf.carryover_remaining, wf.refund_flag, wf.void_flag, wf.established_flag,
            wf.data_div, wf.data_created,
        ),
    )
    rows = [(wf.year, wf.month_day, combo, payout, hit) for combo, payout, hit in wf.payouts]
    if rows:
        conn.executemany(
            "INSERT OR REPLACE INTO win5_payouts "
            "(race_year, race_month_day, combo, payout, hit_votes) VALUES (?,?,?,?,?)",
            rows,
        )
    return len(rows)
