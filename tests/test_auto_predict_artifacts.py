from __future__ import annotations

from scripts import auto_predict


def test_stage_publish_artifacts_includes_prediction_archive(tmp_path, monkeypatch):
    pages = tmp_path / "docs" / "index.html"
    marker = tmp_path / "docs" / "predictions_latest.md"
    archive = (
        tmp_path / "data" / "results" / "2026-07-12" /
        "predictions_source_20260712_100000_gitabc.html"
    )
    pages.parent.mkdir(parents=True)
    pages.write_text("page", encoding="utf-8")
    (pages.parent / ".nojekyll").write_text("", encoding="utf-8")
    marker.write_text("marker", encoding="utf-8")
    archive.parent.mkdir(parents=True)
    archive.write_text("prediction", encoding="utf-8")
    monkeypatch.setattr(auto_predict, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(auto_predict, "PAGES_HTML", pages)
    monkeypatch.setattr(auto_predict, "MARKER", marker)
    calls = []
    monkeypatch.setattr(
        auto_predict.subprocess, "run",
        lambda command, **kwargs: calls.append((command, kwargs)),
    )

    paths = auto_predict._stage_publish_artifacts(
        "20260712", sync_status_path=tmp_path / "missing_status.json"
    )

    assert archive in paths
    assert str(archive) in calls[0][0]
    assert calls[0][1]["check"] is True


def test_stage_publish_artifacts_uses_archive_from_sync_status(tmp_path, monkeypatch):
    pages = tmp_path / "docs" / "index.html"
    marker = tmp_path / "docs" / "predictions_latest.md"
    archive = tmp_path / "custom_archive" / "actual_generated.html"
    status_path = tmp_path / "icloud" / "_sync_status.json"
    pages.parent.mkdir(parents=True)
    pages.write_text("page", encoding="utf-8")
    (pages.parent / ".nojekyll").write_text("", encoding="utf-8")
    marker.write_text("marker", encoding="utf-8")
    archive.parent.mkdir(parents=True)
    archive.write_text("prediction", encoding="utf-8")
    status_path.parent.mkdir(parents=True)
    status_path.write_text(
        __import__("json").dumps({"repository_archive": str(archive)}),
        encoding="utf-8",
    )
    monkeypatch.setattr(auto_predict, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(auto_predict, "PAGES_HTML", pages)
    monkeypatch.setattr(auto_predict, "MARKER", marker)
    calls = []
    monkeypatch.setattr(
        auto_predict.subprocess, "run",
        lambda command, **kwargs: calls.append((command, kwargs)),
    )

    paths = auto_predict._stage_publish_artifacts(
        "20260712", sync_status_path=status_path
    )

    assert archive in paths
    assert str(archive) in calls[0][0]


def _entry_db(path, days_with_entries=(), days_scheduled=(), placeholder_days=()):
    """races / horse_races だけを持つ最小 DB を作る (出走馬ゲートのテスト用)。"""
    import sqlite3

    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE races (race_year TEXT, race_month_day TEXT, track_code TEXT,"
        " kaiji TEXT, nichiji TEXT, race_num TEXT)"
    )
    conn.execute(
        "CREATE TABLE horse_races (race_year TEXT, race_month_day TEXT, track_code TEXT,"
        " kaiji TEXT, nichiji TEXT, race_num TEXT, horse_num TEXT)"
    )
    for day in set(days_scheduled) | set(days_with_entries) | set(placeholder_days):
        for race_num in ("01", "02"):
            conn.execute(
                "INSERT INTO races VALUES (?,?,'05','01','01',?)",
                (day[:4], day[4:], race_num),
            )
            if day in days_with_entries:
                conn.execute(
                    "INSERT INTO horse_races VALUES (?,?,'05','01','01',?, '01')",
                    (day[:4], day[4:], race_num),
                )
            elif day in placeholder_days:
                # 枠順未確定プレースホルダ ('00') は出走馬として数えない
                conn.execute(
                    "INSERT INTO horse_races VALUES (?,?,'05','01','01',?, '00')",
                    (day[:4], day[4:], race_num),
                )
    conn.commit()
    return conn


def test_entry_coverage_ignores_placeholder_horse_rows(tmp_path):
    """'00' プレースホルダだけのレースは「出走馬あり」に数えない。"""
    db = tmp_path / "t.db"
    conn = _entry_db(db, days_with_entries=("20260822",), placeholder_days=("20260823",))

    assert auto_predict._entry_coverage(conn, "20260822") == (2, 2)
    assert auto_predict._entry_coverage(conn, "20260823") == (0, 2)
    conn.close()


def test_main_aborts_without_publishing_when_entries_missing(tmp_path, monkeypatch):
    """出走馬未取り込みなら generator を呼ばず exit 2 で戻る。

    2026-07-25 / 08-01 に全 36 レース「出走馬未取得」の空ページを publish して
    その日の予想を失った事故の回帰テスト。
    """
    from datetime import date

    today = date.today().strftime("%Y%m%d")
    db = tmp_path / "t.db"
    _entry_db(db, days_scheduled=(today,)).close()
    monkeypatch.setattr(auto_predict, "DB_PATH", str(db))
    ran = []
    monkeypatch.setattr(
        auto_predict.subprocess, "run",
        lambda command, **kwargs: ran.append(command),
    )
    notified = []
    monkeypatch.setattr(auto_predict, "notify_discord", lambda text: notified.append(text) or True)
    monkeypatch.setattr("sys.argv", ["auto_predict"])

    rc = auto_predict.main()

    assert rc == 2
    assert ran == [], "generator / git を一切呼ばない"
    assert notified and "出走馬" in notified[0]


def test_main_proceeds_when_entries_are_present(tmp_path, monkeypatch):
    """出走馬がそろっていればゲートを通過する (--dry-run で generator 前に停止)。"""
    from datetime import date

    today = date.today().strftime("%Y%m%d")
    db = tmp_path / "t.db"
    _entry_db(db, days_with_entries=(today,)).close()
    monkeypatch.setattr(auto_predict, "DB_PATH", str(db))
    ran = []
    monkeypatch.setattr(
        auto_predict.subprocess, "run",
        lambda command, **kwargs: ran.append(command),
    )
    monkeypatch.setattr("sys.argv", ["auto_predict", "--dry-run"])

    assert auto_predict.main() == 0
    assert ran == []


def test_generates_today_only_not_tomorrow(tmp_path, monkeypatch):
    """生成対象は今日のみ (2026-09-13 日別化)。

    以前は今日+明日を 1 ページに出していたが、JRA の出馬表は前日確定なので
    土曜朝の時点で日曜分は大半が「出走馬未取得」になり、スマホで見ると空レースが
    並んで当日分が埋もれていた (実測: 前日先出し分は毎回 2R だけ・オッズ欠損 100%
    で、答え合わせにも使えていない)。翌日分は翌朝の起動で生成されるので
    取りこぼさない。
    """
    from datetime import date, timedelta

    today = date.today().strftime("%Y%m%d")
    tomorrow = (date.today() + timedelta(days=1)).strftime("%Y%m%d")
    db = tmp_path / "t.db"
    # 今日も明日も開催日 (= 一括生成の条件が揃っている状態)
    _entry_db(db, days_with_entries=(today, tomorrow)).close()
    monkeypatch.setattr(auto_predict, "DB_PATH", str(db))
    ran = []
    monkeypatch.setattr(
        auto_predict.subprocess, "run",
        lambda command, **kwargs: ran.append(command),
    )
    monkeypatch.setattr("sys.argv", ["auto_predict", "--dry-run"])
    printed = []
    monkeypatch.setattr("builtins.print", lambda *a, **k: printed.append(" ".join(map(str, a))))

    assert auto_predict.main() == 0

    line = next(p for p in printed if p.startswith("generate:"))
    assert today in line, f"今日を対象にする (got: {line})"
    assert tomorrow not in line, f"翌日分は含めない (got: {line})"


def test_completion_message_is_single_day_with_weekday():
    """Discord 通知は「1 日分 + 曜日」で出す (2026-09-13 日別化)。

    日別化で対象日が常に 1 日になったため、従来の「09/12〜09/13」という
    範囲表記は同じ日を 2 回書くだけになる。ユーザは Discord の通知だけを見て
    「どっちの日の予想が出たのか」を判断するので、曜日を必ず添える。
    """
    msg = auto_predict._completion_message("20260913", 24, "lgbm-v6", True)

    assert "2026/09/13(日)" in msg, msg
    assert "(24R, lgbm-v6)" in msg
    assert "〜" not in msg, f"範囲表記に戻っている: {msg}"
    # 土曜も曜日が正しく出る (weekday() のオフセット間違いを捕まえる)
    assert "2026/09/12(土)" in auto_predict._completion_message(
        "20260912", 12, "lgbm-v6", True)


def test_completion_message_always_carries_observation_only_notice():
    """「観察専用」の一文が通知から落ちないこと。

    現状のモデルは 1 番人気ベタ買い (79%) に負けており (◎ベタ 71.5%)、
    利益エッジは未証明。通知だけを見た人が実弾の根拠と誤読すると
    そのまま資金喪失につながるので、文面の必須要素として固定する。
    """
    for push_ok in (True, False):
        msg = auto_predict._completion_message("20260913", 24, "lgbm-v6", push_ok)
        assert "観察専用" in msg, msg
        assert "エッジは未証明" in msg


def test_completion_message_reports_push_failure():
    """push に失敗したら Web 版が未更新であることを通知に書く。"""
    ok = auto_predict._completion_message("20260913", 24, "v", True)
    ng = auto_predict._completion_message("20260913", 24, "v", False)
    assert "数分で更新" in ok
    assert "push 失敗" in ng and "手動確認要" in ng
