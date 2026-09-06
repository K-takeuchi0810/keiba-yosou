from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

from web.generator import _odds_fetched_time, _top_probability_horse_num
from web.publish_safety import assess_race_completeness


ROOT = Path(__file__).resolve().parent.parent


def _prediction(num: str, mark: str, probability: float) -> SimpleNamespace:
    return SimpleNamespace(
        horse_num=num,
        mark=mark,
        win_probability=probability,
    )


def test_top_probability_marker_only_when_it_differs_from_favorite():
    mismatched = [
        _prediction("01", "◎", 0.24),
        _prediction("02", "○", 0.31),
        _prediction("03", "▲", 0.18),
    ]
    aligned = [
        _prediction("01", "◎", 0.34),
        _prediction("02", "○", 0.31),
    ]

    assert _top_probability_horse_num(mismatched) == "02"
    assert _top_probability_horse_num(aligned) is None


def test_race_completeness_uses_only_today_and_strict_threshold():
    """完全性アラートは **今日のみ** を見る (2026-09-06 修正)。

    JRA の出馬表は前日確定なので、土曜の朝に日曜分が空なのは正常。
    翌日分を数えていたため 2 日開催の週末は毎回 empty_race_ratio≈47%
    (72R 中 34R が空) となり、予想生成のたびに WARN が Discord に飛んでいた。
    """
    days = [
        {
            "date": "2026/07/19",
            "races": [
                {"horses": [{"num": "1"}]},
                {"horses": []},
                {"horses": [{"num": "2"}]},
                {"horses": [{"num": "3"}]},
            ],
        },
        {
            "date": "2026/07/20",
            "races": [{"horses": []}],
        },
        {
            "date": "2026/07/18",
            "races": [{"horses": []}] * 10,
        },
    ]

    result = assess_race_completeness(days, today=date(2026, 7, 19))
    assert result["total_races"] == 4, "今日 (7/19) の 4 レースだけ"
    assert result["empty_races"] == 1
    assert result["empty_race_ratio"] == 0.25
    assert result["alert"] is True

    # 翌日 (7/20) が全部空でもアラートにならない = 前日確定の正常状態
    tomorrow_only_empty = assess_race_completeness(
        [days[0], days[1]], today=date(2026, 7, 19), threshold=0.30
    )
    assert tomorrow_only_empty["total_races"] == 4
    assert tomorrow_only_empty["alert"] is False

    exact_threshold = assess_race_completeness(
        days[:1], today=date(2026, 7, 19), threshold=0.25
    )
    assert exact_threshold["empty_race_ratio"] == 0.25
    assert exact_threshold["alert"] is False


def test_odds_fetched_time_formats_iso_and_handles_missing_values():
    assert _odds_fetched_time("2026-07-19T11:23:45+09:00") == "11:23"
    assert _odds_fetched_time("2026-07-19 09:08:00") == "09:08"
    assert _odds_fetched_time(None) is None


def test_auto_predict_task_registers_three_ascii_daily_triggers():
    """08:00 / 09:00 / 11:00 の 3 回起動 (ASCII のみ) を固定する。

    3 本目は 2026-08-22 追加。2026-07-25 / 08-01 は出走馬 (SE) が 09:30 時点でも
    未取り込みで、11:30 頃にようやく届いた。auto_predict は空ページを publish
    しなくなった (exit 2) ため、その日の予想を落とさないための遅い再試行が必要。
    """
    script_path = ROOT / "scripts" / "register_auto_predict_task.ps1"
    raw = script_path.read_bytes()
    content = raw.decode("ascii")

    assert '[string]$StartTime = "08:00"' in content
    assert '[string]$SecondStartTime = "09:00"' in content
    assert '[string]$ThirdStartTime = "11:00"' in content
    assert content.count("New-ScheduledTaskTrigger -Daily -At") == 3
    assert "-Trigger $trigger" in content
    assert "-Trigger $triggers" not in content
