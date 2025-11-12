"""Tests for the bridge logic."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List
import pytest

from bridgebot.bridge import BridgeBot
from bridgebot.config import Config, DiscordConfig, TelegramConfig


class StubTeleBot:
    """Minimal TeleBot stub for testing."""

    def __init__(self, *_: Any, **__: Any) -> None:
        self.handlers: List[Dict[str, Any]] = []
        self.files: Dict[str, bytes] = {}

    def add_message_handler(self, handler: Dict[str, Any]) -> None:
        self.handlers.append(handler)

    def get_file(self, file_id: str) -> SimpleNamespace:
        return SimpleNamespace(file_path=f"path/{file_id}")

    def download_file(self, file_path: str) -> bytes:
        return self.files.get(file_path, b"data")

    def infinity_polling(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover - not invoked
        raise AssertionError("Polling should not be invoked in tests")


@pytest.fixture(autouse=True)
def patch_telebot(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch TeleBot with a stub for all tests in this module."""

    monkeypatch.setattr("bridgebot.bridge.TeleBot", StubTeleBot)


@pytest.fixture()
def bridge_bot() -> BridgeBot:
    """Create a bridge bot with stubbed dependencies."""

    config = Config(
        telegram=TelegramConfig(bot_token="token", chat_id=1),
        discord=DiscordConfig(webhook_url="https://discord"),
        polling_interval=0.1,
    )
    bot = BridgeBot(config)
    return bot


def make_user(first_name: str = "Alice", last_name: str | None = None, username: str | None = None):
    return SimpleNamespace(first_name=first_name, last_name=last_name, username=username)


def test_resolve_author_prefers_full_name(bridge_bot: BridgeBot) -> None:
    """Author resolution prefers full names."""

    message = SimpleNamespace(from_user=make_user(last_name="Smith"))
    assert bridge_bot._resolve_author(message) == "Alice Smith"


def test_resolve_author_uses_username(bridge_bot: BridgeBot) -> None:
    """Username is used when no names are provided."""

    message = SimpleNamespace(from_user=make_user(first_name="", last_name="", username="alias"))
    assert bridge_bot._resolve_author(message) == "alias"


def test_compose_content_handles_document(bridge_bot: BridgeBot) -> None:
    """Document messages include the file name when no text is present."""

    document = SimpleNamespace(
        file_id="doc", file_unique_id="u_doc", file_name="report.pdf", mime_type="application/pdf"
    )
    message = SimpleNamespace(
        text=None,
        caption=None,
        content_type="document",
        document=document,
        photo=None,
        video=None,
        audio=None,
        voice=None,
        animation=None,
    )
    assert "report.pdf" in bridge_bot._compose_content(message)


def test_collect_attachments_downloads_files(bridge_bot: BridgeBot) -> None:
    """Attachments are downloaded with the correct filenames."""

    bridge_bot._telegram_bot.files["path/photo"] = b"image"
    photo = SimpleNamespace(file_id="photo", file_unique_id="photo_id")
    message = SimpleNamespace(
        photo=[photo],
        video=None,
        document=None,
        audio=None,
        voice=None,
        animation=None,
    )
    attachments = list(bridge_bot._collect_attachments(message))
    assert attachments[0].filename == "photo_id"
    assert attachments[0].content == b"image"
