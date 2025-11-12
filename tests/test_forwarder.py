"""Tests for the Discord forwarder."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List
import pytest

from bridgebot.config import DiscordConfig
from bridgebot.forwarder import Attachment, DiscordForwarder, format_prefix


class DummyResponse:
    """A fake response object for testing."""

    def __init__(self, status_code: int = 200, text: str = "OK") -> None:
        self.status_code = status_code
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:  # pragma: no cover - not triggered in tests
            raise RuntimeError("HTTP error")


class DummySession:
    """A fake requests session that captures payloads."""

    def __init__(self) -> None:
        self.calls: List[dict] = []

    def post(self, url: str, data=None, headers=None, files=None):  # type: ignore[override]
        self.calls.append({"url": url, "data": data, "headers": headers, "files": files})
        return DummyResponse()


@pytest.fixture()
def dummy_session(monkeypatch: pytest.MonkeyPatch) -> DummySession:
    """Patch requests.Session to return a dummy session."""

    session = DummySession()

    class SessionFactory:
        def __call__(self) -> DummySession:
            return session

    monkeypatch.setattr("bridgebot.forwarder.requests.Session", SessionFactory())
    return session


def test_format_prefix() -> None:
    """Formatting includes the UTC timestamp."""

    timestamp = datetime(2024, 5, 4, 12, 0, tzinfo=timezone.utc)
    assert format_prefix("Alice", timestamp) == "From Alice at 2024-05-04 12:00:00 UTC:"


def test_send_via_webhook(dummy_session: DummySession) -> None:
    """Forwarder posts to the webhook endpoint."""

    config = DiscordConfig(webhook_url="https://discord.test")
    forwarder = DiscordForwarder(config)
    forwarder.send(
        author="Alice",
        timestamp=datetime(2024, 5, 4, 12, 0, tzinfo=timezone.utc),
        content="Hello",
        attachments=[Attachment(filename="file.txt", content=b"data", content_type="text/plain")],
    )
    call = dummy_session.calls[0]
    assert call["url"] == "https://discord.test"
    assert "From Alice" in call["data"]["content"]
    assert call["files"][0][0] == "files[0]"


def test_send_via_bot_api(dummy_session: DummySession) -> None:
    """Forwarder posts to the Bot API when configured."""

    config = DiscordConfig(bot_token="token", channel_id=987654321)
    forwarder = DiscordForwarder(config)
    forwarder.send(
        author="Bob",
        timestamp=datetime(2024, 5, 4, 12, 0, tzinfo=timezone.utc),
        content="Hi",
        attachments=[],
    )
    call = dummy_session.calls[0]
    assert call["url"] == "https://discord.com/api/v10/channels/987654321/messages"
    assert call["headers"]["Authorization"] == "Bot token"
