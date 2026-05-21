"""Proposal CRUD routes: create/update/delete proposals with adoption workflow."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from src.db import get_db
from .base import ALLOWED_FIELDS, get_conn, require_jwt, require_real_user
from .trends import create_trend, delete_trend, get_trend, update_trend
from .industries import create_industry, delete_industry, get_industry, update_industry
from .stocks import create_stock, delete_stock, get_stock, update_stock

DEFAULT_PROPOSAL_LIMIT = 10
REJECT_COOLDOWN_HOURS = 1  # Minimum hours before re-proposing on same target


def _check_cooldown(conn: sqlite3.Connection, user_id: int, target_type: str, target_id: int) -> None:
    """Block re-proposal if the same target was rejected within cooldown period."""
    if not target_id:
        return
    row = conn.execute(
        "SELECT reviewed_at FROM proposals "
        "WHERE user_id = ? AND target_type = ? AND target_id = ? AND status = 'rejected' "
        "ORDER BY reviewed_at DESC LIMIT 1",
        (user_id, target_type, target_id),
    ).fetchone()
    if not row or not row["reviewed_at"]:
        return
    from datetime import datetime, timedelta, timezone
    reviewed = datetime.fromisoformat(row["reviewed_at"]).replace(tzinfo=timezone.utc)
    cooldown_end = reviewed + timedelta(hours=REJECT_COOLDOWN_HOURS)
    now = datetime.now(timezone.utc)
    if now < cooldown_end:
        remaining = int((cooldown_end - now).total_seconds() / 60)
        raise HTTPException(
            status_code=429,
            detail=f"Target was recently rejected. Cooldown: {remaining} min remaining.",
        )
_CREATE = {"trend": create_trend, "industry": create_industry, "stock": create_stock}
_GET = {"trend": get_trend, "industry": get_industry, "stock": get_stock}
_UPDATE = {"trend": update_trend, "industry": update_industry, "stock": update_stock}
_DELETE = {"trend": delete_trend, "industry": delete_industry, "stock": delete_stock}


def _sanitize_payload(target_type: str, payload: dict) -> dict:
    """Keep only allowed fields for the given target type."""
    allowed = ALLOWED_FIELDS.get(target_type, set())
    return {k: v for k, v in payload.items() if k in allowed}


# ============================================================================
# Pydantic Models
# ============================================================================

class ProposalCreate(BaseModel):
    target_type: str = Field(..., pattern=r"^(trend|industry|stock)$")
    action: str = Field(..., pattern=r"^(create|update|delete)$")
    target_id: Optional[int] = None  # required for update/delete
    title: str = Field(..., min_length=1, max_length=200)
    summary: Optional[str] = None
    confidence: int = Field(5, ge=0, le=10)
    payload: str  # JSON string with target field values
    original_payload: Optional[str] = None  # auto-filled for update
    run_id: Optional[str] = None
    source_agent: Optional[str] = None


class ProposalResponse(BaseModel):
    id: int
    user_id: int
    target_type: str
    target_id: int
    action: str
    status: str
    title: str
    summary: Optional[str] = None
    confidence: int = 5
    payload: str
    original_payload: Optional[str] = None
    run_id: Optional[str] = None
    source_agent: Optional[str] = None
    created_at: Optional[str] = None
    reviewed_at: Optional[str] = None

    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_confidence(cls, v):
        return int(v)


class ProposalListResponse(BaseModel):
    items: List[ProposalResponse]
    total: int
    page: int
    per_page: int


class ProposalActionRequest(BaseModel):
    reason: Optional[str] = None


# ============================================================================
# Audit logging
# ============================================================================

def _write_audit_log(
    conn: sqlite3.Connection,
    user_id: int,
    action: str,
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
    details: Optional[dict] = None,
    actor_type: str = "user",
    actor_id: str = "",
) -> None:
    conn.execute(
        "INSERT INTO audit_logs (user_id, action, target_type, target_id, details, actor_type, actor_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, action, target_type, target_id, json.dumps(details or {}), actor_type, actor_id),
    )


# ============================================================================
# Eviction helpers
# ============================================================================

def _evict_if_lower_confidence(
    conn: sqlite3.Connection,
    user_id: int,
    target_type: str,
    target_id: int,
    new_confidence: int,
    actor_id: str,
) -> None:
    """Auto-evict existing pending proposal on same target if new confidence is higher."""
    from .base import TABLE_MAP
    existing = conn.execute(
        "SELECT id, action, confidence FROM proposals "
        "WHERE user_id = ? AND target_type = ? AND target_id = ? AND status = 'pending'",
        (user_id, target_type, target_id),
    ).fetchone()
    if not existing:
        return
    if new_confidence <= existing["confidence"]:
        raise HTTPException(status_code=409, detail="A pending proposal already exists for this target with equal or higher confidence")
    old_id = existing["id"]
    old_action = existing["action"]
    conn.execute("UPDATE proposals SET status = 'rejected', reviewed_at = datetime('now') WHERE id = ?", (old_id,))
    # Evicted create-proposals: mark the fact row as rejected so it disappears from default views.
    # This is intentional — the row was only created to back the proposal, not user-authored.
    if old_action == "create":
        _UPDATE[target_type](target_id, user_id, status="rejected", conn=conn)
    _write_audit_log(
        conn, user_id, "proposal_evicted", target_type, target_id,
        details={"evicted_proposal_id": old_id, "reason": "replaced_by_higher_confidence"},
        actor_type="system", actor_id=actor_id,
    )


def _evict_if_over_limit(
    conn: sqlite3.Connection,
    user_id: int,
    target_type: str,
    actor_id: str,
) -> None:
    """Evict lowest-confidence pending create proposals if over limit."""
    count = conn.execute(
        "SELECT COUNT(*) as cnt FROM proposals "
        "WHERE user_id = ? AND target_type = ? AND status = 'pending' AND action = 'create'",
        (user_id, target_type),
    ).fetchone()["cnt"]
    overflow = count - DEFAULT_PROPOSAL_LIMIT
    if overflow <= 0:
        return
    victims = conn.execute(
        "SELECT id, target_id FROM proposals "
        "WHERE user_id = ? AND target_type = ? AND status = 'pending' AND action = 'create' "
        "ORDER BY confidence ASC, created_at ASC LIMIT ?",
        (user_id, target_type, overflow),
    ).fetchall()
    for v in victims:
        conn.execute("UPDATE proposals SET status = 'rejected', reviewed_at = datetime('now') WHERE id = ?", (v["id"],))
        _UPDATE[target_type](v["target_id"], user_id, status="rejected", conn=conn)
        _write_audit_log(
            conn, user_id, "proposal_evicted", target_type, v["target_id"],
            details={"evicted_proposal_id": v["id"], "reason": "create_limit_exceeded"},
            actor_type="system", actor_id=actor_id,
        )


# ============================================================================
# Route registration
# ============================================================================

def register_proposal_routes(app: FastAPI) -> None:

    @app.post("/api/proposals", response_model=ProposalResponse, status_code=status.HTTP_201_CREATED)
    async def create_proposal(req: ProposalCreate, user_id: int = Depends(require_real_user)):
        target_type = req.target_type
        action = req.action
        actor_id = f"agent:{req.source_agent}" if req.source_agent else f"user:{user_id}"

        try:
            payload_data = json.loads(req.payload)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON in payload")

        with get_db() as conn:
            target_id = req.target_id
            payload_data = _sanitize_payload(target_type, payload_data)

            if action == "create":
                if not payload_data:
                    raise HTTPException(status_code=400, detail="Payload has no valid fields")
                result = _CREATE[target_type](user_id, status="proposed", conn=conn, **payload_data)
                target_id = result["id"]
                original_payload = None
            elif action == "update":
                if not target_id:
                    raise HTTPException(status_code=400, detail="target_id required for update action")
                _check_cooldown(conn, user_id, target_type, target_id)
                # Snapshot current state for original_payload
                current = _GET[target_type](target_id, user_id, conn=conn)
                exclude = {"id", "user_id", "created_at", "updated_at", "recommended_count"}
                original_payload = json.dumps({k: v for k, v in current.items() if k not in exclude})
                _evict_if_lower_confidence(conn, user_id, target_type, target_id, req.confidence, actor_id)
            elif action == "delete":
                if not target_id:
                    raise HTTPException(status_code=400, detail="target_id required for delete action")
                _check_cooldown(conn, user_id, target_type, target_id)
                _GET[target_type](target_id, user_id, conn=conn)  # validate exists
                original_payload = None
                _evict_if_lower_confidence(conn, user_id, target_type, target_id, req.confidence, actor_id)

            try:
                cursor = conn.execute(
                    "INSERT INTO proposals "
                    "(user_id, target_type, target_id, action, status, title, summary, confidence, "
                    "payload, original_payload, run_id, source_agent) "
                    "VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)",
                    (user_id, target_type, target_id, action, req.title, req.summary,
                     req.confidence, req.payload, original_payload, req.run_id, req.source_agent),
                )
            except sqlite3.IntegrityError:
                raise HTTPException(status_code=409, detail="Conflicting pending proposal exists for this target")

            proposal_id = cursor.lastrowid
            _evict_if_over_limit(conn, user_id, target_type, actor_id)
            _write_audit_log(
                conn, user_id, "proposal_created", target_type, target_id,
                details={"proposal_id": proposal_id, "action": action},
                actor_type="agent" if req.source_agent else "user", actor_id=actor_id,
            )

            row = conn.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
            return dict(row)

    @app.get("/api/proposals", response_model=ProposalListResponse)
    async def list_proposals(
        type: Optional[str] = Query(None),
        status: Optional[str] = Query(None),
        target_id: Optional[int] = Query(None),
        since: Optional[str] = Query(None, description="ISO date, e.g. 2026-05-01"),
        page: int = Query(1, ge=1),
        per_page: int = Query(20, ge=1, le=100),
        user_id: int = Depends(require_real_user),
    ):
        conditions = ["user_id = ?"]
        params: list[Any] = [user_id]
        if type:
            conditions.append("target_type = ?")
            params.append(type)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if target_id is not None:
            conditions.append("target_id = ?")
            params.append(target_id)
        if since:
            conditions.append("created_at >= ?")
            params.append(since)

        where = " AND ".join(conditions)
        with get_db() as conn:
            total = conn.execute(f"SELECT COUNT(*) FROM proposals WHERE {where}", params).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM proposals WHERE {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                params + [per_page, (page - 1) * per_page],
            ).fetchall()
        return ProposalListResponse(
            items=[dict(r) for r in rows], total=total, page=page, per_page=per_page,
        )

    @app.get("/api/proposals/{proposal_id}", response_model=ProposalResponse)
    async def get_proposal(proposal_id: int, user_id: int = Depends(require_real_user)):
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM proposals WHERE id = ? AND user_id = ?",
                (proposal_id, user_id),
            ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Proposal not found")
        return dict(row)

    @app.post("/api/proposals/{proposal_id}/adopt")
    async def adopt_proposal(proposal_id: int, user_id: int = Depends(require_real_user)):
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM proposals WHERE id = ? AND user_id = ?",
                (proposal_id, user_id),
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Proposal not found")
            if row["status"] != "pending":
                raise HTTPException(status_code=409, detail="Proposal is not pending")

            proposal = dict(row)
            target_type = proposal["target_type"]
            action = proposal["action"]
            target_id = proposal["target_id"]

            if action == "create":
                if target_id:
                    _UPDATE[target_type](target_id, user_id, status="adopted", conn=conn)
                else:
                    payload = _sanitize_payload(target_type, json.loads(proposal["payload"]))
                    _CREATE[target_type](user_id, status="adopted", conn=conn, **payload)
            elif action == "update":
                payload = _sanitize_payload(target_type, json.loads(proposal["payload"]))
                if payload:
                    _UPDATE[target_type](target_id, user_id, status="adopted", conn=conn, **payload)
                else:
                    _UPDATE[target_type](target_id, user_id, status="adopted", conn=conn)
            elif action == "delete":
                _DELETE[target_type](target_id, user_id, conn=conn)

            conn.execute(
                "UPDATE proposals SET status = 'adopted', reviewed_at = datetime('now') WHERE id = ?",
                (proposal_id,),
            )
            _write_audit_log(
                conn, user_id, "proposal_adopted", target_type, target_id,
                details={"proposal_id": proposal_id, "action": action},
                actor_type="user", actor_id=f"user:{user_id}",
            )

            updated = conn.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
            return dict(updated)

    @app.post("/api/proposals/{proposal_id}/reject", response_model=ProposalResponse)
    async def reject_proposal(proposal_id: int, user_id: int = Depends(require_real_user)):
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM proposals WHERE id = ? AND user_id = ?",
                (proposal_id, user_id),
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Proposal not found")
            if row["status"] != "pending":
                raise HTTPException(status_code=409, detail="Proposal is not pending")

            proposal = dict(row)
            target_type = proposal["target_type"]
            action = proposal["action"]
            target_id = proposal["target_id"]

            if action == "create":
                _UPDATE[target_type](target_id, user_id, status="rejected", conn=conn)

            conn.execute(
                "UPDATE proposals SET status = 'rejected', reviewed_at = datetime('now') WHERE id = ?",
                (proposal_id,),
            )
            _write_audit_log(
                conn, user_id, "proposal_rejected", target_type, target_id,
                details={"proposal_id": proposal_id, "action": action},
                actor_type="user", actor_id=f"user:{user_id}",
            )

            updated = conn.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
            return dict(updated)

    @app.post("/api/proposals/{proposal_id}/cancel", response_model=ProposalResponse)
    async def cancel_proposal(proposal_id: int, user_id: int = Depends(require_real_user)):
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM proposals WHERE id = ? AND user_id = ?",
                (proposal_id, user_id),
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Proposal not found")
            if row["status"] != "pending":
                raise HTTPException(status_code=409, detail="Proposal is not pending")

            proposal = dict(row)
            target_type = proposal["target_type"]
            action = proposal["action"]
            target_id = proposal["target_id"]

            if action == "create":
                _UPDATE[target_type](target_id, user_id, status="rejected", conn=conn)

            conn.execute(
                "UPDATE proposals SET status = 'cancelled', reviewed_at = datetime('now') WHERE id = ?",
                (proposal_id,),
            )
            _write_audit_log(
                conn, user_id, "proposal_cancelled", target_type, target_id,
                details={"proposal_id": proposal_id, "action": action},
                actor_type="user", actor_id=f"user:{user_id}",
            )

            updated = conn.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,)).fetchone()
            return dict(updated)
