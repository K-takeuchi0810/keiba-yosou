"""別の日の予想を、対象日の同じ場・同じ R として採点しないこと (2026-09-26)。

## 何が起きていたか

`build_daily_results` の HTML 解析は、レース ID (`race-20260823-01-11`) の末尾の
「場-R」だけを見て日付を捨てていた。日次分割 (2026-09-13) より前の土曜の HTML には、
先に出馬表が出た日曜の 2 レースが入っていたので、

    8/23 (日) 01-11 の ◎ ルシード → 8/22 (土) 01-11 の 2 番の着順 (8 着) で採点

のように、別の日の予想が対象日の着順で採点されていた。そのレースには ◎ が 2 頭並ぶ。
7/18・8/08・8/15 (と開催の無い日付の 6/12・6/17・7/03) を INVALID、8/22・8/29・9/05・9/12 を
NOT_GENERATED として `docs/EVALUATION_DATA_QUALITY.md` に登録している。

## ここで固定すること

- 予想の日付 == 評価の対象日 を必須にする。別の日のレースは評価しない
- 別の日のレースは **黙って捨てない**: 件数と ID を manifest に残す
- 1 レースに ◎ は最大 1 頭。同じ馬番が 2 回出てこない。崩れていれば評価せずに止める
- レース ID の形が読めなければ止める (日付を確かめられないまま採点しない)

すべて本物の `main()` を通し、出力の CSV と manifest を読む。
"""
from __future__ import annotations

import json

import pytest

from scripts import build_daily_results as bdr
from tests.test_build_daily_results import _read_csv, _run_main


def _race(date: str, track: str, rn: int, horses) -> str:
    """予想 HTML の 1 レース分。`horses` は (馬番, 印, 馬名) の並び。"""
    rows = "".join(
        f'<tr><td class="mark-cell" title="t">{mark}</td>'
        f'<td class="horse-num waku-1">{num}</td>'
        f'<td class="horse-name">{name}</td>'
        f'<td>22.9<br><span class="pick-reason">6人気</span></td></tr>'
        for num, mark, name in horses)
    return (f'<details id="race-{date}-{track}-{rn}" class="race">'
            f'<table class="entries"><tbody>{rows}</tbody></table></details>')


def _summary(out):
    return _read_csv(out / "evaluation_summary.csv")


def _manifest(out):
    return json.loads((out / "manifest.json").read_text(encoding="utf-8"))["counts"]


# --- レース ID の解析 ---------------------------------------------------------

@pytest.mark.parametrize("anchor,want", [
    ("race-20260822-01-11", ("20260822", "01", 11)),
    ("race-20260712-02-1", ("20260712", "02", 1)),
    ("race-2026-07-12-02-1", None),        # 日付に区切りがある (保存済み HTML には無い形)
    ("race-02-1", None),                   # 日付が無い
    ("race-20260712-2-1", None),           # 場が 1 桁
    ("", None),
])
def test_the_anchor_keeps_the_date(anchor, want):
    assert bdr.parse_race_anchor(anchor) == want


# --- 別の日の予想 ---------------------------------------------------------

def test_a_foreign_race_with_the_same_track_and_number_is_not_scored(tmp_path, monkeypatch):
    """★ 翌日の同じ場・同じ R の予想が、対象日の着順で採点されないこと。

    実際に起きた形: 対象日 07/12 の 02-1 と、翌日 07/13 の 02-1 が同じ HTML にある。
    日付を捨てると、翌日の馬が対象日の 02-1 の着順で採点され、◎ が 2 頭並ぶ。
    """
    html = (_race("20260712", "02", 1, [("1", "◎", "テストホース")])
            + _race("20260713", "02", 1, [("1", "◎", "翌日の馬A"), ("2", "○", "翌日の馬B")]))

    out = _run_main(tmp_path, monkeypatch, html_text=html,
                    extra_horses=(("02", 2, "0"),))

    rows = [r for r in _summary(out) if r["race_id"] == "20260712-02-01"]
    names = sorted(r["horse_name"] for r in rows)
    assert "翌日の馬A" not in names and "翌日の馬B" not in names, (
        f"翌日の予想が対象日の着順で採点されている: {names}")
    assert sum(r["mark"] == "◎" for r in rows) == 1
    preds = _read_csv(out / "predictions.csv")
    assert not any(p["horse_name"].startswith("翌日") for p in preds), (
        "翌日の予想が predictions.csv に入っている")


def test_foreign_races_are_recorded_not_silently_dropped(tmp_path, monkeypatch):
    """★ 外した別の日のレースは、件数と ID を manifest に残すこと。"""
    html = (_race("20260712", "02", 1, [("1", "◎", "テストホース")])
            + _race("20260713", "02", 1, [("1", "◎", "A"), ("2", "○", "B")])
            + _race("20260713", "05", 11, [("3", "◎", "C")]))

    counts = _manifest(_run_main(tmp_path, monkeypatch, html_text=html))

    assert counts["foreign_date_races_dropped"] == 2
    assert counts["foreign_date_predictions_dropped"] == 3
    assert counts["foreign_date_race_ids"] == ["20260713-02-01", "20260713-05-11"]
    # HTML に入っていた全体の件数は、別の日の分も含めて残す
    assert counts["html_races_parsed"] == 3
    assert counts["predictions"] == 1


def test_no_foreign_races_means_zero(tmp_path, monkeypatch):
    """対照: 対象日のレースだけなら、別の日の件数は 0 と空。"""
    counts = _manifest(_run_main(
        tmp_path, monkeypatch, html_text=_race("20260712", "02", 1, [("1", "◎", "x")])))

    assert counts["foreign_date_races_dropped"] == 0
    assert counts["foreign_date_predictions_dropped"] == 0
    assert counts["foreign_date_race_ids"] == []


def test_a_past_date_race_is_also_foreign(tmp_path, monkeypatch):
    """翌日だけでなく、前の日の予想も別の日として扱うこと。"""
    html = (_race("20260712", "02", 1, [("1", "◎", "x")])
            + _race("20260711", "02", 1, [("1", "◎", "前日の馬")]))

    out = _run_main(tmp_path, monkeypatch, html_text=html)

    assert _manifest(out)["foreign_date_race_ids"] == ["20260711-02-01"]
    assert not any(r["horse_name"] == "前日の馬" for r in _summary(out))


# --- 評価せずに止める場合 --------------------------------------------------

def _no_outputs(out):
    return not (out / "evaluation_summary.csv").exists() and not (out / "manifest.json").exists()


def test_two_honmei_in_one_race_stops(tmp_path, monkeypatch):
    """★ 1 レースに ◎ が 2 頭いれば、評価を続けずに止めること (何も書き出さない)。"""
    html = _race("20260712", "02", 1, [("1", "◎", "x"), ("2", "◎", "y")])

    out = _run_main(tmp_path, monkeypatch, html_text=html, expected_rc=2,
                    extra_horses=(("02", 2, "0"),))

    assert _no_outputs(out), "前提が崩れているのに成果物を書いた"


def test_a_repeated_horse_number_stops(tmp_path, monkeypatch):
    """同じ馬番が 1 レースに 2 回出てくれば止めること。"""
    html = _race("20260712", "02", 1, [("1", "◎", "x"), ("1", "○", "y")])

    out = _run_main(tmp_path, monkeypatch, html_text=html, expected_rc=2)

    assert _no_outputs(out)


def test_an_unreadable_race_id_stops(tmp_path, monkeypatch):
    """レース ID の形が読めなければ止めること (日付を確かめずに採点しない)。"""
    html = ('<details id="race-02-1" class="race"><table class="entries"><tbody>'
            '<tr><td class="mark-cell" title="t">◎</td><td class="horse-num waku-1">1</td>'
            '<td class="horse-name">x</td><td>22.9</td></tr></tbody></table></details>')

    out = _run_main(tmp_path, monkeypatch, html_text=html, expected_rc=2)

    assert _no_outputs(out)


def test_the_invariants_look_only_at_the_target_date(tmp_path, monkeypatch):
    """別の日のレースの中身 (◎ 2 頭など) では止めないこと。外すだけで記録は残す。

    別の日のレースは評価しないので、その中の矛盾で対象日の評価を止める理由は無い。
    """
    html = (_race("20260712", "02", 1, [("1", "◎", "x")])
            + _race("20260713", "02", 1, [("1", "◎", "A"), ("2", "◎", "B")]))

    counts = _manifest(_run_main(tmp_path, monkeypatch, html_text=html))

    assert counts["foreign_date_races_dropped"] == 1
