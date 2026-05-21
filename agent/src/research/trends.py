"""Trend CRUD: explicit-parameter functions + route registration."""

from __future__ import annotations

import sqlite3
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from src.db import get_db
from .base import get_conn, require_jwt, require_real_user, status_filter


# ============================================================================
# Pydantic Models
# ============================================================================

class TrendCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    level: Optional[str] = Field(None, pattern=r"^(long-term|mid-term|short-term)$")
    confidence: int = Field(5, ge=0, le=10)
    evidence: Optional[str] = Field(None, max_length=5000)


class TrendUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    level: Optional[str] = Field(None, pattern=r"^(long-term|mid-term|short-term)$")
    confidence: Optional[int] = Field(None, ge=0, le=10)
    evidence: Optional[str] = Field(None, max_length=5000)
    status: Optional[str] = Field(None, pattern=r"^(proposed|adopted|rejected|removed)$")


class TrendResponse(BaseModel):
    id: int
    user_id: int
    status: str
    title: str
    level: Optional[str] = None
    confidence: int = 5
    evidence: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_confidence(cls, v):
        return int(v)


# ============================================================================
# CRUD Functions
# ============================================================================

def list_trends(user_id: int, status: Optional[str] = None) -> list[dict]:
    filt = status_filter(status)
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM trends WHERE user_id = ? {filt} ORDER BY updated_at DESC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_trend(trend_id: int, user_id: int, conn: Optional[sqlite3.Connection] = None) -> dict:
    with get_conn(conn) as c:
        row = c.execute("SELECT * FROM trends WHERE id = ? AND user_id = ?", (trend_id, user_id)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return dict(row)


def create_trend(
    user_id: int,
    title: str,
    level: Optional[str] = None,
    confidence: int = 5,
    evidence: Optional[str] = None,
    status: str = "adopted",
    conn: Optional[sqlite3.Connection] = None,
) -> dict:
    with get_conn(conn) as c:
        try:
            cursor = c.execute(
                "INSERT INTO trends (user_id, status, title, level, confidence, evidence) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, status, title, level, confidence, evidence or ""),
            )
            row = c.execute("SELECT * FROM trends WHERE id = ?", (cursor.lastrowid,)).fetchone()
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="Duplicate entry or constraint violation")
    return dict(row)


def update_trend(
    trend_id: int,
    user_id: int,
    *,
    title: Optional[str] = None,
    level: Optional[str] = None,
    confidence: Optional[int] = None,
    evidence: Optional[str] = None,
    status: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> dict:
    data = {}
    if title is not None:
        data["title"] = title
    if level is not None:
        data["level"] = level
    if confidence is not None:
        data["confidence"] = confidence
    if evidence is not None:
        data["evidence"] = evidence
    if status is not None:
        data["status"] = status
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    set_clause = ", ".join(f"{k} = ?" for k in data)
    values = list(data.values()) + [trend_id, user_id]
    with get_conn(conn) as c:
        cursor = c.execute(f"UPDATE trends SET {set_clause} WHERE id = ? AND user_id = ?", values)
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Not found")
        row = c.execute("SELECT * FROM trends WHERE id = ? AND user_id = ?", (trend_id, user_id)).fetchone()
    return dict(row)


def delete_trend(trend_id: int, user_id: int, conn: Optional[sqlite3.Connection] = None) -> dict:
    with get_conn(conn) as c:
        cursor = c.execute(
            "UPDATE trends SET status = 'removed' WHERE id = ? AND user_id = ? AND status != 'removed'",
            (trend_id, user_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Not found or already removed")
    return {"id": trend_id, "status": "removed"}


# ============================================================================
# Route Registration
# ============================================================================

def register_routes(app: FastAPI) -> None:
    @app.get("/api/trends", response_model=list[TrendResponse], dependencies=[Depends(require_jwt)])
    async def _list(status: Optional[str] = Query(None), user_id: int = Depends(require_real_user)):
        return list_trends(user_id, status)

    @app.post("/api/trends", response_model=TrendResponse, status_code=status.HTTP_201_CREATED)
    async def _create(req: TrendCreate, user_id: int = Depends(require_real_user)):
        return create_trend(user_id, req.title, req.level, req.confidence, req.evidence)

    @app.get("/api/trends/{trend_id}", response_model=TrendResponse)
    async def _get(trend_id: int, user_id: int = Depends(require_real_user)):
        return get_trend(trend_id, user_id)

    @app.put("/api/trends/{trend_id}", response_model=TrendResponse)
    async def _update(trend_id: int, req: TrendUpdate, user_id: int = Depends(require_real_user)):
        data = {k: v for k, v in req.model_dump().items() if v is not None}
        return update_trend(trend_id, user_id, conn=None, **data)

    @app.delete("/api/trends/{trend_id}")
    async def _delete(trend_id: int, user_id: int = Depends(require_real_user)):
        return delete_trend(trend_id, user_id)
