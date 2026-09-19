"""通知の重複判定の契約テスト (2026-09-19)。

## なぜ要るか

`auto_predict` は Task Scheduler から同じ日に 3 回起動されるので、3 回とも
同じ結果なら同じ本文が 3 通届いていた。監査で 3 回連続の持ち越しになっていた。

抑止を入れると **通知を消してしまう事故**が新たに生まれる。予想生成の中止
通知を握り潰すのが最悪なので、「重複を 1 通許す」より「消す」方が危険という
非対称性をテストで固定する。

指示された 8 ケースをそのまま並べる。
"""
from __future__ import annotations

import json

import pytest

from scripts import notify_dedup
from scripts.notify_dedup import decide, record


def send(notification_type, subject, payload, text, path, delivered=True):
    """本番と同じ順序で 1 通ぶん動かす: 判定 -> 送信 -> **成功したら**記録。

    記録を判定と同時に行うと、送信が失敗したのに「送った」ことになり、次の
    起動で抑止されて通知が永久に消える。その順序をテスト側でも守る。
    """
    d = decide(notification_type, subject, payload, text, path=path)
    if d.should_send and delivered:
        record(notification_type, subject, payload, path=path)
    return d


@pytest.fixture()
def state(tmp_path):
    return tmp_path / "notification_state.json"


def test_1_first_notification_is_sent(state):
    """初回通知 → 送信される。"""
    d = send("generation_complete", "20260919",
               {"n_races": 12}, "本文", path=state)

    assert d.should_send is True
    assert d.reason == "first_time"
    assert d.text == "本文"


def test_2_identical_notification_is_suppressed(state):
    """完全同一通知 → 抑止される。"""
    send("generation_complete", "20260919", {"n_races": 12}, "本文", path=state)

    d = send("generation_complete", "20260919", {"n_races": 12}, "本文",
               path=state)

    assert d.should_send is False
    assert d.reason == "duplicate"


def test_3_changed_field_sends_a_diff(state):
    """同一イベントだが重要項目変更 → 差分通知される。"""
    send("generation_complete", "20260919",
           {"n_races": 12, "push_ok": True}, "本文", path=state)

    d = send("generation_complete", "20260919",
               {"n_races": 24, "push_ok": True}, "新しい本文", path=state)

    assert d.should_send is True
    assert d.reason == "changed"
    assert d.changes == {"n_races": (12, 24)}
    assert "12 -> 24" in d.text
    # 差分だけでなく **全文も** 送る。通知だけを見る運用で文脈が落ちないように。
    assert "新しい本文" in d.text


def test_4_reordering_alone_is_suppressed(state):
    """本質的でない並び順だけ変更 → 抑止される。

    辞書の並びが変わっただけで再通知すると、抑止した意味が無くなる。
    """
    send("artifact_drift_abort", "20260919",
           {"drift": ["a", "b"], "x": 1, "y": 2}, "本文", path=state)

    d = send("artifact_drift_abort", "20260919",
               {"y": 2, "x": 1, "drift": ["a", "b"]}, "本文", path=state)

    assert d.should_send is False, "キーの並びが違うだけで再通知している"


def test_4b_a_changed_timestamp_in_the_body_alone_is_suppressed(state):
    """本文の生成時刻だけが違う → 抑止される。

    本番の本文には生成時刻と URL が入る。**本文一致で重複判定すると 1 通も
    抑止できない**ので、判定は payload だけを見ていること。
    (この観点が抜けていたため、変異テストで「キーを本文にする」欠陥を
     どのテストも捕まえられなかった。)
    """
    send("generation_complete", "20260919", {"n_races": 12},
           "12R 生成完了 (09:03:11)", path=state)

    d = send("generation_complete", "20260919", {"n_races": 12},
               "12R 生成完了 (15:03:47)", path=state)

    assert d.should_send is False, "本文の時刻が違うだけで再通知している"


def test_5_multiple_changes_are_all_reported(state):
    """複数項目変更 → 全変更点が通知される。"""
    send("generation_complete", "20260919",
           {"n_races": 12, "version": "v6", "push_ok": True}, "本文", path=state)

    d = send("generation_complete", "20260919",
               {"n_races": 24, "version": "v7", "push_ok": False}, "本文",
               path=state)

    assert set(d.changes) == {"n_races", "version", "push_ok"}
    for fragment in ("12 -> 24", "v6 -> v7", "True -> False"):
        assert fragment in d.text, f"{fragment} が通知に含まれていない"


def test_6_restart_does_not_resend(state):
    """プロセス再起動 → 同一通知を再送しない。

    状態をメモリだけに持つと、Task Scheduler が別プロセスで起動するたびに
    初回扱いになる。ファイルに残っていることを確かめる。
    """
    send("generation_complete", "20260919", {"n_races": 12}, "本文", path=state)
    assert state.exists(), "状態が永続化されていない"

    # 別プロセス相当: モジュール内の状態を一切共有せず、ファイルだけから判定する
    d = send("generation_complete", "20260919", {"n_races": 12}, "本文",
               path=state)

    assert d.should_send is False


def test_7_a_different_day_is_not_inherited(state):
    """日付変更 → 前日の状態を誤って引き継がない。"""
    send("generation_complete", "20260919", {"n_races": 12}, "本文", path=state)

    d = send("generation_complete", "20260920", {"n_races": 12}, "本文",
               path=state)

    assert d.should_send is True, "対象日が違うのに前日の記録で抑止している"
    assert d.reason == "first_time"


def test_8_corrupt_state_does_not_swallow_the_notification(state):
    """状態ファイル破損 → 通知そのものを消失させない。"""
    state.write_text("{壊れた JSON", encoding="utf-8")

    d = send("coverage_abort", "20260919", {"total": 12}, "中止通知",
               path=state)

    assert d.should_send is True
    assert d.text == "中止通知"
    # 壊れたファイルは書き直され、次回から判定が効く
    assert json.loads(state.read_text(encoding="utf-8"))


def test_unwritable_state_still_sends(tmp_path, monkeypatch):
    """状態を書けない場合も通知を消さない (送る側に倒す)。"""
    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(notify_dedup, "_save", boom)

    d = send("coverage_abort", "20260919", {"total": 12}, "中止通知",
             path=tmp_path / "s.json")

    assert d.should_send is True
    assert d.text == "中止通知"


def test_unreadable_state_fails_open(tmp_path, monkeypatch):
    """状態を読めない場合は fail_open として送る。"""
    def boom(*a, **k):
        raise OSError("io error")

    monkeypatch.setattr(notify_dedup, "_load", boom)

    d = decide("coverage_abort", "20260919", {"total": 12}, "中止通知",
               path=tmp_path / "s.json")

    assert d.should_send is True
    assert d.reason.startswith("fail_open")
    assert d.text == "中止通知"


def test_a_failed_send_is_retried_next_time(state):
    """送信に失敗したら記録しない → 次の起動で再送する。

    **これが一番危ない経路**。判定と同時に記録すると、Discord への POST が
    失敗したのに「送った」ことになり、次の起動で抑止されて通知が永久に
    消える。中止通知でこれが起きると、その日の予想を失ったことに誰も
    気付けない。
    """
    first = send("coverage_abort", "20260919", {"total": 12}, "⚠ 中止",
                 path=state, delivered=False)
    assert first.should_send is True

    second = send("coverage_abort", "20260919", {"total": 12}, "⚠ 中止",
                  path=state)

    assert second.should_send is True, "届いていないのに抑止している"
    assert second.reason == "first_time"

    third = send("coverage_abort", "20260919", {"total": 12}, "⚠ 中止",
                 path=state)
    assert third.should_send is False, "届いた後は抑止すること"


def test_state_path_can_be_redirected(tmp_path, monkeypatch):
    """NOTIFY_STATE_PATH で本番の状態ファイルから切り離せること。

    テストが `main()` を通すと本番の状態に架空の payload が書かれ、当日の
    本物の中止通知が抑止されうる (導入直後に実際に起きた)。
    """
    target = tmp_path / "elsewhere.json"
    monkeypatch.setenv("NOTIFY_STATE_PATH", str(target))

    assert notify_dedup.state_path() == target

    record("coverage_abort", "__test_marker__", {"total": 12})
    assert target.exists()

    # 本番ファイルは実運用で存在しうるので「無いこと」ではなく
    # **書き込まれていないこと** を見る。
    from config import PROJECT_ROOT
    prod = PROJECT_ROOT / "data" / "runtime" / "notification_state.json"
    if prod.exists():
        assert "__test_marker__" not in prod.read_text(encoding="utf-8"), (
            "テストが本番の状態ファイルに書き込んでいる")


def test_different_notification_types_do_not_collide(state):
    """種類が違えば別の通知として扱うこと。"""
    send("coverage_abort", "20260919", {"x": 1}, "中止", path=state)

    d = send("generation_complete", "20260919", {"x": 1}, "完了", path=state)

    assert d.should_send is True


def test_old_entries_are_pruned(state):
    """古い記録は捨てる (ファイルが際限なく育たないこと)。"""
    old = notify_dedup.jst_today()[:4] + "0101"
    state.write_text(json.dumps({
        "generation_complete:19990101": {
            "canonical": "{}", "payload": {}, "date_jst": "19990101"},
    }), encoding="utf-8")

    send("generation_complete", old, {"n": 1}, "本文", path=state)

    kept = json.loads(state.read_text(encoding="utf-8"))
    assert "generation_complete:19990101" not in kept


def test_jst_is_used_not_system_local_time(monkeypatch):
    """「同日」の判定に JST を使うこと。システムのローカル時刻任せにしない。"""
    from datetime import datetime, timedelta, timezone

    # UTC では前日、JST では当日になる時刻
    fixed = datetime(2026, 9, 19, 16, 30, tzinfo=timezone.utc)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz else fixed

    monkeypatch.setattr(notify_dedup, "datetime", FixedDateTime)

    assert notify_dedup.jst_today() == "20260920", (
        "UTC 16:30 は JST では翌日 01:30。JST で判定していない")
    assert notify_dedup.JST.utcoffset(None) == timedelta(hours=9)


# --- 配線側 ---------------------------------------------------------------
# 上のテストは decide() の契約。ここは **auto_predict が本当に抑止するか**。
# payload に生成時刻を入れてしまう、force を配線し忘れる、といった回帰は
# decide() のテストでは 1 件も捕まらない。


@pytest.fixture()
def wired(tmp_path, monkeypatch):
    """_notify を差し替えて、送信された本文を集める。"""
    from scripts import auto_predict

    monkeypatch.setattr(notify_dedup, "state_path", lambda: tmp_path / "s.json")
    sent: list[str] = []
    monkeypatch.setattr(auto_predict, "_notify", lambda text: sent.append(text) or True)
    return auto_predict, sent


def test_three_scheduler_runs_send_one_notification(wired):
    """Task Scheduler が同じ日に 3 回起動しても 1 通しか送らない。

    これが元の苦情そのもの。本文には生成時刻が入るので **毎回違う文字列**に
    なる。それでも 1 通であること。
    """
    auto_predict, sent = wired
    for _ in range(3):
        auto_predict._notify_once(
            "generation_complete", "20260919",
            {"n_races": 12, "version": "v6", "push_ok": True},
            auto_predict._completion_message("20260919", 12, "v6", True))

    assert len(sent) == 1, f"{len(sent)} 通送っている"


def test_a_real_change_still_gets_through(wired):
    """レース数が変われば 2 通目が届く (抑止しすぎない)。"""
    auto_predict, sent = wired
    auto_predict._notify_once("generation_complete", "20260919",
                              {"n_races": 12, "version": "v6", "push_ok": True},
                              "本文 A")
    auto_predict._notify_once("generation_complete", "20260919",
                              {"n_races": 24, "version": "v6", "push_ok": True},
                              "本文 B")

    assert len(sent) == 2
    assert "n_races: 12 -> 24" in sent[1]


def test_force_notify_bypasses_suppression(wired):
    """--force-notify なら抑止しない。

    この引数は docstring に書いてあるのに **実装されていなかった**
    (2026-09-19 発見)。幻の引数を二度と作らないよう固定する。
    """
    auto_predict, sent = wired
    for _ in range(3):
        auto_predict._notify_once("generation_complete", "20260919",
                                  {"n_races": 12}, "本文", force=True)

    assert len(sent) == 3


def test_force_notify_is_an_actual_cli_argument(wired):
    """--force-notify が argparse に存在すること (docstring だけで終わらせない)。"""
    auto_predict, _ = wired
    import contextlib, io

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), pytest.raises(SystemExit):
        monkey = __import__("sys")
        old = monkey.argv
        monkey.argv = ["auto_predict", "--help"]
        try:
            auto_predict.main()
        finally:
            monkey.argv = old

    assert "--force-notify" in buf.getvalue()


def test_the_abort_notification_is_never_lost(wired, monkeypatch):
    """重複判定が壊れても中止通知は届く。

    予想生成の中止を握り潰すのが最悪の事故。判定が例外を出す状況でも
    本文がそのまま送られること。
    """
    auto_predict, sent = wired
    monkeypatch.setattr(notify_dedup, "_load",
                        lambda p: (_ for _ in ()).throw(RuntimeError("boom")))

    auto_predict._notify_once("coverage_abort", "20260919",
                              {"with_entries": 0, "total": 12}, "⚠ 中止")

    assert sent == ["⚠ 中止"]


def test_completion_payload_has_no_time_or_url(wired):
    """生成完了 payload に生成時刻・URL を入れないこと。

    ここが崩れると抑止が全く効かなくなるが、`_notify_once` に payload を
    直接渡すテストでは 1 件も捕まらないので、キー集合を固定する。
    """
    auto_predict, _ = wired
    payload = auto_predict._completion_payload(12, "v6", True)

    assert set(payload) == {"n_races", "version", "push_ok"}, (
        "キーが増えている。生成時刻や URL を足していないか")
    for v in payload.values():
        assert not isinstance(v, (str,)) or "http" not in v


def test_wiring_does_not_record_a_failed_send(tmp_path, monkeypatch):
    """Discord への送信が失敗したら記録せず、次の起動で再送すること。

    `send()` helper ではなく **auto_predict の実配線** を見る。
    `_notify_once` が送信結果を無視して記録すると、helper 側のテストでは
    1 件も捕まらないまま、本番だけで通知が消える。
    """
    from scripts import auto_predict

    monkeypatch.setattr(notify_dedup, "state_path", lambda: tmp_path / "s.json")
    attempts: list[str] = []
    delivered = {"ok": False}
    monkeypatch.setattr(
        auto_predict, "_notify",
        lambda text: (attempts.append(text), delivered["ok"])[1])

    assert auto_predict._notify_once("coverage_abort", "20260919",
                                     {"total": 12}, "⚠ 中止") is False
    assert auto_predict._notify_once("coverage_abort", "20260919",
                                     {"total": 12}, "⚠ 中止") is False
    assert len(attempts) == 2, "失敗した通知が再送されていない"

    delivered["ok"] = True
    assert auto_predict._notify_once("coverage_abort", "20260919",
                                     {"total": 12}, "⚠ 中止") is True
    auto_predict._notify_once("coverage_abort", "20260919",
                              {"total": 12}, "⚠ 中止")
    assert len(attempts) == 3, "届いた後も送り続けている"
