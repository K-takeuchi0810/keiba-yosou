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

from pathlib import Path

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


# `predictor/features.py` で市場語を読んでよい関数。**ここと完全一致を要求する**。
# 増えたら必ずテストが落ちるので、台帳に追記するか経路を断つかを迫られる。
ALLOWED_MARKET_READERS = {
    "horse_past_runs",        # 過去走の取得。特徴には流していない (要確認の対象)
    "_track_recent_stats",    # track_recent_*_avg_winning_pop の生成元
    "compute_features",       # 上記特徴名を文字列として持つだけ
}


def test_code_paths_reading_market_columns_match_the_allowlist_exactly():
    """市場語を読む関数の集合が **許可リストと完全一致** すること。

    「含まれる」だけを見ると、新しく市場列を読み始めた関数が増えても気づけない。
    完全一致にすれば、増えた瞬間にテストが落ちて台帳更新を強制できる。
    """
    found = fm.market_reading_functions()

    assert set(found) == ALLOWED_MARKET_READERS, (
        f"市場語を読む関数が許可リストと違う。増えた: "
        f"{set(found) - ALLOWED_MARKET_READERS} / 消えた: "
        f"{ALLOWED_MARKET_READERS - set(found)}")
    assert "popularity" in found["_track_recent_stats"]


def test_the_fundamental_generation_code_reads_no_market_column():
    """**Fundamental の実データ経路**に検出器を当てる。

    ここが本命。2026-09-18 のレビューで、`build_dataset` の SELECT に
    `win_popularity` を 1 列足してもテスト 14 本が全部通ることが実証された
    (台帳の名前と Fundamental の特徴名は名前空間が交わらないので、
    集合積による照合は原理的に空振りする)。
    """
    assert fm.market_reading_functions(
        Path("scripts/fundamental_model.py")) == {}


def test_planting_a_market_column_in_the_fundamental_path_raises(tmp_path):
    """植え込んだら例外になること (対照実験)。

    上のテストが「たまたま空」なのか「本当に守っている」のかを区別する。
    """
    src = tmp_path / "fundamental_model.py"
    src.write_text(
        "def build_dataset(conn):\n"
        "    return conn.execute('SELECT win_popularity FROM horse_races')\n",
        encoding="utf-8")

    with pytest.raises(ValueError, match="市場列を読んでいる"):
        fm.assert_no_market_features(["h_winrate"], source_module=src)


def test_market_token_matching_survives_underscores():
    """`odds` が `place_odds` や `odds_low` にも当たること。

    以前は `` 付きの完全語一致だったが、正規表現では `_` が語文字なので
    `win_odds` を登録しても `place_odds` に当たらなかった。
    """
    assert any(t in "place_odds" for t in fm.MARKET_TOKENS)
    assert any(t in "odds_low" for t in fm.MARKET_TOKENS)
    assert any(t in "tan_pop1" for t in fm.MARKET_TOKENS)
    assert not any(t in "confirmed_order" for t in fm.MARKET_TOKENS)


def test_detector_finds_a_planted_market_read(tmp_path):
    """検出器が本当に市場列を見つけられること (対照実験)。"""
    src = tmp_path / "fake_features.py"
    src.write_text(
        "def some_derived_feature(conn):\n"
        "    return conn.execute('SELECT win_popularity FROM horse_races')\n",
        encoding="utf-8")

    found = fm.market_reading_functions(src)

    assert list(found) == ["some_derived_feature"]
    assert "popularity" in found["some_derived_feature"]


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
