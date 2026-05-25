"""Industry CRUD: explicit-parameter functions + route registration."""

from __future__ import annotations

import json
import sqlite3
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from src.db import get_db
from .base import get_conn, require_jwt, require_real_user, status_filter


# ============================================================================
# Pydantic Models
# ============================================================================

class IndustryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    confidence: int = Field(5, ge=0, le=10)
    abstract: Optional[str] = None
    research_report: Optional[str] = None


class IndustryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    confidence: Optional[int] = Field(None, ge=0, le=10)
    abstract: Optional[str] = None
    research_report: Optional[str] = None
    status: Optional[str] = Field(None, pattern=r"^(proposed|adopted|rejected|removed)$")


class IndustryResponse(BaseModel):
    id: int
    user_id: int
    status: str
    name: str
    confidence: int = 5
    abstract: Optional[str] = None
    research_report: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_confidence(cls, v):
        return int(v)


# ============================================================================
# CRUD Functions
# ============================================================================

def list_industries(user_id: int, status: Optional[str] = None) -> list[dict]:
    filt = status_filter(status)
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM industries WHERE user_id = ? {filt} ORDER BY updated_at DESC",
            (user_id,),
        ).fetchall()
    return [(dict(r)) for r in rows]


def get_industry(industry_id: int, user_id: int, conn: Optional[sqlite3.Connection] = None) -> dict:
    with get_conn(conn) as c:
        row = c.execute("SELECT * FROM industries WHERE id = ? AND user_id = ?", (industry_id, user_id)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return dict(row)


def create_industry(
    user_id: int,
    name: str,
    confidence: int = 5,
    abstract: Optional[str] = None,
    research_report: Optional[str] = None,
    status: str = "adopted",
    conn: Optional[sqlite3.Connection] = None,
) -> dict:
    with get_conn(conn) as c:
        try:
            cursor = c.execute(
                "INSERT INTO industries (user_id, status, name, confidence, abstract, research_report) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, status, name, confidence, abstract or "", research_report or ""),
            )
            row = c.execute("SELECT * FROM industries WHERE id = ?", (cursor.lastrowid,)).fetchone()
        except sqlite3.IntegrityError:
            existing = c.execute(
                "SELECT id FROM industries WHERE user_id = ? AND name = ? AND status = 'removed'",
                (user_id, name),
            ).fetchone()
            if existing:
                c.execute(
                    "UPDATE industries SET status = ?, confidence = ?, abstract = ?, "
                    "research_report = ?, updated_at = datetime('now') WHERE id = ?",
                    (status, confidence, abstract or "", research_report or "", existing["id"]),
                )
                row = c.execute("SELECT * FROM industries WHERE id = ?", (existing["id"],)).fetchone()
            else:
                raise HTTPException(status_code=409, detail="Duplicate entry or constraint violation")
    return dict(row)


def update_industry(
    industry_id: int,
    user_id: int,
    *,
    name: Optional[str] = None,
    confidence: Optional[int] = None,
    abstract: Optional[str] = None,
    research_report: Optional[str] = None,
    status: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> dict:
    data: dict = {}
    if name is not None:
        data["name"] = name
    if confidence is not None:
        data["confidence"] = confidence
    if abstract is not None:
        data["abstract"] = abstract
    if research_report is not None:
        data["research_report"] = research_report
    if status is not None:
        data["status"] = status
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    set_clause = ", ".join(f"{k} = ?" for k in data)
    values = list(data.values()) + [industry_id, user_id]
    with get_conn(conn) as c:
        cursor = c.execute(f"UPDATE industries SET {set_clause} WHERE id = ? AND user_id = ?", values)
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Not found")
        row = c.execute("SELECT * FROM industries WHERE id = ? AND user_id = ?", (industry_id, user_id)).fetchone()
    return dict(row)


def delete_industry(industry_id: int, user_id: int, conn: Optional[sqlite3.Connection] = None) -> dict:
    with get_conn(conn) as c:
        cursor = c.execute(
            "UPDATE industries SET status = 'removed' WHERE id = ? AND user_id = ? AND status != 'removed'",
            (industry_id, user_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Not found or already removed")
    return {"id": industry_id, "status": "removed"}


# ============================================================================
# Route Registration
# ============================================================================

def register_routes(app: FastAPI) -> None:
    @app.get("/api/industries", response_model=list[IndustryResponse], dependencies=[Depends(require_jwt)])
    async def _list(status: Optional[str] = Query(None), user_id: int = Depends(require_real_user)):
        return list_industries(user_id, status)

    @app.post("/api/industries", response_model=IndustryResponse, status_code=status.HTTP_201_CREATED)
    async def _create(req: IndustryCreate, user_id: int = Depends(require_real_user)):
        return create_industry(user_id, req.name, req.confidence, req.abstract, req.research_report)

    @app.get("/api/industries/{industry_id}", response_model=IndustryResponse)
    async def _get(industry_id: int, user_id: int = Depends(require_real_user)):
        return get_industry(industry_id, user_id)

    @app.put("/api/industries/{industry_id}", response_model=IndustryResponse)
    async def _update(industry_id: int, req: IndustryUpdate, user_id: int = Depends(require_real_user)):
        data = {k: v for k, v in req.model_dump().items() if v is not None}
        if "recommended_stocks" in data:
            data["recommended_stocks"] = data["recommended_stocks"]  # keep as list for update_industry
        return update_industry(industry_id, user_id, **data)

    @app.delete("/api/industries/{industry_id}")
    async def _delete(industry_id: int, user_id: int = Depends(require_real_user)):
        return delete_industry(industry_id, user_id)
