"""Telegram to Discord bridge implementation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, List
import logging

from telebot import TeleBot
from telebot.types import Message

from bridgebot.config import Config
from bridgebot.forwarder import Attachment, DiscordForwarder

LOGGER = logging.getLogger(__name__)


class BridgeBot:
    """Bridge that forwards Telegram messages to Discord."""

    SUPPORTED_CONTENT_TYPES = [
        "text",
        "photo",
        "video",
        "document",
        "animation",
        "audio",
        "voice",
    ]

    def __init__(self, config: Config) -> None:
        self._config = config
        self._telegram_bot = TeleBot(config.telegram.bot_token, parse_mode=None)
        self._forwarder = DiscordForwarder(config.discord)
        self._register_handlers()

    def _register_handlers(self) -> None:
        """Register message handler for the Telegram bot."""

        self._telegram_bot.add_message_handler(
            {
                "function": self._handle_message,
                "filters": {
                    "content_types": self.SUPPORTED_CONTENT_TYPES,
                    "func": self._is_target_chat,
                },
            }
        )

    def run(self) -> None:
        """Start polling Telegram for new messages."""

        LOGGER.info("Starting Telegram polling loop")
        self._telegram_bot.infinity_polling(interval=self._config.polling_interval, timeout=20)

    def _is_target_chat(self, message: Message) -> bool:
        """Check whether a message comes from the configured chat."""

        return message.chat.id == self._config.telegram.chat_id

    def _handle_message(self, message: Message) -> None:
        """Forward incoming Telegram messages to Discord."""

        try:
            author = self._resolve_author(message)
            timestamp = datetime.fromtimestamp(message.date, tz=timezone.utc)
            content = self._compose_content(message)
            attachments = list(self._collect_attachments(message))
            self._forwarder.send(
                author=author, timestamp=timestamp, content=content, attachments=attachments
            )
        except Exception as exc:  # pragma: no cover - log and continue
            LOGGER.exception("Failed to forward message: %s", exc)

    @staticmethod
    def _resolve_author(message: Message) -> str:
        """Determine the display name of the Telegram message author."""

        if message.from_user is None:
            return "Unknown"
        name_parts = [message.from_user.first_name or "", message.from_user.last_name or ""]
        name = " ".join(part for part in name_parts if part).strip()
        if not name:
            return message.from_user.username or "Unknown"
        return name

    def _compose_content(self, message: Message) -> str:
        """Build the textual content to send to Discord."""

        pieces: List[str] = []
        if message.text:
            pieces.append(message.text)
        if message.caption:
            pieces.append(message.caption)
        if message.content_type == "voice":
            pieces.append("[Voice message]")
        elif message.content_type == "audio":
            pieces.append("[Audio clip]")
        elif message.content_type == "animation":
            pieces.append("[Animation]")
        elif message.content_type == "document" and not message.text:
            pieces.append(f"[Document] {message.document.file_name or ''}".strip())
        elif message.content_type == "video" and not message.caption:
            pieces.append("[Video]")
        elif message.content_type == "photo" and not message.caption:
            pieces.append("[Photo]")
        if not pieces:
            pieces.append("(no text content)")
        return "\n".join(pieces)

    def _collect_attachments(self, message: Message) -> Iterable[Attachment]:
        """Collect attachments from a Telegram message."""

        if message.photo:
            photo = message.photo[-1]
            yield self._download_attachment(photo.file_id, photo.file_unique_id, "image/jpeg")
        if message.video:
            yield self._download_attachment(
                message.video.file_id,
                message.video.file_unique_id,
                message.video.mime_type or "video/mp4",
                suggested_name=message.video.file_name,
            )
        if message.document:
            yield self._download_attachment(
                message.document.file_id,
                message.document.file_unique_id,
                message.document.mime_type or "application/octet-stream",
                suggested_name=message.document.file_name,
            )
        if message.audio:
            yield self._download_attachment(
                message.audio.file_id,
                message.audio.file_unique_id,
                message.audio.mime_type or "audio/mpeg",
                suggested_name=message.audio.file_name,
            )
        if message.voice:
            yield self._download_attachment(
                message.voice.file_id,
                message.voice.file_unique_id,
                message.voice.mime_type or "audio/ogg",
                suggested_name="voice-message.ogg",
            )
        if message.animation:
            yield self._download_attachment(
                message.animation.file_id,
                message.animation.file_unique_id,
                message.animation.mime_type or "image/gif",
                suggested_name=message.animation.file_name,
            )

    def _download_attachment(
        self,
        file_id: str,
        unique_id: str,
        content_type: str,
        *,
        suggested_name: str | None = None,
    ) -> Attachment:
        """Download a file from Telegram and build an :class:`Attachment`."""

        file_info = self._telegram_bot.get_file(file_id)
        data = self._telegram_bot.download_file(file_info.file_path)
        filename = suggested_name or f"{unique_id}"
        return Attachment(filename=filename, content=data, content_type=content_type)
