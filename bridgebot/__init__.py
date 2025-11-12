"""Bridgebot package for forwarding Telegram messages to Discord."""

from bridgebot.bridge import BridgeBot
from bridgebot.config import Config, DiscordConfig, TelegramConfig, load_config

__all__ = [
    "BridgeBot",
    "Config",
    "DiscordConfig",
    "TelegramConfig",
    "load_config",
]
