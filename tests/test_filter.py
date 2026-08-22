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


def test_default_spec_is_suspended_in_production(monkeypatch):
    """既定 (config.BUY_FILTER_DEFAULT) はサスペンド中なので買い候補は 0 件。

    2026-08-22: 2026 OOS で絞り込み 53.4% < ◎ベタ 65.3%、新規窓 31.3% < 75.3% と
    2 期連続で価値破壊が確認され、必須ルール 4 に従い停止した。
    """
    monkeypatch.delenv("BET_FILTER_IGNORE_SUSPENSION", raising=False)
    from config import BUY_FILTER_DEFAULT
    assert BUY_FILTER_DEFAULT["suspended"] is True
    assert not is_buy_candidate(FakePred(), horse(win_popularity=3), False)


def test_default_spec_matches_adopted_strategy(monkeypatch):
    """計測モードでの主絞り境界 (pop1-3) を固定する。

    2026-06-14 答え合わせ診断で min_kelly 閾値は撤廃 (anti-predictive と確証)、
    主絞りは market favorite pop1-3 に転換。サスペンド後も「何をサスペンドして
    いるのか」を仕様として固定しておく (再選定時の差分の基準になる)。
    """
    monkeypatch.setenv("BET_FILTER_IGNORE_SUSPENSION", "1")
    from config import BUY_FILTER_DEFAULT
    assert BUY_FILTER_DEFAULT["min_popularity"] == 1
    assert BUY_FILTER_DEFAULT["max_popularity"] == 3
    # 1-3 番人気 + kelly>0 (EV>1) は通る
    assert is_buy_candidate(FakePred(), horse(win_popularity=3), False)
    # 4 番人気以降は主絞り (pop1-3) で落ちる
    assert not is_buy_candidate(FakePred(), horse(win_popularity=5), False)
    # popularity 不明 (0) も落ちる
    assert not is_buy_candidate(FakePred(), horse(win_popularity=0), False)


def test_filter_summary_tracks_config(monkeypatch):
    """_build_filter_summary が BUY_FILTER_DEFAULT に追随すること。

    P24 review (code-quality #1) で「戦略変更時に filter 要約文字列が静かに
    乖離する (テスト未保護)」と指摘されたため固定する。web/gui の要約は
    config 単一出典から動的生成される契約を恒久ブロックする。
    """
    from config import BUY_FILTER_DEFAULT
    from web.generator import _build_filter_summary
    # サスペンド中は「条件が書いてあるのに 0 件」の誤読を避けるため、要約自体が
    # サスペンド表示に切り替わる契約を固定する。
    monkeypatch.delenv("BET_FILTER_IGNORE_SUSPENSION", raising=False)
    if BUY_FILTER_DEFAULT.get("suspended"):
        suspended_summary = _build_filter_summary()
        assert "サスペンド" in suspended_summary
    # 以下は仕様側 (再選定の基準) の固定なので計測モードで確認する。
    monkeypatch.setenv("BET_FILTER_IGNORE_SUSPENSION", "1")
    summary = _build_filter_summary()
    # 人気帯制約が設定されていれば要約に必ず現れる
    if BUY_FILTER_DEFAULT.get("min_popularity") or BUY_FILTER_DEFAULT.get("max_popularity"):
        lo = BUY_FILTER_DEFAULT.get("min_popularity") or 1
        hi = BUY_FILTER_DEFAULT.get("max_popularity") or "-"
        assert f"{lo}-{hi}番人気" in summary
    # min_kelly が None なら "min_kelly" 表記は出ない (撤廃の固定)
    if BUY_FILTER_DEFAULT.get("min_kelly") is None:
        assert "min_kelly" not in summary


def test_odds_age_minutes_parsing():
    assert odds_age_minutes(None, NOW) is None
    assert odds_age_minutes("not-a-date", NOW) is None
    assert odds_age_minutes((NOW - timedelta(minutes=5)).isoformat(), NOW) == 5
    # 未来の時刻 (時計ずれ) は 0 に丸める
    assert odds_age_minutes((NOW + timedelta(minutes=5)).isoformat(), NOW) == 0


def test_suspended_filter_yields_no_buy_candidates(monkeypatch):
    """サスペンド中は他の条件を満たしても買い候補にならない。

    2026-08-22: pop1-3 フィルタが 2 期連続で ◎ベタ買いを下回ったため
    (2026 YTD 53.4% vs 65.3%、新規窓 31.3% vs 75.3%) 必須ルール 4 に従い停止。
    """
    monkeypatch.delenv("BET_FILTER_IGNORE_SUSPENSION", raising=False)
    assert is_buy_candidate(
        FakePred(), horse(win_popularity=2), False,
        filter_spec=spec(suspended=True, min_popularity=1, max_popularity=3),
    ) is False


def test_suspension_can_be_ignored_for_measurement(monkeypatch):
    """BET_FILTER_IGNORE_SUSPENSION=1 なら計測目的で従来判定に戻る。"""
    monkeypatch.setenv("BET_FILTER_IGNORE_SUSPENSION", "1")
    assert is_buy_candidate(
        FakePred(), horse(win_popularity=2), False,
        filter_spec=spec(suspended=True, min_popularity=1, max_popularity=3),
    ) is True


def test_unsuspended_spec_is_unaffected(monkeypatch):
    """suspended を持たない (= 従来の) spec は挙動が変わらない。"""
    monkeypatch.delenv("BET_FILTER_IGNORE_SUSPENSION", raising=False)
    assert is_buy_candidate(FakePred(), horse(), False, filter_spec=spec()) is True


def test_backtest_measures_suspended_spec_by_contract():
    """backtest は計測器なのでサスペンドの影響を受けない、という契約を固定する。

    2026-08-22: config のコメントが「計測は env で」と書いていたのに、backtest の
    spec には suspended が乗らないため env が no-op という不一致が指摘された
    (code-quality / validation / prediction-logic の 3 名)。実装側の意図は
    「backtest は仕様を測り続ける」なので、その契約をテストで固定する。
    逆方向の事故 (誰かが全キーコピーに直して backtest が無言で 0 bets 化) も
    ここで検出される。
    """
    from scripts.backtest import buy_filter_from_generator

    spec = buy_filter_from_generator()
    assert "suspended" not in spec, (
        "backtest 経路にサスペンドを伝播させない契約。変えるなら config.py の"
        "コメントと env_overrides 記録も同時に直すこと"
    )
    # 仕様側 (pop1-3) は生きている = 何をサスペンドしているか計測できる
    assert spec["min_popularity"] == 1
    assert spec["max_popularity"] == 3


def test_suspension_env_is_tracked_in_backtest_meta():
    """BET_FILTER_IGNORE_SUSPENSION が backtest の env_overrides 追跡対象であること。

    サスペンド中の計測 run が「override あり」と自己申告しないと、JSON 単体で
    構成を再現・監査できない (2026-08-22 検証監査の停止条件)。
    """
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent / "scripts" / "backtest.py").read_text(
        encoding="utf-8"
    )
    assert '"BET_FILTER_IGNORE_SUSPENSION"' in source
