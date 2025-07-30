import asyncio
import logging
import os
from datetime import datetime

import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from .database import Database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GITHUB_API = 'https://api.github.com'
CHECK_INTERVAL = 60  # seconds

class GitHubWatcher:
    def __init__(self, repo: str, db: Database):
        self.repo = repo
        self.db = db

    def _get_last_event_id(self) -> str | None:
        return self.db.get(f'last_event_{self.repo}')

    def _set_last_event_id(self, event_id: str):
        self.db.set(f'last_event_{self.repo}', event_id)

    async def check(self, send_callback):
        url = f'{GITHUB_API}/repos/{self.repo}/events'
        logger.info('Checking GitHub events for %s', self.repo)
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
        except Exception as e:
            logger.error('GitHub request failed: %s', e)
            return
        events = resp.json()
        if not events:
            return
        last_event_id = self._get_last_event_id()
        new_events = []
        for event in events:
            if event['id'] == last_event_id:
                break
            new_events.append(event)
        if new_events:
            self._set_last_event_id(new_events[0]['id'])
            for event in reversed(new_events):
                text = f"New GitHub event on {self.repo}: {event['type']} at {event['created_at']}"
                await send_callback(text)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('GitHub watcher bot is running.')

async def main():
    token = os.getenv('TELEGRAM_TOKEN')
    repo = os.getenv('GITHUB_REPOSITORY')
    if not token or not repo:
        raise SystemExit('TELEGRAM_TOKEN and GITHUB_REPOSITORY must be set')
    db = Database()
    app = ApplicationBuilder().token(token).build()
    watcher = GitHubWatcher(repo, db)
    async def send(text):
        await app.bot.send_message(chat_id=os.getenv('TELEGRAM_CHAT_ID'), text=text)
    async def periodic():
        while True:
            await watcher.check(send)
            await asyncio.sleep(CHECK_INTERVAL)
    app.add_handler(CommandHandler('start', start))
    async with app:
        task = asyncio.create_task(periodic())
        await app.run_polling()
        task.cancel()

if __name__ == '__main__':
    asyncio.run(main())
