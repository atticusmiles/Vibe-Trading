"""SQLite database initialization, connection management, and schema migration."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from src.core.config import get_data_dir

_SCHEMA_VERSION = 4

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


_CREATE_FACT_TABLES = [
    """CREATE TABLE IF NOT EXISTS trends (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL REFERENCES users(id),
        status      TEXT NOT NULL DEFAULT 'adopted' CHECK(status IN ('proposed','adopted','rejected','removed')),
        title       TEXT NOT NULL,
        level       TEXT CHECK(level IN ('long-term','mid-term','short-term')),
        confidence  INTEGER DEFAULT 5 CHECK(confidence BETWEEN 0 AND 10),
        evidence    TEXT,
        created_at  TEXT DEFAULT (datetime('now')),
        updated_at  TEXT DEFAULT (datetime('now')),
        UNIQUE(user_id, title)
    )""",
    """CREATE TABLE IF NOT EXISTS industries (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id             INTEGER NOT NULL REFERENCES users(id),
        status              TEXT NOT NULL DEFAULT 'adopted' CHECK(status IN ('proposed','adopted','rejected','removed')),
        name                TEXT NOT NULL,
        confidence          INTEGER DEFAULT 5 CHECK(confidence BETWEEN 0 AND 10),
        reason              TEXT,
        research_report     TEXT,
        recommended_stocks  TEXT DEFAULT '[]',
        created_at          TEXT DEFAULT (datetime('now')),
        updated_at          TEXT DEFAULT (datetime('now')),
        UNIQUE(user_id, name)
    )""",
    """CREATE TABLE IF NOT EXISTS stocks (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id         INTEGER NOT NULL REFERENCES users(id),
        status          TEXT NOT NULL DEFAULT 'adopted' CHECK(status IN ('proposed','adopted','rejected','removed')),
        name            TEXT NOT NULL,
        code            TEXT NOT NULL,
        confidence      INTEGER DEFAULT 5 CHECK(confidence BETWEEN 0 AND 10),
        industry_name   TEXT,
        position        REAL,
        advice          TEXT,
        target_price    REAL,
        stop_loss       REAL,
        reason          TEXT,
        created_at      TEXT DEFAULT (datetime('now')),
        updated_at      TEXT DEFAULT (datetime('now')),
        UNIQUE(user_id, code)
    )""",
    """CREATE TRIGGER IF NOT EXISTS trg_trends_updated_at
    AFTER UPDATE ON trends FOR EACH ROW
    BEGIN
        UPDATE trends SET updated_at = datetime('now') WHERE id = NEW.id;
    END""",
    """CREATE TRIGGER IF NOT EXISTS trg_industries_updated_at
    AFTER UPDATE ON industries FOR EACH ROW
    BEGIN
        UPDATE industries SET updated_at = datetime('now') WHERE id = NEW.id;
    END""",
    """CREATE TRIGGER IF NOT EXISTS trg_stocks_updated_at
    AFTER UPDATE ON stocks FOR EACH ROW
    BEGIN
        UPDATE stocks SET updated_at = datetime('now') WHERE id = NEW.id;
    END""",
    "CREATE INDEX IF NOT EXISTS idx_trends_user_status ON trends(user_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_industries_user_status ON industries(user_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_stocks_user_status ON stocks(user_id, status)",
]

_MIGRATIONS: list[tuple[int, list[str]]] = [
    (1, [_CREATE_SCHEMA_META, _CREATE_USERS_TABLE]),
    (2, _CREATE_SESSION_SEARCH_TABLES + _CREATE_FTS_AND_TRIGGERS),
    (3, ["ALTER TABLE users DROP COLUMN api_keys"]),
    (4, _CREATE_FACT_TABLES),
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
