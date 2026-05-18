"""Database migration for datasources tables.

Creates flash_news_raw and news_digests in ~/.vibe-trading/vibe.db.
Idempotent — safe to run multiple times.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path.home() / ".vibe-trading" / "vibe.db"

_MIGRATIONS = [
    """\
CREATE TABLE IF NOT EXISTS flash_news_raw (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT NOT NULL,
    content      TEXT,
    level        TEXT,
    source       TEXT NOT NULL DEFAULT 'cls',
    published_at TEXT NOT NULL,
    fetched_at   TEXT DEFAULT (datetime('now')),
    UNIQUE(title, published_at)
)""",
    """\
CREATE TABLE IF NOT EXISTS news_digests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    digest_date TEXT NOT NULL,
    content     TEXT NOT NULL,
    summary     TEXT,
    created_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(user_id, digest_date)
)""",
]


def run_migrations() -> None:
    """Apply all pending migrations."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    try:
        for sql in _MIGRATIONS:
            conn.execute(sql)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    run_migrations()
    print(f"Migrations applied to {DB_PATH}")
