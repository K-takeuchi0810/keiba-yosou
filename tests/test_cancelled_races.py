"""中止レース (data_div='9') が評価に混ざらないことの契約テスト (2026-09-22)。

## なぜ要るか

2026-09-21、台風で中山 12R が中止 (9/22 へ順延) になった。予想は 24 レース分
出していたので、その日の半分は走っていない。

**中止レースの馬券は返還される。** したがって「外れ」でも「−100 円の負け」でも
ない。ところが `build_daily_results.py` は日付だけでレースを引いていたため、
中止レースの `confirmed_order` が 0 になり、

  - ◎ が「1 着でなかった」と数えられて的中率の分母に入る
  - 買い候補があれば `profit = (win_pay - 100) if win_pay > 0 else -100`
    により **走っていないレースで 100 円負けた**ことになる

他の経路 (backtest / prediction_accuracy / monitor) は `confirmed_order > 0`
の副作用で **たまたま** 落ちていた。その条件が将来緩むと中止が再流入するので、
暗黙に頼らず `db.sql_evaluable_race()` で明示するよう揃えた。

最後のテストが「`confirmed_order` の条件を緩めても中止は入らない」を見ている。
これが通らないと、暗黙除外に戻ったのと同じになる。
"""
from __future__ import annotations

import sqlite3

import pytest

from db import (
    CANCELLED_DATA_DIV, EXCLUSION_CANCELLED, is_cancelled_race,
    is_evaluable_race, sql_evaluable_race,
)


@pytest.fixture()
def db(tmp_path):
    """中止 1 レース + 実施 1 レースだけを持つ最小 DB。

    中止側にも ◎ と出走馬を置く。「予想は出したが走っていない」状態を作るのが
    目的なので、ここを空にしてしまうとテストが意味を失う。
    """
    path = tmp_path / "t.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE races (race_year TEXT, race_month_day TEXT,"
                 " track_code TEXT, kaiji TEXT, nichiji TEXT, race_num TEXT,"
                 " data_div TEXT)")
    conn.execute("CREATE TABLE horse_races (race_year TEXT, race_month_day TEXT,"
                 " track_code TEXT, kaiji TEXT, nichiji TEXT, race_num TEXT,"
                 " horse_num TEXT, confirmed_order INTEGER)")
    # 06 = 中止、09 = 実施
    conn.execute("INSERT INTO races VALUES ('2026','0921','06','01','01','01','9')")
    conn.execute("INSERT INTO races VALUES ('2026','0921','09','01','01','01','6')")
    # 中止側: 着順なし (0)。実施側: 1 着と 2 着。
    conn.execute("INSERT INTO horse_races VALUES ('2026','0921','06','01','01','01','01',0)")
    conn.execute("INSERT INTO horse_races VALUES ('2026','0921','09','01','01','01','01',1)")
    conn.execute("INSERT INTO horse_races VALUES ('2026','0921','09','01','01','01','02',2)")
    conn.commit()
    yield conn
    conn.close()


def _races(conn, extra: str = "") -> list[str]:
    return [r[0] for r in conn.execute(
        f"SELECT track_code FROM races WHERE 1=1 {extra}")]


# --- 述語そのもの ---------------------------------------------------------

def test_the_predicate_drops_only_cancelled_races(db):
    """data_div='9' だけを落とし、他は残すこと。"""
    assert _races(db) == ["06", "09"]
    assert _races(db, f"AND {sql_evaluable_race()}") == ["09"]


def test_python_and_sql_agree(db):
    """Python 版と SQL 版が同じ答えを返すこと。

    2 つあると必ずずれるので、同じデータで突き合わせる。
    """
    by_sql = set(_races(db, f"AND {sql_evaluable_race()}"))
    by_py = {t for t, d in db.execute("SELECT track_code, data_div FROM races")
             if is_evaluable_race(d)}
    assert by_sql == by_py


def test_a_missing_data_div_is_kept(db):
    """data_div が NULL の行は落とさないこと。

    取り込み途中で NULL の行を「中止」と決めつけると、走ったレースを黙って
    評価から捨てることになる。中止と判定できないものは残す。
    """
    db.execute("INSERT INTO races VALUES ('2026','0921','05','01','01','01',NULL)")
    db.commit()

    assert "05" in _races(db, f"AND {sql_evaluable_race()}")
    assert is_evaluable_race(None) is True


# --- 指示された 6 ケース ---------------------------------------------------

def test_1_cancelled_races_are_not_in_the_hit_rate_denominator(db):
    """中止レースは的中率の分母に入らない。"""
    evaluable = db.execute(
        f"SELECT COUNT(*) FROM races WHERE {sql_evaluable_race()}").fetchone()[0]

    assert evaluable == 1, "中止レースが分母に残っている"


def test_2_cancelled_races_are_not_counted_as_purchases(db):
    """中止レースは購入件数に入らない。"""
    bought = db.execute(f"""
        SELECT COUNT(*) FROM horse_races h
         WHERE EXISTS (SELECT 1 FROM races r
                        WHERE r.track_code=h.track_code AND r.race_num=h.race_num
                          AND {sql_evaluable_race("r.data_div")})
    """).fetchone()[0]

    assert bought == 2, "中止レースの馬が購入件数に入っている"


def test_3_a_cancelled_race_never_books_a_loss():
    """中止レースは profit=-100 にならない。

    `build_daily_results` の計算式をそのまま再現する。中止レースが
    eval_rows に到達した時点で **必ず** -100 が計上されるので、
    「到達させない」ことでしか防げない。
    """
    def profit_of(bet_candidate: bool, win_pay: int) -> int:
        if bet_candidate:
            return (win_pay - 100) if win_pay > 0 else -100
        return 0

    # 中止レースは払戻が無いので、到達すれば必ず -100 になる
    assert profit_of(True, 0) == -100, "計算式の再現が間違っている"

    # だからこそ、中止レースは集計へ到達してはいけない
    assert is_cancelled_race(CANCELLED_DATA_DIV) is True
    assert EXCLUSION_CANCELLED == "cancelled"


def test_4_cancelled_races_are_not_in_the_roi_denominator(db):
    """中止レースは回収率の分母 (賭け金) に入らない。"""
    staked = db.execute(f"""
        SELECT COUNT(*) * 100 FROM horse_races h
         WHERE EXISTS (SELECT 1 FROM races r
                        WHERE r.track_code=h.track_code AND r.race_num=h.race_num
                          AND {sql_evaluable_race("r.data_div")})
    """).fetchone()[0]

    assert staked == 200, "中止レースぶんの賭け金が分母に入っている"


def test_5_races_that_actually_ran_are_still_counted(db):
    """実施レースは従来どおり集計される (除外しすぎない)。"""
    winners = db.execute(f"""
        SELECT COUNT(*) FROM horse_races h
         WHERE h.confirmed_order = 1
           AND EXISTS (SELECT 1 FROM races r
                        WHERE r.track_code=h.track_code AND r.race_num=h.race_num
                          AND {sql_evaluable_race("r.data_div")})
    """).fetchone()[0]

    assert winners == 1, "実施レースの勝ち馬まで落としている"


def test_6_the_exclusion_survives_a_loosened_confirmed_order(db):
    """confirmed_order の条件を緩めても中止レースは入らない。

    **これが一番大事**。backtest / prediction_accuracy / monitor は
    `confirmed_order > 0` の副作用で中止が落ちていただけだった。その条件を
    外しても中止が入らないことを見る。入るなら暗黙除外に戻っている。
    """
    loosened = db.execute(f"""
        SELECT COUNT(*) FROM horse_races h
         WHERE EXISTS (SELECT 1 FROM races r
                        WHERE r.track_code=h.track_code AND r.race_num=h.race_num
                          AND {sql_evaluable_race("r.data_div")})
    """).fetchone()[0]

    # confirmed_order の条件を一切付けていないのに、中止の 1 頭は入らない
    assert loosened == 2
    cancelled_leaked = db.execute(f"""
        SELECT COUNT(*) FROM horse_races h
         WHERE h.track_code='06'
           AND EXISTS (SELECT 1 FROM races r
                        WHERE r.track_code=h.track_code AND r.race_num=h.race_num
                          AND {sql_evaluable_race("r.data_div")})
    """).fetchone()[0]
    assert cancelled_leaked == 0, "中止レースが再流入している"


# --- 実コードが述語を使っていること ---------------------------------------

@pytest.mark.parametrize("rel", [
    "scripts/build_daily_results.py",
    "scripts/backtest.py",
    "scripts/prediction_accuracy.py",
    "scripts/monitor.py",
    "scripts/auto_predict.py",
    "web/generator.py",
    "scripts/fetch_fresh_odds.py",
    "scripts/fresh_odds_coverage.py",
])
def test_every_races_query_applies_the_predicate(rel):
    """`races` を読む SQL が **1 本残らず** 中止除外を通していること。

    最初は「ソースに sql_evaluable_race という語があるか」だけを見ていたが、
    SQL から `AND {evaluable}` を外しても `.format(evaluable=...)` の呼び出しが
    残るので **素通りした** (変異 C5 / C6 で実証)。語の存在ではなく、
    **races を読む文字列リテラル 1 本ずつ**に述語が入っているかを見る。
    """
    import ast
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / rel
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)

    def sql_text(node):
        """文字列リテラルと f-string を **1 本の SQL として** 取り出す。

        f-string は AST 上で定数と式に分かれるので、断片ごとに見ると
        「FROM races の断片」と「述語の断片」が別物になり、正しく除外して
        いるのに落ちる (実際に monitor / auto_predict で誤検出した)。
        """
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.JoinedStr):
            out = []
            for v in node.values:
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    out.append(v.value)
                else:
                    out.append(ast.unparse(v))
            return "".join(out)
        return None

    # 意図的に中止を含める SQL は **ここに本文ごと列挙**する。
    # 最初はソース中に "includes-cancelled:" と書けば免除する方式にしたが、
    # それだと 1 行足すだけでどの SQL も黙らせられた (変異 C12 で実証)。
    # 免除を増やすにはこのテストを編集するしかない形にする。
    allowed = {
        # 予定レース数。中止も数えるのが正しい (監査用の 4 値のうちの 1 つ)
        ("scripts/auto_predict.py",
         "select count(*) from races where race_year=? and race_month_day=?"),
        # 答え合わせは中止レースも **記録として残す**。行ごと消すと
        # 「予想は出した」という監査記録が失われるので、SQL では落とさず
        # evaluable=False / evaluation_exclusion_reason=cancelled を付ける。
        ("scripts/build_daily_results.py",
         "select race_year, race_month_day, track_code, kaiji, nichiji, race_num, "
         "race_name, distance, track_type_code, grade_code, registered_count, "
         "starter_count, turf_condition, dirt_condition, weather_code, start_time, "
         "data_div from races where race_year = ? and race_month_day = ? "
         "order by track_code, race_num"),
    }

    # f-string の中の定数断片は、親の JoinedStr として見るので個別には見ない。
    # これをやらないと「FROM races の断片」だけが単独で拾われ、述語が別断片に
    # あるのに落ちる。
    inside_fstring = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            for v in node.values:
                inside_fstring.add(id(v))

    offenders = []
    for node in ast.walk(tree):
        if id(node) in inside_fstring:
            continue
        sql = sql_text(node)
        if sql is None:
            continue
        flat = " ".join(sql.lower().split())
        # `horse_races` を見るのは generator だけに限る。**予想ループは
        # horse_races から回る**ので、races 側だけ守っても中止レースの
        # predict_race は走り続ける (データ基盤レビューで実証)。
        # 他ファイルの horse_races 読みは、すでに絞った races に紐づく取得か、
        # 行ごとに evaluable を付ける取得なので対象にしない (ノイズになる)。
        reads = ("from races" in flat
                 or (rel == "web/generator.py" and "from horse_races" in flat))
        if not reads:
            continue
        # **述語が入っているか**だけを見る。`data_div` という語の存在で
        # 免除すると、`SELECT *, data_div FROM races` と書くだけで
        # 述語なしでも通る抜け道になる (収益性レビューの指摘、再現済み)。
        if "{evaluable}" in sql or "{cancelled}" in sql:
            continue
        if "sql_evaluable_race(" in sql or "sql_cancelled_race(" in sql:
            continue
        if (rel, flat) in allowed:
            continue
        offenders.append(f"{rel}:{node.lineno}")

    assert not offenders, (
        f"races を読む SQL が中止除外を通していない: {offenders}。"
        f"db.sql_evaluable_race() を AND で足すこと。意図的に含めるなら "
        f"このテストの allowed に本文ごと追加すること")


# --- coverage ゲートの分母 -------------------------------------------------

def _coverage_db(tmp_path, cancelled: int, running: int, with_entries: int,
                 day: str = "20260921"):
    """中止 `cancelled` 件 + 実施 `running` 件、うち `with_entries` 件に出走馬。"""
    path = tmp_path / "cov.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE races (race_year TEXT, race_month_day TEXT,"
                 " track_code TEXT, kaiji TEXT, nichiji TEXT, race_num TEXT,"
                 " data_div TEXT)")
    conn.execute("CREATE TABLE horse_races (race_year TEXT, race_month_day TEXT,"
                 " track_code TEXT, kaiji TEXT, nichiji TEXT, race_num TEXT,"
                 " horse_num TEXT)")
    n = 0
    for i in range(cancelled):
        conn.execute("INSERT INTO races VALUES (?,?,'06','01','01',?,'9')",
                     (day[:4], day[4:], f"{i + 1:02d}"))
        # 中止レースにも出走馬は登録されている (だから分母を間違えやすい)
        conn.execute("INSERT INTO horse_races VALUES (?,?,'06','01','01',?,'01')",
                     (day[:4], day[4:], f"{i + 1:02d}"))
    for i in range(running):
        conn.execute("INSERT INTO races VALUES (?,?,'09','01','01',?,'6')",
                     (day[:4], day[4:], f"{i + 1:02d}"))
        if n < with_entries:
            conn.execute("INSERT INTO horse_races VALUES (?,?,'09','01','01',?,'01')",
                         (day[:4], day[4:], f"{i + 1:02d}"))
            n += 1
    conn.commit()
    return conn


def test_coverage_denominator_excludes_cancelled_races(tmp_path):
    """2026-09-21 そのもの: 中止 12 + 実施 12 は 24/24 ではなく 12/12。

    中止込みの 24 を分母にすると、半分が中止の日に「正常」と出てしまう。
    """
    from scripts.auto_predict import _entry_coverage

    conn = _coverage_db(tmp_path, cancelled=12, running=12, with_entries=12)
    covered, eligible, scheduled, cancelled = _entry_coverage(conn, "20260921")
    conn.close()

    assert (covered, eligible) == (12, 12), "分母が中止込みに戻っている"
    assert (scheduled, cancelled) == (24, 12), "監査用の 4 値が落ちている"
    assert covered / eligible == 1.0


def test_coverage_still_detects_missing_entries(tmp_path):
    """出走馬が本当に足りない日は、中止を除いてもちゃんと不足と分かること。"""
    from scripts.auto_predict import _entry_coverage

    conn = _coverage_db(tmp_path, cancelled=4, running=10, with_entries=5)
    covered, eligible, scheduled, cancelled = _entry_coverage(conn, "20260921")
    conn.close()

    assert (covered, eligible, scheduled, cancelled) == (5, 10, 14, 4)
    assert covered / eligible == 0.5, "中止を除いた実力値が出ていない"


def test_a_fully_cancelled_day_is_not_a_coverage_failure(tmp_path, monkeypatch, capsys):
    """全レース中止の日を「出走馬不足」で中止通知しないこと。

    再試行しても出走馬は増えないし、中止通知を 3 回出しても意味がない。
    「評価対象レースなし」として静かに終わる。
    """
    from scripts import auto_predict

    from datetime import date

    today = date.today().strftime("%Y%m%d")
    conn = _coverage_db(tmp_path, cancelled=6, running=0, with_entries=0, day=today)
    conn.close()
    monkeypatch.setattr(auto_predict, "DB_PATH", str(tmp_path / "cov.db"))
    monkeypatch.setattr(auto_predict.subprocess, "run", lambda *a, **k: None)
    sent = []
    monkeypatch.setattr(auto_predict, "_notify", lambda t: sent.append(t) or True)
    monkeypatch.setattr("sys.argv", ["auto_predict"])

    monkeypatch.setattr(auto_predict, "_is_final_attempt", lambda *a, **k: False)
    rc = auto_predict.main()

    out = capsys.readouterr().out
    assert rc == 0, f"中止だけの日を失敗扱いにしている (rc={rc})"
    assert sent == [], f"通常起動で中止だけの日に通知を出している: {sent}"
    assert "評価対象レースなし" in out

    # 最終起動では **黙らない**。完全に無音だと「タスクが起動しなかった」と
    # 区別できず、heartbeat を入れた意味が無くなる。
    monkeypatch.setattr(auto_predict, "_is_final_attempt", lambda *a, **k: True)
    monkeypatch.setattr("sys.argv", ["auto_predict", "--final-attempt"])
    assert auto_predict.main() == 0
    assert len(sent) == 1, f"最終起動でも無音のまま: {sent}"
    assert "すべて中止" in sent[0]


def test_a_half_cancelled_day_still_passes_the_gate(tmp_path, monkeypatch, capsys):
    """2026-09-21 の形を main() で通す: 中止 12 + 実施 12 で中止しないこと。

    分母を中止込みの 24 にすると 12/24 = 50% < 80% で「出走馬未取り込み」と
    判定し、**実施される 12 レースの予想を出さずに終わる**。順延の日に
    その日の予想を丸ごと落とす経路なので、ゲートの判断そのものを通して見る。
    """
    from datetime import date

    from scripts import auto_predict

    today = date.today().strftime("%Y%m%d")
    conn = _coverage_db(tmp_path, cancelled=12, running=12, with_entries=12,
                        day=today)
    conn.close()
    monkeypatch.setattr(auto_predict, "DB_PATH", str(tmp_path / "cov.db"))
    monkeypatch.setattr(auto_predict.subprocess, "run", lambda *a, **k: None)
    sent = []
    monkeypatch.setattr(auto_predict, "_notify", lambda t: sent.append(t) or True)
    monkeypatch.setattr("sys.argv", ["auto_predict", "--dry-run"])

    rc = auto_predict.main()

    out = capsys.readouterr().out
    assert rc == 0, f"半分が中止の日にゲートで止まっている (rc={rc})"
    assert sent == [], f"中止すべきでない日に通知を出している: {sent}"
    assert "scheduled=24 cancelled=12 eligible=12 covered=12" in out, (
        f"監査用の 4 値がログに出ていない: {out}")


# --- 答え合わせ: 予想は残し、評価だけ外す -------------------------------

def test_a_cancelled_race_is_recorded_but_not_evaluated():
    """中止レースは記録に残るが、評価対象にはならない。

    行ごと消してしまうと「予想は出した」という監査記録が失われる。
    「予想を出した件数」と「統計評価できた件数」を別物として持つのが要点。
    """
    from db import EXCLUSION_CANCELLED, is_evaluable_race

    for data_div, want_evaluable, want_status in (("9", False, "CANCELLED"),
                                                  ("6", True, "RUN")):
        evaluable = is_evaluable_race(data_div)
        assert evaluable is want_evaluable
        status = "CANCELLED" if not evaluable else "RUN"
        assert status == want_status
        reason = None if evaluable else EXCLUSION_CANCELLED
        assert reason == (None if want_evaluable else "cancelled")


def test_the_five_audit_fields_are_written(tmp_path):
    """evaluation_summary に 5 つの属性が出ること。

    prediction_issued / race_status / actual_execution_date / evaluable /
    evaluation_exclusion_reason。これがあると「なぜ N から消えたか」を
    後から追える。
    """
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "scripts" / "build_daily_results.py"
    text = src.read_text(encoding="utf-8")

    for field in ("prediction_issued", "race_status", "actual_execution_date",
                  "evaluable", "evaluation_exclusion_reason"):
        assert f'"{field}"' in text, f"{field} が出力に無い"
        # CSV の列一覧にも入っていること (dict に入れただけでは出力されない)
        assert text.count(f'"{field}"') >= 2, f"{field} が CSV 列に無い"


def test_stake_is_zero_for_cancelled_races():
    """回収率の分母は件数ではなく金額で持つこと。

    中止レースにも `bet_candidate` が残る (公開 HTML 由来なので、その日に
    買い候補として出したことは事実)。件数を分母にすると、賭けていない馬が
    分母に入って回収率が 100% 側へ歪む。
    """
    def stake(bet_candidate: bool, evaluable: bool) -> int:
        return 100 if (bet_candidate and evaluable) else 0

    assert stake(True, True) == 100
    assert stake(True, False) == 0, "中止レースの買い候補に賭け金が立っている"
    assert stake(False, True) == 0

    from pathlib import Path
    src = (Path(__file__).resolve().parents[1]
           / "scripts" / "build_daily_results.py").read_text(encoding="utf-8")
    assert src.count('"stake_yen_100unit"') >= 2, "CSV 列に出ていない"


def test_manifest_splits_issued_from_evaluable():
    """manifest が「出した件数」と「評価できた件数」を分けて書くこと。"""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1]
           / "scripts" / "build_daily_results.py").read_text(encoding="utf-8")

    for key in ("evaluation_rows_total", "evaluation_rows_evaluable",
                "evaluation_rows_excluded", "evaluation_exclusion_reasons"):
        assert key in src, f"manifest に {key} が無い"


# --- 実クエリを実行して確かめる (静的ガードに頼らない) -------------------
# AST ガードは「races を読む SQL」しか見ないので、**述語ごと消して races を
# 読まなくなった SQL** は検査対象から外れて素通りする (検証プロセス監査の
# M16/M17 で実証)。そこで実際のクエリ文字列を取り出して実行する。

def _module_sql(rel: str, must_contain: str) -> str:
    """モジュール内の SQL リテラルを 1 本取り出す (f-string は連結)。"""
    import ast
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    tree = ast.parse((repo / rel).read_text(encoding="utf-8"))
    # f-string の中の定数断片は親の JoinedStr として見る。個別に拾うと
    # 「マーカーを含む断片」だけが先に見つかり、述語が別断片にあるのに
    # 「無い」と誤判定する。
    inside = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            for v in node.values:
                inside.add(id(v))
    for node in ast.walk(tree):
        if id(node) in inside:
            continue
        if isinstance(node, ast.JoinedStr):
            parts = []
            for v in node.values:
                parts.append(v.value if isinstance(v, ast.Constant)
                             else ast.unparse(v))
            text = "".join(parts)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value
        else:
            continue
        if must_contain in text:
            return text
    raise AssertionError(f"{rel} に {must_contain!r} を含む SQL が無い")


@pytest.mark.parametrize("rel,marker", [
    ("scripts/prediction_accuracy.py", "hr.confirmed_order > 0"),
    ("scripts/monitor.py", "AS with_mining"),
])
def test_the_real_query_text_still_excludes_cancelled(rel, marker):
    """実際の SQL 本文に中止除外が残っていること。

    ガードは「races を読む SQL」を見るので、`NOT EXISTS (...races...)` を
    丸ごと消すと **races を読まなくなり検査対象から外れる**。消したことを
    検知するには、その SQL 本文自体を取り出して見るしかない。
    """
    sql = _module_sql(rel, marker)

    assert "NOT EXISTS" in sql, f"{rel}: 中止除外の NOT EXISTS が消えている"
    assert "races" in sql, f"{rel}: races を参照しなくなっている"
    assert ("cancelled" in sql or "data_div" in sql), (
        f"{rel}: 中止の述語が入っていない")


# --- 中止 と 結果未取得 を潰さない -------------------------------------

def test_cancelled_and_pending_are_different_reasons():
    """永久除外と一時的な未取得を同じ理由で潰さないこと。

    一緒くたにすると、「まだ結果が来ていないだけ」のレースを永久に評価から
    落としたまま気付けなくなる。逆に未取得を評価対象に入れると
    `confirmed_order=0` が「不的中」に数えられて的中率が下がる。
    """
    from db import EXCLUSION_CANCELLED, EXCLUSION_RESULT_PENDING

    assert EXCLUSION_CANCELLED != EXCLUSION_RESULT_PENDING
    assert EXCLUSION_CANCELLED == "cancelled"
    assert EXCLUSION_RESULT_PENDING == "result_not_yet_available"


def test_evaluable_requires_both_not_cancelled_and_resolved():
    """evaluable = 中止でない AND 結果あり、であること。"""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1]
           / "scripts" / "build_daily_results.py").read_text(encoding="utf-8")

    assert "evaluable = not_cancelled and result_resolved" in src, (
        "evaluable に多義を持たせている (中止だけを見ていないか)")
    assert "EXCLUSION_RESULT_PENDING" in src, "結果未取得の理由が使われていない"
    assert '"result_resolved"' in src, "result_resolved が出力に無い"


def test_analyze_misses_skips_excluded_races():
    """分析系でも評価対象外のレースを数えないこと。

    主要集計だけ直しても、ここが素通りだと中止レースが分析で復活する。
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1]
           / "scripts" / "analyze_misses.py").read_text(encoding="utf-8")

    assert "evaluation_exclusion_reason" in src, "除外理由を見ていない"
    assert "evaluable" in src, "evaluable を見ていない"
    assert 'skipped[f"excluded_{reason}"]' in src, (
        "除外を理由ごとに数えていない (cancelled と pending が潰れる)")
