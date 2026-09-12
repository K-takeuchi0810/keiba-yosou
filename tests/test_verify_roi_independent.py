"""独立再計算スクリプトの契約テスト。

このスクリプトは「71.5% という数字が backtest.py のバグではないか」を潰す
ための外部検証器なので、**検証器自身が壊れていないこと**を固定する。

2026-09-06 の実バグ: `mask_post_race` だけを掛けていたため市場列 (win_odds) が
確定オッズのまま素通りし、(a) 発走後に判明する値で予想していた、
(b) --require-market が 1 件も除外しなかった (2,226 戦がそのまま通った)。
検算結果を既存実装と突き合わせて初めて気づいたので、テストで固定する。
"""
from __future__ import annotations

import sqlite3

import pytest

from scripts import verify_roi_independent as mod

KEYS = ("2026", "0822", "05", "01", "01", "01")


@pytest.fixture()
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute(
        "CREATE TABLE payouts (race_year TEXT, race_month_day TEXT, track_code TEXT,"
        " kaiji TEXT, nichiji TEXT, race_num TEXT,"
        " tan_horse_num1 TEXT, tan_payout1 INTEGER,"
        " tan_horse_num2 TEXT, tan_payout2 INTEGER,"
        " tan_horse_num3 TEXT, tan_payout3 INTEGER)"
    )
    return c


def _payout_row(conn, *cols):
    conn.execute(
        "INSERT INTO payouts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (*KEYS, *cols))
    conn.commit()


def test_payout_matches_on_horse_number(conn):
    """的中判定は馬番一致で行う (backtest の「払戻額>0」とは別経路)。"""
    _payout_row(conn, "07", 640, "", 0, "", 0)

    assert mod.independent_payout(conn, KEYS, "07") == 640
    assert mod.independent_payout(conn, KEYS, "7") == 640, "0 埋めの有無を吸収する"
    assert mod.independent_payout(conn, KEYS, "08") == 0, "外れは 0"


def test_dead_heat_sums_all_matching_payouts(conn):
    """同着は該当口だけ合算する (無関係な口を足さない)。"""
    _payout_row(conn, "03", 500, "09", 700, "", 0)

    assert mod.independent_payout(conn, KEYS, "03") == 500
    assert mod.independent_payout(conn, KEYS, "09") == 700
    assert mod.independent_payout(conn, KEYS, "05") == 0


def test_missing_payout_row_is_distinguished_from_a_loss(conn):
    """払戻データ欠損 (-1) と外れ (0) を混同しない。

    混同すると「データが無いレース」を全部ハズレとして数え、回収率が
    不当に低く出る。
    """
    assert mod.independent_payout(conn, KEYS, "01") == -1


def test_pit_reconstruction_is_applied_before_prediction():
    """予想入力が PIT 再構成を通ること (2026-09-06 のバグの回帰)。

    ソース上で apply_pit_odds を呼び、その結果を predict_race に渡している
    ことを固定する。ここが抜けると確定オッズで予想する状態に戻り、
    --require-market も無効化される。
    """
    import inspect

    src = inspect.getsource(mod.run)
    assert "apply_pit_odds(conn, race, horses)" in src
    assert "pit_meta.get(\"has_market\")" in src, (
        "市場有無の判定は pit_meta を見る (win_odds の生値を見てはいけない)"
    )
    # apply_pit_odds の結果を predict_race に渡していること
    pit_at = src.index("apply_pit_odds")
    pred_at = src.index("predict_race(pred_input")
    assert pit_at < pred_at
