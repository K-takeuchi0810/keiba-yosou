"""PIT パリティ: live と backtest が同一入力・同一出力であることの恒久保証 (改革 P0)。

## このテストが存在する理由

同じ事故が 2 度起きた。どちらも「発走後にしか埋まらない列を、特徴が間接的に
参照していた」ことによる train-serve skew:

1. 2026-07: LGBM の `leg_code` が発走後値依存 → live 条件で AUC 0.579 ≒ ランダム
2. 2026-08-23: `same_day_bias_score` が当該レースの `leg_quality_code` を
   キーにしていた → 発火率 backtest 30.2% vs live 0%、ルールスコアが 64% の馬で
   最大 15 点乖離 (実測: 2026-08-16、159 頭)

いずれも「レビューで気づく」運用だったから漏れた。本テストは
**マスク有無で特徴量とスコアが一致すること**を機械的に検査するので、
発走後列を参照する特徴を足した瞬間に落ちる。

## 落ちたときの直し方

特徴が発走後列を読んでいる。過去走から作った事前 proxy に置き換えること
(例: `leg_quality_code` → `estimated_leg_code`)。
「マスク対象から外す」で通すのは**禁止** — それは検証の意味を捨てる行為。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from predictor.pit_view import (
    POST_RACE_COLUMNS,
    PRE_RACE_COLUMNS,
    UnclassifiedColumnError,
    classify_columns,
    mask_post_race,
    post_race_fields_present,
)

DB = Path(__file__).resolve().parent.parent / "data" / "keiba.db"

# 特徴計算に本物の DB (過去走・同日他レース) が要るため、無ければ skip。
requires_db = pytest.mark.skipif(not DB.exists(), reason="data/keiba.db が無い")


def _ro_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# 1. 台帳の完全性 (新しい列を黙って使えないようにする門)
# ---------------------------------------------------------------------------

def test_ledger_has_no_overlap():
    assert not (POST_RACE_COLUMNS & PRE_RACE_COLUMNS)


@requires_db
def test_every_column_is_classified():
    """horse_races の全列が台帳のどちらかに登録されていること。

    列を追加したのに分類していない場合、ここで落ちる。分類を強制することで
    「発走後列を知らずに特徴へ流す」経路を閉じる。
    """
    conn = _ro_conn()
    try:
        got = classify_columns(conn)  # 未登録があれば raise
    finally:
        conn.close()
    assert got["post_race"], "発走後列が 1 つも認識できていない (台帳か DB が異常)"
    assert "confirmed_order" in got["post_race"]
    assert "leg_quality_code" in got["post_race"], (
        "脚質は発走後列。2026-07 / 2026-08 の 2 度のリークの原因列なので"
        "発走前扱いに戻してはならない"
    )


def test_unclassified_column_raises():
    """未知の列があれば必ず raise する (門が実際に機能することの確認)。"""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE horse_races (horse_num TEXT, brand_new_column TEXT)")
    with pytest.raises(UnclassifiedColumnError, match="brand_new_column"):
        classify_columns(conn)
    conn.close()


def test_mask_does_not_mutate_input():
    src = {"horse_num": "01", "confirmed_order": 1, "leg_quality_code": "2"}
    masked = mask_post_race(src)
    assert src["confirmed_order"] == 1, "入力を破壊しない"
    assert masked["confirmed_order"] is None
    assert masked["leg_quality_code"] is None
    assert masked["horse_num"] == "01", "発走前列は保持する"


def test_post_race_fields_present_detects_contamination():
    assert post_race_fields_present({"confirmed_order": 3}) == ["confirmed_order"]
    assert post_race_fields_present({"confirmed_order": None}) == []


# ---------------------------------------------------------------------------
# 2. パリティ本体: マスク有無で特徴量とスコアが一致すること
# ---------------------------------------------------------------------------

def _sample_race(conn: sqlite3.Connection) -> tuple[dict, list[dict]] | None:
    """発走後データが充填済みの実レースを 1 つ取る (汚染が起きうる条件)。"""
    row = conn.execute(
        """
        SELECT r.* FROM races r
         WHERE r.track_code BETWEEN '01' AND '10'
           AND r.race_year || r.race_month_day <= '20260816'
           AND EXISTS (
                SELECT 1 FROM horse_races h
                 WHERE h.race_year=r.race_year AND h.race_month_day=r.race_month_day
                   AND h.track_code=r.track_code AND h.kaiji=r.kaiji
                   AND h.nichiji=r.nichiji AND h.race_num=r.race_num
                   AND TRIM(COALESCE(h.leg_quality_code,'')) <> ''
           )
         ORDER BY r.race_year DESC, r.race_month_day DESC, r.track_code, r.race_num
         LIMIT 1
        """
    ).fetchone()
    if row is None:
        return None
    race = dict(row)
    horses = [dict(h) for h in conn.execute(
        """SELECT * FROM horse_races
            WHERE race_year=? AND race_month_day=? AND track_code=?
              AND kaiji=? AND nichiji=? AND race_num=?
              AND horse_num NOT IN ('', '00')
            ORDER BY CAST(horse_num AS INTEGER)""",
        (race["race_year"], race["race_month_day"], race["track_code"],
         race["kaiji"], race["nichiji"], race["race_num"]),
    ).fetchall()]
    return (race, horses) if horses else None


@requires_db
def test_rule_score_is_identical_with_and_without_post_race_columns():
    """ルールスコアが発走後列に依存しないこと。

    依存していると backtest と live が別モデルになり、改善の有無を判定できない。
    """
    from predictor.features import compute_features
    from predictor.rules import _score_one

    conn = _ro_conn()
    try:
        sample = _sample_race(conn)
        if sample is None:
            pytest.skip("発走後データ入りの実レースが見つからない")
        race, horses = sample
        # 汚染が起きうる条件であることを先に確認 (でないとテストが空振りする)
        assert any(post_race_fields_present(h) for h in horses), (
            "この race には発走後データが無く、パリティ検査の意味がない"
        )
        diffs = []
        for h in horses:
            raw_score, _ = _score_one(h, compute_features(conn, h, race, cache={}))
            masked = mask_post_race(h)
            m_score, _ = _score_one(masked, compute_features(conn, masked, race, cache={}))
            if abs(raw_score - m_score) > 1e-9:
                diffs.append((h.get("horse_num"), round(raw_score, 2), round(m_score, 2)))
    finally:
        conn.close()

    assert not diffs, (
        "発走後列の有無でルールスコアが変わる = backtest と live が別モデル。\n"
        f"乖離した馬 (馬番, DBそのまま, マスク後): {diffs}\n"
        "特徴が発走後列を参照している。過去走からの事前 proxy に置き換えること "
        "(マスク対象から外して通すのは禁止)。"
    )


@requires_db
def test_same_day_bias_does_not_depend_on_post_race_columns():
    """当日傾向特徴が発走後列に依存しないこと (2026-08-23 検出のリークの回帰)。

    設計意図 (同日の前レース結果から馬場傾向を測る) は発走前情報で成立するが、
    実装が「当該馬の今走の脚質」をキーにしていたため live では常に 0 だった。
    """
    from predictor.features import compute_features

    conn = _ro_conn()
    try:
        sample = _sample_race(conn)
        if sample is None:
            pytest.skip("発走後データ入りの実レースが見つからない")
        race, horses = sample
        bad = []
        for h in horses:
            raw = compute_features(conn, h, race, cache={})
            masked = compute_features(conn, mask_post_race(h), race, cache={})
            for key in ("same_day_bias_score", "same_day_gate_bias_score"):
                if (raw.get(key) or 0) != (masked.get(key) or 0):
                    bad.append((h.get("horse_num"), key,
                                raw.get(key), masked.get(key)))
    finally:
        conn.close()

    assert not bad, (
        "当日傾向特徴が発走後列に依存している (live では常に 0 になる)。\n"
        f"乖離: {bad[:10]}\n"
        "脚質は estimated_leg_code (過去走からの推定) を使うこと。"
    )
