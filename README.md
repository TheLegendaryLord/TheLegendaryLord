# Telegram ➜ Discord Bridge Bot

A lightweight Python service that forwards messages from a configured Telegram chat to a Discord
channel using either a Discord webhook or bot token.

## Features

- Polls Telegram with the `telebot` library and forwards supported messages to Discord.
- Supports text, links, photos, videos, documents, audio, voice messages, and animations.
- Preserves author names and timestamps in forwarded messages.
- Downloads Telegram attachments and uploads them directly to Discord.
- Works with Discord webhooks or direct bot token/channel combinations.
- Provides structured logging and basic error handling.

## Requirements

- Python 3.12+
- Telegram bot token and chat ID.
- Discord webhook URL **or** bot token plus channel ID.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

## Configuration

Create a JSON configuration file (for example `config.json`) with the following structure:

```json
{
  "telegram": {
    "bot_token": "123456789:ABCDEF...",
    "chat_id": 123456789
  },
  "discord": {
    "webhook_url": "https://discord.com/api/webhooks/..."
  },
  "polling_interval": 2.0
}
```

If you prefer to use a Discord bot token instead of a webhook, provide the `bot_token` and
`channel_id` fields instead of `webhook_url`:

```json
  "discord": {
    "bot_token": "bot-token-value",
    "channel_id": 9876543210
  }
```

Only one sending mode is required: webhook or bot token + channel ID.

## Running the bot

```bash
python -m bridgebot path/to/config.json
```

The bot runs an infinite polling loop suitable for VPS or long-running environments. Configure the
process manager of your choice (systemd, supervisord, Docker, etc.) to keep it alive 24/7.

## Logging

Logs are printed to stdout in the following format:

```
2024-04-10 13:37:00,123 [INFO] bridgebot.bridge: Starting Telegram polling loop
2024-04-10 13:37:05,456 [INFO] bridgebot.forwarder: Forwarded message from Alice
```

## Development

Install development dependencies and run the test suite:

```bash
pip install -r requirements-dev.txt
pytest -q
ruff .
```

The project is formatted with `black` (line length 100) and type hints are required throughout the
codebase.
