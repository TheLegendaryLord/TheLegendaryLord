import sqlite3
from contextlib import closing

DB_PATH = 'bot.sqlite'

CREATE_TABLE_SQL = '''\
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
'''

class Database:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        self._init_db()

    def _init_db(self):
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute(CREATE_TABLE_SQL)
            conn.commit()

    def get(self, key: str) -> str | None:
        with closing(sqlite3.connect(self.path)) as conn:
            cur = conn.execute('SELECT value FROM settings WHERE key=?', (key,))
            row = cur.fetchone()
            return row[0] if row else None

    def set(self, key: str, value: str):
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute('REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
            conn.commit()
