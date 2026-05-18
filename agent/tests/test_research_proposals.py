"""Unit tests for proposals logic: sanitize, eviction, cooldown."""

from __future__ import annotations

import json
import pytest

from src.db import init_db
from src.research.proposals import (
    _sanitize_payload,
    _evict_if_lower_confidence,
    _evict_if_over_limit,
    _check_cooldown,
    DEFAULT_PROPOSAL_LIMIT,
)
from src.research.base import ALLOWED_FIELDS


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    from src.core import config
    monkeypatch.setattr(config, "get_data_dir", lambda: tmp_path / "data")
    init_db()
    from src.db import get_db
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, username, password_hash) VALUES (1, 'test', 'x')"
        )


# ============================================================================
# _sanitize_payload
# ============================================================================

class TestSanitizePayload:
    def test_trend_keeps_allowed_fields(self):
        payload = {"title": "AI", "level": "long-term", "confidence": 7, "evidence": "test"}
        result = _sanitize_payload("trend", payload)
        assert result == payload

    def test_trend_strips_disallowed_fields(self):
        payload = {"title": "AI", "id": 99, "user_id": 1, "created_at": "2024-01-01"}
        result = _sanitize_payload("trend", payload)
        assert result == {"title": "AI"}

    def test_industry_keeps_recommended_stocks(self):
        payload = {"name": "半导体", "recommended_stocks": ["600519"]}
        result = _sanitize_payload("industry", payload)
        assert "recommended_stocks" in result

    def test_stock_keeps_all_financial_fields(self):
        payload = {"code": "600519", "target_price": 2000.0, "stop_loss": 1800.0, "position": 0.5}
        result = _sanitize_payload("stock", payload)
        assert result == payload

    def test_empty_payload_returns_empty(self):
        assert _sanitize_payload("trend", {}) == {}

    def test_unknown_type_returns_empty(self):
        assert _sanitize_payload("unknown", {"title": "test"}) == {}

    def test_allowed_fields_consistency(self):
        """Every type in ALLOWED_FIELDS should have at least one required field."""
        for t, fields in ALLOWED_FIELDS.items():
            assert len(fields) > 0, f"Type {t} has no allowed fields"


# ============================================================================
# Eviction: confidence-based
# ============================================================================

class TestEvictConfidence:
    def test_higher_confidence_evicts_old(self):
        from src.db import get_db
        from src.research.trends import create_trend
        with get_db() as conn:
            # Create a fact row and a pending proposal
            trend = create_trend(1, "测试", status="proposed", conn=conn)
            conn.execute(
                "INSERT INTO proposals (user_id, target_type, target_id, action, status, title, confidence, payload) "
                "VALUES (?, 'trend', ?, 'update', 'pending', '旧提案', 5, '{}')",
                (1, trend["id"]),
            )
            # Higher confidence should evict
            _evict_if_lower_confidence(conn, 1, "trend", trend["id"], 8, "test")
            row = conn.execute("SELECT status FROM proposals WHERE target_id = ?", (trend["id"],)).fetchone()
            assert row["status"] == "rejected"

    def test_lower_confidence_raises_409(self):
        from src.db import get_db
        from src.research.trends import create_trend
        with get_db() as conn:
            trend = create_trend(1, "冲突测试", status="proposed", conn=conn)
            conn.execute(
                "INSERT INTO proposals (user_id, target_type, target_id, action, status, title, confidence, payload) "
                "VALUES (?, 'trend', ?, 'update', 'pending', '高置信', 8, '{}')",
                (1, trend["id"]),
            )
            with pytest.raises(Exception, match="409"):
                _evict_if_lower_confidence(conn, 1, "trend", trend["id"], 3, "test")

    def test_no_existing_pending_is_noop(self):
        from src.db import get_db
        with get_db() as conn:
            # Should not raise
            _evict_if_lower_confidence(conn, 1, "trend", 9999, 5, "test")


# ============================================================================
# Eviction: over limit
# ============================================================================

class TestEvictOverLimit:
    def test_evicts_lowest_confidence(self):
        from src.db import get_db
        from src.research.trends import create_trend
        with get_db() as conn:
            # Create LIMIT+1 proposals (confidence capped at 10)
            for i in range(DEFAULT_PROPOSAL_LIMIT + 1):
                trend = create_trend(1, f"趋势{i}", status="proposed", conn=conn)
                confidence = min(i + 1, 10)
                conn.execute(
                    "INSERT INTO proposals (user_id, target_type, target_id, action, status, title, confidence, payload) "
                    "VALUES (?, 'trend', ?, 'create', 'pending', ?, ?, '{}')",
                    (1, trend["id"], f"提案{i}", confidence),
                )
            _evict_if_over_limit(conn, 1, "trend", "test")
            count = conn.execute(
                "SELECT COUNT(*) FROM proposals WHERE user_id=1 AND target_type='trend' AND status='pending' AND action='create'"
            ).fetchone()[0]
            assert count == DEFAULT_PROPOSAL_LIMIT

    def test_under_limit_is_noop(self):
        from src.db import get_db
        with get_db() as conn:
            # Only 2 proposals, limit is 10
            _evict_if_over_limit(conn, 1, "trend", "test")


# ============================================================================
# Cooldown
# ============================================================================

class TestCooldown:
    def test_recently_rejected_blocks(self):
        from src.db import get_db
        from src.research.trends import create_trend
        with get_db() as conn:
            trend = create_trend(1, "冷却测试", status="proposed", conn=conn)
            # Insert a recently rejected proposal
            conn.execute(
                "INSERT INTO proposals (user_id, target_type, target_id, action, status, title, confidence, payload, reviewed_at) "
                "VALUES (?, 'trend', ?, 'create', 'rejected', '已否决', 5, '{}', datetime('now'))",
                (1, trend["id"]),
            )
            with pytest.raises(Exception, match="429"):
                _check_cooldown(conn, 1, "trend", trend["id"])

    def test_no_rejected_allows(self):
        from src.db import get_db
        with get_db() as conn:
            # No rejected proposals for this target
            _check_cooldown(conn, 1, "trend", 9999)

    def test_old_rejected_allows(self):
        from src.db import get_db
        with get_db() as conn:
            # Rejected 2 hours ago (cooldown is 1h)
            conn.execute(
                "INSERT INTO proposals (user_id, target_type, target_id, action, status, title, confidence, payload, reviewed_at) "
                "VALUES (1, 'trend', 1, 'create', 'rejected', '旧否决', 5, '{}', datetime('now', '-2 hours'))",
            )
            _check_cooldown(conn, 1, "trend", 1)

    def test_zero_target_id_skips(self):
        from src.db import get_db
        with get_db() as conn:
            _check_cooldown(conn, 1, "trend", 0)
