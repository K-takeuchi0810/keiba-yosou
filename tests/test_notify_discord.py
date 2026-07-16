from __future__ import annotations

from scripts import notify_discord as mod


def test_shared_notifier_posts_expected_message_without_real_network(
    tmp_path, monkeypatch
):
    webhook = tmp_path / "webhook.txt"
    webhook.write_text("https://example.invalid/hook", encoding="utf-8")
    sent = []
    monkeypatch.setattr(mod, "_post_webhook", lambda url, text: sent.append((url, text)))

    assert mod.notify_discord("WARN: test", webhook) is True
    assert sent == [("https://example.invalid/hook", "WARN: test")]


def test_notification_failure_is_best_effort(tmp_path, monkeypatch, capsys):
    webhook = tmp_path / "webhook.txt"
    webhook.write_text("https://example.invalid/hook", encoding="utf-8")
    monkeypatch.setattr(
        mod, "_post_webhook", lambda *_: (_ for _ in ()).throw(OSError("offline"))
    )

    assert mod.notify_discord("WARN: test", webhook) is False
    assert "Discord notification failed" in capsys.readouterr().err
