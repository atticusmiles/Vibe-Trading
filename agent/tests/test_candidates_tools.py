"""Unit tests for manage_candidates and manage_proposals tools."""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Setup path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def db_path(tmp_path):
    """Create a temporary database with schema."""
    db_file = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row

    # Create minimal tables
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
        CREATE TABLE IF NOT EXISTS proposals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            target_type TEXT NOT NULL,
            target_id INTEGER NOT NULL,
            action TEXT NOT NULL CHECK(action IN ('create','update','delete')),
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','adopted','rejected','cancelled')),
            title TEXT NOT NULL,
            summary TEXT,
            confidence INTEGER DEFAULT 5,
            payload TEXT NOT NULL,
            original_payload TEXT,
            run_id TEXT,
            source_agent TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            reviewed_at TEXT
        );
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
            proposal_id INTEGER REFERENCES proposals(id),
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_candidates_status ON research_candidates(target_type, status);
    """)
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

    with patch("src.db.database.get_db", _get_db):
        yield db_path


class TestManageCandidatesAdd:
    def test_add_single_candidate(self, mock_db):
        from src.tools.manage_candidates_tool import ManageCandidatesTool
        tool = ManageCandidatesTool()
        result = json.loads(tool.execute(
            action="add",
            target_type="trend",
            candidates=json.dumps([{"name": "AI算力增长", "score": 8, "reason": "政策支持+资金流入"}]),
        ))
        assert result["status"] == "ok"
        assert result["inserted"] == 1
        assert result["skipped"] == 0

    def test_add_multiple_candidates(self, mock_db):
        from src.tools.manage_candidates_tool import ManageCandidatesTool
        tool = ManageCandidatesTool()
        result = json.loads(tool.execute(
            action="add",
            target_type="stock",
            candidates=json.dumps([
                {"name": "贵州茅台", "code": "600519", "score": 7},
                {"name": "宁德时代", "code": "300750", "score": 6},
            ]),
        ))
        assert result["status"] == "ok"
        assert result["inserted"] == 2

    def test_add_duplicate_same_day_skipped(self, mock_db):
        """Test per-day dedup: same candidate on same day is skipped."""
        from src.tools.manage_candidates_tool import ManageCandidatesTool
        tool = ManageCandidatesTool()
        tool.execute(
            action="add",
            target_type="trend",
            candidates=json.dumps([{"name": "AI算力增长", "score": 8}]),
        )
        result = json.loads(tool.execute(
            action="add",
            target_type="trend",
            candidates=json.dumps([{"name": "AI算力增长", "score": 9}]),
        ))
        assert result["skipped"] == 1

    def test_add_with_run_id(self, mock_db):
        from src.tools.manage_candidates_tool import ManageCandidatesTool
        tool = ManageCandidatesTool()
        result = json.loads(tool.execute(
            action="add",
            target_type="trend",
            candidates=json.dumps([{"name": "测试趋势"}]),
            _run_id="run-123",
        ))
        assert result["status"] == "ok"

        # Verify run_id was stored
        import sqlite3
        conn = sqlite3.connect(str(mock_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT source_run_id FROM research_candidates WHERE name = '测试趋势'").fetchone()
        assert row["source_run_id"] == "run-123"
        conn.close()

    def test_add_invalid_json(self, mock_db):
        from src.tools.manage_candidates_tool import ManageCandidatesTool
        tool = ManageCandidatesTool()
        result = json.loads(tool.execute(
            action="add",
            target_type="trend",
            candidates="not valid json{{{",
        ))
        assert result["status"] == "error"


class TestManageCandidatesUpdate:
    def _add_candidate(self, tool, name="测试趋势"):
        tool.execute(
            action="add",
            target_type="trend",
            candidates=json.dumps([{"name": name, "score": 5}]),
        )

    def test_update_report(self, mock_db):
        from src.tools.manage_candidates_tool import ManageCandidatesTool
        tool = ManageCandidatesTool()
        self._add_candidate(tool)

        result = json.loads(tool.execute(
            action="update",
            target_type="trend",
            target_name="测试趋势",
            report="# 调研报告\n这是报告内容",
            report_type="macro_analysis",
        ))
        assert result["status"] == "ok"
        assert result["fields_updated"] >= 2  # report + report_type + reported_at

    def test_update_extra_report_appends(self, mock_db):
        from src.tools.manage_candidates_tool import ManageCandidatesTool
        tool = ManageCandidatesTool()
        self._add_candidate(tool)

        # First extra report
        tool.execute(
            action="update",
            target_type="trend",
            target_name="测试趋势",
            extra_report=json.dumps({"agent_id": "pro", "title": "支持", "content": "理由..."}),
        )
        # Second extra report
        result = json.loads(tool.execute(
            action="update",
            target_type="trend",
            target_name="测试趋势",
            extra_report=json.dumps({"agent_id": "con", "title": "反对", "content": "风险..."}),
        ))
        assert result["status"] == "ok"

    def test_update_status_proposed(self, mock_db):
        from src.tools.manage_candidates_tool import ManageCandidatesTool
        tool = ManageCandidatesTool()
        self._add_candidate(tool)

        # Patch event trigger (delayed import in tool code)
        with patch("src.scheduler.events.check_event_triggers", return_value=[]):
            result = json.loads(tool.execute(
                action="update",
                target_type="trend",
                target_name="测试趋势",
                status="proposed",
                conclusion="趋势确认成立",
            ))
        assert result["status"] == "ok"

    def test_update_status_invalid(self, mock_db):
        from src.tools.manage_candidates_tool import ManageCandidatesTool
        tool = ManageCandidatesTool()
        self._add_candidate(tool)

        result = json.loads(tool.execute(
            action="update",
            target_type="trend",
            target_name="测试趋势",
            status="researching",
        ))
        assert result["status"] == "error"

    def test_update_not_found(self, mock_db):
        from src.tools.manage_candidates_tool import ManageCandidatesTool
        tool = ManageCandidatesTool()
        result = json.loads(tool.execute(
            action="update",
            target_type="trend",
            target_name="不存在的趋势",
            status="proposed",
        ))
        assert result["status"] == "error"

    def test_update_no_name(self, mock_db):
        from src.tools.manage_candidates_tool import ManageCandidatesTool
        tool = ManageCandidatesTool()
        result = json.loads(tool.execute(
            action="update",
            target_type="trend",
            status="proposed",
        ))
        assert result["status"] == "error"

    def test_update_nothing_to_update(self, mock_db):
        from src.tools.manage_candidates_tool import ManageCandidatesTool
        tool = ManageCandidatesTool()
        self._add_candidate(tool)

        result = json.loads(tool.execute(
            action="update",
            target_type="trend",
            target_name="测试趋势",
        ))
        assert result["status"] == "error"


class TestManageProposalsCreate:
    def test_create_proposal_for_trend(self, mock_db):
        from src.tools.manage_proposals_tool import ManageProposalsTool
        tool = ManageProposalsTool()
        result = json.loads(tool.execute(
            action="create",
            target_type="trend",
            proposal_action="create",
            title="推荐趋势：AI算力增长",
            payload=json.dumps({"title": "AI算力增长", "confidence": 7, "evidence": "数据支撑"}),
            confidence=7,
            summary="AI算力需求持续增长，政策+产业双驱动",
            _user_id="1",
            _run_id="run-456",
        ))
        assert result["status"] == "ok"
        assert result["proposal_id"] > 0

    def test_create_proposal_missing_user(self, mock_db):
        from src.tools.manage_proposals_tool import ManageProposalsTool
        tool = ManageProposalsTool()
        result = json.loads(tool.execute(
            action="create",
            target_type="trend",
            proposal_action="create",
            title="测试",
            payload="{}",
        ))
        assert result["status"] == "error"

    def test_create_proposal_invalid_target_type(self, mock_db):
        from src.tools.manage_proposals_tool import ManageProposalsTool
        tool = ManageProposalsTool()
        result = json.loads(tool.execute(
            action="create",
            target_type="invalid",
            proposal_action="create",
            title="测试",
            _user_id="1",
        ))
        assert result["status"] == "error"

    def test_create_proposal_invalid_payload(self, mock_db):
        from src.tools.manage_proposals_tool import ManageProposalsTool
        tool = ManageProposalsTool()
        result = json.loads(tool.execute(
            action="create",
            target_type="trend",
            proposal_action="create",
            title="测试",
            payload="not json{{{",
            _user_id="1",
        ))
        assert result["status"] == "error"

    def test_create_update_proposal_without_target_id(self, mock_db):
        from src.tools.manage_proposals_tool import ManageProposalsTool
        tool = ManageProposalsTool()
        result = json.loads(tool.execute(
            action="create",
            target_type="trend",
            proposal_action="update",
            title="更新趋势",
            payload="{}",
            _user_id="1",
        ))
        assert result["status"] == "error"


class TestManageProposalsCancel:
    def _create_proposal(self, tool):
        result = tool.execute(
            action="create",
            target_type="trend",
            proposal_action="create",
            title="测试提案",
            payload=json.dumps({"title": "测试", "confidence": 5}),
            _user_id="1",
        )
        return json.loads(result)["proposal_id"]

    def test_cancel_proposal(self, mock_db):
        from src.tools.manage_proposals_tool import ManageProposalsTool
        tool = ManageProposalsTool()
        pid = self._create_proposal(tool)

        result = json.loads(tool.execute(
            action="cancel",
            proposal_id=pid,
            _user_id="1",
        ))
        assert result["status"] == "ok"

    def test_cancel_not_found(self, mock_db):
        from src.tools.manage_proposals_tool import ManageProposalsTool
        tool = ManageProposalsTool()
        result = json.loads(tool.execute(
            action="cancel",
            proposal_id=99999,
            _user_id="1",
        ))
        assert result["status"] == "error"

    def test_cancel_no_id(self, mock_db):
        from src.tools.manage_proposals_tool import ManageProposalsTool
        tool = ManageProposalsTool()
        result = json.loads(tool.execute(
            action="cancel",
            _user_id="1",
        ))
        assert result["status"] == "error"
