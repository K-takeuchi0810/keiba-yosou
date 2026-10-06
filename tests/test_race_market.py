"""選択集合・返還・再正規化・P_new・比の購入条件の契約 (事前登録 0.5-5 §8-6 / §8-6b、2026-10-06)。

## なぜ要るか

旧 `market_offset_eval` / `fundamental_eval` には 2 つの欠陥があった:

- (a) 価格のある返還の対象 (発走除外・競走除外) を、払戻 0 の外れとして賭けに数えた
- (b) 価格の無い返還の対象がいるレースを、`runner_set_mismatch` で **レースごと黙って** 落とした
  (除外は発走の前後に分かる情報なので、後知恵の選択。2025 なら約 110 レース)

ここでは人工のレースで、返還の対象を除いて 3 頭で正規化し直すと、ある馬の比が実際に変わり購入の判定が反転するところまで数値で固定する。
対照の 2 つ (返還の対象の価格 0 → レースは残る / 返還の対象でない馬の価格なし → レースを明示的に除く) は、変異テストで両方とも殺す。
"""
from __future__ import annotations

import math
import sqlite3
from collections import Counter

import pytest

from predictor import race_market as rm
from predictor.race_market import favourite_flat_roi, market_proportional_roi, tail_calibration


# --- 選択集合と再正規化 -------------------------------------------------------------------------

def test_refunded_runner_without_price_keeps_the_race_and_renormalises_over_three():
    """4 頭中 1 頭が競走除外 (3)・価格 0 → レースは残り、残る 3 頭で和 1 に正規化し直す。"""
    cs = rm.build_choice_set({"01": "0", "02": "0", "03": "0", "04": "3"},
                             {"t10": {"01": 2.0, "02": 4.0, "03": 8.0}})
    assert isinstance(cs, rm.ChoiceSet)
    assert cs.choice == ("01", "02", "03") and cs.refunded == ("04",)
    assert cs.implied["t10"] == pytest.approx({"01": 4 / 7, "02": 2 / 7, "03": 1 / 7}, abs=1e-15)
    assert cs.refunded_priced == {"t10": ()}


def test_refunded_runner_with_price_is_removed_and_the_ratio_actually_changes():
    """価格のある発走除外 (2) を除いて正規化し直すと、01 の比が 1.29 (買い) から 1.05 (買わない) に変わる。"""
    abnormal = {"01": "0", "02": "0", "03": "0", "04": "2"}
    odds = {"01": 2.0, "02": 4.0, "03": 8.0, "04": 5.0}
    cs = rm.build_choice_set(abnormal, {"t10": odds})
    assert cs.choice == ("01", "02", "03") and cs.refunded_priced == {"t10": ("04",)}
    p_new_01 = 0.6
    # 旧実装の市場 (返還の対象を含めて正規化): 0.5 / 1.075 = 0.4651 → 比 1.29
    old_market_01 = 0.5 / (0.5 + 0.25 + 0.125 + 0.2)
    assert p_new_01 / old_market_01 == pytest.approx(1.29, abs=1e-12)
    # 正規化し直した市場: 0.5 / 0.875 = 0.5714 → 比 1.05
    assert cs.implied["t10"]["01"] == pytest.approx(4 / 7, abs=1e-15)
    assert p_new_01 / cs.implied["t10"]["01"] == pytest.approx(1.05, abs=1e-12)
    model = {"01": p_new_01, "02": 0.28, "03": 0.12}
    assert rm.ratio_buys(model, cs.implied["t10"]) == []
    old_market = {h: (1 / odds[h]) / 1.075 for h in ("01", "02", "03")}
    assert rm.ratio_buys(model, old_market) == ["01"]       # 旧実装なら買っていた


def test_nonrefund_runner_without_price_excludes_the_race_explicitly():
    """返還の対象でない馬 (異常なし) に価格が無い → 市場の確率を作れないのでレースを除き、理由と馬番を返す。"""
    out = rm.build_choice_set({"01": "0", "02": "0", "03": "0", "04": ""},
                              {"t10": {"01": 2.0, "02": 4.0, "03": 8.0, "04": 0.0}})
    assert out == rm.Excluded("nonrefund_runner_without_price:t10", ("04",))


@pytest.mark.parametrize("code", ["4", "5", "7"])
def test_non_refunded_abnormal_codes_stay_in_the_choice_set(code):
    """競走中止 (4)・失格 (5)・降着 (7) は走っているので選択集合に残す (返還しない)。"""
    cs = rm.build_choice_set({"01": "0", "02": code}, {"t10": {"01": 2.0, "02": 3.0}})
    assert cs.choice == ("01", "02") and cs.refunded == ()
    assert cs.implied["t10"]["02"] == pytest.approx((1 / 3) / (1 / 2 + 1 / 3))


@pytest.mark.parametrize("code", ["4", "5", "7"])
def test_non_refunded_abnormal_code_without_price_excludes_the_race(code):
    out = rm.build_choice_set({"01": "0", "02": code}, {"t10": {"01": 2.0}})
    assert out == rm.Excluded("nonrefund_runner_without_price:t10", ("02",))


@pytest.mark.parametrize("code", ["1", "2", "3", " 3 "])
def test_every_refunded_code_is_removed(code):
    cs = rm.build_choice_set({"01": "0", "02": "0", "03": code}, {"t10": {"01": 2.0, "02": 2.0}})
    assert cs.choice == ("01", "02") and cs.refunded == ("03",)


def test_refund_codes_come_from_db():
    import db
    from db import REFUNDED_ABNORMAL_CODES
    assert rm.is_refunded is db.is_refunded
    assert rm.is_refunded("1") and rm.is_refunded("2") and rm.is_refunded("3")
    assert not rm.is_refunded("4") and not rm.is_refunded("0") and not rm.is_refunded(None)
    assert {c for c in "0123456789" if rm.is_refunded(c)} == set(REFUNDED_ABNORMAL_CODES)


def test_every_market_must_price_every_runner_in_the_choice_set():
    """複数の市場 (T−10 と最終) のどちらかで価格が欠けたら、その市場の名前を理由に残す。"""
    out = rm.build_choice_set({"01": "0", "02": "0"},
                              {"t10": {"01": 2.0, "02": 2.0}, "final": {"01": 1.5}})
    assert out == rm.Excluded("nonrefund_runner_without_price:final", ("02",))


def test_market_runner_not_registered_excludes_the_race():
    out = rm.build_choice_set({"01": "0", "02": "0"}, {"t10": {"01": 2.0, "02": 2.0, "09": 9.0}})
    assert out == rm.Excluded("market_runner_not_registered:t10", ("09",))


def test_race_with_only_refunded_runners_is_excluded():
    assert rm.build_choice_set({"01": "1", "02": "3"}, {"t10": {}}) == rm.Excluded(
        "no_runner_after_refund", ("01", "02"))


# --- 標本の行を選択集合に絞る ---------------------------------------------------------------------

def _rows(*spec):
    return [{"race_id": "R", "horse_num": h, "won": w} for h, w in spec]


def test_choice_rows_drops_the_gate_excluded_loser_row():
    """`build_dataset` は 2・3 を敗者として行に残す (変えない)。評価の標本ではここで除く。"""
    sel = rm.choice_rows(_rows(("01", 1), ("02", 0), ("03", 0)),
                         {"01": "0", "02": "0", "03": "3"}, {"t10": {"01": 2.0, "02": 3.0}})
    cs, kept = sel
    assert [r["horse_num"] for r in kept] == ["01", "02"] and cs.refunded == ("03",)


def test_choice_rows_excludes_a_race_whose_winner_is_refunded():
    out = rm.choice_rows(_rows(("01", 0), ("02", 1)), {"01": "0", "02": "2"}, {"t10": {"01": 2.0}})
    assert out == rm.Excluded("winner_is_refunded", ("02",))


def test_choice_rows_excludes_unregistered_rows_and_missing_rows():
    assert rm.choice_rows(_rows(("01", 1), ("05", 0)), {"01": "0", "02": "0"},
                          {"t10": {"01": 2.0, "02": 2.0}}) == rm.Excluded("sample_row_not_registered", ("05",))
    assert rm.choice_rows(_rows(("01", 1)), {"01": "0", "02": "0"},
                          {"t10": {"01": 2.0, "02": 2.0}}) == rm.Excluded("choice_runner_without_sample_row", ("02",))


# --- P_new と比 ---------------------------------------------------------------------------------

def test_p_new_with_unit_market_coefficient_and_zero_feature_is_exactly_the_market():
    """log P_market で入れるので、β_market = 1・β_S = 0 で P_new は市場そのもの (logit だとそうならない)。"""
    p = {"01": 0.6, "02": 0.3, "03": 0.1}
    s = {"01": 1.0, "02": -2.0, "03": 0.5}
    assert rm.p_new(p, s, 1.0, 0.0) == pytest.approx(p, abs=1e-15)
    # logit で入れた場合は本命が過大になる (この差が β_market = 0.867 の大半だった、学習期で確認)
    lo = {h: v / (1 - v) for h, v in p.items()}
    t = sum(lo.values())
    assert lo["01"] / t > 0.6 + 0.1


def test_market_term_is_log_and_p_new_goes_through_it(monkeypatch):
    assert rm.market_term(0.25) == math.log(0.25)
    calls = []
    real = rm.market_term
    monkeypatch.setattr(rm, "market_term", lambda p: calls.append(p) or real(p))
    rm.p_new({"01": 0.5, "02": 0.5}, {"01": 0.0, "02": 0.0}, 1.0, 0.0)
    assert sorted(calls) == [0.5, 0.5]


def test_p_new_matches_a_hand_softmax():
    p = {"01": 0.5, "02": 0.3, "03": 0.2}
    s = {"01": 0.0, "02": 1.0, "03": -1.0}
    bm, bs = 0.9, 0.2
    u = {h: bm * math.log(p[h]) + bs * s[h] for h in p}
    z = sum(math.exp(v) for v in u.values())
    assert rm.p_new(p, s, bm, bs) == pytest.approx({h: math.exp(v) / z for h, v in u.items()}, abs=1e-15)


def test_p_new_refuses_mismatched_runner_sets():
    with pytest.raises(ValueError, match="馬の集合"):
        rm.p_new({"01": 0.5, "02": 0.5}, {"01": 0.0}, 1.0, 0.1)


def test_ratio_threshold_is_inclusive_and_fixed_at_1_25():
    assert rm.RATIO_BUY == 1.25 and rm.RATIO_140 == 1.75
    market = {"01": 0.25, "02": 0.75}
    assert rm.ratio_buys({"01": 0.3125, "02": 0.6875}, market) == ["01"]          # ちょうど 1.25 は買う
    assert rm.ratio_buys({"01": 0.3124, "02": 0.6876}, market) == []
    with pytest.raises(ValueError):
        rm.ratio_buys({"01": 0.5}, market)


# --- 金額の区分 (事前登録 §4-5・§8-7) ---------------------------------------------------------------

@pytest.mark.parametrize("n,roi,lo,want", [
    (99, 3.0, float("nan"), "MONEY_UNTESTABLE"),
    (100, 3.0, 2.0, "MONEY_UNDERPOWERED"),          # 区間の下限が 100% を超えても、1,500 点未満は合格を主張しない
    (1499, 3.0, 2.0, "MONEY_UNDERPOWERED"),
    (1500, 1.3, 1.01, "MONEY_PASS"),
    (1500, 1.3, 1.0, "MONEY_NOT_PASSED"),           # 下限ちょうど 100% は合格でない
    (1500, 1.2, 0.9, "MONEY_NOT_PASSED"),           # 点推定が 100% を超えても、区間の下限で判定する
    (2000, 1.5, float("nan"), "MONEY_NOT_PASSED"),  # 区間が無効
])
def test_money_class_boundaries(n, roi, lo, want):
    assert rm.MIN_BUYS_FOR_MONEY_PASS == 1500
    assert rm.money_class({"n_bets": n, "roi": roi, "roi_ci95": [lo, lo + 1.0]}) == want


# --- 対照 (事前登録 §4-5) -----------------------------------------------------------------------

def _bet(race, h, p, odds, won, payout=None):
    return {"race_id": race, "horse_num": h, "p_t10": p, "odds_t10": odds, "won": won,
            "payout_odds": (odds if payout is None else payout) if won else 0.0}


def test_market_proportional_control_spreads_100_yen_by_market_probability():
    rows = [_bet("A", "01", 0.5, 2.0, 1), _bet("A", "02", 0.5, 2.0, 0),
            _bet("B", "01", 0.8, 1.2, 0), _bet("B", "02", 0.2, 4.0, 1, payout=5.0)]
    r = market_proportional_roi(rows, "p_t10", n_boot=200)
    # A: 50 円 × 2.0 = 100 / B: 20 円 × 5.0 = 100 → 200 / 200
    assert r["roi"] == pytest.approx(1.0) and r["n_races"] == 2


def test_favourite_control_picks_the_lowest_odds_and_breaks_ties_by_horse_number():
    rows = [_bet("A", "02", 0.4, 2.0, 0), _bet("A", "01", 0.4, 2.0, 1), _bet("A", "03", 0.2, 5.0, 0),
            _bet("B", "01", 0.3, 3.0, 0), _bet("B", "02", 0.7, 1.4, 1)]
    r = favourite_flat_roi(rows, "odds_t10", n_boot=200)
    assert r["n_bets"] == 2 and r["roi"] == pytest.approx((2.0 + 1.4) / 2)
    # 同値は馬番を数値で比べる (文字列だと "10" < "9")
    rows = [_bet("C", "10", 0.5, 2.0, 0), _bet("C", "9", 0.5, 2.0, 1)]
    assert favourite_flat_roi(rows, "odds_t10", n_boot=200)["roi"] == pytest.approx(2.0)


def test_tail_calibration_records_wins_and_both_probability_sums():
    rows = [{"won": 1, "pn": 0.2, "pm": 0.1}, {"won": 0, "pn": 0.3, "pm": 0.2}]
    assert tail_calibration(rows, "pn", "pm") == {"n": 2, "wins": 1, "sum_p_new": pytest.approx(0.5),
                                                  "sum_p_market": pytest.approx(0.3)}


# --- 評価スクリプトの配線 (一時 DB) ---------------------------------------------------------------

RACE = {"race_year": "2026", "race_month_day": "0712", "track_code": "02", "kaiji": "01",
        "nichiji": "01", "race_num": "01"}


def _db(abnormal: dict[str, str]):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE horse_races (race_year TEXT, race_month_day TEXT, track_code TEXT, kaiji TEXT, "
                 "nichiji TEXT, race_num TEXT, horse_num TEXT, abnormal_code TEXT)")
    for h, c in abnormal.items():
        conn.execute("INSERT INTO horse_races VALUES (?,?,?,?,?,?,?,?)", (*RACE.values(), h, c))
    conn.execute("INSERT INTO horse_races VALUES (?,?,?,?,?,?,?,?)", (*RACE.values(), "00", "0"))
    # 同じ日・同じ場の次のレース (異常コードの読み込みがレースキーで絞れていることを確かめる)
    conn.execute("INSERT INTO horse_races VALUES (?,?,?,?,?,?,?,?)", (*list(RACE.values())[:5], "02", "05", "0"))
    return conn


def _eval_rows(*spec):
    return [{"race_id": "2026-0712-02-01-01-01", "horse_num": h, "won": w} for h, w in spec]


def test_select_race_keeps_a_race_whose_refunded_runner_has_no_price_and_counts_it():
    from scripts.fundamental_eval import select_race
    conn = _db({"01": "0", "02": "0", "03": "0", "04": "3"})
    c, ex = Counter(), []
    sel = select_race(conn, RACE, _eval_rows(("01", 1), ("02", 0), ("03", 0), ("04", 0)),
                      {"01": 2.0, "02": 4.0, "03": 8.0}, {"01": 2.1, "02": 4.0, "03": 7.0}, c, ex)
    cs, kept = sel
    assert [r["horse_num"] for r in kept] == ["01", "02", "03"]
    assert cs.implied["t10"]["01"] == pytest.approx(4 / 7)
    assert c["races_with_refunded_runner"] == 1 and c["refunded_runners_excluded"] == 1
    assert ex == [] and "runner_set_mismatch" not in c


def test_select_race_records_the_reason_horses_and_race_of_an_exclusion():
    from scripts.fundamental_eval import select_race
    conn = _db({"01": "0", "02": "0", "03": "0"})
    c, ex = Counter(), []
    assert select_race(conn, RACE, _eval_rows(("01", 1), ("02", 0), ("03", 0)),
                       {"01": 2.0, "02": 4.0}, {"01": 2.0, "02": 4.0, "03": 9.0}, c, ex) is None
    assert ex == [{"race_id": "2026-0712-02-01-01-01", "reason": "nonrefund_runner_without_price:t10",
                   "horses": ["03"]}]
    assert c["excluded:nonrefund_runner_without_price:t10"] == 1


def test_select_race_counts_priced_refunded_runners_per_market():
    from scripts.fundamental_eval import select_race
    conn = _db({"01": "0", "02": "0", "03": "2"})
    c, ex = Counter(), []
    select_race(conn, RACE, _eval_rows(("01", 1), ("02", 0), ("03", 0)),
                {"01": 2.0, "02": 4.0, "03": 6.0}, {"01": 2.0, "02": 4.0}, c, ex)
    assert c["refunded_runners_priced:t10"] == 1 and c["refunded_runners_priced:final"] == 0


def test_special_payouts_and_winners_without_payout_are_counted():
    from scripts.fundamental_eval import count_special_payouts
    c = Counter()
    count_special_payouts(_eval_rows(("01", 1), ("02", 0)), {"01": 0.7}, c)
    count_special_payouts(_eval_rows(("01", 1)), {"01": 1.0}, c)
    count_special_payouts(_eval_rows(("1", 1)), {"01": 0.7}, c)          # 馬番 "1" は払戻の "01" で引く
    count_special_payouts(_eval_rows(("03", 1)), {"01": 2.0}, c)         # 勝ち馬の払戻が無い
    assert c["special_payout_winners"] == 2 and c["winner_without_payout"] == 1


def test_select_race_refuses_empty_rows():
    from scripts.fundamental_eval import select_race
    with pytest.raises(ValueError, match="空"):
        select_race(_db({}), RACE, [], {}, {}, Counter(), [])


def test_ratio_set_selects_per_race_against_the_market_column():
    from predictor.race_market import ratio_set
    rows = [{"race_id": "A", "horse_num": "01", "p_offset": 0.3125, "p_t10": 0.25},
            {"race_id": "A", "horse_num": "02", "p_offset": 0.6875, "p_t10": 0.75},
            {"race_id": "B", "horse_num": "01", "p_offset": 0.5, "p_t10": 0.5},
            {"race_id": "B", "horse_num": "02", "p_offset": 0.5, "p_t10": 0.5}]
    assert [(r["race_id"], r["horse_num"]) for r in ratio_set(rows, "p_offset", 1.25)] == [("A", "01")]
    assert ratio_set(rows, "p_offset", 1.75) == []


def _synthetic_eval_samples(n_races=60, seed=11, boost=1.6):
    """run() の金額の段を確かめる人工の標本 (collect の戻り値の形)。"""
    import random
    rng = random.Random(seed)
    out = []
    for i in range(n_races):
        k = 6
        raw = [rng.random() + 0.2 for _ in range(k)]
        tot = sum(raw)
        p = [x / tot for x in raw]
        off_raw = [pi * (boost if j == 0 else 1.0) for j, pi in enumerate(p)]
        t2 = sum(off_raw)
        winner = rng.choices(range(k), weights=p)[0]
        for j in range(k):
            po = off_raw[j] / t2
            out.append({"race_id": f"2026-07{i:02d}", "horse_num": f"{j + 1:02d}", "date": "20260712",
                        "won": int(j == winner), "lead_min": 12.0, "final_odds_confirmed": 1,
                        "p_t10": p[j], "p_offset": po, "margin": math.log(po / p[j]),
                        "z_t10": math.log(p[j] / (1 - p[j])), "edge": po - p[j],
                        "odds_t10": 0.8 / p[j], "payout_odds": (0.8 / p[j]) if j == winner else 0.0})
    return out


def test_market_offset_run_judges_money_on_the_ratio_set_and_records_controls(monkeypatch, tmp_path):
    import scripts.market_offset_eval as moe
    sqlite3.connect(tmp_path / "empty.db").close()
    monkeypatch.setattr(moe, "DB_PATH", tmp_path / "empty.db")
    samples = _synthetic_eval_samples()
    monkeypatch.setattr(moe, "collect", lambda f, t: (
        [dict(s) for s in samples], Counter({"analysed": 60}),
        {"race_exclusions": [{"race_id": "X", "reason": "nonrefund_runner_without_price:t10", "horses": ["03"]}]}))
    monkeypatch.setattr(moe, "snapshot", lambda conn: {})
    monkeypatch.setattr(moe, "N_BOOT_PRIMARY", 20)
    out = moe.run("20260601", "20260731", run_index=0)
    want = moe.ratio_set([s for s in samples if s["lead_min"] <= moe.DEFAULT_MAX_LEAD_MINUTES], "p_offset", moe.RATIO_BUY)
    assert out["flat_bet_ratio"]["n_bets"] == len(want) > 0
    assert all(r["horse_num"] == "01" for r in want)        # 比 1.25 を超えうるのは各レースの 1 番目の馬だけ
    assert out["money_pass"] is None or out["money_pass"] == (out["flat_bet_ratio"]["roi_ci95"][0] > 1.0)
    assert out["legacy_flat_bet_edge_5pt"]["n_bets"] == sum(s["edge"] > moe.BUY_EDGE_PT for s in samples)
    assert out["race_exclusions"] == [{"race_id": "X", "reason": "nonrefund_runner_without_price:t10",
                                       "horses": ["03"]}]
    assert "race_exclusions" not in out["meta"] and out["meta"]["buy_ratio"] == 1.25
    assert out["control_1_market_proportional"]["n_races"] == 60
    assert out["control_2_favourite"]["n_bets"] == 60
    assert out["ratio_tail_calibration"]["ge_1_25"]["n"] == len(want)
    assert out["money_class"] == "MONEY_UNTESTABLE" and out["money_pass"] is None
    assert "購入条件 (比 ≥ 1.25)" in out["verdict"]["money_untestable_reason"]
    assert out["refund_accounting"].startswith("refunded_runners_excluded")


def test_market_offset_run_never_claims_money_below_1500_bets(monkeypatch, tmp_path):
    """100 点以上 (区間が定義される) でも 1,500 点未満は MONEY_UNDERPOWERED で、合格を主張しない。

    人工の標本は各レースの 1 番目の馬が必ず比 ≥ 1.25 になり、払戻を大きくして区間の下限を 100% より上にする
    (旧実装なら「金額 合格」が立つ)。対照 1 はモデルに依存しないこと、1.75 の集合が RATIO_140 で作られることも確かめる。
    """
    import scripts.market_offset_eval as moe
    from predictor.race_market import ratio_set
    samples = _synthetic_eval_samples(n_races=130, seed=3, boost=2.0)
    for s in samples:
        if s["won"]:
            s["payout_odds"] = 30.0
    sqlite3.connect(tmp_path / "empty.db").close()
    monkeypatch.setattr(moe, "DB_PATH", tmp_path / "empty.db")
    monkeypatch.setattr(moe, "snapshot", lambda conn: {})
    monkeypatch.setattr(moe, "N_BOOT_PRIMARY", 20)
    monkeypatch.setattr(moe, "collect", lambda f, t: ([dict(s) for s in samples], Counter(), {"race_exclusions": []}))
    out = moe.run("20260601", "20260731", run_index=0)
    fb = out["flat_bet_ratio"]
    assert fb["n_bets"] == 130 and fb["testable"] and fb["roi_ci95"][0] > 1.0
    assert out["money_class"] == "MONEY_UNDERPOWERED"
    assert out["money_pass"] is None and out["verdict"]["overall_pass"] is False
    assert out["verdict"]["money_untestable_reason"].startswith("MONEY_UNDERPOWERED")
    # 対照 1 は市場の確率だけで決まる (P_offset で配分するとずれる)
    want_c1 = market_proportional_roi(samples, "p_t10", n_boot=200)["roi"]
    assert out["control_1_market_proportional"]["roi"] == pytest.approx(want_c1)
    assert market_proportional_roi(samples, "p_offset", n_boot=200)["roi"] != pytest.approx(want_c1)
    n175 = len(ratio_set(samples, "p_offset", 1.75))
    assert out["ratio_tail_calibration"]["ge_1_75"]["n"] == n175 < 130


def test_fundamental_run_records_exclusions_and_the_ratio_reference_set(monkeypatch, tmp_path):
    import scripts.fundamental_eval as fe
    samples = _synthetic_eval_samples(n_races=40, seed=5)
    for s in samples:
        s["p_fund"] = s.pop("p_offset")
        s["p_final"] = s["p_t10"]
        s["delta_ai"] = s["p_fund"] - s["p_t10"]
        s["odds_final"] = s["odds_t10"]
    sqlite3.connect(tmp_path / "empty.db").close()
    monkeypatch.setattr(fe, "DB_PATH", tmp_path / "empty.db")
    monkeypatch.setattr(fe, "snapshot", lambda conn: {})
    monkeypatch.setattr(fe, "collect", lambda f, t: (
        [dict(s) for s in samples], Counter({"analysed": 40}),
        {"race_exclusions": [{"race_id": "Y", "reason": "winner_is_refunded", "horses": ["02"]}]}))
    out = fe.run("20260601", "20260731", 30)
    assert out["race_exclusions"] == [{"race_id": "Y", "reason": "winner_is_refunded", "horses": ["02"]}]
    assert "race_exclusions" not in out["meta"]
    want = [s for s in samples if s["p_fund"] >= 1.25 * s["p_t10"]]
    assert out["flat_bet_ratio_ge_1_25"]["n_bets"] == len(want) > 0


# --- collect() を通した配線 (人工の 1 レース、価格のある発走除外 1 頭) ---------------------------------

def _collect_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE races (race_year TEXT, race_month_day TEXT, track_code TEXT, kaiji TEXT, "
                 "nichiji TEXT, race_num TEXT)")
    conn.execute("INSERT INTO races VALUES (?,?,?,?,?,?)", tuple(RACE.values()))
    conn.execute("CREATE TABLE horse_races (race_year TEXT, race_month_day TEXT, track_code TEXT, kaiji TEXT, "
                 "nichiji TEXT, race_num TEXT, horse_num TEXT, abnormal_code TEXT)")
    for h, c in {"01": "0", "02": "0", "03": "0", "04": "2"}.items():
        conn.execute("INSERT INTO horse_races VALUES (?,?,?,?,?,?,?,?)", (*RACE.values(), h, c))
    conn.commit()
    conn.close()
    return path


@pytest.mark.parametrize("final_prices_the_excluded", [False, True])
@pytest.mark.parametrize("module_name", ["market_offset_eval", "fundamental_eval"])
def test_collect_removes_a_priced_gate_exclusion_and_renormalises(tmp_path, monkeypatch, module_name,
                                                                  final_prices_the_excluded):
    """T−10 で価格のあった発走除外 (2) は、標本 (賭け) から消え、残る 3 頭で T−10 市場を正規化し直す。

    旧実装は T−10 と最終の馬の集合が違うのでレースごと落とし (`runner_set_mismatch`)、集合が同じなら外れの賭けに数えた。
    """
    import importlib
    from datetime import datetime
    from types import SimpleNamespace

    import numpy as np

    import scripts.fundamental_eval as fe
    mod = importlib.import_module(f"scripts.{module_name}")
    rid = "2026-0712-02-01-01-01"
    rows = [{"race_id": rid, "horse_num": h, "won": int(h == "01"), "date": "20260712"}
            for h in ("01", "02", "03", "04")]           # build_dataset は 2・3 を敗者として残す
    t10_odds = {"01": 2.0, "02": 4.0, "03": 8.0, "04": 5.0}
    inv = {h: 1 / o for h, o in t10_odds.items()}
    m10 = SimpleNamespace(ok=True, odds=t10_odds, odds_received_at="2026-07-12T10:00:00",
                          implied={h: v / sum(inv.values()) for h, v in inv.items()})   # 旧: 4 頭で正規化

    class _Booster:
        def predict(self, X, raw_score=False):
            return np.zeros(len(X)) if raw_score else np.full(len(X), 0.25)

    monkeypatch.setattr(mod, "assert_model_window_disjoint", lambda *a: None)
    monkeypatch.setattr(mod, "build_dataset", lambda f, t: (rows, {}))
    monkeypatch.setattr(mod, "load_model_schema", lambda p, f: (_Booster(), [], {"n_features": 0}))
    monkeypatch.setattr(mod, "feature_matrix", lambda data, feats: np.zeros((len(data), 1)))
    monkeypatch.setattr(mod, "eval_audit_info", lambda data: {})
    monkeypatch.setattr(mod, "t10_market", lambda conn, race: m10)
    monkeypatch.setattr(mod, "decision_time", lambda conn, race: (None, datetime(2026, 7, 12, 10, 10)))
    final = {"01": 2.2, "02": 3.8, "03": 7.5, **({"04": 6.0} if final_prices_the_excluded else {})}
    monkeypatch.setattr(mod, "_final_market_odds", lambda conn, race: final)
    monkeypatch.setattr(mod, "confirmed_win_payouts", lambda conn, race: {"01": 2.2})
    db = _collect_db(tmp_path / "k.db")
    monkeypatch.setattr(mod, "DB_PATH", db)
    monkeypatch.setattr(fe, "DB_PATH", db)
    samples, counts, info = mod.collect("20260601", "20260731")
    assert [s["horse_num"] for s in samples] == ["01", "02", "03"]
    assert sum(s["p_t10"] for s in samples) == pytest.approx(1.0)
    assert samples[0]["p_t10"] == pytest.approx(4 / 7)           # 旧実装なら 0.4651
    assert counts["analysed"] == 1 and counts["refunded_runners_excluded"] == 1
    assert counts["refunded_runners_priced:t10"] == 1 and "runner_set_mismatch" not in counts
    assert counts["refunded_runners_priced:final"] == int(final_prices_the_excluded)
    assert info["race_exclusions"] == []
    if module_name == "market_offset_eval":
        # 補正 0 なら P_offset は正規化し直した市場と同じ順位・同じ比 (z も 3 頭の市場から)
        assert samples[0]["z_t10"] == pytest.approx(math.log((4 / 7) / (3 / 7)))
        assert all(abs(s["edge"]) < 0.05 for s in samples)
    else:
        assert samples[0]["p_final"] == pytest.approx((1 / 2.2) / (1 / 2.2 + 1 / 3.8 + 1 / 7.5))
        assert samples[0]["delta_ai"] == pytest.approx(1 / 3 - 4 / 7)
