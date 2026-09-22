import csv
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

from scripts import build_daily_results

def _html_fragment(
    *,
    horse_name_html: str = "テストホース",
    odds_html: str = '22.9<br><span class="pick-reason">6人気</span>',
    top_pick: str = "",
) -> str:
    """`top_pick` に本命行を渡すと bet_candidate 付きの予想を作れる。

    中止レースで損益が計上されないことを見るには **買い候補が立っている行**が
    要る。立っていないと profit は元から 0 で、`and evaluable` を外しても
    何も変わらず、テストが変異を捕まえられない。
    """
    return f"""
    <details id="race-20260712-02-1" class="race">
      <table class="entries"><tbody><tr>
        <td class="mark-cell" title="テスト"></td>
        <td class="horse-num waku-1">1</td>
        <td class="horse-name">{horse_name_html}</td>
        <td>{odds_html}</td>
      </tr></tbody></table>
      {top_pick}
    </details>
    """


def _run_main(
    tmp_path: Path,
    monkeypatch,
    *,
    html_text: str | None = None,
    expected_rc: int = 0,
    starter_count: int = 18,
    registered_count: int = 18,
    data_div: str = "6",
    confirmed_order: int = 1,
    with_payout: bool = True,
    abnormal_code: str = "0",
    extra_horses: tuple = (),
    dead_heat: bool = False,
) -> Path:
    """`extra_horses` は (horse_num, confirmed_order, abnormal_code) の並び。

    検査したいセルが fixture に無いと、変異を植えても何も変わらず
    テストが素通りする (実際に 6 種を逃した)。返還馬・速報・同着はいずれも
    **同じレースに別の馬が居ること**が前提なので、足せるようにしておく。
    """
    db_path = tmp_path / "daily_results.sqlite3"
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE horse_races (
          race_year TEXT, race_month_day TEXT, track_code TEXT, kaiji TEXT,
          nichiji TEXT, race_num TEXT, horse_num TEXT, horse_name TEXT,
          win_odds INTEGER, win_popularity INTEGER, confirmed_order INTEGER,
          odds_fetched_at TEXT, abnormal_code TEXT
        );
        CREATE TABLE payouts (
          race_year TEXT, race_month_day TEXT, track_code TEXT, kaiji TEXT,
          nichiji TEXT, race_num TEXT, tan_horse_num1 TEXT, tan_payout1 INTEGER,
          tan_horse_num2 TEXT, tan_payout2 INTEGER,
          fuku_horse_num1 TEXT, fuku_payout1 INTEGER,
          fuku_horse_num2 TEXT, fuku_payout2 INTEGER,
          fuku_horse_num3 TEXT, fuku_payout3 INTEGER,
          fuku_horse_num4 TEXT, fuku_payout4 INTEGER,
          fuku_horse_num5 TEXT, fuku_payout5 INTEGER
        );
        CREATE TABLE races (
          race_year TEXT, race_month_day TEXT, track_code TEXT, kaiji TEXT,
          nichiji TEXT, race_num TEXT, race_name TEXT, distance INTEGER,
          track_type_code TEXT, grade_code TEXT, registered_count INTEGER,
          starter_count INTEGER,
          turf_condition TEXT, dirt_condition TEXT, weather_code TEXT,
          start_time TEXT, data_div TEXT
        );
        """
    )
    common = ("2026", "0712", "02", "01", "01", "1")
    conn.execute(
        "INSERT INTO horse_races VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (*common, "00", "プレースホルダ", 0, 0, 0, None, "0"),
    )
    conn.execute(
        "INSERT INTO horse_races VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (*common, "01", "テストホース", 229, 6, confirmed_order,
         "2026-07-12T10:00:00", abnormal_code),
    )
    for hn, order, abn in extra_horses:
        conn.execute(
            "INSERT INTO horse_races VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (*common, hn, f"馬{hn}", 100, 1, order, "2026-07-12T10:00:00", abn),
        )
    if with_payout:
        conn.execute(
            "INSERT INTO payouts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (*common,
             ("02" if dead_heat else "01"), 500,
             ("01" if dead_heat else None), (700 if dead_heat else None),
             "01", 200, None, None, "00", 0, None, None, None, None),
        )
    conn.execute(
        "INSERT INTO races VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            *common, "テスト競走", 1200, "24", "",
            registered_count, starter_count, "", "1", "1", "1100", data_div,
        ),
    )
    conn.commit()
    conn.close()

    html_path = tmp_path / "predictions.html"
    html_path.write_text(html_text or _html_fragment(), encoding="utf-8")
    output_dir = tmp_path / "out"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_daily_results",
            "--date", "20260712",
            "--html", str(html_path),
            "--db", str(db_path),
            "--output-dir", str(output_dir),
        ],
    )
    assert build_daily_results.main() == expected_rc
    return output_dir


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_entries_odds_and_popularity_are_parsed_separately():
    parser = build_daily_results.IndexHtmlParser()
    parser.feed(_html_fragment())

    horse = parser.races[0]["horses"][0]
    assert horse["odds"] == 22.9
    assert horse["popularity"] == 6


def test_entries_data_attributes_take_priority_over_display_text():
    parser = build_daily_results.IndexHtmlParser()
    parser.feed(
        _html_fragment(
            odds_html=(
                '<span class="pick-reason">18人気</span>'
            )
        ).replace(
            "<td><span",
            '<td class="col-odds" data-odds="7.5" data-popularity="3"><span',
        )
    )

    horse = parser.races[0]["horses"][0]
    assert horse["odds"] == 7.5
    assert horse["popularity"] == 3


def test_horse_name_nested_span_does_not_insert_space():
    parser = build_daily_results.IndexHtmlParser()
    parser.feed(_html_fragment(horse_name_html="テスト<span>ホース</span>"))

    assert parser.races[0]["horses"][0]["name"] == "テストホース"


def test_popularity_only_cell_does_not_become_odds():
    parser = build_daily_results.IndexHtmlParser()
    parser.feed(
        _html_fragment(
            odds_html='<span class="pick-reason">6人気</span>'
        )
    )

    horse = parser.races[0]["horses"][0]
    assert horse["odds"] is None
    assert horse["popularity"] == 6


def test_placeholder_horse_num_00_is_excluded(tmp_path, monkeypatch):
    output_dir = _run_main(tmp_path, monkeypatch)

    for name in ("final_odds.csv", "race_results.csv"):
        rows = _read_csv(output_dir / name)
        assert len(rows) == 1
        assert {row["horse_num"] for row in rows} == {"1"}


def test_race_num_is_zero_padded_in_every_csv(tmp_path, monkeypatch):
    output_dir = _run_main(tmp_path, monkeypatch)

    for name in (
        "predictions.csv",
        "final_odds.csv",
        "race_results.csv",
        "payouts.csv",
        "evaluation_summary.csv",
    ):
        rows = _read_csv(output_dir / name)
        assert rows
        assert {row["race_num"] for row in rows} == {"01"}


def test_payout_horse_numbers_match_other_csv_representation(tmp_path, monkeypatch):
    output_dir = _run_main(tmp_path, monkeypatch)

    payout = _read_csv(output_dir / "payouts.csv")[0]
    prediction = _read_csv(output_dir / "predictions.csv")[0]
    assert payout["tan_horse_num1"] == prediction["horse_num"] == "1"
    assert payout["fuku_horse_num1"] == prediction["horse_num"]
    assert payout["fuku_horse_num3"] == ""


def test_quality_gate_rejects_out_of_range_popularity(tmp_path, monkeypatch, capsys):
    output_dir = _run_main(
        tmp_path,
        monkeypatch,
        html_text=_html_fragment(
            odds_html='77.3<br><span class="pick-reason">310人気</span>'
        ),
        expected_rc=1,
    )

    assert "morning_popularity outside registered/starter limit" in capsys.readouterr().err
    assert not (output_dir / "predictions.csv").exists()


def test_manifest_records_builder_provenance_and_superseded_hash(tmp_path, monkeypatch):
    output_dir = _run_main(tmp_path, monkeypatch)
    manifest_path = output_dir / "manifest.json"
    first_bytes = manifest_path.read_bytes()
    first = json.loads(first_bytes)
    assert first["builder_git_sha"]
    assert isinstance(first["builder_git_dirty"], bool)
    assert first["supersedes_manifest_sha256"] is None
    assert first["warnings"] == {
        # 列を 12 個足したので版数を上げた
        "schema": 3,
        "excluded_placeholder_rows": 1,
        "null_odds_fetched_at_rows": 0,
        "post_start_stamped_rows": 0,
        "post_start_unclassified_rows": 0,
        "morning_popularity_populated_rows": 1,
    }

    _run_main(tmp_path, monkeypatch)
    second = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert second["supersedes_manifest_sha256"] == hashlib.sha256(first_bytes).hexdigest()


def test_race_num_of_is_directly_testable():
    assert build_daily_results.race_num_of(1) == "01"
    assert build_daily_results.race_num_of("12") == "12"


def test_post_start_stamped_rows_counts_only_late_odds():
    races = [{
        "track_code": "02", "kaiji": "01", "nichiji": "01",
        "race_num": "1", "start_time": "1100",
    }]
    horses = [
        {"track_code": "02", "kaiji": "01", "nichiji": "01", "race_num": "1",
         "odds_fetched_at": "2026-07-12T10:59:00"},
        {"track_code": "02", "kaiji": "01", "nichiji": "01", "race_num": "1",
         "odds_fetched_at": "2026-07-12T11:01:00"},
    ]
    assert build_daily_results.count_post_start_stamped_rows(
        horses, races, "20260712"
    ) == 1


def test_post_start_unclassified_counts_missing_or_invalid_start():
    horses = [
        {"track_code": "02", "kaiji": "01", "nichiji": "01", "race_num": "1",
         "odds_fetched_at": "2026-07-12T10:59:00"},
        {"track_code": "02", "kaiji": "01", "nichiji": "01", "race_num": "2",
         "odds_fetched_at": "2026-07-12T10:59:00"},
    ]
    races = [{
        "track_code": "02", "kaiji": "01", "nichiji": "01",
        "race_num": "1", "start_time": "bad",
    }]
    assert build_daily_results.classify_post_start_rows(
        horses, races, "20260712"
    ) == (0, 2)


def test_popularity_quality_gate_allows_withdrawal_gap(tmp_path, monkeypatch):
    output_dir = _run_main(
        tmp_path,
        monkeypatch,
        html_text=_html_fragment(
            odds_html='7.7<br><span class="pick-reason">14人気</span>'
        ),
        starter_count=13,
        registered_count=14,
    )
    assert (output_dir / "predictions.csv").exists()


def test_popularity_quality_gate_rejects_true_abnormality():
    errors = build_daily_results.validate_output_quality(
        [{"race_id": "R1", "horse_num": "1", "morning_popularity": 20}],
        popularity_limit_by_race={
            "R1": (14, "max(starter_count=13, registered_count=14)")
        },
    )
    assert errors == [
        "morning_popularity outside registered/starter limit: 1 rows; "
        "R1 limit=14 (max(starter_count=13, registered_count=14))"
    ]


def test_would_be_candidate_derivation():
    """サスペンド中の仮想買い候補判定 (2026-08-22、収益性監査の指摘)。

    ◎ + 朝1-3人気 + p<=0.40 + EV>1.0 で True。p/EV 欠測は None (判定不能)。
    """
    from scripts.build_daily_results import derive_would_be_candidate

    base = {"mark": "◎", "morning_popularity": 2,
            "win_probability": 0.25, "expected_value": 1.1}
    assert derive_would_be_candidate(base) is True
    assert derive_would_be_candidate({**base, "mark": "○"}) is False
    assert derive_would_be_candidate({**base, "morning_popularity": 5}) is False
    assert derive_would_be_candidate({**base, "win_probability": 0.45}) is False
    assert derive_would_be_candidate({**base, "expected_value": 0.9}) is False
    assert derive_would_be_candidate({**base, "win_probability": None}) is None
    assert derive_would_be_candidate({**base, "morning_popularity": None}) is False


# --- 中止レース: 予想は残すが評価しない -------------------------------
# ここは **production の main() を実際に走らせて出力 CSV を読む**。
# 式を自前で再現して自分と比べる形だと、実装側で `and evaluable` を外しても
# テストは通ってしまう (検証プロセス監査で実証された)。

_BET_PICK = (
    '<div class="pick-line">'
    '<span class="pick-mark">◎</span>'
    '<span class="pick-num">1</span>'
    '<span class="conf-tag">P 30.0%</span>'
    '<span class="conf-tag">EV 1.20</span>'
    '<span class="conf-tag">標準</span>'
    '<span class="bet-tag">買い候補</span>'
    '</div>'
)


def _summary_rows(output_dir):
    return _read_csv(output_dir / "evaluation_summary.csv")


def test_a_cancelled_race_books_no_loss_through_main(tmp_path, monkeypatch):
    """中止レースの買い候補に損益と賭け金が立たないこと (main() 経由)。

    この改修が直した当のバグ。買い候補が立っている行で確かめないと、
    profit は元から 0 で変異を捕まえられない。
    """
    # **中止レースに着順は無い**。confirmed_order=1 の中止レースという
    # 非現実な組合せで試していたため、「中止 かつ 結果なし」という現実の
    # セルが未検査で、分岐の並びを入れ替える変異を逃していた (監査で実証)。
    output_dir = _run_main(
        tmp_path, monkeypatch, data_div="9", confirmed_order=0,
        html_text=_html_fragment(top_pick=_BET_PICK))

    rows = _summary_rows(output_dir)
    assert rows, "行ごと消してはいけない (予想を出した記録は残す)"
    for row in rows:
        assert row["bet_candidate"] in ("True", "true", "1"), (
            "買い候補が立っていないと、この変異を捕まえられない")
        assert row["profit_loss_yen_100unit"] == "0", (
            f"走っていないレースで損益が計上されている: {row}")
        assert row["settled_stake_yen_100unit"] == "0", (
            f"走っていないレースに決済ぶんの賭け金が立っている: {row}")
        assert row["planned_stake_yen_100unit"] == "100", (
            "予想時に買う予定だったという事実まで消してはいけない")
        assert row["evaluable"] == "False"
        assert row["race_status"] == "CANCELLED"
        assert row["evaluation_exclusion_reason"] == "cancelled"
        # 走っていないので「実施日」は空。ここを日付で埋めると、順延先の
        # 結果へ紐付ける誤用 (9/21 予想 → 9/22 結果) の入口になる。
        assert row["actual_execution_date"] in ("", "None"), (
            f"中止レースに実施日が入っている: {row['actual_execution_date']}")


def test_a_running_race_still_books_its_loss_through_main(tmp_path, monkeypatch):
    """実施レースでは従来どおり損益が立つこと (除外しすぎていない対照)。"""
    output_dir = _run_main(
        tmp_path, monkeypatch, data_div="6",
        html_text=_html_fragment(top_pick=_BET_PICK))

    rows = _summary_rows(output_dir)
    bet_rows = [r for r in rows if r["bet_candidate"] in ("True", "true", "1")]
    assert bet_rows, "対照が成立していない (買い候補が無い)"
    for row in bet_rows:
        assert row["settled_stake_yen_100unit"] == "100"
        assert row["planned_stake_yen_100unit"] == "100"
        assert row["profit_loss_yen_100unit"] != "0", (
            "実施レースの損益まで 0 にしている")
        assert row["evaluable"] == "True"
        assert row["race_status"] == "RUN"
        assert row["evaluation_exclusion_reason"] in ("", "None")


def test_manifest_counts_split_evaluable_from_issued(tmp_path, monkeypatch):
    """manifest が発行 N と評価可 N を分けて書くこと (main() 経由)。"""
    import json

    output_dir = _run_main(
        tmp_path, monkeypatch, data_div="9",
        html_text=_html_fragment(top_pick=_BET_PICK))

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    counts = manifest["counts"]

    assert counts["evaluation_rows_total"] >= 1
    assert counts["evaluation_rows_evaluable"] == 0, (
        f"中止しかない日に評価可の行がある: {counts}")
    assert counts["evaluation_rows_excluded"] == counts["evaluation_rows_total"]
    assert counts["evaluation_exclusion_reasons"].get("cancelled") == (
        counts["evaluation_rows_excluded"])


def test_a_race_without_results_is_pending_not_a_loss(tmp_path, monkeypatch):
    """結果がまだ来ていないレースを「不的中・負け」にしないこと。

    中止 (永久除外) と結果未取得 (一時的) を同じ扱いにすると、前者は
    永久に評価から落ち、後者は結果が来ても戻らないまま気付けなくなる。
    ここでは **走ったが結果がまだ取り込まれていない** 状態を作る。
    """
    output_dir = _run_main(
        tmp_path, monkeypatch, data_div="6", confirmed_order=0,
        html_text=_html_fragment(top_pick=_BET_PICK))

    rows = _summary_rows(output_dir)
    assert rows
    for row in rows:
        assert row["race_status"] == "RUN", "中止ではない (走る予定のレース)"
        assert row["result_resolved"] == "False"
        assert row["evaluable"] == "False"
        assert row["evaluation_exclusion_reason"] == "result_not_yet_available", (
            f"中止と同じ理由で潰している: {row['evaluation_exclusion_reason']}")
        assert row["profit_loss_yen_100unit"] == "0", "結果待ちを負けにしている"
        assert row["settled_stake_yen_100unit"] == "0"


def test_a_finished_race_without_payouts_is_not_a_loss(tmp_path, monkeypatch):
    """★ 着順は来たが払戻がまだ、の中間状態を負けにしないこと。

    **ここが次に事故になりやすい境界**。着順と払戻は別のタイミングで届く。
    着順だけで評価可にすると、勝った買い候補の払戻がまだ 0 なので
    `profit = -100` が計上される — 中止レースとまったく同型の事故。
    """
    output_dir = _run_main(
        tmp_path, monkeypatch, data_div="6", confirmed_order=1,
        with_payout=False, html_text=_html_fragment(top_pick=_BET_PICK))

    rows = _summary_rows(output_dir)
    assert rows
    for row in rows:
        assert row["race_status"] == "RUN"
        assert row["result_resolved"] == "True", "着順は届いている"
        assert row["payout_resolved"] == "False", "払戻はまだ"
        assert row["evaluable"] == "False"
        assert row["evaluation_exclusion_reason"] == "payout_not_yet_available", (
            f"結果待ちや中止と同じ理由で潰している: "
            f"{row['evaluation_exclusion_reason']}")
        assert row["profit_loss_yen_100unit"] == "0", (
            "払戻待ちを負けにしている (勝っていても -100 になる経路)")
        assert row["settled_stake_yen_100unit"] == "0", "未決済を分母に入れている"
        assert row["planned_stake_yen_100unit"] == "100", (
            "買う予定だったという事実まで消してはいけない")


def test_payout_arrival_moves_the_race_to_resolved(tmp_path, monkeypatch):
    """払戻が届けば同じレースが resolved へ遷移すること (一時状態であることの確認)。"""
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    pending = _summary_rows(_run_main(
        tmp_path / "a", monkeypatch, data_div="6", confirmed_order=1,
        with_payout=False, html_text=_html_fragment(top_pick=_BET_PICK)))
    arrived = _summary_rows(_run_main(
        tmp_path / "b", monkeypatch, data_div="6", confirmed_order=1,
        with_payout=True, html_text=_html_fragment(top_pick=_BET_PICK)))

    assert pending[0]["evaluation_exclusion_reason"] == "payout_not_yet_available"
    assert pending[0]["evaluable"] == "False"
    assert arrived[0]["evaluation_exclusion_reason"] in ("", "None")
    assert arrived[0]["evaluable"] == "True", "払戻が来ても評価可へ遷移しない"


def test_a_cancelled_race_never_becomes_resolved(tmp_path, monkeypatch):
    """中止は払戻が来ても評価可にならないこと (永久除外)。"""
    rows = _summary_rows(_run_main(
        tmp_path, monkeypatch, data_div="9", confirmed_order=1,
        with_payout=True, html_text=_html_fragment(top_pick=_BET_PICK)))

    assert rows[0]["evaluation_exclusion_reason"] == "cancelled"
    assert rows[0]["evaluable"] == "False"


def test_a_refunded_horse_is_not_a_loss(tmp_path, monkeypatch):
    """出走取消・除外の馬を「外れ −100 円」に数えないこと。

    **馬券は返還される**。レース単位の中止とまったく同型で、こちらは馬単位。
    ★ レースが確定していないと評価対象外になって返還ゲートを一度も通らない。
    別の馬を完走させてレースを確定させる (最初これを忘れて変異を 2 種逃した)。
    """
    output_dir = _run_main(
        tmp_path, monkeypatch, data_div="6", confirmed_order=0,
        abnormal_code="1",                       # ◎ は出走取消
        extra_horses=(("02", 1, "0"), ("03", 2, "0")),  # 他は完走 = レース確定
        html_text=_html_fragment(top_pick=_BET_PICK))

    rows = _summary_rows(output_dir)
    bet = [r for r in rows if r["bet_candidate"] in ("True", "true", "1")]
    assert bet, "買い候補が立っていないと、この変異を捕まえられない"
    for row in bet:
        assert row["evaluable"] == "True", (
            "レースが確定していないと返還ゲートを通らずテストが無意味になる")
        assert row["horse_refunded"] == "True"
        assert row["profit_loss_yen_100unit"] == "0", (
            "返還された馬券を負けに計上している")
        assert row["settled_stake_yen_100unit"] == "0", (
            "返還ぶんが回収率の分母に入っている")
        assert row["planned_stake_yen_100unit"] == "100", (
            "買う予定だったという事実は残す")


def test_a_provisional_result_is_not_final(tmp_path, monkeypatch):
    """速報 (一部だけ着順) を「結果あり」にしないこと。

    1 頭でも着順があれば resolved としていたため、3-5 着までの速報レースが
    evaluable になり、◎ が 4 着以下だと confirmed_order=0 のまま
    「評価済み」と記録された (実データで確認された設計欠陥)。
    """
    # 3 頭中 1 頭だけ着順が入っている = 速報段階
    output_dir = _run_main(
        tmp_path, monkeypatch, data_div="6", confirmed_order=0,
        extra_horses=(("02", 1, "0"), ("03", 0, "0")),
        html_text=_html_fragment(top_pick=_BET_PICK))

    rows = _summary_rows(output_dir)
    assert rows
    for row in rows:
        assert row["result_resolved"] == "False", (
            "着順がそろっていないのに確定扱いしている")
        assert row["evaluation_exclusion_reason"] == "result_not_yet_available"
        assert row["profit_loss_yen_100unit"] == "0"


def test_a_race_with_a_scratch_still_becomes_final(tmp_path, monkeypatch):
    """取消馬が居ても、走った馬が全員そろえば確定になること。

    取消・除外・競走中止の馬にまで着順を要求すると、そのレースは永久に
    「結果待ち」のまま評価されない。除外しすぎの対照。
    """
    output_dir = _run_main(
        tmp_path, monkeypatch, data_div="6", confirmed_order=1,
        extra_horses=(("02", 2, "0"), ("03", 0, "1")),  # 03 は出走取消
        html_text=_html_fragment(top_pick=_BET_PICK))

    rows = _summary_rows(output_dir)
    for row in rows:
        assert row["result_resolved"] == "True", (
            "取消馬に着順を要求して永久に確定しなくなっている")


def test_a_dead_heat_winner_is_paid(tmp_path, monkeypatch):
    """同着の 2 頭目にも払戻が付くこと。

    1 頭目しか拾わないと、同着で勝った買い候補が「払戻 0 = −100 円」になる
    (実 DB に 67 件)。
    """
    output_dir = _run_main(
        tmp_path, monkeypatch, data_div="6", confirmed_order=1,
        extra_horses=(("02", 1, "0"),), dead_heat=True,
        html_text=_html_fragment(top_pick=_BET_PICK))

    # ◎ (1 番) を **同着の 2 頭目** にしてある。1 頭目しか拾わないと
    # 払戻 0 になり、勝っているのに -100 円が計上される。
    by_num = {r["horse_num"]: r for r in _summary_rows(output_dir)}
    assert by_num["1"]["win_payout"] == "700", (
        f"同着 2 頭目の払戻を拾えていない: {by_num['1']['win_payout']}")
    assert by_num["1"]["profit_loss_yen_100unit"] == "600", (
        "同着で勝ったのに損益が正しくない")
