"""Stock CRUD: explicit-parameter functions + route registration."""

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

class StockCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    code: str = Field(..., min_length=1, max_length=50)
    confidence: int = Field(5, ge=0, le=10)
    industry_name: Optional[str] = None
    position: Optional[float] = Field(None, ge=0)
    advice: Optional[str] = None
    target_price: Optional[float] = Field(None, ge=0)
    stop_loss: Optional[float] = Field(None, ge=0)
    reason: Optional[str] = None


class StockUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    code: Optional[str] = Field(None, min_length=1, max_length=50)
    confidence: Optional[int] = Field(None, ge=0, le=10)
    industry_name: Optional[str] = None
    position: Optional[float] = Field(None, ge=0)
    advice: Optional[str] = None
    target_price: Optional[float] = Field(None, ge=0)
    stop_loss: Optional[float] = Field(None, ge=0)
    reason: Optional[str] = None
    status: Optional[str] = Field(None, pattern=r"^(proposed|adopted|rejected|removed)$")


class StockResponse(BaseModel):
    id: int
    user_id: int
    status: str
    name: str
    code: str
    confidence: int = 5
    industry_name: Optional[str] = None
    position: Optional[float] = None
    advice: Optional[str] = None
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    reason: Optional[str] = None
    research_report: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_confidence(cls, v):
        return int(v)

    @field_validator("target_price", "stop_loss", "position", mode="before")
    @classmethod
    def _coerce_float(cls, v):
        if v is None or v == "":
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None


# ============================================================================
# CRUD Functions
# ============================================================================

def list_stocks(user_id: int, status: Optional[str] = None) -> list[dict]:
    filt = status_filter(status)
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM stocks WHERE user_id = ? {filt} ORDER BY updated_at DESC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_stock(stock_id: int, user_id: int, conn: Optional[sqlite3.Connection] = None) -> dict:
    with get_conn(conn) as c:
        row = c.execute("SELECT * FROM stocks WHERE id = ? AND user_id = ?", (stock_id, user_id)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return dict(row)


def _coerce_float(v: object) -> Optional[float]:
    """Coerce a value to float or None (handles string payloads from LLM proposals)."""
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def create_stock(
    user_id: int,
    name: str,
    code: str,
    confidence: int = 5,
    industry_name: Optional[str] = None,
    position: Optional[float] = None,
    advice: Optional[str] = None,
    target_price: Optional[float] = None,
    stop_loss: Optional[float] = None,
    reason: Optional[str] = None,
    status: str = "adopted",
    conn: Optional[sqlite3.Connection] = None,
) -> dict:
    target_price = _coerce_float(target_price)
    stop_loss = _coerce_float(stop_loss)
    position = _coerce_float(position)
    with get_conn(conn) as c:
        try:
            cursor = c.execute(
                "INSERT INTO stocks (user_id, status, name, code, confidence, industry_name, position, advice, target_price, stop_loss, reason) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, status, name, code, confidence, industry_name or "", position, advice or "", target_price, stop_loss, reason or ""),
            )
            row = c.execute("SELECT * FROM stocks WHERE id = ?", (cursor.lastrowid,)).fetchone()
        except sqlite3.IntegrityError:
            existing = c.execute(
                "SELECT id FROM stocks WHERE user_id = ? AND code = ? AND status = 'removed'",
                (user_id, code),
            ).fetchone()
            if existing:
                c.execute(
                    "UPDATE stocks SET status = ?, name = ?, confidence = ?, industry_name = ?, "
                    "position = ?, advice = ?, target_price = ?, stop_loss = ?, reason = ?, "
                    "updated_at = datetime('now') WHERE id = ?",
                    (status, name, confidence, industry_name or "", position, advice or "",
                     target_price, stop_loss, reason or "", existing["id"]),
                )
                row = c.execute("SELECT * FROM stocks WHERE id = ?", (existing["id"],)).fetchone()
            else:
                raise HTTPException(status_code=409, detail="Duplicate entry or constraint violation")
    return dict(row)


def update_stock(
    stock_id: int,
    user_id: int,
    *,
    name: Optional[str] = None,
    code: Optional[str] = None,
    confidence: Optional[int] = None,
    industry_name: Optional[str] = None,
    position: Optional[float] = None,
    advice: Optional[str] = None,
    target_price: Optional[float] = None,
    stop_loss: Optional[float] = None,
    reason: Optional[str] = None,
    status: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> dict:
    target_price = _coerce_float(target_price)
    stop_loss = _coerce_float(stop_loss)
    position = _coerce_float(position)
    data: dict = {}
    if name is not None:
        data["name"] = name
    if code is not None:
        data["code"] = code
    if confidence is not None:
        data["confidence"] = confidence
    if industry_name is not None:
        data["industry_name"] = industry_name
    if position is not None:
        data["position"] = position
    if advice is not None:
        data["advice"] = advice
    if target_price is not None:
        data["target_price"] = target_price
    if stop_loss is not None:
        data["stop_loss"] = stop_loss
    if reason is not None:
        data["reason"] = reason
    if status is not None:
        data["status"] = status
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    set_clause = ", ".join(f"{k} = ?" for k in data)
    values = list(data.values()) + [stock_id, user_id]
    with get_conn(conn) as c:
        cursor = c.execute(f"UPDATE stocks SET {set_clause} WHERE id = ? AND user_id = ?", values)
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Not found")
        row = c.execute("SELECT * FROM stocks WHERE id = ? AND user_id = ?", (stock_id, user_id)).fetchone()
    return dict(row)


def delete_stock(stock_id: int, user_id: int, conn: Optional[sqlite3.Connection] = None) -> dict:
    with get_conn(conn) as c:
        cursor = c.execute(
            "UPDATE stocks SET status = 'removed' WHERE id = ? AND user_id = ? AND status != 'removed'",
            (stock_id, user_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Not found or already removed")
    return {"id": stock_id, "status": "removed"}


# ============================================================================
# Route Registration
# ============================================================================

def register_routes(app: FastAPI) -> None:
    @app.get("/api/stocks", response_model=list[StockResponse], dependencies=[Depends(require_jwt)])
    async def _list(status: Optional[str] = Query(None), user_id: int = Depends(require_real_user)):
        return list_stocks(user_id, status)

    @app.post("/api/stocks", response_model=StockResponse, status_code=status.HTTP_201_CREATED)
    async def _create(req: StockCreate, user_id: int = Depends(require_real_user)):
        return create_stock(user_id, req.name, req.code, req.confidence, req.industry_name, req.position, req.advice, req.target_price, req.stop_loss, req.reason)

    @app.get("/api/stocks/{stock_id}", response_model=StockResponse)
    async def _get(stock_id: int, user_id: int = Depends(require_real_user)):
        return get_stock(stock_id, user_id)

    @app.put("/api/stocks/{stock_id}", response_model=StockResponse)
    async def _update(stock_id: int, req: StockUpdate, user_id: int = Depends(require_real_user)):
        data = {k: v for k, v in req.model_dump().items() if v is not None}
        return update_stock(stock_id, user_id, **data)

    @app.delete("/api/stocks/{stock_id}")
    async def _delete(stock_id: int, user_id: int = Depends(require_real_user)):
        return delete_stock(stock_id, user_id)
