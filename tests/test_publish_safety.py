"""web.publish_safety と publish_to_icloud の検証 HTML ガードのテスト。

判定マトリクス (ignore × publish × allow_stale) の全 8 セルを網羅し、
CLI / GUI / Python 直 import の 3 経路で挙動が一致することを保証する。
"""
from __future__ import annotations

import pytest


from web.publish_safety import (
    STALE_PUBLISH_WARNING,
    VERIFICATION_BANNER_MARKER,
    assert_safe_to_publish,
)


@pytest.fixture(autouse=True)
def _archive_root(tmp_path, monkeypatch):
    from web import generator
    monkeypatch.setattr(generator, "PREDICTION_ARCHIVE_ROOT", tmp_path / "results")


def test_normal_mode_publish_true_returns_unchanged():
    decision, warn = assert_safe_to_publish(
        ignore_odds_freshness=False, publish=True, allow_stale=False
    )
    assert decision is True
    assert warn is None


def test_normal_mode_publish_false_returns_unchanged():
    decision, warn = assert_safe_to_publish(
        ignore_odds_freshness=False, publish=False, allow_stale=False
    )
    assert decision is False
    assert warn is None


def test_verification_mode_no_publish_is_safe():
    decision, warn = assert_safe_to_publish(
        ignore_odds_freshness=True, publish=False, allow_stale=False
    )
    assert decision is False
    assert warn is None


def test_verification_mode_publish_without_allow_stale_blocks():
    """検証モード + publish=True + allow_stale=False は publish=False に倒し warning"""
    decision, warn = assert_safe_to_publish(
        ignore_odds_freshness=True, publish=True, allow_stale=False
    )
    assert decision is False
    assert warn == STALE_PUBLISH_WARNING


def test_verification_mode_publish_with_allow_stale_is_explicit_ok():
    """allow_stale=True で明示解除された場合のみ publish 通過"""
    decision, warn = assert_safe_to_publish(
        ignore_odds_freshness=True, publish=True, allow_stale=True
    )
    assert decision is True
    assert warn is None


def test_allow_stale_without_verification_mode_is_noop():
    """通常モードで allow_stale=True を渡してもただの publish。warning なし。"""
    decision, warn = assert_safe_to_publish(
        ignore_odds_freshness=False, publish=True, allow_stale=True
    )
    assert decision is True
    assert warn is None


def test_publish_to_icloud_refuses_verification_banner_html(tmp_path, monkeypatch):
    """index.html に verification-banner が含まれていたら StalePublishRefused"""
    from web import generator

    web_dist = tmp_path / "dist"
    web_dist.mkdir()
    (web_dist / "index.html").write_text(
        '<!DOCTYPE html><html><body>'
        '<div class="verification-banner">⚠ 検証モード</div>'
        '</body></html>',
        encoding="utf-8",
    )
    monkeypatch.setattr(generator, "WEB_DIST", web_dist)
    monkeypatch.setattr(generator, "ICLOUD_PUBLISH_DIR", tmp_path / "icloud")

    with pytest.raises(generator.StalePublishRefused):
        generator.publish_to_icloud()


def test_publish_to_icloud_allows_verification_banner_when_allow_stale(tmp_path, monkeypatch):
    """allow_stale=True で明示的に許可されれば公開が通る"""
    from web import generator

    web_dist = tmp_path / "dist"
    web_dist.mkdir()
    (web_dist / "index.html").write_text(
        '<!DOCTYPE html><html><body>'
        '<div class="verification-banner">⚠ 検証モード</div>'
        '</body></html>',
        encoding="utf-8",
    )
    icloud = tmp_path / "icloud"
    monkeypatch.setattr(generator, "WEB_DIST", web_dist)
    monkeypatch.setattr(generator, "ICLOUD_PUBLISH_DIR", icloud)

    out = generator.publish_to_icloud(allow_stale=True)
    assert out.exists()
    assert "verification-banner" in out.read_text(encoding="utf-8")


def test_publish_to_icloud_passes_clean_html(tmp_path, monkeypatch):
    """通常モード HTML (banner なし) は普通に公開される"""
    from web import generator

    web_dist = tmp_path / "dist"
    web_dist.mkdir()
    (web_dist / "index.html").write_text(
        '<!DOCTYPE html><html><body><details id="race-20260712-05-1">'
        '<h1>通常モード</h1></details></body></html>',
        encoding="utf-8",
    )
    icloud = tmp_path / "icloud"
    monkeypatch.setattr(generator, "WEB_DIST", web_dist)
    monkeypatch.setattr(generator, "ICLOUD_PUBLISH_DIR", icloud)

    out = generator.publish_to_icloud()
    assert out.exists()
    archives = list((tmp_path / "results" / "2026-07-12").glob(
        "predictions_source_20260712_*_git*.html"
    ))
    assert len(archives) == 1
    assert archives[0].read_bytes() == (web_dist / "index.html").read_bytes()
    status = __import__("json").loads(
        (icloud / "_sync_status.json").read_text(encoding="utf-8")
    )
    assert status["repository_archive"] == str(archives[0])
    assert status["repository_archive_sha256"] == status["source_sha256"]


def test_archive_atomic_copy_removes_partial_file_on_failure(tmp_path, monkeypatch):
    from datetime import datetime
    from web import generator

    source = tmp_path / "index.html"
    source.write_text('<details id="race-20260712-05-1">ok</details>', encoding="utf-8")
    monkeypatch.setattr(generator, "PREDICTION_ARCHIVE_ROOT", tmp_path / "results")
    monkeypatch.setattr(generator, "_build_version_snapshot", lambda: {"git_sha": "abc123"})

    def fail_mid_copy(_source, temporary):
        temporary.write_bytes(b"partial")
        raise OSError("disk full")

    monkeypatch.setattr(generator.shutil, "copy2", fail_mid_copy)
    with pytest.raises(OSError):
        generator._archive_prediction_html(source, datetime(2026, 7, 12, 10, 0))
    assert not list((tmp_path / "results").rglob("*.html"))
    assert not list((tmp_path / "results").rglob("*.tmp"))


def test_publish_continues_when_repository_archive_fails(tmp_path, monkeypatch, caplog):
    from web import generator

    web_dist = tmp_path / "dist"
    web_dist.mkdir()
    (web_dist / "index.html").write_text("<html>clean</html>", encoding="utf-8")
    icloud = tmp_path / "icloud"
    monkeypatch.setattr(generator, "WEB_DIST", web_dist)
    monkeypatch.setattr(generator, "ICLOUD_PUBLISH_DIR", icloud)
    monkeypatch.setattr(
        generator, "_archive_prediction_html",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("archive offline")),
    )
    notifications = []
    monkeypatch.setattr(
        generator, "_notify_archive_failure", notifications.append
    )

    out = generator.publish_to_icloud()
    status = __import__("json").loads(
        (icloud / "_sync_status.json").read_text(encoding="utf-8")
    )
    assert out.exists()
    assert status["repository_archive"] is None
    assert status["repository_archive_sha256"] is None
    assert "repository prediction archive failed" in caplog.text
    assert notifications == [
        "WARN: repository prediction archive failed; iCloud publish continued"
    ]


def test_publish_records_completeness_and_notifies_best_effort(tmp_path, monkeypatch):
    from web import generator

    web_dist = tmp_path / "dist"
    web_dist.mkdir()
    (web_dist / "index.html").write_text(
        '<!DOCTYPE html><html><head>'
        '<meta name="empty-race-ratio" content="0.250000">'
        '<meta name="completeness-alert" content="1">'
        '</head><body><details id="race-20260719-05-1">ok</details></body></html>',
        encoding="utf-8",
    )
    icloud = tmp_path / "icloud"
    notifications = []
    monkeypatch.setattr(generator, "WEB_DIST", web_dist)
    monkeypatch.setattr(generator, "ICLOUD_PUBLISH_DIR", icloud)
    monkeypatch.setattr(generator, "_notify_incomplete_output", notifications.append)

    generator.publish_to_icloud()
    status = __import__("json").loads(
        (icloud / "_sync_status.json").read_text(encoding="utf-8")
    )

    assert status["empty_race_ratio"] == 0.25
    assert status["completeness_alert"] is True
    assert notifications == [
        "WARN: prediction output incomplete: empty_race_ratio=25.0% (>20%); "
        "some near-term races have no entries"
    ]


def test_verification_banner_marker_matches_template_output():
    """VERIFICATION_BANNER_MARKER (publish_safety) と template (index.html.j2)
    の class 名が一致することの integration test。
    どちらかを変更したときに、もう片方が気付かず publish ガードが沈黙する
    変更失敗モードを CI で検出する。
    """
    from pathlib import Path
    tpl = Path(__file__).resolve().parent.parent / "web" / "templates" / "index.html.j2"
    content = tpl.read_text(encoding="utf-8")
    assert VERIFICATION_BANNER_MARKER in content, (
        f"VERIFICATION_BANNER_MARKER={VERIFICATION_BANNER_MARKER!r} が "
        f"web/templates/index.html.j2 に見つからない。template の class 名と "
        f"publish_safety の定数が同期していない"
    )


def test_marker_is_used_by_publish_to_icloud_scanner():
    """publish_to_icloud のスキャナが VERIFICATION_BANNER_MARKER 定数を参照
    していることをソース上で確認 (リテラル直書きへの回帰を防ぐ)。
    """
    from pathlib import Path
    gen = Path(__file__).resolve().parent.parent / "web" / "generator.py"
    source = gen.read_text(encoding="utf-8")
    assert "VERIFICATION_BANNER_MARKER" in source, (
        "web/generator.py が VERIFICATION_BANNER_MARKER を import していない。"
        "marker 直書き (= class 名変更で publish ガードが沈黙する変更失敗モード) "
        "への回帰を疑う"
    )
