"""Phase 0.5-5 Group C′ の実行 (`scripts/c_prime_run.py`) の契約 (2026-10-06)。

- 検出力の計算は 2025 の対象レースの結果を読まない (allow-list の SQL、返る列の完全一致、行に won なし)
- MDE = 3.4174 × max(解析の SE, 学習期のブートストラップの SE × √(N 比))、MDE > β_target なら判定不能を先に確定
- 錠を git にコミットしてから主検定、同じ run_index で 2 回走らない、固定のファイルは git の blob で照合
"""
from __future__ import annotations

import json
import math
import random
import sqlite3
import subprocess
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import pytest

from predictor import eval_stats as es
from scripts import c_prime as cp
from scripts import c_prime_run as run

ROOT = Path(__file__).resolve().parents[1]


# --- 人工の DB (2021-2025) ------------------------------------------------------------------------------

def _synthetic_db(path: Path, races_per_year: int = 90, seed: int = 0) -> Path:
    rng = random.Random(seed)
    styles = {f"H{i:03d}": rng.choice("1223344") for i in range(260)}
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE races (race_year TEXT, race_month_day TEXT, track_code TEXT, kaiji TEXT, nichiji TEXT, "
                 "race_num TEXT, track_type_code TEXT, data_div TEXT)")
    conn.execute("CREATE TABLE horse_races (race_year TEXT, race_month_day TEXT, track_code TEXT, kaiji TEXT, nichiji TEXT, "
                 "race_num TEXT, horse_num TEXT, blood_register_num TEXT, abnormal_code TEXT, confirmed_order TEXT, "
                 "win_odds INTEGER, leg_quality_code TEXT)")
    for year in range(2021, 2026):
        for i in range(races_per_year):
            d = date(year, 1, 5) + timedelta(days=(i * 360) // races_per_year)
            key = (str(year), d.strftime("%m%d"), "05", "01", "01", f"{(i % 12) + 1:02d}")
            conn.execute("INSERT INTO races VALUES (?,?,?,?,?,?,?,?)", (*key, "23", "7"))
            horses = rng.sample(sorted(styles), 10)
            raw = [rng.random() + 0.15 for _ in horses]
            tot = sum(raw)
            p = [x / tot for x in raw]
            n1 = sum(styles[h] == "1" for h in horses)
            n2 = sum(styles[h] == "2" for h in horses)
            pace = (n1 + 0.5 * n2) / 10
            fit = [(-pace if styles[h] in "12" else pace) for h in horses]
            w = [q * math.exp(3.0 * f) for q, f in zip(p, fit)]
            u, acc, win = rng.random() * sum(w), 0.0, 9
            for j, x in enumerate(w):
                acc += x
                if u <= acc:
                    win = j
                    break
            for j, h in enumerate(horses):
                odds = round(0.8 / p[j], 1)
                conn.execute("INSERT INTO horse_races VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                             (*key, f"{j + 1:02d}", h, "0", "1" if j == win else str(j + 2), int(round(odds * 10)), styles[h]))
    conn.commit()
    conn.close()
    return path


@pytest.fixture(scope="module")
def synth_db(tmp_path_factory):
    return _synthetic_db(tmp_path_factory.mktemp("cpdb") / "k.db")


# --- 結果を読まない読み込み -------------------------------------------------------------------------------

def test_target_sql_has_no_result_columns_and_returns_exactly_the_allow_list(synth_db):
    sql = run.target_sql().lower()
    assert not [c for c in run.FORBIDDEN_COLUMNS if c in sql] and "*" not in sql
    targets = run.load_target_fields(2025, synth_db)
    first = next(iter(targets.values()))[0]
    assert set(first) == {"race_id", "ymd", "horse", "horse_num", "refunded", "win_odds"}


def test_a_result_column_in_the_allow_list_stops(monkeypatch):
    monkeypatch.setattr(run, "TARGET_SELECT", run.TARGET_SELECT + (("h.confirmed_order", "confirmed_order"),))
    with pytest.raises(run.RunError, match="結果の列"):
        run.target_sql()


def test_returned_columns_must_match_the_allow_list(monkeypatch, synth_db):
    monkeypatch.setattr(run, "TARGET_COLUMNS", run.TARGET_COLUMNS[:-1] + ("odds",))
    with pytest.raises(run.RunError, match="allow-list"):
        run.load_target_fields(2025, synth_db)


def test_refund_flag_comes_from_db_codes():
    from db import REFUNDED_ABNORMAL_CODES
    expr = dict((alias, e) for e, alias in run.TARGET_SELECT)["is_refunded"]
    assert all(f"'{c}'" in expr for c in REFUNDED_ABNORMAL_CODES) and "'4'" not in expr


def test_outcome_blind_rows_have_no_won_and_follow_the_choice_set():
    targets = {"20250601_05_01_01_01": [
        {"race_id": "20250601_05_01_01_01", "ymd": "20250601", "horse": "A", "horse_num": "01", "refunded": False, "win_odds": 2.0},
        {"race_id": "20250601_05_01_01_01", "ymd": "20250601", "horse": "B", "horse_num": "02", "refunded": True, "win_odds": 0.0},
        {"race_id": "20250601_05_01_01_01", "ymd": "20250601", "horse": "C", "horse_num": "03", "refunded": False, "win_odds": 4.0}],
        "20250602_05_01_01_01": [
        {"race_id": "20250602_05_01_01_01", "ymd": "20250602", "horse": "A", "horse_num": "01", "refunded": False, "win_odds": 2.0},
        {"race_id": "20250602_05_01_01_01", "ymd": "20250602", "horse": "C", "horse_num": "03", "refunded": False, "win_odds": 0.0}]}
    c, ex = Counter(), []
    rows = run.outcome_blind_rows(targets, {}, {}, c, ex)
    assert [r["horse_num"] for r in rows] == ["01", "03"] and all("won" not in r for r in rows)
    assert rows[0]["p_market"] == pytest.approx(2 / 3)
    assert ex == [{"race_id": "20250602_05_01_01_01", "reason": "nonrefund_runner_without_price:final", "horses": ["03"]}]
    assert c["refunded_runners"] == 1


# --- 検出力・判定 -----------------------------------------------------------------------------------------

def test_fixed_power_takes_the_larger_se_and_flags_inconclusive():
    f = run.fixed_power(0.02, 0.03, 10000, 2500)               # 換算 0.06 > 解析 0.02
    assert f["se_fixed"] == pytest.approx(0.06) and f["mde"] == pytest.approx(run.CRITICAL_MULTIPLIER * 0.06)
    assert f["inconclusive_by_power"] is True                  # 0.205 > 0.1116
    g = run.fixed_power(0.025, 0.01, 10000, 2500)
    assert g["se_fixed"] == pytest.approx(0.025) and g["inconclusive_by_power"] is False
    h = run.fixed_power(0.02, None, 10000, 2500)
    assert h["se_fixed"] == 0.02 and h["se_train_scaled"] is None
    assert run.BETA_TARGET == pytest.approx(math.log(1.25) / 2)


@pytest.mark.parametrize("ci,inc,want", [
    ({"valid": True, "lo": 0.01}, True, ("PRIMARY_INCONCLUSIVE", "mde_above_beta_target")),
    ({"valid": False, "lo": math.nan}, True, ("PRIMARY_INCONCLUSIVE", "mde_above_beta_target+boot_na")),
    ({"valid": False, "lo": math.nan}, False, ("PRIMARY_INCONCLUSIVE", "boot_na")),
    ({"valid": True, "lo": 0.001}, False, ("PRIMARY_PASS", "ci_lower_above_zero")),
    ({"valid": True, "lo": 0.0}, False, ("PRIMARY_FAIL", "ci_lower_not_above_zero")),
])
def test_verdict_rules(ci, inc, want):
    assert run.verdict(ci, {"inconclusive_by_power": inc}) == want


def test_history_digest_sees_leg_code_changes(synth_db, tmp_path):
    races, _ = cp.load_races(2024, db_path=synth_db)
    d1 = run.history_digest(races, (2021, 2022))
    next(iter(races.values())).runs[0].leg = "9"
    assert run.history_digest(races, (2021, 2022)) != d1


def test_lock_is_committed_uses_git(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    monkeypatch.setattr(cp, "ROOT", repo)
    lock = repo / "PRIMARY_LOCK.json"
    lock.write_text("{}", encoding="utf-8")
    assert run._lock_is_committed(lock) is False
    subprocess.run(["git", "-C", str(repo), "add", "PRIMARY_LOCK.json"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "lock"], check=True)
    assert run._lock_is_committed(lock) is True
    lock.write_text('{"x": 1}', encoding="utf-8")
    assert run._lock_is_committed(lock) is False
    assert run._lock_is_committed(tmp_path / "outside.json") is False


def test_check_pinned_refuses_dirty_trees_and_changed_blobs(monkeypatch):
    base = {f: "a" for f in run.PINNED_FILES}
    man = {"provenance": {"db": {"path": "x"}, "files_blob_sha1": dict(base)}}
    power = {"provenance": {"files_blob_sha1": dict(base)}}
    monkeypatch.setattr(cp, "provenance", lambda *a, **k: {"git_dirty": True, "git_status": [" M x"], "git_sha": "s",
                                                           "files_blob_sha1": dict(base)})
    with pytest.raises(run.RunError, match="未コミット"):
        run._check_pinned(man, power)
    changed = {**base, "scripts/c_prime.py": "b"}
    monkeypatch.setattr(cp, "provenance", lambda *a, **k: {"git_dirty": False, "git_status": [], "git_sha": "s",
                                                           "files_blob_sha1": changed})
    with pytest.raises(run.RunError, match="凍結・検出力の時点と違う"):
        run._check_pinned(man, power)
    monkeypatch.setattr(cp, "provenance", lambda *a, **k: {"git_dirty": False, "git_status": [], "git_sha": "s",
                                                           "files_blob_sha1": dict(base)})
    assert run._check_pinned(man, power)["pinned_blob_sha1"] == base


# --- 端から端まで (人工の DB) --------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def frozen_and_power(synth_db, tmp_path_factory):
    out = tmp_path_factory.mktemp("cprun")
    mp = pytest.MonkeyPatch()
    mp.setattr(run, "BOOT_N", 120)
    try:
        man = run.run_freeze(str(synth_db), out / "frozen", ["t"])
        pw = run.run_power(str(synth_db), out / "frozen", out / "power", ["t"])
    finally:
        mp.undo()
    return out, man, pw


def test_freeze_records_the_composite_and_bootstrap(frozen_and_power):
    out, man, _ = frozen_and_power
    assert man["est_years"] == [2022, 2023, 2024] and man["bootstrap"]["n_boot"] == 120
    payload = json.loads((out / "frozen" / run.FROZEN_FILE).read_text(encoding="utf-8"))
    assert payload["composite"]["weights"]["style_x_pace_fit"] > 0
    assert man["history_digest"]["years"] == [2021, 2022, 2023, 2024]
    assert set(man["provenance"]["files_blob_sha1"]) >= set(run.PINNED_FILES)


def test_power_reads_no_outcomes_and_counts_with_the_normalised_ratio(frozen_and_power):
    _, man, pw = frozen_and_power
    assert pw["frozen_sha256"] == man["frozen_sha256"]
    assert pw["fisher"]["assumption"].startswith("beta_market=1")
    assert pw["purchase_projection"]["counting"].endswith("ratio_buys_at(rows, 1.0, beta_target)")
    assert pw["power"]["mde"] == pytest.approx(run.CRITICAL_MULTIPLIER * pw["power"]["se_fixed"])


def test_frozen_tampering_is_detected(frozen_and_power, tmp_path):
    out, _, _ = frozen_and_power
    import shutil
    bad = tmp_path / "frozen"
    shutil.copytree(out / "frozen", bad)
    p = bad / run.FROZEN_FILE
    p.write_text(p.read_text(encoding="utf-8").replace('"history_runs": 5', '"history_runs": 6'), encoding="utf-8")
    with pytest.raises(run.RunError, match="sha256"):
        run._load_frozen(bad)


def test_arm_then_primary_runs_once(frozen_and_power, synth_db, tmp_path, monkeypatch):
    out, man, pw = frozen_and_power
    import shutil
    frozen = tmp_path / "frozen"
    shutil.copytree(out / "frozen", frozen)
    power_path = out / "power" / run.POWER_FILE
    pinned = {"git_sha": "s", "pinned_blob_sha1": {f: "x" for f in run.PINNED_FILES}}
    monkeypatch.setattr(run, "_check_pinned", lambda m, p: pinned)
    with pytest.raises(run.RunError, match="錠が無い"):
        run.run_primary(str(synth_db), frozen, power_path, tmp_path / "p0", ["t"])
    lock = run.run_arm(str(synth_db), frozen, power_path, ["t"])
    assert lock["run_index"] == 1
    with pytest.raises(run.RunError, match="既にある"):
        run.run_arm(str(synth_db), frozen, power_path, ["t"])
    monkeypatch.setattr(run, "_lock_is_committed", lambda p: False)
    with pytest.raises(run.RunError, match="コミットされていない"):
        run.run_primary(str(synth_db), frozen, power_path, tmp_path / "p1", ["t"])
    monkeypatch.setattr(run, "_lock_is_committed", lambda p: True)
    monkeypatch.setattr(es, "PRIMARY_N_BOOT", 150)
    res = run.run_primary(str(synth_db), frozen, power_path, tmp_path / "p2", ["t"])
    assert res["run_index"] == 1 and res["ci_99"]["n_boot"] == 150
    assert res["category"].startswith("PRIMARY_")
    assert (frozen / run.STARTED_FILE.format(1)).exists()
    side = json.loads((tmp_path / "p2" / run.SIDE_FILE).read_text(encoding="utf-8"))
    assert "error" not in side and "diagnostic_sets_final_market_2025" in side
    with pytest.raises(run.RunError, match="既に始まっている"):
        run.run_primary(str(synth_db), frozen, power_path, tmp_path / "p3", ["t"])
    lock2 = run.run_arm(str(synth_db), frozen, power_path, ["t"], rerun_reason="テスト: 欠陥を特定した場合")
    assert lock2["run_index"] == 2 and lock2["history"][0]["run_index"] == 1


def test_primary_refuses_a_lock_for_another_power(frozen_and_power, synth_db, tmp_path, monkeypatch):
    out, _, _ = frozen_and_power
    import shutil
    frozen = tmp_path / "frozen"
    shutil.copytree(out / "frozen", frozen)
    monkeypatch.setattr(run, "_check_pinned", lambda m, p: {"git_sha": "s", "pinned_blob_sha1": {}})
    power_path = out / "power" / run.POWER_FILE
    run.run_arm(str(synth_db), frozen, power_path, ["t"])
    lk = json.loads((frozen / run.LOCK_FILE).read_text(encoding="utf-8"))
    lk["power_sha256"] = "0" * 64
    (frozen / run.LOCK_FILE).write_text(json.dumps(lk), encoding="utf-8")
    monkeypatch.setattr(run, "_lock_is_committed", lambda p: True)
    with pytest.raises(run.RunError, match="別の凍結物・検出力"):
        run.run_primary(str(synth_db), frozen, power_path, tmp_path / "p", ["t"])


def test_c_prime_run_does_not_use_group_a_market_code():
    src = (ROOT / "scripts" / "c_prime_run.py").read_text(encoding="utf-8")
    for bad in ("group_a_power", "from scripts import group_a\n", "import group_a\n", "logit_p_market", "add_market_logit",
                "math.log(", "np.log("):
        assert bad not in src, bad


def test_power_counts_purchases_through_ratio_buys_at(frozen_and_power, synth_db, tmp_path, monkeypatch):
    out, _, _ = frozen_and_power
    from predictor import market_clogit as mc
    seen = {}

    def fake(rows, bm, bs, *a, **k):
        seen["args"] = (bm, bs)
        return [("r", "01")] * 7
    monkeypatch.setattr(mc, "ratio_buys_at", fake)
    pw = run.run_power(str(synth_db), out / "frozen", tmp_path / "pw", ["t"])
    assert pw["purchase_projection"]["n_horses"] == 7 and seen["args"] == (1.0, run.BETA_TARGET)


def test_power_refuses_a_changed_history(frozen_and_power, synth_db, tmp_path):
    out, _, _ = frozen_and_power
    import shutil
    frozen = tmp_path / "frozen"
    shutil.copytree(out / "frozen", frozen)
    m = json.loads((frozen / run.MANIFEST_FILE).read_text(encoding="utf-8"))
    m["history_digest"]["sha256"] = "0" * 64
    (frozen / run.MANIFEST_FILE).write_text(json.dumps(m), encoding="utf-8")
    with pytest.raises(run.RunError, match="履歴"):
        run.run_power(str(synth_db), frozen, tmp_path / "pw", ["t"])


def test_frozen_constants_must_match_the_code(frozen_and_power, tmp_path):
    out, _, _ = frozen_and_power
    import hashlib
    import shutil
    frozen = tmp_path / "frozen"
    shutil.copytree(out / "frozen", frozen)
    p = frozen / run.FROZEN_FILE
    payload = json.loads(p.read_text(encoding="utf-8"))
    payload["constants"]["window_days"] = 366
    p.write_text(json.dumps(payload), encoding="utf-8")
    m = json.loads((frozen / run.MANIFEST_FILE).read_text(encoding="utf-8"))
    m["frozen_sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
    (frozen / run.MANIFEST_FILE).write_text(json.dumps(m), encoding="utf-8")
    with pytest.raises(run.RunError, match="定数"):
        run._load_frozen(frozen)


def test_power_from_another_frozen_is_refused(frozen_and_power, tmp_path):
    out, _, _ = frozen_and_power
    pw = json.loads((out / "power" / run.POWER_FILE).read_text(encoding="utf-8"))
    pw["frozen_sha256"] = "0" * 64
    other = tmp_path / "power.json"
    other.write_text(json.dumps(pw), encoding="utf-8")
    with pytest.raises(run.RunError, match="別の凍結物から"):
        run._frozen_and_power(out / "frozen", other)


def test_bootstrap_draws_follow_the_fixed_count(frozen_and_power):
    _, man, _ = frozen_and_power
    b = man["bootstrap"]
    assert b["n_valid"] + b["n_discarded"] == b["n_boot"] == 120


def test_primary_refuses_pinned_files_changed_after_arming(frozen_and_power, synth_db, tmp_path, monkeypatch):
    out, _, _ = frozen_and_power
    import shutil
    frozen = tmp_path / "frozen"
    shutil.copytree(out / "frozen", frozen)
    power_path = out / "power" / run.POWER_FILE
    monkeypatch.setattr(run, "_check_pinned", lambda m, p: {"git_sha": "s", "pinned_blob_sha1": {"a": "1"}})
    run.run_arm(str(synth_db), frozen, power_path, ["t"])
    monkeypatch.setattr(run, "_check_pinned", lambda m, p: {"git_sha": "s", "pinned_blob_sha1": {"a": "2"}})
    monkeypatch.setattr(run, "_lock_is_committed", lambda p: True)
    with pytest.raises(run.RunError, match="錠を書いた時点と違う"):
        run.run_primary(str(synth_db), frozen, power_path, tmp_path / "p", ["t"])
    assert not (frozen / run.STARTED_FILE.format(1)).exists()
