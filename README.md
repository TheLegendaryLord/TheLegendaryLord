# Telegram GitHub Watcher Bot

This project provides a simple Telegram bot that monitors a GitHub repository for new events and sends notifications to a chat.

## Requirements

- Python 3.11+
- Telegram bot token
- GitHub repository name (e.g. `owner/repo`)
- Chat ID where notifications will be sent

Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

Set the following environment variables before running:

- `TELEGRAM_TOKEN` – token of your Telegram bot
- `TELEGRAM_CHAT_ID` – chat ID to send messages to
- `GITHUB_REPOSITORY` – repository in `owner/repo` format

Start the bot:

```bash
python -m bot.github_bot
```

The bot stores state in `bot.sqlite` using SQLite. It periodically checks the GitHub Events API and posts new events to the configured Telegram chat.
