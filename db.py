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
from datetime import date
from datetime import datetime
from pathlib import Path

from config import DB_PATH, PROJECT_ROOT
from jvlink_client.parser import (
    BreedingHorse,
    CourseInfo,
    CourseChange,
    ExoticOdds,
    HorseMaster,
    HorseNameOrigin,
    HorseRaceInfo,
    JockeyChange,
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
def sql_valid_horse_num(column: str = "horse_num") -> str:
    """Return the canonical SQL predicate for a qualified horse_num column."""
    return (
        f"{column} IS NOT NULL AND TRIM({column}) != '' AND {column} != '00'"
    )


SQL_VALID_HORSE_NUM = sql_valid_horse_num()


def is_valid_horse_num(value: object) -> bool:
    """Return whether a Python horse number matches SQL_VALID_HORSE_NUM."""
    text = str(value or "").strip()
    return bool(text) and text != "00"


# --- 中止レース ---------------------------------------------------------
# JV-Data の data_div='9' は「中止」。台風などで開催が飛ぶとこの値になり、
# 確定着順も払戻も存在しない。**馬券は返還される**ので、的中率の分母にも
# 購入件数にも利益にも入れてはいけない。
#
# 2026-09-21 の中山 12R (台風で 9/22 へ順延) で、これを除外していない経路が
# 1 つ見つかった: `build_daily_results.py` は日付だけで引くため、中止レースの
# confirmed_order が 0 になって「◎ が外れた」と数えられ、買い候補があれば
# `profit = -100` に計上されていた。走っていないレースの負けである。
#
# 他の経路 (backtest / prediction_accuracy / monitor) は `confirmed_order > 0`
# の副作用で **たまたま**落ちていた。その条件が将来緩むと中止が再流入するので、
# 暗黙に頼らず下の述語で明示する。
CANCELLED_DATA_DIV = "9"

#: 評価対象から外した理由。`evaluation_exclusion_reason` に入れる。
#
# **この 2 つを同じ「評価対象外」で潰してはいけない。**
#   cancelled              = 永久除外。レースが行われず馬券は返還された
#   result_not_yet_available = 一時的。結果が取り込まれれば評価可能へ遷移する
# 一緒くたにすると、「まだ結果が来ていないだけ」のレースを永久に評価から
# 落としたまま気付けなくなる。逆に結果未取得を評価対象に入れると、
# confirmed_order=0 が「不的中」に数えられて的中率が下がる。
EXCLUSION_CANCELLED = "cancelled"
EXCLUSION_RESULT_PENDING = "result_not_yet_available"
#: 着順は来たが払戻がまだ。**これを負けにも 0 円決済にもしてはいけない**。
# 「着順だけ先に入る → 払戻未取得 → 勝った買い候補を -100 円」は、今回の
# 中止レースと同型の事故。着順の到着と払戻の到着は別のタイミングで来る。
EXCLUSION_PAYOUT_PENDING = "payout_not_yet_available"


def sql_evaluable_race(column: str = "data_div") -> str:
    """統計評価に使えるレースだけを残す SQL 述語。

    `column` には `races` 側の data_div を修飾名で渡す (例 "r.data_div")。
    NULL は中止と判定できないので残す (取り込み途中の行を黙って捨てない)。
    """
    return f"({column} IS NULL OR {column} <> '{CANCELLED_DATA_DIV}')"


SQL_EVALUABLE_RACE = sql_evaluable_race()


#: 馬券が **返還** される異常区分 (出走取消・除外)。走っていないので外れでもない。
# `scripts/fundamental_model.py` の `NOT_A_START` と同じ集合
# (あちらは「1 戦」に数えない基準)。値がずれたらテストで落ちる。
REFUNDED_ABNORMAL_CODES = frozenset({"1", "2", "3"})

#: 着順が付かない異常区分。上記に加えて競走中止 (4) を含む。
# **競走中止は馬券が返還されない** (出走はしている) ので返還集合とは別。
# 「結果が確定したか」を判定するとき、この馬たちに着順を要求してはいけない。
NON_FINISHER_ABNORMAL_CODES = REFUNDED_ABNORMAL_CODES | frozenset({"4"})


def is_refunded(abnormal_code: object) -> bool:
    """この馬の馬券が返還されるか (出走取消・除外)。

    返還された馬券を「外れ = -100 円」に数えるのは、中止レースを負けに
    数えるのとまったく同じ誤り。
    """
    return str(abnormal_code or "").strip() in REFUNDED_ABNORMAL_CODES


def expects_a_finishing_order(abnormal_code: object) -> bool:
    """この馬に確定着順が付くはずか (速報と確定の区別に使う)。"""
    return str(abnormal_code or "").strip() not in NON_FINISHER_ABNORMAL_CODES


def exclusion_reason(not_cancelled: bool, has_finish: bool,
                     has_payout: bool) -> str | None:
    """評価対象外の理由を決める **唯一の場所**。

    呼び出し側で if/elif を並べると、**順序を入れ替えるだけで中止レースが
    `result_not_yet_available` として記録される** (中止レースは結果も無いので
    複数の条件に当てはまる)。2026-09-22 の監査で、分岐の並びを入れ替える変異が
    テストを全部素通りし、実データで中止 161 行が「結果待ち」になることが
    実証された。ここに集約して全通りをテストで固定する。

        中止                       -> cancelled                (永久除外。馬券は返還)
        実施 / 着順なし            -> result_not_yet_available (結果が来れば評価可へ)
        実施 / 着順あり / 払戻なし -> payout_not_yet_available (払戻が来れば評価可へ)
        実施 / 着順あり / 払戻あり -> None                     (評価する)

    `has_payout` は **レース単位**で「その馬券種の確定払戻データが届いたか」。
    各馬に払戻行が要るという意味ではない (敗戦馬に払戻は無い)。
    """
    if not not_cancelled:
        return EXCLUSION_CANCELLED
    if not has_finish:
        return EXCLUSION_RESULT_PENDING
    if not has_payout:
        return EXCLUSION_PAYOUT_PENDING
    return None


def is_evaluable(not_cancelled: bool, has_finish: bool, has_payout: bool) -> bool:
    """評価に使えるか。`exclusion_reason` と必ず一致すること。"""
    return exclusion_reason(not_cancelled, has_finish, has_payout) is None


def sql_cancelled_race(column: str = "data_div") -> str:
    """**中止と分かっている**行だけを指す述語。

    `races` を外部結合や EXISTS で参照するときは、こちらを `NOT EXISTS` で
    使う。`EXISTS (evaluable)` にすると、`races` 行がまだ取り込まれていない
    レースまで黙って落ちてしまい、件数が理由も分からず減る。
    「中止と積極的に判明したものだけ除く」方が安全側。
    """
    return f"{column} = '{CANCELLED_DATA_DIV}'"


def is_evaluable_race(data_div: object) -> bool:
    """Python 側の判定。`sql_evaluable_race` と同じ答えを返すこと。"""
    if data_div is None:
        return True
    return str(data_div).strip() != CANCELLED_DATA_DIV


def is_cancelled_race(data_div: object) -> bool:
    """中止レースか (`is_evaluable_race` の裏)。"""
    return not is_evaluable_race(data_div)


def sql_invalid_horse_num(column: str = "horse_num") -> str:
    """SQL inverse of sql_valid_horse_num, including NULL explicitly."""
    return f"NOT COALESCE(({sql_valid_horse_num(column)}), 0)"


def horse_num_violation_counts(
    conn: sqlite3.Connection, today: str | None = None
) -> dict[str, int]:
    """Count invalid horse numbers by violation reason.

    Invalid rows are violations when they coexist with a resolved horse number,
    or when their race date is already before ``today``. The latter restores
    detection for abandoned all-placeholder races without flagging future
    pre-draw entries.
    """
    today = today or date.today().strftime("%Y%m%d")
    row = conn.execute(
        f"""
        SELECT
            SUM(CASE WHEN EXISTS (
                SELECT 1 FROM horse_races resolved
                 WHERE resolved.race_year=invalid.race_year
                   AND resolved.race_month_day=invalid.race_month_day
                   AND resolved.track_code=invalid.track_code
                   AND resolved.kaiji=invalid.kaiji
                   AND resolved.nichiji=invalid.nichiji
                   AND resolved.race_num=invalid.race_num
                   AND {sql_valid_horse_num('resolved.horse_num')}
            ) THEN 1 ELSE 0 END) AS coexist,
            SUM(CASE WHEN NOT EXISTS (
                SELECT 1 FROM horse_races resolved
                 WHERE resolved.race_year=invalid.race_year
                   AND resolved.race_month_day=invalid.race_month_day
                   AND resolved.track_code=invalid.track_code
                   AND resolved.kaiji=invalid.kaiji
                   AND resolved.nichiji=invalid.nichiji
                   AND resolved.race_num=invalid.race_num
                   AND {sql_valid_horse_num('resolved.horse_num')}
            ) AND (invalid.race_year || invalid.race_month_day) < ?
            THEN 1 ELSE 0 END) AS past_only
          FROM horse_races invalid
         WHERE {sql_invalid_horse_num('invalid.horse_num')}
        """
        ,
        (today,),
    ).fetchone()
    coexist = int(row[0] or 0)
    past_only = int(row[1] or 0)
    return {
        "coexist": coexist,
        "past_only": past_only,
        "total": coexist + past_only,
    }


def count_horse_num_violations(
    conn: sqlite3.Connection, today: str | None = None
) -> int:
    return horse_num_violation_counts(conn, today=today)["total"]


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


@contextmanager
def open_db_readonly(path: Path | str = DB_PATH):
    """読み取り専用接続 (webapp 等の観察系ツール用。2026-07-05)。

    open_db は接続のたびに init_db (schema 実行 + ALTER migration = 書込み
    トランザクション) を発行するため、観察系ツールが使うと GUI/ingest の
    予想生成ワークフローと書込みロックで競合し得る。本関数は:
      - init_db を実行しない (migration は予想生成側の open_db だけが担う)
      - URI mode=ro で開き、さらに PRAGMA query_only=ON で SQL 層でも書込みを封じる
      - WAL リーダなので writer (GUI/ingest) をブロックしない
    DB ファイルが無ければ FileNotFoundError (mode=ro は新規作成しない)。
    WAL の -shm が read-only で開けない環境では rw ハンドル + query_only に
    フォールバックする。保証強度の差に注意: 主経路 mode=ro は OS レベルで
    不可逆、フォールバックは SQL 層ガード (query_only) のみ — 同一接続で
    PRAGMA query_only=OFF を発行すれば解除できるため、観察系コードに
    query_only=OFF を書かないこと (tests の不変条件テストが混入を検知する)。
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"DB がありません: {p}")
    try:
        conn = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)
    except sqlite3.OperationalError:
        # read-only WAL の -shm 制約等で開けない場合のフォールバック。
        # mode=rw (no-create) にすることで、exists() チェックと connect の間に
        # DB が消えた場合 (TOCTOU) でも空ファイルを新規作成しない
        # (2026-07-05 fable data-pipeline 監査指摘)。
        conn = sqlite3.connect(f"file:{p.as_posix()}?mode=rw", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        yield conn
    finally:
        conn.close()


def init_db(conn: sqlite3.Connection) -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    # schema.sql の idx_horse_masters_dam_sire が dam_sire_breeding_num を参照する
    # ため、この列の補修は executescript より**先**に行う。後置だと「テーブルは
    # あるが列が無い」旧 DB で index 作成が no such column で落ち、補修行に到達
    # できず writer が起動不能になる (2026-07-05 data-pipeline 監査 R1)。
    # 他の migration 列 (corner/lap/odds_fetched_at 等) は schema.sql に index が
    # 無いので後置で問題ない。
    _ensure_column_if_exists(conn, "horse_masters", "dam_sire_breeding_num", "TEXT")
    conn.executescript(schema)
    _ensure_column(conn, "horse_races", "odds_fetched_at", "TEXT")
    _ensure_column(conn, "horse_races", "odds_dataspec", "TEXT")
    _ensure_column(conn, "training_times", "data_div", "TEXT")
    _ensure_column(conn, "training_times", "data_created", "TEXT")
    # コーナー通過順位 (Phase 4)。既存 DB への後方互換 migration。
    for _c in ("corner_order_1", "corner_order_2", "corner_order_3", "corner_order_4"):
        _ensure_column(conn, "horse_races", _c, "INTEGER")
    # レースラップ / ハロンタイム (2026-07-05)。既存 DB への後方互換 migration。
    for _c in ("front3f_time", "front4f_time", "last3f_time", "last4f_time"):
        _ensure_column(conn, "races", _c, "INTEGER")
    _ensure_column(conn, "races", "lap_times", "TEXT")
    # 予測の出所 (2026-09-17 憲法 Phase 0.5 項目 0)。既存 DB への後方互換 migration。
    # 「どのコードがこの予測を出したのか分からない」状態を禁止する。
    _ensure_column(conn, "prediction_log", "code_version", "TEXT")
    _ensure_column(conn, "prediction_log", "data_version", "TEXT")
    # 提供元が示すオッズ発表時刻 (2026-09-17 憲法 Phase 0.5-1)。
    # 「受信した時刻」と「提供元が示す観測時刻」を分けて持つため。
    _ensure_column(conn, "odds_snapshots", "announced_at", "TEXT")
    # 3 代血統 (父母父/母母父) + HN 産地情報 (2026-07-05)。schema.sql に index が
    # 無いので後置で安全 (index を足す場合は dam_sire_breeding_num と同様に前置へ)。
    for _c in ("sire_dam_sire_breeding_num", "sire_dam_sire_name",
               "dam_dam_sire_breeding_num", "dam_dam_sire_name"):
        _ensure_column(conn, "horse_masters", _c, "TEXT")
    for _c in ("mochikomi_kubun", "import_year", "birthplace"):
        _ensure_column(conn, "breeding_horses", _c, "TEXT")


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, decl: str) -> None:
    cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def _ensure_column_if_exists(conn: sqlite3.Connection, table: str, column: str, decl: str) -> None:
    """テーブルが存在する場合のみ列補修する (新規 DB は直後の schema.sql が列ごと作る)。"""
    cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if cols and column not in cols:
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
    update_exprs = []
    for col in cols:
        if col in _RACE_PK:
            continue
        if col in ("front3f_time", "front4f_time", "last3f_time", "last4f_time"):
            # 結果確定後のラップを、後から来る発走前 RA (全 0) で潰さない
            # (horse_races.corner_order と同型ガード。2026-07-05 data-pipeline 監査指摘)。
            update_exprs.append(
                f"{col}=CASE WHEN excluded.{col} > 0 THEN excluded.{col} ELSE races.{col} END")
        elif col == "lap_times":
            # 非ゼロラップを 1 つでも含む場合のみ上書き (GLOB の文字クラスで判定)。
            update_exprs.append(
                "lap_times=CASE WHEN excluded.lap_times GLOB '*[1-9]*' "
                "THEN excluded.lap_times ELSE races.lap_times END")
        else:
            update_exprs.append(f"{col}=excluded.{col}")
    sql = (
        f"INSERT INTO races ({','.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT({','.join(_RACE_PK)}) DO UPDATE SET {','.join(update_exprs)}"
    )
    conn.execute(sql, row)


def upsert_horse_race(conn: sqlite3.Connection, se: HorseRaceInfo) -> None:
    row = _se_to_row(se)
    horse_num = str(row.get("horse_num") or "").strip()
    if horse_num == "00":
        # 古い枠順未確定 SE の逆順リプレイで、確定済みレースへ
        # placeholder が復活するのを入口で防ぐ。
        existing = conn.execute(
            f"""
            SELECT 1 FROM horse_races
             WHERE race_year=:race_year AND race_month_day=:race_month_day
               AND track_code=:track_code AND kaiji=:kaiji AND nichiji=:nichiji
               AND race_num=:race_num AND {SQL_VALID_HORSE_NUM}
             LIMIT 1
            """,
            row,
        ).fetchone()
        if existing is not None:
            return
    cols = list(row.keys())
    placeholders = ",".join(f":{c}" for c in cols)
    update_exprs = []
    for col in cols:
        if col in {"race_year", "race_month_day", "track_code", "kaiji", "nichiji", "race_num", "horse_num"}:
            continue
        if col in {"mining_time", "mining_predicted_order", "win_odds", "win_popularity",
                   "corner_order_1", "corner_order_2", "corner_order_3", "corner_order_4"}:
            # 確定後の corner 順位を、後から来る発走前 SE (corner=0) で潰さない。
            update_exprs.append(f"{col}=CASE WHEN excluded.{col} > 0 THEN excluded.{col} ELSE horse_races.{col} END")
        else:
            update_exprs.append(f"{col}=excluded.{col}")
    sql = (
        f"INSERT INTO horse_races ({','.join(cols)}) VALUES ({placeholders}) "
        "ON CONFLICT(race_year, race_month_day, track_code, kaiji, nichiji, race_num, horse_num) "
        f"DO UPDATE SET {','.join(update_exprs)}"
    )
    conn.execute(sql, row)
    if is_valid_horse_num(horse_num):
        # 枠順確定後の正規SEを同じトランザクションで取り込んだ時点で、
        # 同一レースに残る枠順未確定 horse_num='00' 行を冪等に除去する。
        conn.execute(
            """
            DELETE FROM horse_races
             WHERE race_year=:race_year AND race_month_day=:race_month_day
               AND track_code=:track_code AND kaiji=:kaiji AND nichiji=:nichiji
               AND race_num=:race_num AND horse_num='00'
            """,
            row,
        )


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


def _race_start_iso(conn: sqlite3.Connection, o1: O1Odds) -> str | None:
    """races.start_time から発走時刻を ISO8601 (秒精度) で返す。取れなければ None。

    races 行が無い / start_time が空 / start_time 列自体が無い (旧 schema の
    テスト DB 等) 場合は None を返し、呼び出し側は「発走時刻不明」として
    従来どおりの更新を行う。
    """
    try:
        row = conn.execute(
            """
            SELECT start_time FROM races
             WHERE race_year=? AND race_month_day=? AND track_code=?
               AND kaiji=? AND nichiji=? AND race_num=?
            """,
            (o1.year, o1.month_day, o1.track_code, o1.kaiji, o1.nichiji, o1.race_num),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    if row is None:
        return None
    start = str(row[0] or "").strip().zfill(4)
    if len(start) < 4 or not start[:4].isdigit():
        return None
    md = str(o1.month_day or "").zfill(4)
    if len(str(o1.year or "")) != 4 or len(md) != 4:
        return None
    return (
        f"{o1.year}-{md[:2]}-{md[2:]}T{start[:2]}:{start[2:4]}:00"
    )


def update_win_odds(
    conn: sqlite3.Connection,
    o1: O1Odds,
    fetched_at: str | None = None,
    dataspec: str = "0B31",
    historical: bool = False,
) -> int:
    """O1 単勝オッズを horse_races に反映する。

    発走時刻以降に取得した realtime オッズは自動的に historical 扱いに落とす
    (odds_fetched_at=NULL)。理由は下の post-start 判定のコメント参照。

    historical=True は RACE dataspec 等の **確定オッズ (data_div=5)** 用。
    odds_fetched_at を NULL (= 歴史的確定・信頼) のまま書き、既存の
    リアルタイム snapshot (odds_fetched_at 非 NULL) は上書きしない。
    2026-06-30 の RACE バックフィルが確定オッズ行にファイル mtime (発走後) を
    刻印し、Step1 odds ゲートが全レースを post-start 扱いにする事故が起きた
    (2026-07-03 検出)。確定オッズの取り込みは必ず historical=True で行うこと。
    """
    updated = 0
    params_base = (
        o1.year,
        o1.month_day,
        o1.track_code,
        o1.kaiji,
        o1.nichiji,
        o1.race_num,
    )
    if not historical:
        fetched_at = fetched_at or datetime.now().isoformat(timespec="seconds")
        # 発走時刻以降に取得した realtime オッズは「確定オッズ相当」として扱い、
        # odds_fetched_at を刻印しない (historical と同じ経路に落とす)。
        #
        # 刻印すると backtest の odds 鮮度ゲート (scripts.backtest.
        # race_odds_untrusted) がそのレースを post-start 扱いで除外するため、
        # 発走後に走った ingest が過去のレースを遡って検証母数から蹴り落とす。
        # 実害: 2026 年 1-6 月の適格レースが 1,568 → 1,135 に縮小 (2026-08-22 検出、
        # 原因は毎分実行の外部 live ingest と 20:00 の傾向収集バッチ)。
        # 発走後のオッズは締切後で動かないので確定値と等価であり、NULL 刻印
        # (= 確定・信頼、ただし PIT 特徴には使用禁止) が正しい意味づけになる。
        # 既存の pre-start snapshot は上書きしない (historical 側の
        # `AND odds_fetched_at IS NULL` ガードがそれを保証する)。
        start_iso = _race_start_iso(conn, o1)
        if start_iso is not None and fetched_at >= start_iso:
            historical = True
    if historical:
        for horse_num, odds, popularity in o1.win_odds:
            cur = conn.execute(
                """
                UPDATE horse_races
                   SET win_odds = ?, win_popularity = ?,
                       odds_fetched_at = NULL, odds_dataspec = ?
                 WHERE race_year=? AND race_month_day=? AND track_code=?
                   AND kaiji=? AND nichiji=? AND race_num=? AND horse_num=?
                   AND odds_fetched_at IS NULL
                """,
                (odds, popularity, dataspec, *params_base, horse_num),
            )
            updated += cur.rowcount
        return updated

    # fetched_at は上の `if not historical:` で必ず設定済み (historical 分岐は
    # return するため、ここに到達するのは realtime 経路のみ)。
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


def insert_horse_master_if_absent(conn: sqlite3.Connection, um: HorseMaster) -> None:
    """行が無い場合のみ INSERT (HS レコード用)。

    HS (市場取引) は血統登録番号と父母の繁殖番号程度しか持たない骨組み行で、
    INSERT OR REPLACE に流すと UM 由来のフル行 (馬名/父名/3代血統/産地参照…) を
    空文字で丸ごと潰す (2026-07-05 data-pipeline 監査 R2 で実証されたクロバー)。
    raw 全量再構築の取込順は DIFN(UM) < HOSE(HS) なので、REPLACE のままだと
    再構築が正しい状態に収束しない。IF ABSENT 化で順序非依存になる
    (HS 先行 → 骨組み、後から UM がフル REPLACE / UM 先行 → HS は no-op)。
    """
    row = asdict(um)
    row.pop("record_type", None)
    cols = list(row.keys())
    placeholders = ",".join(f":{c}" for c in cols)
    sql = f"INSERT OR IGNORE INTO horse_masters ({','.join(cols)}) VALUES ({placeholders})"
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
    """year/month_day を race_year/race_month_day にリネームして INSERT OR REPLACE する汎用 upsert。

    注意: `year`/`month_day` は **レース開催日付の列限定**。馬の生年など別意味の
    `year` を持つ dataclass をこの関数に通すと race_year 列へ誤って流れるので使わないこと。
    """
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


def upsert_jockey_change(conn: sqlite3.Connection, jc: JockeyChange) -> None:
    """JC速報を保存し、出馬表の騎手・負担重量も現在値へ更新する。"""
    _upsert_race_keyed(conn, "jockey_changes", jc)
    conn.execute(
        "UPDATE horse_races SET burden_weight=?,jockey_code=?,"
        "jockey_short_name=?,jockey_apprentice_code=? "
        "WHERE race_year=? AND race_month_day=? AND track_code=? AND kaiji=? "
        "AND nichiji=? AND race_num=? AND horse_num=?",
        (jc.new_burden_weight, jc.new_jockey_code, jc.new_jockey_name,
         jc.new_apprentice_code, jc.year, jc.month_day, jc.track_code, jc.kaiji,
         jc.nichiji, jc.race_num, jc.horse_num),
    )


def upsert_start_time_change(conn: sqlite3.Connection, tc: StartTimeChange) -> None:
    _upsert_race_keyed(conn, "start_time_changes", tc)
    if _valid_hhmm(tc.new_start_time):
        conn.execute(
            "UPDATE races SET start_time=? WHERE race_year=? AND race_month_day=? "
            "AND track_code=? AND kaiji=? AND nichiji=? AND race_num=?",
            (tc.new_start_time, tc.year, tc.month_day, tc.track_code, tc.kaiji,
             tc.nichiji, tc.race_num),
        )


def _valid_hhmm(value: object) -> bool:
    raw = str(value or "")
    if len(raw) != 4 or not raw.isdigit():
        return False
    return 0 <= int(raw[:2]) <= 23 and 0 <= int(raw[2:]) <= 59


def upsert_course_change(conn: sqlite3.Connection, cc: CourseChange) -> None:
    _upsert_race_keyed(conn, "course_changes", cc)
    track_type = str(cc.new_track_type_code or "").strip()
    if cc.new_distance > 0 and len(track_type) == 2 and track_type.isdigit():
        conn.execute(
            "UPDATE races SET distance=?,track_type_code=? WHERE race_year=? "
            "AND race_month_day=? AND track_code=? AND kaiji=? AND nichiji=? "
            "AND race_num=?",
            (cc.new_distance, cc.new_track_type_code, cc.year, cc.month_day,
             cc.track_code, cc.kaiji, cc.nichiji, cc.race_num),
        )


def insert_odds_snapshot(
    conn: sqlite3.Connection,
    o1: O1Odds,
    fetched_at: str,
    source: str,
) -> int:
    """O1 スナップショットを odds_snapshots (F3 時系列) に追記する。

    horse_races.win_odds (最新 1 枚) の update_win_odds とは独立の経路。
    同一 (レース, 馬, fetched_at) は INSERT OR REPLACE で冪等。戻り値は行数。
    """
    rows = [
        (o1.year, o1.month_day, o1.track_code, o1.kaiji, o1.nichiji, o1.race_num,
         horse_num, fetched_at, o1.announced_at or None, odds, popularity, source)
        for horse_num, odds, popularity in o1.win_odds
    ]
    if not rows:
        return 0
    conn.executemany(
        "INSERT OR REPLACE INTO odds_snapshots "
        "(race_year, race_month_day, track_code, kaiji, nichiji, race_num, "
        " horse_num, fetched_at, announced_at, win_odds, win_popularity, source) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    return len(rows)


def insert_prediction_log(
    conn: sqlite3.Connection,
    race: dict,
    rows: list[dict],
    generated_at: str,
    model_version: str = "",
    calibrator_version: str = "",
) -> int:
    """発行時点の予想を prediction_log に追記 (答え合わせ用、append-only)。

    rows は 1 馬 1 dict:
      {horse_num, mark, rank, score, win_probability, raw_blended_probability,
       win_odds, win_popularity, confidence}
    同一 (generated_at, レース, 馬番) は INSERT OR REPLACE。戻り値は行数。
    """
    # 出所を毎回刻む (2026-09-17 憲法 Phase 0.5 項目 0)。
    # 呼び出し側が忘れられないよう、引数ではなくここで取る。
    from predictor.provenance import code_version, data_version

    code_v = code_version()
    data_v = data_version(conn)
    payload = [
        (
            generated_at,
            race.get("race_year"), race.get("race_month_day"), race.get("track_code"),
            race.get("kaiji"), race.get("nichiji"), race.get("race_num"),
            r.get("horse_num"), r.get("mark") or "", r.get("rank"), r.get("score"),
            r.get("win_probability"), r.get("raw_blended_probability"),
            r.get("win_odds"), r.get("win_popularity"), r.get("confidence") or "",
            model_version, calibrator_version, code_v, data_v,
        )
        for r in rows
    ]
    if not payload:
        return 0
    conn.executemany(
        "INSERT OR REPLACE INTO prediction_log "
        "(generated_at, race_year, race_month_day, track_code, kaiji, nichiji, race_num, "
        " horse_num, mark, rank, score, win_probability, raw_blended_probability, "
        " win_odds, win_popularity, confidence, model_version, calibrator_version, "
        " code_version, data_version) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        payload,
    )
    return len(payload)


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
