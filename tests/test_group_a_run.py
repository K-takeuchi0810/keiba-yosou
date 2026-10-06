"""scripts/group_a_run.py (凍結 → 検出力 → 主検定) のテスト。判定の規則と、合成の小さな DB での端から端まで。"""
from __future__ import annotations

import json
import math
import sqlite3

import numpy as np
import pytest

from scripts import group_a as g
from scripts import group_a_run as run
from scripts import research_window as rw

# 研究の窓の関所の再現の一覧は、実行済みの run_index 1 だけ (2026-10-06)。中断・再 arm の契約を合成の DB で確かめるこのファイルの中だけで
# run_index 2・3 の目的を足す (本物の DB では、再実行は再凍結と一覧への追加のコミットが先)
RERUN_PURPOSES = frozenset(f"primary: Group A の主検定 (run_index {i})" for i in (2, 3))


@pytest.fixture(scope="module", autouse=True)
def _allow_reruns_on_the_synthetic_db():
    mp = pytest.MonkeyPatch()
    mp.setattr(rw, "REPRODUCIBLE_PURPOSES", rw.REPRODUCIBLE_PURPOSES | RERUN_PURPOSES)
    yield
    mp.undo()


# ---------------------------------------------------------------------------------------------------- 判定の規則

@pytest.mark.parametrize("ci, inconclusive, expected", [
    ({"valid": False, "lo": math.nan, "hi": math.nan}, False, ("PRIMARY_INCONCLUSIVE", "boot_na")),
    ({"valid": False, "lo": math.nan, "hi": math.nan}, True,
     ("PRIMARY_INCONCLUSIVE", "mde_above_beta_target+boot_na")),                                     # MDE の理由を上書きしない
    ({"valid": True, "lo": 0.05, "hi": 0.2}, True, ("PRIMARY_INCONCLUSIVE", "mde_above_beta_target")),  # 下限 > 0 でも
    ({"valid": True, "lo": -0.3, "hi": -0.1}, True, ("PRIMARY_INCONCLUSIVE", "mde_above_beta_target")),
    ({"valid": True, "lo": 0.01, "hi": 0.2}, False, ("PRIMARY_PASS", "ci_lower_above_zero")),
    ({"valid": True, "lo": 0.0, "hi": 0.2}, False, ("PRIMARY_FAIL", "ci_lower_not_above_zero")),         # 0 ちょうどは PASS でない
    ({"valid": True, "lo": -0.1, "hi": 0.2}, False, ("PRIMARY_FAIL", "ci_lower_not_above_zero")),
])
def test_verdict_rules(ci, inconclusive, expected):
    assert run.verdict(ci, {"inconclusive_by_power": inconclusive}) == expected


# ---------------------------------------------------------------------------------------------------- 合成の DB

def _synthetic_db(tmp_path, seed=0):
    """2021-2025、1 つのコース (東京 芝 1600) で週 2 日 × 4 レース。馬 240 頭の能力から時計と、ノイズのある市場を作る。"""
    rng = np.random.default_rng(seed)
    path = tmp_path / "s.db"
    con = sqlite3.connect(path)
    con.execute("""CREATE TABLE races (race_year, race_month_day, track_code, kaiji, nichiji, race_num, data_div,
                   track_type_code, distance, turf_condition, dirt_condition, weight_type_code)""")
    con.execute("""CREATE TABLE horse_races (race_year, race_month_day, track_code, kaiji, nichiji, race_num, horse_num,
                   blood_register_num, abnormal_code, confirmed_order, finish_time, burden_weight, win_odds, age, final_3f)""")
    ability = rng.normal(0, 1, 240)
    classes = {}
    import datetime as dt
    day = dt.date(2021, 1, 9)
    while day.year <= 2025:
        for rn in range(1, 5):
            ymd = day.strftime("%Y%m%d")
            rid = f"{ymd}_05_01_01_{rn:02d}"
            classes[rid] = ("005", "3up")
            con.execute("INSERT INTO races VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (ymd[:4], ymd[4:], "05", "01", "01", f"{rn:02d}", "7", "11", 1600, "1", "0", "3"))
            field = rng.choice(240, size=10, replace=False)
            sec = 96.0 - 0.6 * ability[field] + rng.normal(0, 0.5, 10)
            order = np.argsort(sec)
            fin = np.empty(10, dtype=int)
            fin[order] = np.arange(1, 11)
            strength = np.exp(0.9 * ability[field] + rng.normal(0, 0.6, 10))
            prob = strength / strength.sum()
            for j, h in enumerate(field):
                t = int(sec[j] // 60) * 1000 + int(round((sec[j] % 60) * 10))
                odds = max(11, int(round(10 * 0.8 / prob[j])))
                con.execute("INSERT INTO horse_races VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (ymd[:4], ymd[4:], "05", "01", "01", f"{rn:02d}", f"{j + 1:02d}", f"H{h:03d}", "0",
                             int(fin[j]), t, 550, odds, 4, 350))
        day += dt.timedelta(days=3 if day.weekday() == 5 else 4)
    con.commit()
    con.close()
    return path, classes


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("ga_run")
    path, classes = _synthetic_db(tmp)
    e1b = tmp / "e1b.json"
    e1b.write_text(json.dumps({"selection": {"selected": "S1V1W0"}}), encoding="utf-8")
    return tmp, path, classes, e1b


@pytest.fixture
def patched(world, monkeypatch):
    tmp, path, classes, e1b = world
    monkeypatch.setattr(g, "load_class_table", lambda *a, **k: classes)
    monkeypatch.setattr(run, "BOOT_N", 200)                 # テストを速くする (本番は 1000)
    real = g.provenance

    def clean(*a, **k):                                     # 本物の repo の作業ツリーの状態に左右されないように
        return {**real(*a, **k), "git_dirty": False, "git_status": []}

    monkeypatch.setattr(g, "provenance", clean)
    monkeypatch.setattr(run, "_lock_is_committed", lambda p: True)   # 一時ディレクトリは repo の外 (判定そのものは別のテスト)
    return world


def test_freeze_refuses_a_spec_other_than_the_e1b_selection(patched, tmp_path):
    tmp, path, classes, e1b = patched
    with pytest.raises(run.RunError, match="E1b"):
        run.run_freeze(str(path), "S2V1W0", tmp_path / "f", e1b, ["t"])


def test_end_to_end_freeze_power_primary(patched, tmp_path):
    tmp, path, classes, e1b = patched
    frozen = tmp_path / "frozen"
    man = run.run_freeze(str(path), "S1V1W0", frozen, e1b, ["t"])
    assert man["est_years"] == [2022, 2023, 2024] and man["bootstrap"]["se"] and man["bootstrap"]["n_boot"] == 200
    assert man["bootstrap"]["n_valid"] + man["bootstrap"]["n_discarded"] == 200          # 実際に回した回数
    assert set(man["leave_one_year_out"]) == {"2022", "2023", "2024"}
    assert man["choice_set"]["max_abs_prob_sum_dev"] < 1e-12
    pw_out = tmp_path / "power"
    power = run.run_power(str(path), frozen, pw_out, ["t"])
    assert power["frozen_sha256"] == man["frozen_sha256"] and power["fisher"]["se"] > 0
    assert set(power["power"]) >= {"se_fixed", "mde", "inconclusive_by_power"}
    prim = tmp_path / "primary"
    with pytest.raises(run.RunError, match="錠が無い"):                  # arm の前は走らない
        run.run_primary(str(path), frozen, pw_out / run.POWER_FILE, prim, ["t"])
    lock = run.run_arm(str(path), frozen, pw_out / run.POWER_FILE, ["t"])
    assert lock["run_index"] == 1
    with pytest.raises(run.RunError, match="錠が既にある"):              # 2 回目の arm は拒む
        run.run_arm(str(path), frozen, pw_out / run.POWER_FILE, ["t"])
    res = run.run_primary(str(path), frozen, pw_out / run.POWER_FILE, prim, ["t"])
    assert res["ci_99"]["level"] == 0.99 and res["ci_99"]["n_boot"] == 5000 and res["ci_99"]["seed"] == 20261004
    assert res["category"] in {"PRIMARY_PASS", "PRIMARY_FAIL", "PRIMARY_INCONCLUSIVE"}
    assert res["category"] == run.verdict(res["ci_99"], res["power"])[0]
    assert res["choice_set"]["max_abs_prob_sum_dev"] < 1e-12
    with pytest.raises(run.RunError, match="1 回だけ"):                  # 2 回目は拒む
        run.run_primary(str(path), frozen, pw_out / run.POWER_FILE, prim, ["t"])
    with pytest.raises(run.RunError, match="1 回だけ"):                  # 出力先を変えても拒む (錠は凍結物の側)
        run.run_primary(str(path), frozen, pw_out / run.POWER_FILE, tmp_path / "other", ["t"])
    assert (prim / run.SIDE_FILE).exists() and (frozen / run.STARTED_FILE.format(1)).exists()
    assert res["n_races_power_minus_primary"] >= 0


def test_power_does_not_attach_outcomes(patched, tmp_path, monkeypatch):
    """検出力の行は、対象レース (2025) の着順を書き換えても変わらない (同じ凍結物で)。"""
    tmp, path, classes, e1b = patched
    frozen = tmp_path / "frozen"
    run.run_freeze(str(path), "S1V1W0", frozen, e1b, ["t"])
    a = run.run_power(str(path), frozen, tmp_path / "p1", ["t"])
    # 2025 の最後の日 (それより後に対象レースが無い = 履歴として誰の成分にも入らない) の着順を入れ替える
    con = sqlite3.connect(path)
    last = con.execute("SELECT max(race_year||race_month_day) FROM races").fetchone()[0]
    con.execute("UPDATE horse_races SET confirmed_order = 11 - confirmed_order WHERE race_year||race_month_day = ?", (last,))
    con.commit()
    con.close()
    b = run.run_power(str(path), frozen, tmp_path / "p2", ["t"])
    con = sqlite3.connect(path)
    con.execute("UPDATE horse_races SET confirmed_order = 11 - confirmed_order WHERE race_year||race_month_day = ?", (last,))
    con.commit()
    con.close()
    assert a["fisher"]["se"] == b["fisher"]["se"] and a["power"] == b["power"]


def test_primary_refuses_power_from_another_freeze(patched, tmp_path):
    tmp, path, classes, e1b = patched
    frozen = tmp_path / "frozen"
    run.run_freeze(str(path), "S1V1W0", frozen, e1b, ["t"])
    p = tmp_path / "power.json"
    p.write_text(json.dumps({"frozen_sha256": "x", "power": {}}), encoding="utf-8")
    with pytest.raises(run.RunError, match="別の凍結物"):
        run.run_primary(str(path), frozen, p, tmp_path / "prim", ["t"])


def test_frozen_file_tampering_is_detected(patched, tmp_path):
    tmp, path, classes, e1b = patched
    frozen = tmp_path / "frozen"
    run.run_freeze(str(path), "S1V1W0", frozen, e1b, ["t"])
    f = frozen / run.FROZEN_FILE
    f.write_text(f.read_text(encoding="utf-8").replace('"w": 0.0', '"w": 0.01'), encoding="utf-8")
    with pytest.raises(run.RunError, match="sha256"):
        run.run_power(str(path), frozen, tmp_path / "p", ["t"])


def _frozen_and_power(path, e1b, tmp_path):
    frozen = tmp_path / "frozen"
    run.run_freeze(str(path), "S1V1W0", frozen, e1b, ["t"])
    run.run_power(str(path), frozen, tmp_path / "power", ["t"])
    return frozen, tmp_path / "power" / run.POWER_FILE


def test_side_record_failure_keeps_the_primary_result(patched, tmp_path, monkeypatch):
    tmp, path, classes, e1b = patched
    frozen, power = _frozen_and_power(path, e1b, tmp_path)
    run.run_arm(str(path), frozen, power, ["t"])

    def boom(*a, **k):
        raise ValueError("年齢の読み込みで落ちた")

    monkeypatch.setattr(run, "_target_ages", boom)
    res = run.run_primary(str(path), frozen, power, tmp_path / "p", ["t"])
    saved = json.loads((tmp_path / "p" / run.PRIMARY_FILE).read_text(encoding="utf-8"))
    side = json.loads((tmp_path / "p" / run.SIDE_FILE).read_text(encoding="utf-8"))
    assert saved["category"] == res["category"] and "ValueError" in side["error"]


def test_power_refuses_a_changed_history(patched, tmp_path):
    tmp, path, classes, e1b = patched
    frozen = tmp_path / "frozen"
    run.run_freeze(str(path), "S1V1W0", frozen, e1b, ["t"])
    con = sqlite3.connect(path)
    con.execute("UPDATE horse_races SET finish_time = finish_time + 1 WHERE race_year = '2023' AND horse_num = '01' "
                "AND race_month_day = (SELECT min(race_month_day) FROM races WHERE race_year = '2023')")
    con.commit()
    con.close()
    try:
        with pytest.raises(run.RunError, match="履歴が凍結の時点と違う"):
            run.run_power(str(path), frozen, tmp_path / "p", ["t"])
    finally:
        con = sqlite3.connect(path)
        con.execute("UPDATE horse_races SET finish_time = finish_time - 1 WHERE race_year = '2023' AND horse_num = '01' "
                    "AND race_month_day = (SELECT min(race_month_day) FROM races WHERE race_year = '2023')")
        con.commit()
        con.close()


def test_json_writes_nan_as_null(tmp_path):
    run._write_json(tmp_path / "x.json", {"a": float("nan"), "b": [1.0, float("inf")]})
    assert json.loads((tmp_path / "x.json").read_text(encoding="utf-8")) == {"a": None, "b": [1.0, None]}


def test_pinned_files_are_all_in_the_provenance_dependencies():
    assert set(run.PINNED_FILES) <= set(g.DEPENDENCIES)


def test_a_crash_after_start_consumes_the_run_and_a_rerun_needs_a_new_arm(patched, tmp_path, monkeypatch):
    tmp, path, classes, e1b = patched
    frozen, power = _frozen_and_power(path, e1b, tmp_path)
    run.run_arm(str(path), frozen, power, ["t"])

    def boom(*a, **k):
        raise RuntimeError("区間の計算の途中で落ちた")

    real_ci = run.es.primary_block_ci
    monkeypatch.setattr(run.es, "primary_block_ci", boom)
    with pytest.raises(RuntimeError):
        run.run_primary(str(path), frozen, power, tmp_path / "p1", ["t"])
    monkeypatch.setattr(run.es, "primary_block_ci", real_ci)
    with pytest.raises(run.RunError, match="既に始まっている"):            # 落ちても開始の印は残る
        run.run_primary(str(path), frozen, power, tmp_path / "p2", ["t"])
    lock = run.run_arm(str(path), frozen, power, ["t"], rerun_reason="区間の計算の例外 (テスト)")
    assert lock["run_index"] == 2 and lock["history"][0]["run_index"] == 1
    res = run.run_primary(str(path), frozen, power, tmp_path / "p3", ["t"])
    assert res["run_index"] == 2 and res["rerun_reason"]


def test_primary_refuses_an_uncommitted_lock(world, tmp_path, monkeypatch):
    """錠が git にコミットされていなければ、2025 の結果を読む前に止まる (本物の判定。一時ディレクトリは repo の外 = 未追跡)。"""
    tmp, path, classes, e1b = world
    monkeypatch.setattr(g, "load_class_table", lambda *a, **k: classes)
    monkeypatch.setattr(run, "BOOT_N", 200)
    real = g.provenance
    monkeypatch.setattr(g, "provenance", lambda *a, **k: {**real(*a, **k), "git_dirty": False, "git_status": []})
    frozen, power = _frozen_and_power(path, e1b, tmp_path)
    run.run_arm(str(path), frozen, power, ["t"])
    with pytest.raises(run.RunError, match="コミットされていない"):
        run.run_primary(str(path), frozen, power, tmp_path / "p", ["t"])
    assert not (frozen / run.STARTED_FILE.format(1)).exists()


def test_arm_refuses_a_dirty_tree_or_changed_pinned_files(patched, tmp_path, monkeypatch):
    tmp, path, classes, e1b = patched
    frozen, power = _frozen_and_power(path, e1b, tmp_path)
    real = g.provenance
    monkeypatch.setattr(g, "provenance", lambda *a, **k: {**real(*a, **k), "git_dirty": True, "git_status": [" M x"]})
    with pytest.raises(run.RunError, match="未コミット"):
        run.run_arm(str(path), frozen, power, ["t"])

    def changed(*a, **k):
        p = real(*a, **k)
        return {**p, "git_dirty": False, "git_status": [],
                "files_sha256": {**p["files_sha256"], "docs/PHASE05_5_PREREG.md": "0" * 64}}

    monkeypatch.setattr(g, "provenance", changed)
    with pytest.raises(run.RunError, match="前提のファイル"):
        run.run_arm(str(path), frozen, power, ["t"])
    assert not (frozen / run.LOCK_FILE).exists()                     # 照合で止まったときは錠を書かない


def test_primary_refuses_pinned_files_changed_after_arm(patched, tmp_path, monkeypatch):
    tmp, path, classes, e1b = patched
    frozen, power = _frozen_and_power(path, e1b, tmp_path)
    run.run_arm(str(path), frozen, power, ["t"])
    lock = json.loads((frozen / run.LOCK_FILE).read_text(encoding="utf-8"))
    run._write_json(frozen / run.LOCK_FILE, {**lock, "pinned": {**lock["pinned"], "config.py": "0" * 64}})
    with pytest.raises(run.RunError, match="錠を書いた時点と違う"):
        run.run_primary(str(path), frozen, power, tmp_path / "p", ["t"])


def test_history_mismatch_stops_the_arm_before_the_lock(patched, tmp_path, monkeypatch):
    """2021-2024 の履歴がずれていたら、錠を書く前に止まる (run_index を消費しない)。"""
    tmp, path, classes, e1b = patched
    frozen, power = _frozen_and_power(path, e1b, tmp_path)
    con = sqlite3.connect(path)
    q = ("UPDATE horse_races SET finish_time = finish_time {} 1 WHERE race_year = '2023' AND horse_num = '01' "
         "AND race_month_day = (SELECT min(race_month_day) FROM races WHERE race_year = '2023')")
    con.execute(q.format("+"))
    con.commit()
    con.close()
    try:
        with pytest.raises(run.RunError, match="履歴が凍結の時点と違う"):
            run.run_arm(str(path), frozen, power, ["t"])
        assert not (frozen / run.LOCK_FILE).exists()
    finally:
        con = sqlite3.connect(path)
        con.execute(q.format("-"))
        con.commit()
        con.close()


def test_lock_is_committed_checks_git(tmp_path, monkeypatch):
    """自分で作った一時の git repo で、コミット済み / 変更あり / 未追跡 / repo の外 を確かめる (環境の repo に依存しない)。"""
    import subprocess
    repo = tmp_path / "repo"
    repo.mkdir()
    def git(*a):
        subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)
    git("init", "-q")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    lock = repo / "PRIMARY_LOCK.json"
    lock.write_text("{}", encoding="utf-8")
    git("add", "PRIMARY_LOCK.json")
    git("commit", "-q", "-m", "lock")
    monkeypatch.setattr(g, "ROOT", repo)
    assert run._lock_is_committed(lock) is True
    lock.write_text('{"x": 1}', encoding="utf-8")                     # コミットの後に書き換えた
    assert run._lock_is_committed(lock) is False
    other = repo / "OTHER.json"
    other.write_text("{}", encoding="utf-8")                          # 未追跡
    assert run._lock_is_committed(other) is False
    assert run._lock_is_committed(tmp_path / "outside.json") is False   # repo の外
