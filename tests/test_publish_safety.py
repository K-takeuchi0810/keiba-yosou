"""web.publish_safety と publish_to_icloud の検証 HTML ガードのテスト。

判定マトリクス (ignore × publish × allow_stale) の全 8 セルを網羅し、
CLI / GUI / Python 直 import の 3 経路で挙動が一致することを保証する。
"""
from __future__ import annotations

import pytest


from web.publish_safety import STALE_PUBLISH_WARNING, assert_safe_to_publish


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
        '<!DOCTYPE html><html><body><h1>通常モード</h1></body></html>',
        encoding="utf-8",
    )
    icloud = tmp_path / "icloud"
    monkeypatch.setattr(generator, "WEB_DIST", web_dist)
    monkeypatch.setattr(generator, "ICLOUD_PUBLISH_DIR", icloud)

    out = generator.publish_to_icloud()
    assert out.exists()
