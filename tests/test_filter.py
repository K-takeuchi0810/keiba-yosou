"""predictor.filter.is_buy_candidate の回帰テスト (P23, 2026-06-13)。

金銭直結の単一出典でありながらテストゼロだった (v2 監査 code-quality 指摘)。
過去 2 回発生した「経路ごとのフィルタ項目漏れ」(S5-3: gui の min_kelly 漏れ /
S7-α: web の min_kelly + max_predicted_p 漏れ) と同型の回帰、および
2026-06-13 に統合したオッズ鮮度チェックを恒久ブロックする。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest

from predictor.filter import is_buy_candidate, odds_age_minutes


@dataclass
class FakePred:
    rank: int = 1
    mark: str = "◎"
    confidence: str = "標準"
    value_score: float = 50.0
    expected_value: float = 1.2
    kelly_fraction: float = 0.10
    win_probability: float = 0.20


def spec(**over) -> dict:
    """テスト用 filter_spec。既定は「制約なし + min_kelly/max_p は P15/S5-3 採用値」。"""
    base = {
        "min_value": None,
        "min_ev": None,
        "min_odds": None,
        "max_odds": None,
        "min_kelly": 0.05,
        "max_predicted_p": 0.40,
        "min_popularity": None,
        "max_popularity": None,
        "exclude_confidence": [],
        "max_odds_age_min": 30,
    }
    base.update(over)
    return base


def horse(**over) -> dict:
    base = {"win_odds": 80, "win_popularity": 3, "odds_fetched_at": None}
    base.update(over)
    return base


NOW = datetime(2026, 6, 13, 10, 0, 0)


def test_passes_with_default_strategy():
    assert is_buy_candidate(FakePred(), horse(), False, filter_spec=spec())


def test_rank_mark_tentative_gates():
    assert not is_buy_candidate(FakePred(rank=2), horse(), False, filter_spec=spec())
    assert not is_buy_candidate(FakePred(mark=""), horse(), False, filter_spec=spec())
    assert not is_buy_candidate(FakePred(), horse(), True, filter_spec=spec())


def test_min_kelly_is_enforced():
    """S5-3 / S7-α で 2 回漏れた P15 主絞り条件。最重要回帰テスト。"""
    assert not is_buy_candidate(
        FakePred(kelly_fraction=0.049), horse(), False, filter_spec=spec())
    assert is_buy_candidate(
        FakePred(kelly_fraction=0.05), horse(), False, filter_spec=spec())


def test_max_predicted_p_is_enforced():
    """S5-3 導入の高 p 帯破綻防御 (reliability gap ガード)。"""
    assert not is_buy_candidate(
        FakePred(win_probability=0.41), horse(), False, filter_spec=spec())
    assert is_buy_candidate(
        FakePred(win_probability=0.40), horse(), False, filter_spec=spec())


def test_kelly_must_be_positive():
    assert not is_buy_candidate(
        FakePred(kelly_fraction=0.0), horse(), False,
        filter_spec=spec(min_kelly=None))


def test_odds_range_and_ev():
    s = spec(min_odds=10.0, max_odds=20.0, min_ev=1.05)
    assert is_buy_candidate(FakePred(), horse(win_odds=150), False, filter_spec=s)
    assert not is_buy_candidate(FakePred(), horse(win_odds=90), False, filter_spec=s)
    assert not is_buy_candidate(FakePred(), horse(win_odds=250), False, filter_spec=s)
    assert not is_buy_candidate(
        FakePred(expected_value=1.0), horse(win_odds=150), False, filter_spec=s)


def test_odds_freshness_live_only():
    """2026-06-13 統合: now 指定時のみ鮮度チェック。backtest (now=None) は不変。"""
    stale = horse(odds_fetched_at=(NOW - timedelta(minutes=31)).isoformat())
    fresh = horse(odds_fetched_at=(NOW - timedelta(minutes=29)).isoformat())
    # ライブ: 30 分超は reject
    assert not is_buy_candidate(FakePred(), stale, False, filter_spec=spec(), now=NOW)
    assert is_buy_candidate(FakePred(), fresh, False, filter_spec=spec(), now=NOW)
    # backtest 経路 (now なし): 鮮度は見ない
    assert is_buy_candidate(FakePred(), stale, False, filter_spec=spec())
    # fetched_at 不明はライブでも reject しない (鮮度不明 ≠ 古い)
    assert is_buy_candidate(FakePred(), horse(), False, filter_spec=spec(), now=NOW)
    # max_odds_age_min が None (無効化) なら見ない
    assert is_buy_candidate(
        FakePred(), stale, False, filter_spec=spec(max_odds_age_min=None), now=NOW)


def test_exclude_confidence():
    s = spec(exclude_confidence=["接戦"])
    assert not is_buy_candidate(FakePred(confidence="接戦"), horse(), False, filter_spec=s)
    assert is_buy_candidate(FakePred(confidence="標準"), horse(), False, filter_spec=s)


def test_default_spec_matches_adopted_strategy():
    """filter_spec=None → config.BUY_FILTER_DEFAULT。採用戦略の主絞りが効くこと。"""
    from config import BUY_FILTER_DEFAULT
    assert BUY_FILTER_DEFAULT["min_kelly"] is not None
    assert BUY_FILTER_DEFAULT["max_predicted_p"] is not None
    weak = FakePred(kelly_fraction=BUY_FILTER_DEFAULT["min_kelly"] - 0.001)
    assert not is_buy_candidate(weak, horse(), False)


def test_odds_age_minutes_parsing():
    assert odds_age_minutes(None, NOW) is None
    assert odds_age_minutes("not-a-date", NOW) is None
    assert odds_age_minutes((NOW - timedelta(minutes=5)).isoformat(), NOW) == 5
    # 未来の時刻 (時計ずれ) は 0 に丸める
    assert odds_age_minutes((NOW + timedelta(minutes=5)).isoformat(), NOW) == 0
