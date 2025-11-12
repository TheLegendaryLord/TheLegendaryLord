"""Discord forwarding utilities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Optional
import logging

import requests

from bridgebot.config import DiscordConfig

LOGGER = logging.getLogger(__name__)


@dataclass
class Attachment:
    """File attachment for Discord uploads."""

    filename: str
    content: bytes
    content_type: Optional[str] = None


def format_prefix(author: str, timestamp: datetime) -> str:
    """Format the prefix containing the author and timestamp."""

    formatted_ts = timestamp.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return f"From {author} at {formatted_ts}:"


class DiscordForwarder:
    """Forward messages to Discord using webhook or bot credentials."""

    def __init__(self, config: DiscordConfig) -> None:
        self._config = config
        self._session = requests.Session()

    def send(
        self,
        author: str,
        timestamp: datetime,
        content: str,
        attachments: Optional[Iterable[Attachment]] = None,
    ) -> None:
        """Send a message to Discord."""

        attachments_list = list(attachments or [])
        payload = {"content": f"{format_prefix(author, timestamp)}\n{content}".strip()}
        LOGGER.debug("Dispatching message to Discord: %s", payload["content"])
        if self._config.webhook_url:
            self._send_via_webhook(payload, attachments_list)
        else:
            self._send_via_bot_api(payload, attachments_list)
        LOGGER.info("Forwarded message from %s", author)

    def _send_via_webhook(self, payload: dict, attachments: List[Attachment]) -> None:
        """Send the payload using a Discord webhook."""

        files = self._prepare_files(attachments)
        response = self._session.post(
            self._config.webhook_url, data={"content": payload["content"]}, files=files
        )
        self._handle_response(response)

    def _send_via_bot_api(self, payload: dict, attachments: List[Attachment]) -> None:
        """Send the payload using the Discord Bot API."""

        if not (self._config.bot_token and self._config.channel_id):  # pragma: no cover - guard
            raise RuntimeError("Bot API configuration is incomplete")
        url = f"https://discord.com/api/v10/channels/{self._config.channel_id}/messages"
        headers = {"Authorization": f"Bot {self._config.bot_token}"}
        data = {"content": payload["content"]}
        files = self._prepare_files(attachments)
        response = self._session.post(url, data=data, headers=headers, files=files)
        self._handle_response(response)

    def _prepare_files(self, attachments: List[Attachment]) -> Optional[List[tuple]]:
        """Prepare multipart files payload for Discord uploads."""

        if not attachments:
            return None
        files = []
        for index, attachment in enumerate(attachments):
            files.append(
                (
                    f"files[{index}]",
                    (
                        attachment.filename,
                        attachment.content,
                        attachment.content_type or "application/octet-stream",
                    ),
                )
            )
        return files

    @staticmethod
    def _handle_response(response: requests.Response) -> None:
        """Validate the HTTP response from Discord."""

        if response.status_code >= 400:
            LOGGER.error("Discord API error: %s - %s", response.status_code, response.text)
            response.raise_for_status()
