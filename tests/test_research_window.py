"""研究の窓の関所 (`scripts/research_window.py`、docs/LOCKBOX_GOVERNANCE.md、2026-10-06) の契約。

- 期間は development (〜2024) / consumed (2025〜RESERVED_FROM の前日) / reserved (RESERVED_FROM〜FRESH_FROM の前日) / fresh (FRESH_FROM〜)
- reserved はどの目的でも読まない。FRESH_FROM が未確定の間は RESERVED_FROM 以降すべてが reserved。どの期間にも属さない日は止める
- 2025 の再現は凍結済みの runner の目的の完全一致だけ。development 以外の通過は監査ログに追記 (書けなければ止める)
- 件数の点検と開催日の確定の SQL は結果の列を含まず、返る列は allow-list と完全一致
- 研究の読み込み (group_a / c_prime の load_races と、DB を読む研究のファイル) は関所を通る。本番の封印 (SEALED_FROM) は変えない
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pytest

import config
from scripts import c_prime as cp
from scripts import group_a as ga
from scripts import research_window as rw

REPRO = "power: 2025 の過去走の時計を S の履歴として読む (対象レースの結果は対象の行に付けない)"
ROOT = Path(rw.__file__).resolve().parents[1]


@pytest.fixture
def fresh(monkeypatch):
    monkeypatch.setattr(config, "FRESH_FROM", "20261010")


def _log_lines():
    path = Path(config.RESEARCH_WINDOW_ACCESS_LOG)
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def test_the_production_seal_is_untouched():
    assert config.SEALED_FROM is None and config.SEALED_UNTIL is None


def test_constants_hold_today():
    rw.check_constants()
    assert config.RESERVED_FROM == config.CONFIRM_FROM == "20260914"
    assert config.RESERVED_FROM > config.consumed_until()
    assert config.FRESH_FROM == "20261010"          # 規則どおり確定した値 (fresh_from_determination.json)。中止・順延でも変えない


def test_the_recorded_determination_matches_the_constant():
    rec = json.loads((ROOT / "data" / "backtest" / "research_window_20261006" / "fresh_from_determination.json").read_text(encoding="utf-8"))
    assert rec["fresh_from"] == config.FRESH_FROM and rec["not_before"] == config.FRESH_FROM_NOT_BEFORE
    assert rec["governance_commit"] == config.FRESH_GOVERNANCE_COMMIT and rec["schedule_data_created"] < "20261006"


@pytest.mark.parametrize("frm,to,want", [
    ("20220101", "20241231", {"development"}),
    ("20241231", "20250101", {"development", "consumed"}),
    ("20250601", "20251231", {"consumed"}),
    ("20260913", "20260913", {"consumed"}),
    ("20260914", "20260914", {"reserved"}),
    ("20261009", "20261009", {"reserved"}),
    ("20261010", "20261010", {"fresh"}),
    ("20260913", "20261010", {"consumed", "reserved", "fresh"}),
])
def test_period_boundaries_with_fresh_fixed(fresh, frm, to, want):
    assert rw.periods_spanned(frm, to) == want


def test_everything_from_reserved_is_reserved_while_fresh_is_unfixed(monkeypatch):
    monkeypatch.setattr(config, "FRESH_FROM", None)
    assert rw.periods_spanned("20270101", "20270101") == {"reserved"}
    assert rw.periods_spanned("20260913", "20260913") == {"consumed"}


def test_development_reads_only_development():
    assert rw.check("20210101", "20241231", purpose="development", context="t")["periods"] == ["development"]
    with pytest.raises(rw.ResearchWindowError, match="consumed"):
        rw.check("20220101", "20250101", purpose="development", context="t")


def test_reproduce_consumed_needs_a_registered_runner_purpose_and_stops_before_reserved():
    rw.check("20210101", "20251231", purpose="reproduce_consumed", context="t", reproduces=REPRO)
    rw.check("20250101", "20251231", purpose="reproduce_consumed", context="t", reproduces="primary: Group C′ の主検定 (run_index 1)")
    for bad in (None, "", "anything", "A″ の 2025 での診断", REPRO + " ", "primary: Group C′ の主検定 (run_index 2)"):
        with pytest.raises(rw.ResearchWindowError, match="reproduces"):
            rw.check("20250101", "20251231", purpose="reproduce_consumed", context="t", reproduces=bad)
    with pytest.raises(rw.ResearchWindowError, match="RESERVED_UNTOUCHED"):
        rw.check("20250101", "20260914", purpose="reproduce_consumed", context="t", reproduces=REPRO)


def _runner_purposes(name):
    text = (ROOT / "scripts" / name).read_text(encoding="utf-8")
    return {m.group(2).replace("{run_index}", "1") if m.group(1) else m.group(2)
            for m in re.finditer(r'primary_purpose=(f?)"([^"]+)"', text)}


def test_executed_runner_purposes_are_registered_and_the_stopped_d_runner_is_not():
    """主検定を実行した A / C′ の runner の目的 (run_index 1) は一覧の完全一致。停止した D の runner の目的は 1 つも入らない。"""
    executed = _runner_purposes("group_a_run.py") | _runner_purposes("c_prime_run.py")
    assert len(executed) == 5 and executed == rw.REPRODUCIBLE_PURPOSES - {"test"}
    stopped = _runner_purposes("group_d_run.py")
    assert len(stopped) == 3 and not stopped & rw.REPRODUCIBLE_PURPOSES
    with pytest.raises(rw.ResearchWindowError, match="reproduces"):
        rw.check("20250101", "20251231", purpose="reproduce_consumed", context="t", reproduces="primary: Group D の主検定 (run_index 1)")


def test_non_development_reads_are_logged_and_development_is_not(fresh):
    rw.check("20220101", "20241231", purpose="development", context="dev")
    assert _log_lines() == []
    rw.check("20250101", "20251231", purpose="reproduce_consumed", context="repro", reproduces=REPRO)
    rw.check("20261010", "20261031", purpose="lockbox_count_only", context="count", reads_outcomes=False)
    lines = _log_lines()
    assert [x["context"] for x in lines] == ["repro", "count"] and lines[0]["reproduces"] == REPRO and lines[0]["at"]


def test_an_unwritable_log_stops_the_read(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "RESEARCH_WINDOW_ACCESS_LOG", tmp_path)          # ディレクトリには追記できない
    with pytest.raises(rw.ResearchWindowError, match="監査ログ"):
        rw.check("20250101", "20251231", purpose="reproduce_consumed", context="t", reproduces=REPRO)


@pytest.mark.parametrize("purpose", rw.PURPOSES)
def test_reserved_is_refused_for_every_purpose(fresh, purpose):
    with pytest.raises(rw.ResearchWindowError, match="RESERVED_UNTOUCHED"):
        rw.check("20260920", "20260920", purpose=purpose, context="t", reads_outcomes=False, reproduces=REPRO)


def test_count_only_reads_fresh_without_outcomes(fresh):
    rw.check("20261010", "20261231", purpose="lockbox_count_only", context="t", reads_outcomes=False)
    with pytest.raises(rw.ResearchWindowError, match="reads_outcomes"):
        rw.check("20261010", "20261231", purpose="lockbox_count_only", context="t")
    with pytest.raises(rw.ResearchWindowError, match="consumed"):
        rw.check("20250101", "20250102", purpose="lockbox_count_only", context="t", reads_outcomes=False)


def test_fresh_is_refused_for_development_and_reproduction(fresh):
    for purpose in ("development", "reproduce_consumed"):
        with pytest.raises(rw.ResearchWindowError, match="fresh"):
            rw.check("20261010", "20261010", purpose=purpose, context="t", reproduces=REPRO)


def test_primary_after_unlock_is_not_available_yet(fresh):
    with pytest.raises(rw.ResearchWindowError, match="開封の手順"):
        rw.check("20261010", "20261010", purpose="primary_after_unlock", context="t")


def test_unknown_purpose_missing_context_and_bad_dates_stop():
    with pytest.raises(rw.ResearchWindowError, match="purpose"):
        rw.check("20220101", "20220102", purpose="explore", context="t")
    with pytest.raises(rw.ResearchWindowError, match="context"):
        rw.check("20220101", "20220102", purpose="development", context="")
    with pytest.raises(rw.ResearchWindowError, match="YYYYMMDD"):
        rw.check("2022-01-01", "20220102", purpose="development", context="t")
    with pytest.raises(rw.ResearchWindowError, match=">"):
        rw.check("20220102", "20220101", purpose="development", context="t")


@pytest.mark.parametrize("attr,value,match", [
    ("FRESH_FROM", "20261006", "下限"),
    ("RESERVED_FROM", "20260913", "消費済み"),
    ("FRESH_FROM_NOT_BEFORE", "20260914", "順序"),
])
def test_broken_constants_stop_every_read(monkeypatch, attr, value, match):
    monkeypatch.setattr(config, attr, value)
    with pytest.raises(rw.ResearchWindowError, match=match):
        rw.check("20220101", "20220102", purpose="development", context="t")


def test_a_gap_between_development_and_consumed_stops_every_read(monkeypatch):
    """train の終わりを 1 年早めると 2024 はどの期間にも属さない。そこを『許可』にしない。"""
    split = {k: dict(v) for k, v in config.DATA_SPLIT.items()}
    split["train"]["to"] = "20231231"
    monkeypatch.setattr(config, "DATA_SPLIT", split)
    with pytest.raises(rw.ResearchWindowError, match="隙間"):
        rw.check("20240101", "20241231", purpose="development", context="t")
    monkeypatch.setattr(rw, "check_constants", lambda: None)
    with pytest.raises(rw.ResearchWindowError, match="どの期間にも属さない"):
        rw.periods_spanned("20240101", "20241231")


def test_recording_an_opened_fresh_window_as_consumed_does_not_break_the_guard(monkeypatch, fresh):
    """開封した fresh の窓を CONSUMED_WINDOWS に記録しても、development の読み込みは止まらない。"""
    monkeypatch.setattr(config, "CONSUMED_WINDOWS",
                        config.CONSUMED_WINDOWS + [{"from": "20261010", "to": "20270331", "by": "t", "note": "t"}])
    assert rw.check("20220101", "20241231", purpose="development", context="t")["periods"] == ["development"]


# ------------------------------------------------------------------------------------------------ 研究の読み込みの配線

@pytest.mark.parametrize("load", [ga.load_races, cp.load_races])
def test_loaders_refuse_2026_even_with_the_primary_year_flag(load):
    with pytest.raises(rw.ResearchWindowError, match="RESERVED_UNTOUCHED"):
        load(2026, min_year=2021, db_path="unused.db", allow_primary_year=True, primary_purpose=REPRO)


@pytest.mark.parametrize("load", [ga.load_races, cp.load_races])
def test_loaders_refuse_a_new_2025_purpose(load):
    with pytest.raises(rw.ResearchWindowError, match="reproduces"):
        load(2025, min_year=2021, db_path="unused.db", allow_primary_year=True, primary_purpose="A″ の 2025 での診断")


@pytest.mark.parametrize("load", [ga.load_races, cp.load_races])
def test_loaders_pass_the_purpose_to_the_guard(monkeypatch, load):
    seen = []

    def fake(min_year, max_year, **kw):
        seen.append((min_year, max_year, kw["purpose"], kw.get("reproduces")))
        raise rw.ResearchWindowError("stop here")
    monkeypatch.setattr(rw, "check_years", fake)
    with pytest.raises(rw.ResearchWindowError):
        load(2024, min_year=2021, db_path="unused.db")
    with pytest.raises(rw.ResearchWindowError):
        load(2025, min_year=2021, db_path="unused.db", allow_primary_year=True, primary_purpose="why")
    assert seen == [(2021, 2024, "development", None), (2021, 2025, "reproduce_consumed", "why")]


FROZEN_RESEARCH_READERS = frozenset({          # 主検定まで実行・凍結済みで、2025 の定数でしか読まない runner (完全一致)
    "scripts/group_a_power.py", "scripts/group_a_run.py", "scripts/c_prime_run.py", "scripts/group_d_run.py"})


def test_research_readers_go_through_the_guard():
    """研究の読み込み (group_* / c_prime* / *_run / *_explore) で DB を読むファイルは、関所 (research_window.check) を呼ぶ。"""
    names = {p for pat in ("group_*.py", "c_prime*.py", "*_run.py", "*_explore.py") for p in (ROOT / "scripts").glob(pat)}
    readers = {p.relative_to(ROOT).as_posix() for p in names
               if re.search(r"sqlite3\.connect\(|guard_analysis_window\(|list_races\(|db\.connect\(|open_db",
                            p.read_text(encoding="utf-8"))}
    unguarded = {r for r in readers if "research_window.check" not in (ROOT / r).read_text(encoding="utf-8")}
    assert unguarded == FROZEN_RESEARCH_READERS, sorted(unguarded ^ FROZEN_RESEARCH_READERS)


def test_frozen_runners_read_target_fields_only_for_the_primary_year():
    calls = []
    for name in FROZEN_RESEARCH_READERS:
        calls += re.findall(r"(?<!def )load_target_fields\(([^,]+),", (ROOT / name).read_text(encoding="utf-8"))
    assert sorted(c.strip() for c in calls) == ["PRIMARY_YEAR", "PRIMARY_YEAR", "max(PRIMARY_YEARS)"]


# ------------------------------------------------------------------------------------------------ 件数の点検

def test_count_and_schedule_sql_have_no_result_columns():
    for sql in (rw.count_sql(), rw.schedule_sql()):
        assert not [f for f in rw.FORBIDDEN_FRAGMENTS if f in sql.lower()]


@pytest.mark.parametrize("col", ["r.win_odds", "r.front3f_time", "r.last4f_time", "r.starter_count", "r.weather_code",
                                 "r.turf_condition"])
def test_a_result_column_in_the_count_sql_stops(monkeypatch, col):
    monkeypatch.setattr(rw, "COUNT_SELECT", rw.COUNT_SELECT + ((col, "x"),))
    with pytest.raises(rw.ResearchWindowError, match="結果の列"):
        rw.count_sql()


def _races_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE races (race_year TEXT, race_month_day TEXT, track_code TEXT, kaiji TEXT, nichiji TEXT,"
                 " race_num TEXT, track_type_code TEXT, data_div TEXT, payout_secret TEXT)")
    rows = [("2026", "1010", "05", "4", "1", "01", "17", "7", "x"),   # 芝
            ("2026", "1010", "05", "4", "1", "02", "24", "7", "x"),   # ダート
            ("2026", "1010", "05", "4", "1", "03", "54", "7", "x"),   # 障害 → 数えない
            ("2026", "1010", "05", "4", "1", "04", "17", "9", "x"),   # 中止 → 数えない
            ("2026", "1011", "30", "1", "1", "01", "17", "7", "x"),   # 地方 → 数えない
            ("2026", "1011", "08", "4", "2", "01", "17", "1", "x"),   # 発走前 (データ区分 1) は未確定として数える
            ("2026", "1009", "05", "4", "1", "01", "17", "7", "x")]   # reserved → 範囲外
    conn.executemany("INSERT INTO races VALUES (?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()


def test_count_fresh_races_counts_flat_jra_races_only(fresh, tmp_path):
    db = tmp_path / "k.db"
    _races_db(db)
    out = rw.count_fresh_races(db, "20261010", "20261031", context="t")
    assert out["n_confirmed"] == 2 and out["n_pending"] == 1
    assert out["by_day"] == {"20261010": {"confirmed": 2, "pending": 0}, "20261011": {"confirmed": 0, "pending": 1}}
    assert out["window"]["purpose"] == "lockbox_count_only" and out["window"]["reads_outcomes"] is False


def test_count_stops_on_an_unknown_track_type(fresh, tmp_path):
    db = tmp_path / "k.db"
    _races_db(db)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO races VALUES ('2026','1012','05','4','3','01',NULL,'7','x')")
    conn.commit()
    conn.close()
    with pytest.raises(rw.ResearchWindowError, match="track_type_code"):
        rw.count_fresh_races(db, "20261010", "20261031", context="t")


def test_count_fresh_races_refuses_reserved_days(fresh, tmp_path):
    db = tmp_path / "k.db"
    _races_db(db)
    with pytest.raises(rw.ResearchWindowError, match="RESERVED_UNTOUCHED"):
        rw.count_fresh_races(db, "20261009", "20261031", context="t")


def test_returned_columns_must_match_the_allow_list(fresh, tmp_path, monkeypatch):
    db = tmp_path / "k.db"
    _races_db(db)
    monkeypatch.setattr(rw, "COUNT_COLUMNS", rw.COUNT_COLUMNS + ("extra",))
    with pytest.raises(rw.ResearchWindowError, match="allow-list"):
        rw.count_fresh_races(db, "20261010", "20261031", context="t")


# ------------------------------------------------------------------------------------------------ FRESH_FROM の確定

def _schedules_db(path, rows):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE schedules (race_year TEXT, race_month_day TEXT, track_code TEXT, kaiji TEXT, nichiji TEXT,"
                 " weekday_code TEXT, data_div TEXT, data_created TEXT)")
    conn.executemany("INSERT INTO schedules VALUES (?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()


def test_fresh_from_is_the_first_jra_day_on_or_after_the_floor(tmp_path):
    db = tmp_path / "s.db"
    _schedules_db(db, [("2026", "1004", "05", "4", "2", "2", "1", "20251222"),   # 下限より前
                       ("2026", "1008", "30", "1", "1", "5", "1", "20251222"),   # 地方
                       ("2026", "1011", "05", "4", "4", "2", "1", "20251222"),
                       ("2026", "1010", "08", "4", "3", "1", "1", "20251222")])
    out = rw.determine_fresh_from(db)
    assert out["fresh_from"] == "20261010" and out["not_before"] == "20261007" and out["schedule_data_created"] == "20251222"
    assert out["schedule_rows"] == [["08", "1", "20251222"]]
    assert [x["purpose"] for x in _log_lines()] == ["determine_fresh_from"]


def test_fresh_from_without_a_scheduled_day_stops(tmp_path):
    db = tmp_path / "s.db"
    _schedules_db(db, [("2026", "1004", "05", "4", "2", "2", "1", "20251222")])
    with pytest.raises(rw.ResearchWindowError, match="開催スケジュール"):
        rw.determine_fresh_from(db)


def test_schedule_sql_returned_columns_must_match(tmp_path, monkeypatch):
    db = tmp_path / "s.db"
    _schedules_db(db, [("2026", "1010", "05", "4", "3", "1", "1", "20251222")])
    monkeypatch.setattr(rw, "SCHEDULE_COLUMNS", ("x",))
    with pytest.raises(rw.ResearchWindowError, match="allow-list"):
        rw.determine_fresh_from(db)


# ------------------------------------------------------------------------------------------------ 履歴としてだけの読み (§9 の改訂)

HIST_COLS = ("horse_races.race_year", "horse_races.blood_register_num", "horse_races.finish_time", "horse_races.confirmed_order",
             "horse_races.abnormal_code", "races.distance")


def _hist(**kw):
    args = {"lookback_days": 365, "history_columns": HIST_COLS, "context": "t"}
    args.update(kw)
    return rw.check_history_for_fresh_targets(args.pop("target_from", "20261010"), args.pop("target_to", "20261031"), **args)


def test_history_read_is_only_from_inside_an_opening_for_now():
    """条件を満たしても、開封の手順が無いので今は止まる。止まる理由に履歴の窓 [対象 − 365 日, 最後の対象 − 1 日] が出る。"""
    with pytest.raises(rw.ResearchWindowError, match="20251010〜20261030.*開封の中からだけ"):
        _hist()


@pytest.mark.parametrize("frm,to", [("20261009", "20261031"), ("20260920", "20260930"), ("20250101", "20250131")])
def test_history_read_needs_all_targets_in_fresh(frm, to):
    with pytest.raises(rw.ResearchWindowError, match="対象がすべて fresh"):
        _hist(target_from=frm, target_to=to)


@pytest.mark.parametrize("days", [364, 366, 730, True, "365", 365.0])
def test_history_lookback_must_be_the_fixed_value(days):
    with pytest.raises(rw.ResearchWindowError, match="参照日数"):
        _hist(lookback_days=days)


@pytest.mark.parametrize("cols", [(), ("",), ("finish_time",), ("horse_races.finish_time", "horse_races.win_odds"),
                                  ("payouts.tan_pop1",), ("horse_races.Win_Popularity",), ("vote_counts.combo",), ("Payouts.race_year",),
                                  ("horse_races.*",), ("*",), ("a.b.c",), (".finish_time",),
                                  ("horse_races.tan_pop1",)])      # 市場の表の外に将来できる人気の列 (今のスキーマには無い)
def test_history_columns_are_an_allow_list_without_market_or_payouts(cols):
    with pytest.raises(rw.ResearchWindowError, match="履歴の列"):
        _hist(history_columns=cols)


def test_history_read_needs_a_context():
    with pytest.raises(rw.ResearchWindowError, match="context"):
        _hist(context="")


def _schema_columns():
    conn = sqlite3.connect(":memory:")
    conn.executescript((ROOT / "data" / "schema.sql").read_text(encoding="utf-8"))
    tables = [t for (t,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
    return [(t, r[1]) for t in tables for r in conn.execute(f"PRAGMA table_info({t})")]


def test_every_market_column_in_the_schema_is_refused_as_history():
    """data/schema.sql の全列のうち、市場の表の列と、オッズ・人気・票数・払戻らしい名前の列は、履歴の列として全部止まる (列名はスキーマから引く)。"""
    cols = _schema_columns()
    assert len(cols) > 200
    market = [f"{t}.{c}" for t, c in cols
              if t in rw.MARKET_TABLES or re.search(r"odds|pop|vote|pay|refund|dividend", c.lower())]
    assert {"payouts.tan_pop1", "horse_races.win_popularity", "vote_counts.votes", "win5_payouts.hit_votes",
            "odds_snapshots.win_odds", "win5.refund_flag"} <= set(market)
    for col in market:
        with pytest.raises(rw.ResearchWindowError, match="履歴の列"):
            _hist(history_columns=(col,))
    assert set(rw.MARKET_TABLES) <= {t for t, _ in cols}


def test_ordinary_history_columns_reach_the_opening_gate():
    for col in ("horse_races.finish_time", "horse_races.confirmed_order", "races.track_type_code", "races.turf_condition"):
        with pytest.raises(rw.ResearchWindowError, match="開封の中からだけ"):
            _hist(history_columns=(col,))


def test_market_fragments_are_shared_with_the_count_sql_and_the_lookback_matches_group_a():
    assert set(rw.MARKET_FRAGMENTS) | set(rw.MARKET_TABLES) <= set(rw.FORBIDDEN_FRAGMENTS)
    assert rw.HISTORY_LOOKBACK_DAYS == {ga.WINDOW_DAYS}

