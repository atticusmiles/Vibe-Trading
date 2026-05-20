"""SQLite database initialization, connection management, and schema migration."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from src.core.config import get_data_dir

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 10

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
    except sqlite3.OperationalError:
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

_CREATE_PROPOSAL_TABLES = [
    """CREATE TABLE IF NOT EXISTS proposals (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id           INTEGER NOT NULL REFERENCES users(id),
        target_type       TEXT NOT NULL,
        target_id         INTEGER NOT NULL,
        action            TEXT NOT NULL CHECK(action IN ('create','update','delete')),
        status            TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','adopted','rejected','cancelled')),
        title             TEXT NOT NULL,
        summary           TEXT,
        confidence        INTEGER DEFAULT 5 CHECK(confidence BETWEEN 0 AND 10),
        payload           TEXT NOT NULL,
        original_payload  TEXT,
        run_id            TEXT,
        source_agent      TEXT,
        created_at        TEXT DEFAULT (datetime('now')),
        reviewed_at       TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS audit_logs (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL REFERENCES users(id),
        action      TEXT NOT NULL,
        target_type TEXT,
        target_id   INTEGER,
        details     TEXT,
        actor_type  TEXT NOT NULL,
        actor_id    TEXT NOT NULL,
        created_at  TEXT DEFAULT (datetime('now'))
    )""",
    "CREATE INDEX IF NOT EXISTS idx_proposals_user_status ON proposals(user_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_proposals_target ON proposals(user_id, target_type, target_id)",
    """CREATE UNIQUE INDEX IF NOT EXISTS idx_proposals_pending_target
        ON proposals(user_id, target_type, target_id)
        WHERE status = 'pending'""",
    "CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id, created_at)",
]

_MIGRATIONS: list[tuple[int, list[str]]] = [
    (1, [_CREATE_SCHEMA_META, _CREATE_USERS_TABLE]),
    (2, _CREATE_SESSION_SEARCH_TABLES + _CREATE_FTS_AND_TRIGGERS),
    (3, ["ALTER TABLE users DROP COLUMN api_keys"]),
    (4, _CREATE_FACT_TABLES),
    (5, _CREATE_PROPOSAL_TABLES),
    (6, [
        # Add 'cancelled' to proposals.status CHECK constraint (SQLite requires table rebuild)
        "ALTER TABLE proposals RENAME TO _proposals_old",
        """CREATE TABLE proposals (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id           INTEGER NOT NULL REFERENCES users(id),
            target_type       TEXT NOT NULL,
            target_id         INTEGER NOT NULL,
            action            TEXT NOT NULL CHECK(action IN ('create','update','delete')),
            status            TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','adopted','rejected','cancelled')),
            title             TEXT NOT NULL,
            summary           TEXT,
            confidence        INTEGER DEFAULT 5 CHECK(confidence BETWEEN 0 AND 10),
            payload           TEXT NOT NULL,
            original_payload  TEXT,
            run_id            TEXT,
            source_agent      TEXT,
            created_at        TEXT DEFAULT (datetime('now')),
            reviewed_at       TEXT
        )""",
        "INSERT INTO proposals SELECT * FROM _proposals_old",
        "DROP TABLE IF EXISTS _proposals_old",
        "CREATE INDEX IF NOT EXISTS idx_proposals_user_status ON proposals(user_id, status)",
        "CREATE INDEX IF NOT EXISTS idx_proposals_target ON proposals(user_id, target_type, target_id)",
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_proposals_pending_target
            ON proposals(user_id, target_type, target_id)
            WHERE status = 'pending'""",
    ]),
]

_CREATE_DATASOURCE_TABLES = [
    """CREATE TABLE IF NOT EXISTS news_raw (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id    TEXT NOT NULL,
        title        TEXT NOT NULL,
        content      TEXT,
        level        TEXT,
        source       TEXT NOT NULL DEFAULT 'cls',
        published_at TEXT NOT NULL,
        fetched_at   TEXT DEFAULT (datetime('now')),
        UNIQUE(source_id, source)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_news_raw_published ON news_raw(published_at)",
    """CREATE TABLE IF NOT EXISTS news_digests (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL REFERENCES users(id),
        digest_date TEXT NOT NULL,
        content     TEXT NOT NULL,
        summary     TEXT,
        created_at  TEXT DEFAULT (datetime('now')),
        UNIQUE(user_id, digest_date)
    )""",
]

_MIGRATIONS.append((7, _CREATE_DATASOURCE_TABLES))


def _migration_8(conn: sqlite3.Connection) -> None:
    """Rename flash_news_raw → news_raw, add source_id column.

    Safe on both fresh and existing DBs:
    - Fresh: migration 7 already created news_raw with source_id; this is a no-op.
    - Existing: renames old table and adds the column.
    """
    # Check if old table exists
    old_exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='flash_news_raw'"
    ).fetchone()
    if old_exists:
        # Check if target already exists (migration 7 may have created it)
        target_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='news_raw'"
        ).fetchone()
        if target_exists:
            # Both exist — drop the old one, keep the new
            conn.execute('DROP TABLE "flash_news_raw"')
        else:
            conn.execute('ALTER TABLE "flash_news_raw" RENAME TO "news_raw"')

    # Add source_id column if missing
    try:
        conn.execute('ALTER TABLE "news_raw" ADD COLUMN source_id TEXT NOT NULL DEFAULT ""')
    except sqlite3.OperationalError as exc:
        if "duplicate column" not in str(exc).lower():
            raise

    conn.execute("UPDATE \"news_raw\" SET source_id = CAST(id AS TEXT) WHERE source_id = ''")


_MIGRATIONS.append((8, [
    """SELECT 1""",  # placeholder — actual logic in _migration_8
]))


def _migration_9(conn: sqlite3.Connection) -> None:
    """Ensure news_raw has UNIQUE(source_id, source) constraint.

    SQLite cannot add constraints to existing tables, so we recreate the table
    if the constraint is missing.
    """
    # Check if the correct UNIQUE constraint exists
    table_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='news_raw'"
    ).fetchone()
    if table_sql and "source_id" in table_sql[0] and "UNIQUE(source_id, source)" in table_sql[0]:
        return

    # Recreate table with proper constraint
    conn.execute("ALTER TABLE news_raw RENAME TO news_raw_old")
    conn.execute("""CREATE TABLE news_raw (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id    TEXT NOT NULL,
        title        TEXT NOT NULL,
        content      TEXT,
        level        TEXT,
        source       TEXT NOT NULL DEFAULT 'cls',
        published_at TEXT NOT NULL,
        fetched_at   TEXT DEFAULT (datetime('now')),
        UNIQUE(source_id, source)
    )""")
    conn.execute("INSERT OR IGNORE INTO news_raw (source_id, title, content, level, source, published_at, fetched_at) "
                 "SELECT source_id, title, content, level, source, published_at, fetched_at FROM news_raw_old")
    conn.execute("DROP TABLE news_raw_old")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_news_raw_published ON news_raw(published_at)")


_MIGRATIONS.append((9, [
    """SELECT 1""",
]))

_CREATE_CANDIDATES_TABLE = [
    """CREATE TABLE IF NOT EXISTS research_candidates (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        target_type     TEXT NOT NULL,
        name            TEXT NOT NULL,
        code            TEXT,
        source_context  TEXT,
        initial_score   INTEGER DEFAULT 0,
        status          TEXT NOT NULL DEFAULT 'pending',
        source_run_id   TEXT,
        research_run_id TEXT,
        report          TEXT,
        report_type     TEXT,
        reported_at     TEXT,
        extra_reports   TEXT DEFAULT '[]',
        conclusion      TEXT,
        proposal_id     INTEGER REFERENCES proposals(id),
        created_at      TEXT DEFAULT (datetime('now')),
        updated_at      TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS idx_candidates_status ON research_candidates(target_type, status)",
    "CREATE INDEX IF NOT EXISTS idx_candidates_research_run ON research_candidates(research_run_id)",
]

_MIGRATIONS.append((10, _CREATE_CANDIDATES_TABLE))


def init_db() -> None:
    """Initialize database: create tables and run pending migrations.

    Safe to call multiple times — only runs pending migrations.
    """
    with get_db() as conn:
        current = _get_schema_version(conn)
        for target_version, statements in _MIGRATIONS:
            if current < target_version:
                if target_version == 8:
                    _migration_8(conn)
                elif target_version == 9:
                    _migration_9(conn)
                else:
                    for stmt in statements:
                        try:
                            conn.execute(stmt)
                        except sqlite3.OperationalError as exc:
                            msg = str(exc).lower()
                            if "already exists" in msg or "no such column" in msg or "no such table" in msg or "duplicate column" in msg:
                                logger.debug("Migration %d: suppressed %s", target_version, msg)
                            else:
                                raise
                _set_schema_version(conn, target_version)
        final = _get_schema_version(conn)
        assert final == _SCHEMA_VERSION, f"Schema version mismatch: {final} != {_SCHEMA_VERSION}"
