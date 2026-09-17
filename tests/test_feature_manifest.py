"""市場情報リーク監査の契約テスト (憲法 Phase 0.5-3)。

## なぜ要るか

> 特徴量名検索だけではなく、特徴量生成経路まで追跡してください。

`能力指数 = 元能力指数 + 人気補正` のように、**名前に odds が無くても中身が
市場情報**である特徴がありうる。実際 2026-09-18 の棚卸しで
`track_recent_30d_avg_winning_pop` が「過去レースの勝ち馬の平均人気」から
作られていることが分かった。名前に odds も popularity も含まれない。

手作業の確認だけにせず、**今後特徴を追加したときにも再混入を検出できる**形で
固定する。
"""
from __future__ import annotations

import pytest

from predictor import feature_manifest as fm


def test_market_dependent_features_are_declared():
    """市場依存の特徴が台帳に登録されていること。"""
    assert fm.MARKET_DEPENDENT, "市場依存の特徴が 1 つも登録されていない"
    for spec in fm.MARKET_DEPENDENT:
        assert spec.market_dependency is True
        assert spec.source_columns, "出所の列が空"
        assert spec.transformation, "どう作ったかが空"


def test_known_market_features_are_in_the_ledger():
    """棚卸しで見つかった 2 件が登録されていること (回帰)。

    どちらも **名前からは市場由来と分からない**。名前検索だけに頼ると漏れる。
    """
    assert "track_recent_30d_avg_winning_pop" in fm.MARKET_DEPENDENT_NAMES
    assert "track_recent_90d_avg_winning_pop" in fm.MARKET_DEPENDENT_NAMES


def test_fundamental_model_rejects_market_features():
    """Fundamental Model に市場依存が入ったら例外になること。"""
    with pytest.raises(ValueError, match="市場依存"):
        fm.assert_no_market_features(
            ["h_winrate", "track_recent_30d_avg_winning_pop"])

    fm.assert_no_market_features(["h_winrate", "j_winrate"])   # 通る


def test_the_actual_fundamental_feature_list_is_clean():
    """**実際に使う特徴リスト**に市場依存が無いこと。

    これが Phase 0.5-3 の合格条件「市場由来特徴量数 0」。
    """
    from scripts.fundamental_model import FEATURES

    fm.assert_no_market_features(FEATURES)
    # 名前に市場らしき語が紛れ込んでいないかの二重チェック
    import re
    suspicious = [f for f in FEATURES
                  if re.search(r"odds|popul|market|share|支持|人気", f, re.I)]
    assert not suspicious, f"名前が市場由来に見える特徴: {suspicious}"


def test_code_paths_reading_market_columns_are_detected():
    """特徴生成コードで市場列を読む関数を機械的に検出できること。

    名前検索の網から漏れる派生特徴を捕まえる第 2 の網。空振りしていないか、
    既知の 2 関数が出ることで確かめる。
    """
    found = fm.market_reading_functions()

    assert "_track_recent_stats" in found, (
        "市場列を読む関数を検出できていない = 検査が空振り")
    assert "win_popularity" in found["_track_recent_stats"]
    # horse_past_runs は取得するが特徴には流していない (2026-09-18 確認)。
    # 検出はされるべき (使い始めたら気づけるように)。
    assert "horse_past_runs" in found


def test_detector_finds_a_planted_market_read(tmp_path):
    """検出器が本当に市場列を見つけられること (対照実験)。"""
    src = tmp_path / "fake_features.py"
    src.write_text(
        "def some_derived_feature(conn):\n"
        "    return conn.execute('SELECT win_popularity FROM horse_races')\n",
        encoding="utf-8")

    found = fm.market_reading_functions(src)

    assert found == {"some_derived_feature": ["win_popularity"]}


def test_detector_ignores_clean_code(tmp_path):
    src = tmp_path / "clean.py"
    src.write_text(
        "def pure(conn):\n"
        "    return conn.execute('SELECT confirmed_order FROM horse_races')\n",
        encoding="utf-8")

    assert fm.market_reading_functions(src) == {}


def test_names_that_look_market_but_are_not_have_reasons():
    """誤検出を黙って無視せず、理由付きで登録してあること。"""
    assert fm.NOT_MARKET_DESPITE_NAME
    for name, reason in fm.NOT_MARKET_DESPITE_NAME.items():
        assert reason and len(reason) > 5, f"{name} の理由が空"
        assert name not in fm.MARKET_DEPENDENT_NAMES, (
            f"{name} が両方に登録されている")
