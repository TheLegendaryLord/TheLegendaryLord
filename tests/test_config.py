"""Tests for configuration parsing."""

from __future__ import annotations

from pathlib import Path
import json
import pytest

from bridgebot.config import ConfigError, load_config


@pytest.fixture()
def config_file(tmp_path: Path) -> Path:
    """Create a temporary configuration file."""

    data = {
        "telegram": {"bot_token": "token", "chat_id": 123},
        "discord": {"webhook_url": "https://example.com/webhook"},
        "polling_interval": 1.5,
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_load_config_success(config_file: Path) -> None:
    """Configuration loads and validates correctly."""

    config = load_config(config_file)
    assert config.telegram.bot_token == "token"
    assert config.telegram.chat_id == 123
    assert config.discord.webhook_url == "https://example.com/webhook"
    assert config.polling_interval == 1.5


def test_missing_sections(tmp_path: Path) -> None:
    """Missing sections raise an error."""

    path = tmp_path / "config.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)


def test_invalid_discord_config(tmp_path: Path) -> None:
    """Invalid Discord configuration is rejected."""

    data = {
        "telegram": {"bot_token": "token", "chat_id": 123},
        "discord": {},
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)
