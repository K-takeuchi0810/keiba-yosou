"""index.html.j2 の render smoke test (P22-2, 2026-06-12)。

テンプレート側にロジック (day.buy_count / top_picks[0] プレビュー /
アンカー生成など) が増えたため、最小 fixture で 1 回 render を通し、
- 参照キーの typo (StrictUndefined で即検出)
- 新規セクションの出力欠落
を pytest で恒久ブロックする (code-quality-reviewer P22 提案 1)。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader, StrictUndefined

TEMPLATES = Path(__file__).resolve().parent.parent / "web" / "templates"


def _horse(num: int, mark: str = "") -> dict:
    return {
        "mark": mark,
        "waku": (num + 1) // 2,
        "num": str(num),
        "name": f"テストホース{num}",
        "odds": 4.2,
        "popularity": num,
        "sex": "牡",
        "age": 3,
        "burden": 57.0,
        "jockey": "テスト騎手",
        "trainer": "テスト調教師",
        "rationale": "直近3走平均2.0着" if mark else "",
    }


def _top_pick(num: int, mark: str = "◎") -> dict:
    return {
        "mark": mark,
        "num": str(num),
        "name": f"テストホース{num}",
        "ticket": f"単勝 {num}番",
        "odds": 4.2,
        "popularity": 2,
        "win_probability": 0.21,
        "expected_value": 1.1,
        "confidence": "有力",
        "bet_candidate": mark == "◎",
        "rationale": "直近3走平均2.0着; 騎手勝率12%",
    }


def _race(num: int, has_bet: bool = False) -> dict:
    top_picks = [
        _top_pick(1),
        _top_pick(2, "○"),
        _top_pick(3, "▲"),
        _top_pick(4, "△"),
        _top_pick(5, "☆"),
    ]
    return {
        "anchor": f"race-20260613-05-{num}",
        "race_num": num,
        "race_name": f"テスト特別{num}",
        "grade": "" if num > 1 else "G3",
        "surface": "芝",
        "surface_class": "turf",
        "distance": 1600,
        "start_time": "10:10",
        "has_bet": has_bet,
        "tentative": num == 2,
        "top_picks": top_picks,
        "bet_picks": [top_picks[0]] if has_bet else [],
        "candidate_picks": top_picks if has_bet else [],
        "candidate_summary": "・".join(p["ticket"] for p in top_picks) if has_bet else "",
        "recommended_tickets": [{
            "category": "本線",
            "bet_type": "単勝",
            "ticket": "単勝 1番",
            "stake_units": 1,
            "stake_yen": 100,
            "result_label": "的中 払戻 420円",
            "hit": True,
            "hit_combo": "1",
            "return_pct": 420.0,
            "final_odds": 4.2,
        }] if has_bet else [],
        "horses": [_horse(1, "◎"), _horse(2, "○"), _horse(3, "▲"), _horse(4, "△"), _horse(5, "☆")],
    }


def _day(date: str, track: str, buy_count: int) -> dict:
    return {
        "date": date,
        "weekday": "土",
        "track": track,
        "buy_count": buy_count,
        "races": [_race(1, has_bet=buy_count > 0), _race(2)],
    }


@pytest.fixture()
def context() -> dict:
    return {
        "generated_at": "2026-06-12 10:00:00",
        "race_count": 4,
        "buy_count": 1,
        "stale_suppressed": 0,
        "filter_summary": "max_predicted_p≤0.4 / 1-3番人気 / 全場開放",
        "days": [_day("2026/06/13", "東京", 1), _day("2026/06/14", "阪神", 0)],
        "buy_candidates": [{
            "anchor": "race-20260613-05-1",
            "date": "2026/06/13",
            "track": "東京",
            "race_num": 1,
            "race_name": "テスト特別1",
            "start_time": "10:10",
            "mark": "◎",
            "num": "1",
            "name": "テストホース1",
            "ticket": "単勝 1番",
            "odds": 4.2,
            "popularity": 2,
            "win_probability": 0.21,
            "expected_value": 1.1,
            "kelly_fraction": 0.12,
            "recommended_kelly": 0.03,
            "candidate_picks": [_top_pick(i, m) for i, m in [
                (1, "◎"), (2, "○"), (3, "▲"), (4, "△"), (5, "☆")
            ]],
            "candidate_summary": "単勝 1番・単勝 2番・単勝 3番・単勝 4番・単勝 5番",
            "recommended_tickets": [{
                "category": "本線",
                "bet_type": "単勝",
                "ticket": "単勝 1番",
                "stake_units": 1,
                "stake_yen": 100,
                "result_label": "的中 払戻 420円",
                "hit": True,
                "hit_combo": "1",
                "return_pct": 420.0,
                "final_odds": 4.2,
            }],
        }],
        "portfolio_info": {
            "kelly_mode": "quarter",
            "per_bet_cap_pct": 5.0,
            "cap_pct": 25.0,
            "any_over_cap": False,
            "days": [{"date": "2026-06-13", "total_pct": 3.0, "count": 1,
                      "over_cap": False, "scale": 1.0}],
            "unit_yen": 100,
        },
        "version_info": {
            "calibrator_type": "isotonic",
            "calibrator_rule_version": "test",
            "calibrator_generated_at": "2026-06-01",
            "lgbm_rule_version": "v5",
            "lgbm_generated_at": "2026-06-01",
            "git_sha": "deadbeef",
        },
    }


def _render(context: dict) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), undefined=StrictUndefined)
    return env.get_template("index.html.j2").render(**context)


def test_candidate_picks_uses_three_to_five_window():
    from predictor.candidates import (
        mark_single_race_buy_pick,
        select_buy_candidate_picks,
        select_race_buy_pick,
    )

    picks = [{"ticket": f"ticket-{i}"} for i in range(1, 7)]
    assert select_buy_candidate_picks([]) == []
    assert len(select_buy_candidate_picks(picks[:2])) == 2
    assert len(select_buy_candidate_picks(picks[:3])) == 3
    assert len(select_buy_candidate_picks(picks[:6])) == 5
    assert select_race_buy_pick([{"num": "1"}, {"num": "2", "bet_candidate": True}]) == {
        "num": "2",
        "bet_candidate": True,
    }
    marked = mark_single_race_buy_pick(
        [{"num": "1", "bet_candidate": True}, {"num": "2", "bet_candidate": True}],
        {"num": "1", "bet_candidate": True},
    )
    assert [p["bet_candidate"] for p in marked] == [True, False]


def test_render_succeeds_with_strict_undefined(context):
    html = _render(context)
    assert "<!DOCTYPE html>" in html


def test_new_sections_present(context):
    html = _render(context)
    # P22: 開催日ナビ (複数開催時のみ) + 買い候補数バッジ
    assert 'class="day-nav"' in html
    assert "買1" in html  # nav-buy バッジ
    assert 'class="day-buy-count"' in html
    # P22: 閉じたレース行の本命プレビュー
    assert 'class="head-pick"' in html
    assert "◎" in html
    # P22: 推奨投資率の分離表示
    assert 'class="buy-reco-num"' in html
    assert "3.00%" in html  # recommended_kelly 0.03 → 3.00%
    assert "買い目" in html
    assert "単勝 1番" in html
    assert "候補 5頭" in html
    assert "単勝 5番" in html
    assert "推奨買い目" in html
    assert "確定結果・最終オッズ検証" in html
    assert "的中 払戻 420円" in html
    # P22-2: アンカー遷移の sticky ヘッダ被り対策
    assert "scroll-margin-top" in html
    # 印付き行ハイライト (枠番セル除外)
    assert 'class="marked"' in html


def test_day_nav_hidden_for_single_day(context):
    context["days"] = context["days"][:1]
    html = _render(context)
    assert 'class="day-nav"' not in html


def test_no_buy_message_when_empty(context):
    context["buy_candidates"] = []
    context["buy_count"] = 0
    html = _render(context)
    assert 'class="no-buy"' in html


def test_stale_suppressed_notice(context):
    """オッズ鮮度切れだけで候補が消えたとき、その旨と件数が表示されること。"""
    context["buy_candidates"] = []
    context["buy_count"] = 0
    context["stale_suppressed"] = 26
    html = _render(context)
    assert "うち 26 件は" in html and "オッズ鮮度切れ" in html
