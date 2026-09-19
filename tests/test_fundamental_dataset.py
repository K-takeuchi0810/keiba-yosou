"""Fundamental Model の標本定義の契約テスト (憲法 Phase 0.5-3)。

## なぜ要るか

初版は「horse_races に行がある = 1 頭の出走」とみなしていた。実際には

- **出走取消** の馬にも行がある (`abnormal_code='1'`、馬体重 `000`、オッズ 0)
- **結果が取り込まれていないレース** にも行がある (勝ち馬が 1 頭もいない)

前者は T−10 の市場にも居ないので、標本に入れると市場と頭数が食い違う。
後者は全頭 `won=0` になるので、**「このレースでは誰も勝たない」を学習**する。
2026-09-18 の突合で 933 レースのはずが 923 になったことから発覚した。

一方 **発走除外 / 競走除外 (`'2'` / `'3'`) は残す**。ゲート前後の除外なので
T−10 時点ではまだ買えた。「その後除外された」は当時知りえない情報であり、
それを理由に標本から落とすと後知恵の選択になる。
"""
from __future__ import annotations

import sqlite3

import pytest

from scripts.fundamental_model import (
    DID_NOT_START,
    FEATURES,
    NOT_A_START,
    TRUST_FLOOR_YEAR,
    build_dataset,
)

DDL = """
CREATE TABLE horse_races (
  race_year TEXT, race_month_day TEXT, track_code TEXT, kaiji TEXT,
  nichiji TEXT, race_num TEXT, horse_num TEXT, blood_register_num TEXT,
  jockey_code TEXT, trainer_code TEXT, age TEXT, sex_code TEXT,
  burden_weight TEXT, waku_num TEXT, horse_weight TEXT,
  weight_change_sign TEXT, weight_change_diff TEXT, blinker TEXT,
  confirmed_order INTEGER, abnormal_code TEXT);
CREATE TABLE races (
  race_year TEXT, race_month_day TEXT, track_code TEXT, kaiji TEXT,
  nichiji TEXT, race_num TEXT, distance INTEGER, track_type_code TEXT,
  turf_condition TEXT, dirt_condition TEXT, weather_code TEXT,
  grade_code TEXT, starter_count INTEGER, registered_count INTEGER,
  start_time TEXT, data_div TEXT);
CREATE TABLE horse_masters (
  blood_register_num TEXT, sire_breeding_num TEXT);
"""


def _add_race(conn, date8: str, race_num: str, horses: list[tuple],
              track: str = "05", start_time: str = "1000",
              data_div: str = "7", blood_prefix: str | None = None,
              jockeys: list[str] | None = None,
              trainers: list[str] | None = None,
              ages: list[str] | None = None) -> None:
    """horses = [(馬番, 確定着順, 異常コード), ...]

    騎手・調教師・年齢を馬ごとに変えられる。既定で全頭同じにすると、
    「騎手の数を調教師の列から読む」ような取り違えをテストが見逃す。
    """
    y, md = date8[:4], date8[4:]
    started = [h for h in horses if h[2] != "1"]
    conn.execute(
        "INSERT INTO races VALUES (?,?,?,'01','01',?,1600,'1','1','0','1','',?,?,?,?)",
        (y, md, track, race_num, len(started), len(horses), start_time, data_div))
    for i, (hn, fin, abn) in enumerate(horses):
        bn = f"{blood_prefix}{hn}" if blood_prefix else f"H{hn}{date8}{track}{race_num}"
        jc = jockeys[i] if jockeys else "J1"
        trc = trainers[i] if trainers else "T1"
        age = ages[i] if ages else "04"
        conn.execute(
            "INSERT INTO horse_races VALUES (?,?,?,'01','01',?,?,?,"
            "?,?,?,'1','550','1','470','+','2','0',?,?)",
            (y, md, track, race_num, hn, bn, jc, trc, age, fin, abn))


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "t.db"
    conn = sqlite3.connect(path)
    conn.executescript(DDL)
    yield conn, str(path)
    conn.close()


def test_scratched_horse_is_excluded(db):
    """出走取消の馬は標本に入らない。市場にも居ないため。"""
    conn, path = db
    _add_race(conn, "20260601", "01",
              [("01", 1, "0"), ("02", 2, "0"), ("03", 0, "1")])
    conn.commit()

    rows, stats = build_dataset("20260101", "20261231", db_path=path)

    assert {r["horse_num"] for r in rows} == {"01", "02"}
    assert stats["skip_did_not_start"] == 1


def test_gate_excluded_horse_is_kept_as_a_loser(db):
    """競走除外は残す。T−10 時点ではまだ買えたから。

    ここを取り違えると **後知恵で標本を絞る** ことになる。
    """
    conn, path = db
    _add_race(conn, "20260601", "01",
              [("01", 1, "0"), ("02", 2, "0"), ("03", 0, "3")])
    conn.commit()

    rows, _ = build_dataset("20260101", "20261231", db_path=path)

    assert {r["horse_num"] for r in rows} == {"01", "02", "03"}
    assert next(r for r in rows if r["horse_num"] == "03")["won"] == 0
    assert "2" not in DID_NOT_START and "3" not in DID_NOT_START


def test_race_without_a_winner_is_excluded(db):
    """結果が未取込のレースは丸ごと使わない。

    全頭 won=0 のまま学習すると「誰も勝たない」を教えることになる。
    """
    conn, path = db
    _add_race(conn, "20260601", "01", [("01", 1, "0"), ("02", 2, "0")])
    _add_race(conn, "20260601", "02", [("01", 0, "0"), ("02", 0, "0")],
              start_time="1030", data_div="7")
    conn.commit()

    rows, stats = build_dataset("20260101", "20261231", db_path=path)

    assert {r["race_id"].split("-")[-1] for r in rows} == {"01"}
    assert stats["skip_race_without_winner"] == 2


def test_did_not_start_rows_do_not_count_as_a_career_start(db):
    """取消は「出走」ではない。過去成績の分母に入れない。"""
    conn, path = db
    # 同一馬 (血統登録番号を揃える) が 1 戦目は取消、2 戦目に出走
    _add_race(conn, "20260601", "01", [("01", 1, "0"), ("02", 0, "1")])
    _add_race(conn, "20260608", "01", [("01", 2, "0"), ("02", 1, "0")])
    conn.execute("UPDATE horse_races SET blood_register_num='SAME' "
                 "WHERE horse_num='02'")
    conn.commit()

    rows, _ = build_dataset("20260101", "20261231", db_path=path)

    second = next(r for r in rows
                  if r["horse_num"] == "02" and r["date"] == "20260608")
    assert second["h_starts"] == 0, "取消が 1 戦としてカウントされている"


def test_a_race_with_a_winner_survives_intact(db):
    """正常なレースはそのまま残る (除外規則が効きすぎていないか)。"""
    conn, path = db
    _add_race(conn, "20260601", "01",
              [("01", 1, "0"), ("02", 2, "0"), ("03", 0, "4")])   # 4=競走中止
    conn.commit()

    rows, stats = build_dataset("20260101", "20261231", db_path=path)

    assert len(rows) == 3
    assert sum(r["won"] for r in rows) == 1
    assert stats["skip_did_not_start"] == 0
    assert stats["skip_race_without_winner"] == 0


def test_every_declared_feature_is_produced(db):
    """FEATURES に挙げた列が実際に全部揃うこと。"""
    conn, path = db
    _add_race(conn, "20260601", "01", [("01", 1, "0"), ("02", 2, "0")])
    conn.commit()

    rows, _ = build_dataset("20260101", "20261231", db_path=path)

    missing = [f for f in FEATURES if f not in rows[0]]
    assert not missing, f"生成されない特徴: {missing}"


def test_same_day_later_race_does_not_feed_an_earlier_one(db):
    """**同日の別場で後に発走するレースの結果を使わない**。

    以前は `(日付, 場コード, レース番号)` 順に 1 行ずつ累積していたため、
    場コード 01 の 15:00 発走の結果が場コード 09 の 10:00 発走の特徴に
    入っていた。決定時刻 (T−10) に存在しない情報なので PIT 違反。
    実測で調教師カウンタ 20.1% / 父カウンタ 31.4% の行が該当した。
    """
    conn, path = db
    # 場 01 の 15:00 (同じ騎手 J1 が勝つ) と 場 09 の 10:00
    _add_race(conn, "20260601", "01", [("01", 1, "0"), ("02", 2, "0")],
              track="01", start_time="1500")
    _add_race(conn, "20260601", "01", [("01", 2, "0"), ("02", 1, "0")],
              track="09", start_time="1000")
    conn.commit()

    rows, _ = build_dataset("20260101", "20261231", db_path=path)

    early = [r for r in rows if r["race_id"].split("-")[2] == "09"]
    assert early, "場 09 のレースが取れていない"
    for r in early:
        assert r["j_rides_365"] == 0, (
            "同日後発走 (15:00) の結果が先発走 (10:00) の騎手カウンタに入っている")
        assert r["t_runs_365"] == 0


def test_same_day_earlier_race_is_still_used(db):
    """逆に **先に発走したレースの結果は使える**。除外しすぎていないこと。"""
    conn, path = db
    _add_race(conn, "20260601", "01", [("01", 1, "0"), ("02", 2, "0")],
              track="09", start_time="1000")
    _add_race(conn, "20260601", "01", [("01", 1, "0"), ("02", 2, "0")],
              track="01", start_time="1500")
    conn.commit()

    rows, _ = build_dataset("20260101", "20261231", db_path=path)

    late = [r for r in rows if r["race_id"].split("-")[2] == "01"]
    assert late and all(r["j_rides_365"] == 2 for r in late), (
        "同日先発走の結果が使われていない (絞りすぎ)")


def test_starters_is_what_was_knowable_at_t10(db):
    """出走頭数は「登録 − 取消」。`starter_count` (除外後) を使わない。

    `races.starter_count` はゲート前後の除外を織り込んだ確定値なので、
    T−10 には知りえない。
    """
    conn, path = db
    _add_race(conn, "20260601", "01",
              [("01", 1, "0"), ("02", 2, "0"), ("03", 0, "1"), ("04", 0, "3")])
    conn.commit()

    rows, _ = build_dataset("20260101", "20261231", db_path=path)

    # 登録 4 − 取消 1 = 3。競走除外の 04 は T−10 では出走予定なので引かない。
    assert {r["starters"] for r in rows} == {3.0}


def test_cancelled_race_is_excluded_by_its_own_flag(db):
    """中止レース (data_div='9') は明示フラグで落とす。

    「勝ち馬がいない」という代理判定に頼ると、原因を取り違える。実際
    2026-09-18 の初版は 57 件の中止レースを「結果未取込」と誤診していた。
    """
    conn, path = db
    _add_race(conn, "20260601", "01", [("01", 1, "0"), ("02", 2, "0")])
    _add_race(conn, "20260607", "01", [("01", 0, "0"), ("02", 0, "0")],
              data_div="9")
    conn.commit()

    rows, _ = build_dataset("20260101", "20261231", db_path=path)

    assert {r["date"] for r in rows} == {"20260601"}


def test_corrupted_years_are_not_read_at_all(db):
    """信頼下限より前の年は 1 行も読まない。

    2020 以前は raw のバイト破損で着順がゴミ (98 着など)。血統登録番号は
    無傷なので、放置すると **本物の馬に偽の勝利** が付く。
    """
    conn, path = db
    _add_race(conn, "20200601", "01", [("01", 1, "0"), ("02", 98, "0")],
              blood_prefix="SAME")
    _add_race(conn, "20260601", "01", [("01", 1, "0"), ("02", 2, "0")],
              blood_prefix="SAME")
    conn.commit()

    rows, stats = build_dataset("20200101", "20261231", db_path=path)

    assert {r["date"] for r in rows} == {"20260601"}
    assert all(r["h_starts"] == 0 for r in rows), (
        f"{TRUST_FLOOR_YEAR} 年より前の破損データが過去成績に入っている")


def test_gate_excluded_horse_is_not_counted_as_a_start(db):
    """競走除外は標本に残すが、キャリアの分母には入れない。走っていないため。"""
    conn, path = db
    _add_race(conn, "20260601", "01", [("01", 1, "0"), ("02", 0, "3")],
              blood_prefix="X")
    _add_race(conn, "20260607", "01", [("01", 1, "0"), ("02", 2, "0")],
              blood_prefix="X")
    conn.commit()

    rows, _ = build_dataset("20260101", "20261231", db_path=path)

    second = next(r for r in rows
                  if r["horse_num"] == "02" and r["date"] == "20260607")
    assert second["h_starts"] == 0, "競走除外が 1 戦として数えられている"
    assert "3" in NOT_A_START


def test_rolling_count_forgets_old_rides(db):
    """騎乗数は **直近 365 日ぶんだけ** 数えること。

    累積生涯カウントは信頼下限 (2021) から数え始めるので、実質
    「観測窓の経過時間」を測ってしまう。実測で学習域を出る行が
    2026 窓に `j_rides` 42.5% / `t_runs` 23.2% あった。木モデルは域外を
    定数で外挿するので、その出力は学習して検証した関数の値ではない。
    """
    conn, path = db
    # 2 年前に 1 戦、直近に 1 戦。365 日窓なら古い方は数えない。
    _add_race(conn, "20240101", "01", [("01", 1, "0"), ("02", 2, "0")])
    _add_race(conn, "20260601", "01", [("01", 1, "0"), ("02", 2, "0")])
    conn.commit()

    rows, _ = build_dataset("20210101", "20261231", db_path=path)

    late = [r for r in rows if r["date"] == "20260601"]
    assert late and all(r["j_rides_365"] == 0 for r in late), (
        f"365 日より古い騎乗を数えている: {[r['j_rides_365'] for r in late]}")
    assert all(r["t_runs_365"] == 0 for r in late)


def test_rolling_count_keeps_recent_rides(db):
    """逆に窓の中の騎乗は数えること (忘れすぎていないか)。"""
    conn, path = db
    _add_race(conn, "20260301", "01", [("01", 1, "0"), ("02", 2, "0")])
    _add_race(conn, "20260601", "01", [("01", 1, "0"), ("02", 2, "0")])
    conn.commit()

    rows, _ = build_dataset("20210101", "20261231", db_path=path)

    late = [r for r in rows if r["date"] == "20260601"]
    assert late and all(r["j_rides_365"] == 2 for r in late), (
        f"窓の中の騎乗を数えていない: {[r['j_rides_365'] for r in late]}")


def test_truncated_history_is_flagged(db):
    """信頼下限より前に走った記録がある馬に印が付くこと。

    2020 以前は着順が破損しているが **血統登録番号は無傷**なので、
    「履歴が途切れている」の真値が DB から直接取れる。

    初版は「初出時に 4 歳以上」という年齢のヒューリスティクスで判定しており、
    実測で **取りこぼし 0・誤検出 17.5% (1,448 頭)** だった。3 歳 1-3 月
    デビューが想定より多かったため。
    """
    conn, path = db
    # 2020 (信頼下限より前) に走った馬。着順は破損しているとみなす。
    _add_race(conn, "20200601", "01", [("01", 0, "0")], blood_prefix="OLD")
    # 同じ馬が 2022 に出走
    _add_race(conn, "20220601", "01", [("01", 1, "0"), ("02", 2, "0")],
              blood_prefix="OLD")
    conn.commit()

    rows, _ = build_dataset("20220101", "20261231", db_path=path)

    flagged = {r["horse_num"]: r["h_history_truncated"] for r in rows}
    assert flagged["01"] == 1.0, "2020 に走った馬に印が付いていない"
    assert flagged["02"] == 0.0, "2020 に走っていない馬にまで印が付いている"


def test_late_debut_without_old_record_is_not_flagged(db):
    """2020 以前の記録が無ければ、何歳で初出でも印を付けないこと。

    旧ルール (初出時 4 歳以上) はここで誤検出していた。地方転入や遅い
    デビューは「JRA の履歴が破損で隠れている」のとは **意味が違う集団**。
    """
    conn, path = db
    _add_race(conn, "20230601", "01", [("01", 1, "0"), ("02", 2, "0")],
              ages=["06", "05"])
    conn.commit()

    rows, _ = build_dataset("20220101", "20261231", db_path=path)

    assert rows and all(r["h_history_truncated"] == 0.0 for r in rows), (
        "2020 の記録が無いのに印が付いている (旧ルールの誤検出)")


def test_flag_does_not_depend_on_current_age(db):
    """同じ馬が年を取っても判定が変わらないこと。

    「初出時の年齢」ではなく「現在の年齢」で判定する実装に壊しても、
    1 レースしか無いフィクスチャでは気づけない。歳を重ねる馬を置く。
    """
    conn, path = db
    _add_race(conn, "20220601", "01", [("01", 1, "0"), ("02", 2, "0")],
              blood_prefix="AGE", ages=["02", "02"])
    _add_race(conn, "20240601", "01", [("01", 1, "0"), ("02", 2, "0")],
              blood_prefix="AGE", ages=["04", "04"])
    conn.commit()

    rows, _ = build_dataset("20220101", "20261231", db_path=path)

    later = [r for r in rows if r["date"] == "20240601"]
    assert later and all(r["h_history_truncated"] == 0.0 for r in later), (
        "現在の年齢で判定している (4 歳になった時点で印が付いた)")


def test_jockey_and_trainer_counts_are_not_swapped(db):
    """騎手の数を調教師の列から読んでいないこと。

    全頭を同じ騎手・同じ調教師にすると、取り違えても値が一致して
    テストが素通りする。**わざと非対称にする**。
    """
    conn, path = db
    # 騎手は 2 人で分ける、調教師は 1 人に集約 → 直近の件数が食い違う
    _add_race(conn, "20260301", "01", [("01", 1, "0"), ("02", 2, "0")],
              jockeys=["JA", "JB"], trainers=["TA", "TA"])
    _add_race(conn, "20260601", "01", [("01", 1, "0"), ("02", 2, "0")],
              jockeys=["JA", "JB"], trainers=["TA", "TA"])
    conn.commit()

    rows, _ = build_dataset("20220101", "20261231", db_path=path)

    later = [r for r in rows if r["date"] == "20260601"]
    assert later, "2 走目が取れていない"
    for r in later:
        assert r["j_rides_365"] == 1, f"騎手の件数が違う: {r['j_rides_365']}"
        assert r["t_runs_365"] == 2, f"調教師の件数が違う: {r['t_runs_365']}"


def test_rolling_window_boundary_is_exactly_365_days(db):
    """窓の境界がちょうど 365 日であること。

    `<` と `<=` を取り違えると窓が 1 日ずれる。1 日の差でも
    「何日ぶんを数えているか」が変わるので固定する。
    """
    conn, path = db
    # 2026-06-01 のちょうど 365 日前 = 2025-06-01
    _add_race(conn, "20250601", "01", [("01", 1, "0"), ("02", 2, "0")])
    # その 1 日前 = 窓の外
    _add_race(conn, "20250531", "01", [("01", 1, "0"), ("02", 2, "0")])
    _add_race(conn, "20260601", "01", [("01", 1, "0"), ("02", 2, "0")])
    conn.commit()

    rows, _ = build_dataset("20220101", "20261231", db_path=path)

    later = [r for r in rows if r["date"] == "20260601"]
    assert later and all(r["j_rides_365"] == 2 for r in later), (
        f"窓が 365 日になっていない: {[r['j_rides_365'] for r in later]} "
        "(2025-06-01 の 2 頭だけが入るはず)")


def test_reading_a_rolling_count_does_not_destroy_the_history(db):
    """ローリング件数を読んでも元の履歴を壊さないこと。

    初版は `popleft` で窓の外を捨てていた。現行の呼び出し順では無害だが、
    **同じ列から 2 つ目の窓 (例 30 日) を読んだ瞬間に静かに壊れる**。
    値は「もっともらしい範囲」に収まるので域外率の監査でも捕まらない。
    """
    from scripts.fundamental_model import _roll

    history = [1000, 1100, 1200, 1300, 1340, 1360]

    short = _roll(history, 1365 - 30)     # 直近 30 日 (1335 以降 = 2 件)
    long_ = _roll(history, 1365 - 365)    # 直近 365 日 (1000 以降 = 6 件)

    assert short == 2.0, short
    assert long_ == 6.0, f"短い窓を先に読んだら長い窓が壊れた: {long_}"
    assert history == [1000, 1100, 1200, 1300, 1340, 1360], "元の列が変わった"


def test_no_feature_is_a_lifetime_cumulative_person_count():
    """人的カウントに累積生涯カウントが残っていないこと (回帰)。"""
    assert "j_rides" not in FEATURES and "t_runs" not in FEATURES
    assert "j_rides_365" in FEATURES and "t_runs_365" in FEATURES
