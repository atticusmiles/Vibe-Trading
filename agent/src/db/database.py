"""SQLite database initialization, connection management, and schema migration."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from src.core.config import get_data_dir

_SCHEMA_VERSION = 3

_CREATE_SCHEMA_META = """
CREATE TABLE IF NOT EXISTS _schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    preferences     TEXT DEFAULT '{}',
    settings        TEXT DEFAULT '{}',
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);
"""

_CREATE_SESSION_SEARCH_TABLES = [
    """CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL DEFAULT '',
        started_at REAL NOT NULL,
        message_count INTEGER NOT NULL DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        tool_name TEXT,
        timestamp REAL NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id)",
]

_CREATE_FTS_AND_TRIGGERS = [
    "CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(content, content=messages, content_rowid=id)",
    """CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
        INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
    END""",
    """CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
        INSERT INTO messages_fts(messages_fts, rowid, content)
        VALUES ('delete', old.id, old.content);
    END""",
]


def get_db_path() -> Path:
    return get_data_dir() / "vibe.db"


def _connect() -> sqlite3.Connection:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_db():
    """Yield a database connection with WAL mode and busy timeout."""
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _get_schema_version(conn: sqlite3.Connection) -> int:
    try:
        row = conn.execute("SELECT value FROM _schema_meta WHERE key='version'").fetchone()
        return int(row["value"]) if row else 0
    except Exception:
        return 0


def _set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO _schema_meta (key, value) VALUES ('version', ?)",
        (str(version),),
    )


_MIGRATIONS: list[tuple[int, list[str]]] = [
    (1, [_CREATE_SCHEMA_META, _CREATE_USERS_TABLE]),
    (2, _CREATE_SESSION_SEARCH_TABLES + _CREATE_FTS_AND_TRIGGERS),
    (3, ["ALTER TABLE users DROP COLUMN api_keys"]),
]


def init_db() -> None:
    """Initialize database: create tables and run pending migrations.

    Safe to call multiple times — only runs pending migrations.
    """
    with get_db() as conn:
        current = _get_schema_version(conn)
        for target_version, statements in _MIGRATIONS:
            if current < target_version:
                for stmt in statements:
                    try:
                        conn.execute(stmt)
                    except sqlite3.OperationalError as exc:
                        msg = str(exc).lower()
                        if "already exists" in msg or "no such column" in msg:
                            pass  # table/index already created
                        else:
                            raise
                _set_schema_version(conn, target_version)
