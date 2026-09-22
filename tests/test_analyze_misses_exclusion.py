"""`analyze_misses` が評価対象外のレースを分母に入れないこと (2026-09-22)。

## なぜ production 関数を通すのか

最初は「ソースに `evaluable` という語があるか」を見ていた。それだと除外の
`if` を消しても、語がどこかに残っていれば通ってしまう。**主要集計で除外しても
分析系で中止レースが復活する**のを防ぐのが目的なので、実際に `build()` を
走らせて出力を見る。

fixture には 5 種類を混ぜる。1 種類ずつ別々に試すと「たまたま全部落ちている」
のか「狙ったものだけ落ちている」のか区別できない。

    RUN + resolved で不的中   -> miss として数える
    RUN + resolved で的中     -> 数えるが miss ではない
    RUN + 結果待ち            -> 数えない (一時)
    RUN + 払戻待ち            -> 数えない (一時)
    CANCELLED                 -> 数えない (永久)
"""
from __future__ import annotations

import csv
import sqlite3

import pytest

from scripts import analyze_misses

_COLUMNS = [
    "race_id", "track_code", "race_num", "race_name", "distance",
    "track_type_code", "starter_count", "horse_num", "horse_name", "mark",
    "model_rank_by_mark", "morning_odds", "morning_popularity", "final_odds",
    "final_popularity", "market_probability", "win_probability",
    "expected_value_morning", "confidence", "bet_candidate",
    "planned_stake_yen_100unit", "settled_stake_yen_100unit",
    "prediction_issued", "race_status", "result_resolved", "payout_resolved",
    "actual_execution_date", "evaluable", "evaluation_exclusion_reason",
    "confirmed_order", "win_payout", "place_payout", "profit_loss_yen_100unit",
    "rationale",
]


def _row(race_num, horse_num, mark, confirmed, *, evaluable, reason,
         status="RUN", resolved="True", payout="True"):
    return {c: "" for c in _COLUMNS} | {
        "race_id": f"20260921-09-{race_num}",
        "track_code": "09", "race_num": race_num, "race_name": "テスト",
        "distance": "1200", "track_type_code": "1", "starter_count": "10",
        "horse_num": horse_num, "horse_name": f"馬{horse_num}", "mark": mark,
        "model_rank_by_mark": "1", "morning_popularity": "2",
        "final_popularity": "2", "win_probability": "0.3",
        "confidence": "標準", "bet_candidate": "False",
        "prediction_issued": "True", "race_status": status,
        "result_resolved": resolved, "payout_resolved": payout,
        "evaluable": str(evaluable), "evaluation_exclusion_reason": reason,
        "confirmed_order": str(confirmed), "rationale": "テスト;",
    }


@pytest.fixture()
def results_dir(tmp_path, monkeypatch):
    """5 種類を 1 つの日に混ぜた evaluation_summary.csv を作る。"""
    day = tmp_path / "2026-09-21"
    day.mkdir()
    rows = []
    # 01: 評価可・不的中 (◎ が 2 着、1 着は別馬) -> miss として数える
    rows += [_row("01", "1", "◎", 2, evaluable=True, reason=""),
             _row("01", "2", "○", 1, evaluable=True, reason="")]
    # 02: 評価可・的中 -> 数えるが miss ではない
    rows += [_row("02", "1", "◎", 1, evaluable=True, reason=""),
             _row("02", "2", "○", 2, evaluable=True, reason="")]
    # 03: 結果待ち -> 数えない
    rows += [_row("03", "1", "◎", 0, evaluable=False,
                  reason="result_not_yet_available", resolved="False",
                  payout="False")]
    # 04: 払戻待ち (着順はある) -> 数えない
    rows += [_row("04", "1", "◎", 2, evaluable=False,
                  reason="payout_not_yet_available", payout="False"),
             _row("04", "2", "○", 1, evaluable=False,
                  reason="payout_not_yet_available", payout="False")]
    # 05: 中止 -> 数えない
    rows += [_row("05", "1", "◎", 0, evaluable=False, reason="cancelled",
                  status="CANCELLED", resolved="False", payout="False")]

    with (day / "evaluation_summary.csv").open("w", encoding="utf-8",
                                               newline="") as f:
        w = csv.DictWriter(f, fieldnames=_COLUMNS)
        w.writeheader()
        w.writerows(rows)

    # 列を 1 つずつ足すより **実スキーマ**を読む。fixture が実態から乖離すると、
    # 「fixture では通るが本番では落ちる」テストになる。
    from config import PROJECT_ROOT

    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        (PROJECT_ROOT / "data" / "schema.sql").read_text(encoding="utf-8"))
    for rn in ("01", "02", "03", "04", "05"):
        conn.execute(
            "INSERT INTO races (race_year, race_month_day, track_code, kaiji,"
            " nichiji, race_num, race_name, distance, starter_count, data_div)"
            " VALUES ('2026','0921','09','01','01',?,'テスト',1200,10,?)",
            (rn, "9" if rn == "05" else "6"))
        for hn in ("01", "02"):
            conn.execute(
                "INSERT INTO horse_races (race_year, race_month_day, track_code,"
                " kaiji, nichiji, race_num, horse_num, confirmed_order)"
                " VALUES ('2026','0921','09','01','01',?,?,0)", (rn, hn))
    conn.commit()
    conn.close()

    monkeypatch.setattr(analyze_misses, "RESULTS_DIR", tmp_path)
    return str(db)


def test_only_evaluable_races_reach_the_analysis(results_dir):
    """評価可のレースだけが分析に入ること (production の build() を通す)。"""
    rows, stats = analyze_misses.build(db_path=results_dir)
    skipped = stats["skipped"]

    analysed = {r["race_id"].rsplit("-", 1)[-1] for r in rows}
    # 評価可の 2 レース (不的中 01 / 的中 02) だけが分析に入る。
    # 03 結果待ち / 04 払戻待ち / 05 中止 は分母に入らない。
    assert analysed == {"01", "02"}, (
        f"評価対象外のレースが分析に入っている: {sorted(analysed)}")
    assert stats["races"] == 2, f"分母が合わない: {stats['races']}"
    assert stats["hits"] == 1, "的中が数えられていない"


def test_each_exclusion_reason_is_counted_separately(results_dir):
    """除外を理由ごとに数えること (まとめると永久と一時の区別が消える)。"""
    _rows, stats = analyze_misses.build(db_path=results_dir)
    skipped = stats["skipped"]

    assert skipped["excluded_cancelled"] == 1
    assert skipped["excluded_result_not_yet_available"] == 1
    assert skipped["excluded_payout_not_yet_available"] == 1


def test_a_cancelled_race_is_not_a_miss(results_dir):
    """中止レースが miss の分母に入らないこと。"""
    rows, _stats = analyze_misses.build(db_path=results_dir)

    assert all("05" != r["race_id"].rsplit("-", 1)[-1] for r in rows)
    assert all("04" != r["race_id"].rsplit("-", 1)[-1] for r in rows), (
        "払戻待ちが miss に数えられている")


def test_the_reason_breakdown_is_not_collapsed(results_dir):
    """2 つ以上の理由が混ざったとき、内訳が潰れないこと。

    1 理由しか無い fixture だと「まとめて数える」変異を捕まえられない
    (M25 として 2 回持ち越された)。ここは 3 理由が同時に立つ。
    """
    _rows, stats = analyze_misses.build(db_path=results_dir)
    skipped = stats["skipped"]

    reasons = {k: v for k, v in skipped.items()
               if k.startswith("excluded_") and v}
    assert len(reasons) == 3, f"理由がまとめられている: {reasons}"
    assert set(reasons) == {
        "excluded_cancelled",
        "excluded_result_not_yet_available",
        "excluded_payout_not_yet_available",
    }
    assert sum(reasons.values()) == 3
