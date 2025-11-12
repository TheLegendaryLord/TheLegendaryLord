"""Configuration handling for the Telegram to Discord bridge."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
import json


class ConfigError(Exception):
    """Raised when configuration loading or validation fails."""


@dataclass
class TelegramConfig:
    """Telegram configuration options.

    Attributes:
        bot_token: Token for the Telegram bot provided by BotFather.
        chat_id: Numeric identifier of the Telegram chat to monitor.
    """

    bot_token: str
    chat_id: int


@dataclass
class DiscordConfig:
    """Discord configuration options.

    Attributes:
        webhook_url: Discord webhook URL for posting messages.
        bot_token: Discord bot token used for the HTTP Bot API.
        channel_id: Target Discord channel identifier.
    """

    webhook_url: Optional[str] = None
    bot_token: Optional[str] = None
    channel_id: Optional[int] = None

    def validate(self) -> None:
        """Validate the configuration and raise an error if invalid."""

        if self.webhook_url:
            return
        if self.bot_token and self.channel_id:
            return
        raise ConfigError(
            "Discord configuration requires either a webhook_url or both bot_token and channel_id."
        )


@dataclass
class Config:
    """Combined configuration for the bridge bot."""

    telegram: TelegramConfig
    discord: DiscordConfig
    polling_interval: float = 2.0


def _read_file(path: Path) -> Dict[str, Any]:
    """Read a JSON file and return the parsed content."""

    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:  # pragma: no cover - thin wrapper
        raise ConfigError(f"Configuration file not found: {path}") from exc
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON configuration: {exc}") from exc


def _parse_telegram_config(data: Dict[str, Any]) -> TelegramConfig:
    """Parse the Telegram configuration section."""

    try:
        bot_token = data["bot_token"]
        chat_id = int(data["chat_id"])
    except KeyError as exc:
        raise ConfigError(f"Missing Telegram configuration value: {exc.args[0]}") from exc
    except (TypeError, ValueError) as exc:
        raise ConfigError("chat_id must be an integer") from exc
    if not bot_token:
        raise ConfigError("bot_token must not be empty")
    return TelegramConfig(bot_token=bot_token, chat_id=chat_id)


def _parse_discord_config(data: Dict[str, Any]) -> DiscordConfig:
    """Parse the Discord configuration section."""

    config = DiscordConfig(
        webhook_url=data.get("webhook_url"),
        bot_token=data.get("bot_token"),
        channel_id=_parse_optional_int(data.get("channel_id")),
    )
    config.validate()
    return config


def _parse_optional_int(value: Any) -> Optional[int]:
    """Convert a value to an integer when possible."""

    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError("channel_id must be an integer") from exc


def load_config(path: str | Path) -> Config:
    """Load configuration from a JSON file.

    Args:
        path: Path to the configuration JSON file.

    Returns:
        A validated :class:`Config` object.
    """

    raw = _read_file(Path(path))
    try:
        telegram = _parse_telegram_config(raw["telegram"])
        discord = _parse_discord_config(raw["discord"])
    except KeyError as exc:
        raise ConfigError(f"Missing top-level configuration section: {exc.args[0]}") from exc
    polling_interval = float(raw.get("polling_interval", 2.0))
    return Config(telegram=telegram, discord=discord, polling_interval=polling_interval)
