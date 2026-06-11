"""predictor.portfolio.compute_day_portfolio の境界テスト (P20-3 / 2026-06-07)。

web/generator.py と gui/app.py の重複を解消した単一出典 helper の契約を固定する。
DB 不要の純粋関数なので tests/ 新設の第一歩に最適。
"""

import math

import pytest

from config import BET_KELLY_MAX_PCT, BET_KELLY_MODE, BET_PORTFOLIO_MAX_PCT
from predictor.portfolio import compute_day_portfolio


def _cand(date, rec, ev=None, *, ev_key="expected_value"):
    """買い候補 dict を組む補助。ev_key で expected_value / ev を切替。"""
    c = {"date": date, "recommended_kelly": rec}
    if ev is not None:
        c[ev_key] = ev
    return c


# --------------------------------------------------------------------------
# 空 list → default
# --------------------------------------------------------------------------
def test_empty_returns_defaults():
    r = compute_day_portfolio([])
    assert r["count"] == 0
    assert r["days"] == []
    assert r["max_day_pct"] == 0.0
    assert r["any_over_cap"] is False
    assert r["exp_return_pct"] is None
    assert r["multi_day"] is False
    # 表示メタは config 由来
    assert r["cap_pct"] == pytest.approx(BET_PORTFOLIO_MAX_PCT * 100)
    assert r["per_bet_cap_pct"] == pytest.approx(BET_KELLY_MAX_PCT * 100)
    assert r["kelly_mode"] == BET_KELLY_MODE


# --------------------------------------------------------------------------
# cap 未満 → scale = 1.0
# --------------------------------------------------------------------------
def test_under_cap_scale_one():
    cands = [
        _cand("2026-06-07", 0.03, ev=1.4),
        _cand("2026-06-07", 0.05, ev=1.2),
    ]
    r = compute_day_portfolio(cands, portfolio_cap=0.25)
    assert r["count"] == 2
    assert len(r["days"]) == 1
    day = r["days"][0]
    assert day["date"] == "2026-06-07"
    assert day["count"] == 2
    assert day["total_pct"] == pytest.approx(8.0)  # (0.03+0.05)*100
    assert day["over_cap"] is False
    assert day["scale"] == 1.0
    assert r["any_over_cap"] is False
    assert r["max_day_pct"] == pytest.approx(8.0)
    assert r["multi_day"] is False


# --------------------------------------------------------------------------
# cap 超過 → 按分 scale (cap / total)
# --------------------------------------------------------------------------
def test_over_cap_scales_down():
    cands = [
        _cand("2026-06-07", 0.20, ev=1.5),
        _cand("2026-06-07", 0.20, ev=1.5),
    ]  # 合計 0.40 > cap 0.25
    r = compute_day_portfolio(cands, portfolio_cap=0.25)
    day = r["days"][0]
    assert day["total_pct"] == pytest.approx(40.0)
    assert day["over_cap"] is True
    # scale は cap / total = 0.25 / 0.40 = 0.625
    assert day["scale"] == pytest.approx(0.625)
    assert r["any_over_cap"] is True
    # scale を掛けると丁度 cap に収まる
    assert day["total_pct"] / 100 * day["scale"] == pytest.approx(0.25)


# --------------------------------------------------------------------------
# 多日窓 → max_day を採用 (日をまたいで合算しない)
# --------------------------------------------------------------------------
def test_multi_day_uses_max_not_sum():
    cands = [
        _cand("2026-06-07", 0.10),
        _cand("2026-06-08", 0.18),
        _cand("2026-06-08", 0.04),
    ]
    r = compute_day_portfolio(cands, portfolio_cap=0.25)
    assert r["multi_day"] is True
    assert len(r["days"]) == 2
    # days は date 昇順
    assert [d["date"] for d in r["days"]] == ["2026-06-07", "2026-06-08"]
    # max は 6/8 の 0.22 (= 22%)、全合算 0.32 ではない
    assert r["max_day_pct"] == pytest.approx(22.0)
    # どちらの日も cap 0.25 未満 → 超過なし (全合算なら誤って超過する)
    assert r["any_over_cap"] is False


# --------------------------------------------------------------------------
# exp_return_pct: 推奨賭金加重平均 EV
# --------------------------------------------------------------------------
def test_exp_return_is_recommended_weighted():
    cands = [
        _cand("2026-06-07", 0.10, ev=2.0),
        _cand("2026-06-07", 0.30, ev=1.0),
    ]
    r = compute_day_portfolio(cands, portfolio_cap=1.0)
    # (0.10*2.0 + 0.30*1.0) / (0.10+0.30) = 0.5/0.4 = 1.25 → 125.0%
    assert r["exp_return_pct"] == pytest.approx(125.0)


def test_exp_return_none_when_no_weight():
    # recommended_kelly が全て 0 → 加重分母ゼロ → None (ゼロ除算回避)
    cands = [_cand("2026-06-07", 0.0, ev=1.5)]
    r = compute_day_portfolio(cands)
    assert r["exp_return_pct"] is None


# --------------------------------------------------------------------------
# ev フィールド後方互換 (gui/app.py の item は "ev" を使う)
# --------------------------------------------------------------------------
def test_ev_legacy_key_fallback():
    cands = [_cand("2026-06-07", 0.10, ev=3.0, ev_key="ev")]
    r = compute_day_portfolio(cands, portfolio_cap=1.0)
    assert r["exp_return_pct"] == pytest.approx(300.0)


def test_expected_value_preferred_over_ev():
    # 両方ある場合は expected_value を優先
    c = {"date": "2026-06-07", "recommended_kelly": 0.10,
         "expected_value": 2.0, "ev": 9.9}
    r = compute_day_portfolio([c], portfolio_cap=1.0)
    assert r["exp_return_pct"] == pytest.approx(200.0)


# --------------------------------------------------------------------------
# 欠損フィールドの頑健性
# --------------------------------------------------------------------------
def test_missing_date_buckets_into_question_mark():
    r = compute_day_portfolio([{"recommended_kelly": 0.05}], portfolio_cap=0.25)
    assert r["days"][0]["date"] == "?"
    assert r["days"][0]["total_pct"] == pytest.approx(5.0)
    # ev 欠損は 0 扱い。分母 (rec=0.05) は非ゼロなので None ではなく 0.0
    assert r["exp_return_pct"] == pytest.approx(0.0)


def test_missing_recommended_kelly_treated_as_zero():
    r = compute_day_portfolio([{"date": "2026-06-07"}], portfolio_cap=0.25)
    assert r["days"][0]["total_pct"] == 0.0
    assert r["max_day_pct"] == 0.0


# --------------------------------------------------------------------------
# 既定 cap (config 由来) が効くこと
# --------------------------------------------------------------------------
def test_default_cap_from_config():
    # 合計 0.30 > config 既定 0.25 → 超過
    cands = [_cand("2026-06-07", 0.30, ev=1.1)]
    r = compute_day_portfolio(cands)
    assert r["any_over_cap"] is True
    assert math.isclose(r["days"][0]["scale"], BET_PORTFOLIO_MAX_PCT / 0.30)


# --------------------------------------------------------------------------
# generator (非 list iterable) でも count が正しい
# --------------------------------------------------------------------------
def test_accepts_generator_input():
    gen = (_cand("2026-06-07", 0.05) for _ in range(3))
    r = compute_day_portfolio(gen, portfolio_cap=0.25)
    assert r["count"] == 3
    assert r["days"][0]["total_pct"] == pytest.approx(15.0)
