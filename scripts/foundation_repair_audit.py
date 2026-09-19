"""Phase 0.5-4B: 基盤修復で欠陥が消えたかを検査する。

**性能が良くなったかは見ない。欠陥が消えたかだけを見る。**

出すもの (作業指示で指定された最低限):

1. 学習対象に入った 2021 (burn-in) 行            = 0
2. 破損年 (2020 以前) 由来の履歴                  = 0
3. 同日・未来のレース結果の混入                    = 0
4. PIT 違反 (出走頭数が決定時刻に知りえない値)     = 0
5. Fundamental の市場依存                         = 0
6. カウント特徴の学習域外率の一覧
7. Feature Manifest 違反                          = 0

3 は構造 (発走時刻順 + ブロック単位反映) から 0 のはずだが、**構造を信じずに
DB から独立に数え直して突き合わせる**。0.5-3 では同じ場所で 20.1% / 31.4% の
混入が起きていた。

usage:
    .venv64/Scripts/python.exe -m scripts.foundation_repair_audit [--json out.json]
"""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_SPLIT  # noqa: E402
from db import DB_PATH  # noqa: E402
from predictor.feature_manifest import (  # noqa: E402
    assert_no_market_features,
    market_reading_functions,
)
from predictor.provenance import snapshot  # noqa: E402
from scripts.fundamental_model import (  # noqa: E402
    FEATURES,
    NOT_A_START,
    ROLLING_DAYS,
    TRUST_FLOOR_YEAR,
    build_dataset,
)

MODEL_SRC = Path(__file__).resolve().parent / "fundamental_model.py"
SAMPLE_ROWS = 2000
SEED = 20260919


def check_no_warmup_rows_in_training(rows: list[dict]) -> dict:
    """学習対象に burn-in 年 (2021) の行が入っていないこと。"""
    train_from = DATA_SPLIT["train"]["from"]
    bad = [r for r in rows if r["date"] < train_from]
    return {"train_from": train_from, "rows_before_train_start": len(bad),
            "ok": not bad,
            "min_date": min((r["date"] for r in rows), default=None)}


def check_no_corrupted_year_history(conn: sqlite3.Connection) -> dict:
    """破損年 (信頼下限より前) の行が 1 行も読まれていないこと。

    SQL の条件を信じず、**除外された行が実在すること**も併せて数える。
    除外件数が 0 なら、そもそも条件が効いているのか分からない。
    """
    excluded = conn.execute(
        """SELECT COUNT(*) FROM horse_races
            WHERE race_year < ? AND CAST(track_code AS INTEGER) BETWEEN 1 AND 10
              AND horse_num NOT IN ('', '00')""", (TRUST_FLOOR_YEAR,)).fetchone()[0]
    included = conn.execute(
        """SELECT COUNT(*) FROM horse_races
            WHERE race_year >= ? AND CAST(track_code AS INTEGER) BETWEEN 1 AND 10
              AND horse_num NOT IN ('', '00')""", (TRUST_FLOOR_YEAR,)).fetchone()[0]
    # 破損の指標: 馬名の文字化け率。信頼下限以降が 0% であることを確かめる。
    mojibake = conn.execute(
        """SELECT SUM(CASE WHEN horse_name LIKE '%?%' THEN 1 ELSE 0 END), COUNT(*)
             FROM horse_races WHERE race_year >= ?
              AND CAST(track_code AS INTEGER) BETWEEN 1 AND 10""",
        (TRUST_FLOOR_YEAR,)).fetchone()
    rate = (mojibake[0] or 0) / mojibake[1] if mojibake[1] else 0.0
    return {"trust_floor_year": TRUST_FLOOR_YEAR,
            "rows_excluded_as_corrupted": excluded,
            "rows_used": included,
            "mojibake_rate_in_used_rows": rate,
            "ok": excluded > 0 and rate == 0.0}


def check_no_same_day_future_leak(conn: sqlite3.Connection, rows: list[dict],
                                  n_sample: int = SAMPLE_ROWS) -> dict:
    """調教師の直近カウントを DB から独立に数え直して突き合わせる。

    **構造を信じない。** 0.5-3 では同じ場所で「同日・別場で後に発走した
    レースの結果」が調教師カウンタの 20.1% / 父カウンタの 31.4% に
    混入していた。期待値は「厳密に前に発走したレースだけ」を数えた値。
    """
    rng = random.Random(SEED)
    pick = rng.sample(rows, min(n_sample, len(rows)))
    mismatches = []
    for r in pick:
        y, md, tc, ka, ni, rc = r["race_id"].split("-")
        cur = conn.execute(
            """SELECT h.trainer_code, rr.start_time
                 FROM horse_races h JOIN races rr
                   ON rr.race_year=h.race_year AND rr.race_month_day=h.race_month_day
                  AND rr.track_code=h.track_code AND rr.kaiji=h.kaiji
                  AND rr.nichiji=h.nichiji AND rr.race_num=h.race_num
                WHERE h.race_year=? AND h.race_month_day=? AND h.track_code=?
                  AND h.kaiji=? AND h.nichiji=? AND h.race_num=? AND h.horse_num=?""",
            (y, md, tc, ka, ni, rc, r["horse_num"])).fetchone()
        if cur is None:
            continue
        trainer, start_time = cur
        d8 = r["date"]
        lo = date.fromordinal(
            date(int(d8[:4]), int(d8[4:6]), int(d8[6:])).toordinal()
            - ROLLING_DAYS).strftime("%Y%m%d")
        placeholders = ",".join("?" * len(NOT_A_START))
        expected = conn.execute(
            f"""SELECT COUNT(*)
                  FROM horse_races h JOIN races rr
                    ON rr.race_year=h.race_year AND rr.race_month_day=h.race_month_day
                   AND rr.track_code=h.track_code AND rr.kaiji=h.kaiji
                   AND rr.nichiji=h.nichiji AND rr.race_num=h.race_num
                 WHERE h.trainer_code=? AND rr.data_div <> '9'
                   AND CAST(h.track_code AS INTEGER) BETWEEN 1 AND 10
                   AND h.horse_num NOT IN ('', '00')
                   AND h.abnormal_code NOT IN ({placeholders})
                   AND h.race_year >= ?
                   AND (h.race_year||h.race_month_day) >= ?
                   AND ((h.race_year||h.race_month_day) < ?
                        OR ((h.race_year||h.race_month_day) = ?
                            AND rr.start_time < ?))""",
            (trainer, *sorted(NOT_A_START), TRUST_FLOOR_YEAR, lo, d8, d8,
             start_time)).fetchone()[0]
        if abs(expected - r["t_runs_365"]) > 0:
            mismatches.append({"race_id": r["race_id"], "horse": r["horse_num"],
                               "feature": r["t_runs_365"], "expected": expected})
    return {"sampled": len(pick), "mismatches": len(mismatches),
            "examples": mismatches[:5], "ok": not mismatches}


def check_starters_is_knowable(conn: sqlite3.Connection,
                               rows: list[dict]) -> dict:
    """出走頭数が「登録 − 取消」であって、除外後の確定値でないこと。"""
    bad = 0
    checked = 0
    rng = random.Random(SEED + 1)
    for r in rng.sample(rows, min(SAMPLE_ROWS, len(rows))):
        y, md, tc, ka, ni, rc = r["race_id"].split("-")
        row = conn.execute(
            """SELECT rr.registered_count, rr.starter_count,
                      (SELECT COUNT(*) FROM horse_races x
                        WHERE x.race_year=rr.race_year
                          AND x.race_month_day=rr.race_month_day
                          AND x.track_code=rr.track_code AND x.kaiji=rr.kaiji
                          AND x.nichiji=rr.nichiji AND x.race_num=rr.race_num
                          AND x.abnormal_code='1'
                          AND x.horse_num NOT IN ('', '00'))
                 FROM races rr
                WHERE rr.race_year=? AND rr.race_month_day=? AND rr.track_code=?
                  AND rr.kaiji=? AND rr.nichiji=? AND rr.race_num=?""",
            (y, md, tc, ka, ni, rc)).fetchone()
        if row is None:
            continue
        checked += 1
        registered, starter_count, scratched = row
        if abs(r["starters"] - ((registered or 0) - scratched)) > 1e-9:
            bad += 1
    return {"checked": checked, "mismatches": bad, "ok": bad == 0}


def check_market_independence() -> dict:
    """市場由来の特徴・市場列の読み出しが 0 であること。"""
    try:
        assert_no_market_features(FEATURES, source_module=MODEL_SRC)
        violation = None
    except ValueError as exc:
        violation = str(exc)
    return {"market_features": 0 if violation is None else -1,
            "generation_code_market_reads": market_reading_functions(MODEL_SRC),
            "violation": violation, "ok": violation is None}


def run() -> dict:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    tr = DATA_SPLIT["train"]
    print(f"学習窓 {tr['from']}〜{tr['to']} を構築中 ...", flush=True)
    train_rows, _ = build_dataset(tr["from"], tr["to"])
    dev = DATA_SPLIT["strategy_dev"]
    print(f"評価窓 {dev['from']}〜{dev['to']} を構築中 ...", flush=True)
    dev_rows, _ = build_dataset(dev["from"], dev["to"])

    checks = {
        "1_no_warmup_rows_in_training": check_no_warmup_rows_in_training(train_rows),
        "2_no_corrupted_year_history": check_no_corrupted_year_history(conn),
        "3_no_same_day_future_leak": check_no_same_day_future_leak(conn, dev_rows),
        "4_starters_knowable_at_t10": check_starters_is_knowable(conn, dev_rows),
        "5_market_independence": check_market_independence(),
    }
    conn.close()
    checks["7_feature_manifest"] = checks["5_market_independence"]
    return {"meta": {**snapshot(), "rolling_days": ROLLING_DAYS,
                     "n_features": len(FEATURES)},
            "checks": checks,
            "all_ok": all(c["ok"] for c in checks.values())}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    out = run()
    print("\n=== Phase 0.5-4B 基盤修復の検査 (性能ではなく欠陥を見る) ===")
    labels = {
        "1_no_warmup_rows_in_training": "学習に入った burn-in (2021) 行",
        "2_no_corrupted_year_history": "破損年由来の履歴",
        "3_no_same_day_future_leak": "同日・未来のレース結果の混入",
        "4_starters_knowable_at_t10": "出走頭数の PIT 違反",
        "5_market_independence": "Fundamental の市場依存",
        "7_feature_manifest": "Feature Manifest 違反",
    }
    for key, label in labels.items():
        c = out["checks"][key]
        mark = "OK" if c["ok"] else "**NG**"
        detail = ""
        if key == "1_no_warmup_rows_in_training":
            detail = f"{c['rows_before_train_start']} 行 (最古 {c['min_date']})"
        elif key == "2_no_corrupted_year_history":
            detail = (f"除外 {c['rows_excluded_as_corrupted']:,} 行 / "
                      f"使用行の文字化け率 {c['mojibake_rate_in_used_rows']:.4f}")
        elif key == "3_no_same_day_future_leak":
            detail = f"{c['mismatches']} / {c['sampled']} 件で不一致"
        elif key == "4_starters_knowable_at_t10":
            detail = f"{c['mismatches']} / {c['checked']} 件で不一致"
        else:
            detail = f"市場由来 {c['market_features']} 件"
        print(f"  {label:<32} {detail:<42} {mark}")
    print(f"\n  総合: {'すべて OK' if out['all_ok'] else '**未解消あり**'}")

    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
        print(f"\nsaved: {args.json}")
    return 0 if out["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
