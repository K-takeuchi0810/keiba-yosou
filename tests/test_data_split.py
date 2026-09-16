"""データ 4 分割の契約テスト (憲法 docs/CHARTER_2026_09_17.md 方針 8)。

分割が重なったり、探索用の期間が検証用に混ざったりすると OOS が成立せず、
そこから先の数字はすべて意味を失う。分割は設計の土台なのでテストで固定する。
"""
from __future__ import annotations

import pytest

import config


def test_four_splits_exist():
    """憲法が要求する 4 分割が揃っていること。"""
    assert set(config.DATA_SPLIT) == {"train", "validation", "strategy_dev", "lockbox"}


def test_splits_do_not_overlap():
    """分割どうしが重ならないこと。重なると OOS が成立しない。"""
    assert config.splits_are_disjoint()


def test_strategy_dev_starts_after_pre_race_odds_exist():
    """探索期間が「発走前オッズのある期間」に収まっていること。

    方針 7 は最終オッズでの購入判定を禁じる。発走前 (T−10) のオッズは
    2026-05-02 以降しか存在しないので、購入判断を含む探索はそれ以降に限る。
    ここを緩めると、取得できなかったはずの情報で判断することになる。
    """
    start, _ = config.data_split("strategy_dev")
    # 2026-09-17 実測: 適格スナップショットの最初のレース日は 05-09。
    # odds_snapshots は 05-02 から行があるが、05-02〜05-06 は後から埋めたもので
    # 取得時刻が発走後。
    assert start >= "20260509", (
        "探索期間が発走前オッズの無い時期に食い込んでいる "
        "(最終オッズで判断することになる = 方針 7 違反)")


def test_lockbox_is_not_scheduled_yet():
    """Lockbox はまだ開始していないこと (2026-09-17 ユーザ決定で延期)。

    開始するときは SEALED_FROM と同時にここも設定する。
    """
    start, end = config.data_split("lockbox")
    assert start is None and end is None
    assert config.SEALED_FROM is None, "Lockbox と封印の開始日は同じものを指す"


def test_unknown_split_name_raises():
    with pytest.raises(KeyError, match="未知の分割名"):
        config.data_split("test")        # 旧 DATA_PERIODS の名前は使わせない


def test_new_split_does_not_collide_with_legacy_periods():
    """新旧の期間が食い違わないこと。

    旧 DATA_PERIODS は既存コード (filter_sweep / bias_scan / monitor /
    webapp) が参照しており当面残る。このとき **同名なのに期間が違う** 状態を
    作ってはいけない。旧 train で学習して新 train で評価すれば in-sample に
    なるが、何も落ちずに通ってしまう (2026-09-17 コード品質レビュー指摘)。
    """
    assert set(config.DATA_PERIODS) == {"train", "test", "production"}
    # 同名 train は同じ境界であること
    assert config.data_split("train") == (
        config.DATA_PERIODS["train"]["from"], config.DATA_PERIODS["train"]["to"])
    # 旧 test = 新 validation (名前だけ変えた関係) であること
    assert config.data_split("validation") == (
        config.DATA_PERIODS["test"]["from"], config.DATA_PERIODS["test"]["to"])


def test_confirm_window_starts_after_strategy_dev():
    """事前登録後の確認用期間が、探索期間より後にあること。"""
    _, dev_end = config.data_split("strategy_dev")
    assert config.CONFIRM_FROM > dev_end


def test_confirm_window_is_not_already_consumed():
    """確認用の期間を、既に結果を見た期間と重ねないこと。

    2026-09-17 の検証レビューで、2026-09-01〜09-13 を自分の分析
    (residual_learn / MODEL_VS_MARKET) の検証窓として既に使っていたことが
    判明した。「未使用のつもりの窓が実は消費済み」は、事前登録を無効にする。
    窓を結果目的で使ったら CONSUMED_WINDOWS に追記すること。
    """
    assert config.CONFIRM_FROM > config.consumed_until(), (
        f"確認窓の開始 {config.CONFIRM_FROM} が、消費済みの最終日 "
        f"{config.consumed_until()} より後になっていない")


def test_consumed_ledger_entries_are_well_formed():
    for w in config.CONSUMED_WINDOWS:
        assert set(w) >= {"from", "to", "by"}
        assert len(w["from"]) == 8 and w["from"].isdigit()
        assert len(w["to"]) == 8 and w["to"].isdigit()
        assert w["from"] <= w["to"]
