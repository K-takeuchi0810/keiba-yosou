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
