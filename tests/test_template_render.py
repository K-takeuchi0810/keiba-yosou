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
        "odds_fetched_time": "10:05",
        "is_top_p": False,
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
        "predicted_count": 4,
        "empty_count": 0,
        "empty_race_ratio": 0.0,
        "completeness_alert": False,
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


def test_odds_data_attributes_match_index_html_parser_contract(context):
    from scripts.build_daily_results import IndexHtmlParser

    html = _render(context)
    parser = IndexHtmlParser()
    parser.feed(html)

    horse = parser.races[0]["horses"][0]
    assert 'class="col-odds" data-odds="4.2" data-popularity="1"' in html
    assert horse["odds"] == 4.2
    assert horse["popularity"] == 1


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
    assert "買い条件 (1-3 番人気 かつ 予測勝率≤40%)" in html
    assert "下の EV・印は観察用で購入推奨ではありません" in html


def test_stale_suppressed_notice(context):
    """オッズ鮮度切れだけで候補が消えたとき、その旨と件数が表示されること。"""
    context["buy_candidates"] = []
    context["buy_count"] = 0
    context["stale_suppressed"] = 26
    html = _render(context)
    assert "うち 26 件は" in html and "オッズ鮮度切れ" in html


def test_verification_banner_hidden_by_default(context):
    """ignore_odds_freshness が無いか False のとき、警告バナーは出ない。"""
    html = _render(context)
    assert 'class="verification-banner"' not in html
    context["ignore_odds_freshness"] = False
    assert 'class="verification-banner"' not in _render(context)


def test_observation_notice_is_always_visible(context):
    html = _render(context)
    assert 'class="observation-notice" role="note"' in html
    assert "OOS 検証で利益エッジは確認されていません" in html
    assert "回収率 CI 上限 &lt;100%" in html

    context["ignore_odds_freshness"] = True
    verification_html = _render(context)
    assert 'class="observation-notice" role="note"' in verification_html
    assert 'class="verification-banner"' in verification_html


def test_model_legend_explains_marks_probability_and_ev(context):
    html = _render(context)
    assert "◎○▲△☆ = 総合本命度" in html
    assert "P = 校正済み勝率 (LGBM v6 ブレンド、別指標)" in html
    assert "オッズ確定前の P はモデル単独値" in html
    assert "EV は検証で的中回収と結びつかないと確認済 (2026-06)" in html


def test_top_probability_badge_and_visible_favorite_rationale(context):
    context["days"][0]["races"][0]["horses"][1]["is_top_p"] = True
    html = _render(context)
    assert html.count('class="top-p"') == 1
    assert "最高勝率" in html
    assert 'class="head-pick-reason"' in html
    assert "直近3走平均2.0着; 騎手勝率12%" in html


def test_meta_completeness_warning_and_odds_freshness(context):
    context["predicted_count"] = 3
    context["empty_count"] = 1
    context["empty_race_ratio"] = 0.25
    context["completeness_alert"] = True
    context["days"][0]["races"][0]["horses"][0]["odds"] = 0
    html = _render(context)
    assert "予想 3 レース / 出走馬未確定 1" in html
    assert "一部レースは出走馬未確定 (翌日分は当日朝に反映)" in html
    assert 'title="取得 10:05"' in html
    assert "—" in html


def test_verification_banner_visible_when_ignore_odds_freshness(context):
    """ignore_odds_freshness=True のとき、role=alert の強警告バナーが出ること。

    実弾運用 HTML として誤って iCloud 公開しないための視覚的セーフティ。
    """
    context["ignore_odds_freshness"] = True
    html = _render(context)
    assert 'class="verification-banner"' in html
    assert 'role="alert"' in html
    assert "実弾運用には使えません" in html


def test_body_has_verification_mode_class_when_ignore_odds_freshness(context):
    """ignore_odds_freshness=True で <body class="verification-mode"> となり、
    scroll-margin-top が 13.5rem に切替わって verification-banner 高さを吸収できる"""
    context["ignore_odds_freshness"] = True
    html = _render(context)
    assert '<body class="verification-mode">' in html
    assert "body.verification-mode .day-section" in html


def test_body_has_no_verification_mode_class_in_normal_mode(context):
    html = _render(context)
    assert '<body class="verification-mode">' not in html
    assert '<body>' in html
