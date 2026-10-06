"""Phase 0.5-5 Group D の実行 (`scripts/group_d_run.py`) の契約 (2026-10-06)。

- 検出力は 2025 の対象レースの結果を読まない (allow-list の SQL、行に won なし)。2025 の着順をすべて書き換えても対象の行は変わらない
- 3 列 (市場・class_move・S) の情報行列からの S のシューア補元
- 錠のコミット、開始の印、run_index、履歴の照合は開始の印の前
"""
from __future__ import annotations

import json
import math
import shutil
import sqlite3
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from predictor import eval_stats as es
from scripts import group_a as ga
from scripts import group_d as gd
from scripts import group_d_run as run
from scripts import prereg_runner as pr

ROOT = Path(__file__).resolve().parents[1]
CLASSES = ("703", "005", "010", "016")


def _synthetic_db(tmp_path, seed=0):
    """2021-2025、東京 芝 1600 とダ 1600 で週 2 日 × 4 レース。クラスを回す。馬の能力から時計と市場を作る。"""
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
    k = 0
    while day.year <= 2025:
        for rn in range(1, 5):
            ymd = day.strftime("%Y%m%d")
            rid = f"{ymd}_05_01_01_{rn:02d}"
            cls = CLASSES[k % len(CLASSES)]
            surf = "11" if rn % 2 else "24"
            k += 1
            classes[rid] = (cls, "3up")
            con.execute("INSERT INTO races VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (ymd[:4], ymd[4:], "05", "01", "01", f"{rn:02d}", "7", surf, 1600, "1", "1", "3"))
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
    tmp = tmp_path_factory.mktemp("gd_run")
    path, classes = _synthetic_db(tmp)
    mp = pytest.MonkeyPatch()
    mp.setattr(ga, "load_class_table", lambda *a, **k: classes)
    mp.setattr(run, "BOOT_N", 120)
    real = pr.provenance
    mp.setattr(pr, "provenance", lambda *a, **k: {**real(*a, **k), "git_dirty": False, "git_status": []})
    try:
        man = run.run_freeze(str(path), tmp / "frozen", ["t"])
        pw = run.run_power(str(path), tmp / "frozen", tmp / "power", ["t"])
    finally:
        mp.undo()
    return tmp, path, classes, man, pw


@pytest.fixture
def patched(world, monkeypatch):
    tmp, path, classes, man, pw = world
    monkeypatch.setattr(ga, "load_class_table", lambda *a, **k: classes)
    monkeypatch.setattr(run, "_check_pinned", lambda m, p: {"git_sha": "s", "pinned_blob_sha1": {}})
    monkeypatch.setattr(pr, "lock_is_committed", lambda root, p: True)
    monkeypatch.setattr(es, "PRIMARY_N_BOOT", 120)
    return world


def _copy_frozen(world, tmp_path):
    frozen = tmp_path / "frozen"
    shutil.copytree(world[0] / "frozen", frozen)
    return frozen


def test_freeze_records_scale_tables_and_bootstrap(world):
    tmp, _, _, man, _ = world
    assert man["est_years"] == [2022, 2023, 2024] and man["bootstrap"]["n_valid"] + man["bootstrap"]["n_discarded"] == 120
    payload = json.loads((tmp / "frozen" / run.FROZEN_FILE).read_text(encoding="utf-8"))
    assert payload["S_scale"]["sd"] > 0 and payload["constants"]["spec"] == "S1V1W0"
    assert payload["rating_tables"]["est_years"] == [2022, 2023, 2024]
    assert set(run.PINNED_FILES) <= set(man["provenance"]["files_blob_sha1"])


def test_power_is_decidable_or_not_with_the_mde_rule(world):
    _, _, _, man, pw = world
    assert pw["power"]["mde"] == pytest.approx(pr.CRITICAL_MULTIPLIER * pw["power"]["se_fixed"])
    assert pw["fisher"]["assumption"].startswith("beta_market=1, beta_move=0")
    assert pw["frozen_sha256"] == man["frozen_sha256"]


def test_power_output_does_not_depend_on_2025_target_results(world, tmp_path, monkeypatch):
    """2025 の **最後の日** の着順・走破タイムを書き換えても検出力の出力は変わらない (最後の日の結果は、どの対象の行の履歴にも入らない)。"""
    tmp, path, classes, _, pw = world
    monkeypatch.setattr(ga, "load_class_table", lambda *a, **k: classes)
    db2 = tmp_path / "s2.db"
    shutil.copy(path, db2)
    con = sqlite3.connect(db2)
    last = con.execute("SELECT MAX(race_month_day) FROM races WHERE race_year = '2025'").fetchone()[0]
    con.execute("UPDATE horse_races SET confirmed_order = 11 - CAST(confirmed_order AS INTEGER), finish_time = finish_time + 37 "
                "WHERE race_year = '2025' AND race_month_day = ?", (last,))     # 着順と走破タイム (対象レース自身の結果)
    con.commit()
    con.close()
    real = pr.provenance
    monkeypatch.setattr(pr, "provenance", lambda *a, **k: {**real(*a, **k), "git_dirty": False, "git_status": []})
    pw2 = run.run_power(str(db2), tmp / "frozen", tmp_path / "pw", ["t"])
    for k in ("fisher", "power", "purchase_projection", "target_counts", "exclusions", "S_variance_decomposition_2025", "n_rows"):
        assert pw2[k] == pw[k], k


def test_target_sql_has_no_result_columns(world):
    sql = run.target_sql().lower()
    assert not [c for c in run.FORBIDDEN_COLUMNS if c in sql]
    with pytest.raises(pr.RunError):
        old = run.TARGET_SELECT
        run.TARGET_SELECT = old + (("h.confirmed_order", "confirmed_order"),)
        try:
            run.target_sql()
        finally:
            run.TARGET_SELECT = old


def test_fisher_matches_a_hand_schur_complement():
    rows = []
    rng = np.random.default_rng(3)
    for i in range(30):
        raw = rng.random(6) + 0.2
        p = raw / raw.sum()
        for j in range(6):
            rows.append({"race_id": f"R{i}", "horse_num": f"{j + 1:02d}", "p_market": float(p[j]),
                         "class_move_filled": float(rng.integers(-1, 2)), "S_std": float(rng.normal())})
    got = run.fisher_se_at_null(rows)
    info = np.zeros((3, 3))
    for i in range(30):
        rs = [r for r in rows if r["race_id"] == f"R{i}"]
        p = np.array([r["p_market"] for r in rs])
        X = np.array([[math.log(r["p_market"]), r["class_move_filled"], r["S_std"]] for r in rs])
        m = p @ X
        info += (X * p[:, None]).T @ X - np.outer(m, m)
    assert np.allclose(got["info"], info) and got["se"] == pytest.approx(math.sqrt(np.linalg.inv(info)[2, 2]))
    with pytest.raises(pr.RunError, match="勝ちの列"):
        run.fisher_se_at_null([{**rows[0], "won": 1}])


def test_arm_then_primary_runs_once(patched, tmp_path):
    frozen = _copy_frozen(patched, tmp_path)
    tmp, path = patched[0], patched[1]
    power_path = tmp / "power" / run.POWER_FILE
    with pytest.raises(pr.RunError, match="錠が無い"):
        run.run_primary(str(path), frozen, power_path, tmp_path / "p0", ["t"])
    lock = run.run_arm(str(path), frozen, power_path, ["t"])
    assert lock["run_index"] == 1
    with pytest.raises(pr.RunError, match="既にある"):
        run.run_arm(str(path), frozen, power_path, ["t"])
    res = run.run_primary(str(path), frozen, power_path, tmp_path / "p", ["t"])
    assert res["category"].startswith("PRIMARY_") and res["ci_99"]["n_boot"] == 120
    assert set(res["beta"]) == {"market", "class_move", "S", "converged"}
    side = json.loads((tmp_path / "p" / run.SIDE_FILE).read_text(encoding="utf-8"))
    assert "error" not in side and "gap_to_current_class_equivalence" in side
    with pytest.raises(pr.RunError, match="既に始まっている"):
        run.run_primary(str(path), frozen, power_path, tmp_path / "p2", ["t"])


def test_primary_refuses_a_changed_2025_history_before_the_marker(patched, tmp_path, monkeypatch):
    frozen = _copy_frozen(patched, tmp_path)
    tmp, path = patched[0], patched[1]
    power_path = tmp / "power" / run.POWER_FILE
    run.run_arm(str(path), frozen, power_path, ["t"])
    real = run.primary_year_history_digest
    monkeypatch.setattr(run, "primary_year_history_digest", lambda r, y: {**real(r, y), "sha256": "f" * 64})
    with pytest.raises(pr.RunError, match="2025 の履歴"):
        run.run_primary(str(path), frozen, power_path, tmp_path / "p", ["t"])
    assert not (frozen / run.STARTED_FILE.format(1)).exists()


def test_freeze_refuses_to_overwrite(patched):
    tmp, path = patched[0], patched[1]
    with pytest.raises(pr.RunError, match="上書きしない"):
        run.run_freeze(str(path), tmp / "frozen", ["t"])


def test_power_from_another_frozen_is_refused(patched, tmp_path):
    tmp = patched[0]
    pw = json.loads((tmp / "power" / run.POWER_FILE).read_text(encoding="utf-8"))
    pw["frozen_sha256"] = "0" * 64
    other = tmp_path / "power.json"
    other.write_text(json.dumps(pw), encoding="utf-8")
    with pytest.raises(pr.RunError, match="別の凍結物"):
        run._frozen_and_power(tmp / "frozen", other)


def test_side_record_failure_keeps_the_verdict(patched, tmp_path, monkeypatch):
    frozen = _copy_frozen(patched, tmp_path)
    tmp, path = patched[0], patched[1]
    power_path = tmp / "power" / run.POWER_FILE
    run.run_arm(str(path), frozen, power_path, ["t"])

    def boom(*a):
        assert (tmp_path / "p" / run.PRIMARY_FILE).exists()
        raise ValueError("side failed")
    monkeypatch.setattr(run, "_side_records", boom)
    res = run.run_primary(str(path), frozen, power_path, tmp_path / "p", ["t"])
    side = json.loads((tmp_path / "p" / run.SIDE_FILE).read_text(encoding="utf-8"))
    assert side["error"] == "ValueError: side failed" and res["category"].startswith("PRIMARY_")


def test_group_d_run_does_not_use_group_a_market_code():
    src = (ROOT / "scripts" / "group_d_run.py").read_text(encoding="utf-8")
    for bad in ("group_a_power", "logit_p_market", "add_market_logit", "math.log(", "np.log(", "fit_composite(", "apply_composite("):
        assert bad not in src, bad


def test_power_refuses_a_changed_2021_2024_history(patched, tmp_path):
    frozen = _copy_frozen(patched, tmp_path)
    m = json.loads((frozen / run.MANIFEST_FILE).read_text(encoding="utf-8"))
    m["history_digest"]["sha256"] = "0" * 64
    (frozen / run.MANIFEST_FILE).write_text(json.dumps(m), encoding="utf-8")
    with pytest.raises(pr.RunError, match="履歴"):
        run.run_power(str(patched[1]), frozen, tmp_path / "pw", ["t"])


def test_arm_refuses_a_changed_2025_history(patched, tmp_path, monkeypatch):
    frozen = _copy_frozen(patched, tmp_path)
    tmp, path = patched[0], patched[1]
    real = run.primary_year_history_digest
    monkeypatch.setattr(run, "primary_year_history_digest", lambda r, y: {**real(r, y), "sha256": "e" * 64})
    with pytest.raises(pr.RunError, match="2025 の履歴"):
        run.run_arm(str(path), frozen, tmp / "power" / run.POWER_FILE, ["t"])
    assert not (frozen / run.LOCK_FILE).exists()


def test_primary_refuses_to_overwrite_an_existing_result(patched, tmp_path):
    frozen = _copy_frozen(patched, tmp_path)
    tmp, path = patched[0], patched[1]
    power_path = tmp / "power" / run.POWER_FILE
    run.run_arm(str(path), frozen, power_path, ["t"])
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / run.PRIMARY_FILE).write_text("{}", encoding="utf-8")
    with pytest.raises(pr.RunError, match="上書きしない"):
        run.run_primary(str(path), frozen, power_path, tmp_path / "p", ["t"])
    assert not (frozen / run.STARTED_FILE.format(1)).exists()

