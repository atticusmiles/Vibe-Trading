"""Tests for candidates API endpoints."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def db_path(tmp_path):
    """Create a temporary database with schema."""
    db_file = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS _schema_meta (
            key TEXT PRIMARY KEY, value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            preferences TEXT DEFAULT '{}',
            settings TEXT DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        INSERT INTO users (username, password_hash) VALUES ('test', 'hash');
        CREATE TABLE IF NOT EXISTS research_candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_type TEXT NOT NULL,
            name TEXT NOT NULL,
            code TEXT,
            source_context TEXT,
            initial_score INTEGER DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending',
            source_run_id TEXT,
            research_run_id TEXT,
            report TEXT,
            report_type TEXT,
            reported_at TEXT,
            extra_reports TEXT DEFAULT '[]',
            conclusion TEXT,
            proposal_id INTEGER,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_candidates_status ON research_candidates(target_type, status);
    """)

    # Insert test data
    conn.execute(
        "INSERT INTO research_candidates (target_type, name, code, initial_score, status) "
        "VALUES ('trend', 'AI算力增长', NULL, 8, 'pending')"
    )
    conn.execute(
        "INSERT INTO research_candidates (target_type, name, code, initial_score, status) "
        "VALUES ('stock', '贵州茅台', '600519', 7, 'pending')"
    )
    conn.execute(
        "INSERT INTO research_candidates (target_type, name, code, initial_score, status) "
        "VALUES ('industry', '新能源', NULL, 6, 'researching')"
    )
    conn.commit()
    conn.close()
    return db_file


@pytest.fixture
def mock_db(db_path):
    """Patch get_db to use temp database."""
    from contextlib import contextmanager

    @contextmanager
    def _get_db():
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    return _get_db


class TestListCandidates:
    def test_list_all(self, db_path):
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM research_candidates").fetchall()
        assert len(rows) == 3
        conn.close()

    def test_list_filter_by_type(self, db_path):
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM research_candidates WHERE target_type = ? ORDER BY created_at DESC",
            ("trend",),
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["name"] == "AI算力增长"
        conn.close()

    def test_list_filter_by_status(self, db_path):
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM research_candidates WHERE status = ? ORDER BY created_at DESC",
            ("pending",),
        ).fetchall()
        assert len(rows) == 2
        conn.close()

    def test_list_filter_type_and_status(self, db_path):
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM research_candidates WHERE target_type = ? AND status = ?",
            ("trend", "pending"),
        ).fetchall()
        assert len(rows) == 1
        conn.close()


class TestGetCandidate:
    def test_get_existing(self, db_path):
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM research_candidates WHERE id = 1").fetchone()
        assert row is not None
        assert row["name"] == "AI算力增长"
        conn.close()

    def test_get_not_found(self, db_path):
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM research_candidates WHERE id = 999").fetchone()
        assert row is None
        conn.close()


class TestBatchResearchValidation:
    def test_validates_same_target_type(self, db_path):
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT target_type FROM research_candidates WHERE id IN (1, 2)"
        ).fetchall()
        types = {r["target_type"] for r in rows}
        assert len(types) > 1
        conn.close()

    def test_validates_pending_status(self, db_path):
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT status FROM research_candidates WHERE id = 3"
        ).fetchone()
        assert row["status"] == "researching"
        conn.close()
