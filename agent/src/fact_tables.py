"""Fact table CRUD routes: trends, industries, stocks, and dashboard."""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from src.db import get_db

_bearer = HTTPBearer(auto_error=False)


async def _require_jwt(
    request: Request,
    cred: Optional[HTTPAuthorizationCredentials] = Security(_bearer),
) -> int:
    """JWT auth dependency — delegates to src.auth.middleware."""
    from src.auth.middleware import require_jwt_auth
    return await require_jwt_auth(request, cred)


async def _require_real_user(user_id: int = Depends(_require_jwt)) -> int:
    """Reject dev-mode user_id=0."""
    if user_id == 0:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user_id


# ============================================================================
# Status filter helper
# ============================================================================

_STATUS_MAP: Dict[Optional[str], str] = {
    "active": "AND status IN ('proposed','adopted')",
    "proposed": "AND status = 'proposed'",
    "adopted": "AND status = 'adopted'",
    "rejected": "AND status = 'rejected'",
    "removed": "AND status = 'removed'",
    None: "AND status != 'removed'",
}


def _status_filter(status: Optional[str]) -> str:
    return _STATUS_MAP.get(status, _STATUS_MAP[None])


# ============================================================================
# Pydantic Models — Trends
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


# ============================================================================
# Pydantic Models — Industries
# ============================================================================

class IndustryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    confidence: int = Field(5, ge=0, le=10)
    reason: Optional[str] = None
    research_report: Optional[str] = None
    recommended_stocks: Optional[List[str]] = None


class IndustryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    confidence: Optional[int] = Field(None, ge=0, le=10)
    reason: Optional[str] = None
    research_report: Optional[str] = None
    recommended_stocks: Optional[List[str]] = None
    status: Optional[str] = Field(None, pattern=r"^(proposed|adopted|rejected|removed)$")


class IndustryResponse(BaseModel):
    id: int
    user_id: int
    status: str
    name: str
    confidence: int = 5
    reason: Optional[str] = None
    research_report: Optional[str] = None
    recommended_stocks: Optional[str] = "[]"
    recommended_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ============================================================================
# Pydantic Models — Stocks
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
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ============================================================================
# Pydantic Models — Dashboard
# ============================================================================

class RecentlyUpdatedItem(BaseModel):
    type: str
    id: int
    title: str
    confidence: int = 5
    updated_at: Optional[str] = None


class DashboardResponse(BaseModel):
    stats: Dict[str, Dict[str, int]]
    recently_updated: List[RecentlyUpdatedItem]
    latest_runs: List[Dict[str, Any]]


# ============================================================================
# Generic CRUD helpers
# ============================================================================

def _list_items(table: str, user_id: int, status_filter: Optional[str]) -> list[dict]:
    filt = _status_filter(status_filter)
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM {table} WHERE user_id = ? {filt} ORDER BY updated_at DESC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def _get_item(table: str, item_id: int, user_id: int) -> dict:
    with get_db() as conn:
        row = conn.execute(
            f"SELECT * FROM {table} WHERE id = ? AND user_id = ?",
            (item_id, user_id),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return dict(row)


def _create_item(table: str, user_id: int, columns: list[str], values: list) -> dict:
    placeholders = ", ".join("?" for _ in values)
    col_str = ", ".join(columns)
    with get_db() as conn:
        try:
            conn.execute(
                f"INSERT INTO {table} (user_id, {col_str}) VALUES (?, {placeholders})",
                [user_id, *values],
            )
            row = conn.execute(
                f"SELECT * FROM {table} WHERE id = last_insert_rowid()",
            ).fetchone()
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
    return dict(row)


def _update_item(table: str, item_id: int, user_id: int, data: dict) -> dict:
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    set_clause = ", ".join(f"{k} = ?" for k in data)
    values = list(data.values()) + [item_id, user_id]
    with get_db() as conn:
        cursor = conn.execute(
            f"UPDATE {table} SET {set_clause} WHERE id = ? AND user_id = ?",
            values,
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Not found")
        row = conn.execute(
            f"SELECT * FROM {table} WHERE id = ? AND user_id = ?",
            (item_id, user_id),
        ).fetchone()
    return dict(row)


def _soft_delete(table: str, item_id: int, user_id: int) -> dict:
    with get_db() as conn:
        cursor = conn.execute(
            f"UPDATE {table} SET status = 'removed' WHERE id = ? AND user_id = ? AND status != 'removed'",
            (item_id, user_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Not found or already removed")
    return {"id": item_id, "status": "removed"}


# ============================================================================
# Dashboard helpers
# ============================================================================

def _count_by_status(conn: sqlite3.Connection, table: str, user_id: int) -> dict[str, int]:
    rows = conn.execute(
        f"SELECT status, COUNT(*) as cnt FROM {table} WHERE user_id = ? GROUP BY status",
        (user_id,),
    ).fetchall()
    return {r["status"]: r["cnt"] for r in rows}


def _get_recently_updated(conn: sqlite3.Connection, user_id: int, limit: int = 5) -> list[dict]:
    items: list[dict] = []
    queries = [
        ("trend", "SELECT id, title, confidence, updated_at FROM trends WHERE user_id = ? AND status != 'removed' ORDER BY updated_at DESC LIMIT ?"),
        ("industry", "SELECT id, name as title, confidence, updated_at FROM industries WHERE user_id = ? AND status != 'removed' ORDER BY updated_at DESC LIMIT ?"),
        ("stock", "SELECT id, code as title, confidence, updated_at FROM stocks WHERE user_id = ? AND status != 'removed' ORDER BY updated_at DESC LIMIT ?"),
    ]
    for type_name, sql in queries:
        for r in conn.execute(sql, (user_id, limit)).fetchall():
            items.append({"type": type_name, "id": r["id"], "title": r["title"], "confidence": r["confidence"], "updated_at": r["updated_at"]})
    items.sort(key=lambda x: x["updated_at"] or "", reverse=True)
    return items[:limit]


# ============================================================================
# Route registration
# ============================================================================

def register_fact_table_routes(app: FastAPI) -> None:
    """Register all fact table CRUD + dashboard routes on the FastAPI app."""

    # --- Trends ---
    @app.get("/api/trends", response_model=List[TrendResponse], dependencies=[Depends(_require_jwt)])
    async def list_trends(status: Optional[str] = Query(None), user_id: int = Depends(_require_real_user)):
        return _list_items("trends", user_id, status)

    @app.post("/api/trends", response_model=TrendResponse, status_code=status.HTTP_201_CREATED)
    async def create_trend(req: TrendCreate, user_id: int = Depends(_require_real_user)):
        return _create_item(
            "trends", user_id,
            ["status", "title", "level", "confidence", "evidence"],
            ["adopted", req.title, req.level, req.confidence, req.evidence or ""],
        )

    @app.get("/api/trends/{trend_id}", response_model=TrendResponse)
    async def get_trend(trend_id: int, user_id: int = Depends(_require_real_user)):
        return _get_item("trends", trend_id, user_id)

    @app.put("/api/trends/{trend_id}", response_model=TrendResponse)
    async def update_trend(trend_id: int, req: TrendUpdate, user_id: int = Depends(_require_real_user)):
        data = {k: v for k, v in req.model_dump().items() if v is not None}
        return _update_item("trends", trend_id, user_id, data)

    @app.delete("/api/trends/{trend_id}")
    async def delete_trend(trend_id: int, user_id: int = Depends(_require_real_user)):
        return _soft_delete("trends", trend_id, user_id)

    # --- Industries ---
    @app.get("/api/industries", response_model=List[IndustryResponse], dependencies=[Depends(_require_jwt)])
    async def list_industries(status: Optional[str] = Query(None), user_id: int = Depends(_require_real_user)):
        return [
            {**r, "recommended_count": len(__import__("json").loads(r.get("recommended_stocks", "[]")))}
            for r in _list_items("industries", user_id, status)
        ]

    @app.post("/api/industries", response_model=IndustryResponse, status_code=status.HTTP_201_CREATED)
    async def create_industry(req: IndustryCreate, user_id: int = Depends(_require_real_user)):
        import json
        r = _create_item(
            "industries", user_id,
            ["status", "name", "confidence", "reason", "research_report", "recommended_stocks"],
            ["adopted", req.name, req.confidence, req.reason or "", req.research_report or "", json.dumps(req.recommended_stocks or [])],
        )
        r["recommended_count"] = len(req.recommended_stocks or [])
        return r

    @app.get("/api/industries/{industry_id}", response_model=IndustryResponse)
    async def get_industry(industry_id: int, user_id: int = Depends(_require_real_user)):
        import json
        r = _get_item("industries", industry_id, user_id)
        r["recommended_count"] = len(json.loads(r.get("recommended_stocks", "[]")))
        return r

    @app.put("/api/industries/{industry_id}", response_model=IndustryResponse)
    async def update_industry(industry_id: int, req: IndustryUpdate, user_id: int = Depends(_require_real_user)):
        import json
        data = {k: v for k, v in req.model_dump().items() if v is not None}
        if "recommended_stocks" in data:
            data["recommended_stocks"] = json.dumps(data["recommended_stocks"])
        r = _update_item("industries", industry_id, user_id, data)
        r["recommended_count"] = len(json.loads(r.get("recommended_stocks", "[]")))
        return r

    @app.delete("/api/industries/{industry_id}")
    async def delete_industry(industry_id: int, user_id: int = Depends(_require_real_user)):
        return _soft_delete("industries", industry_id, user_id)

    # --- Stocks ---
    @app.get("/api/stocks", response_model=List[StockResponse], dependencies=[Depends(_require_jwt)])
    async def list_stocks(status: Optional[str] = Query(None), user_id: int = Depends(_require_real_user)):
        return _list_items("stocks", user_id, status)

    @app.post("/api/stocks", response_model=StockResponse, status_code=status.HTTP_201_CREATED)
    async def create_stock(req: StockCreate, user_id: int = Depends(_require_real_user)):
        return _create_item(
            "stocks", user_id,
            ["status", "name", "code", "confidence", "industry_name", "position", "advice", "target_price", "stop_loss", "reason"],
            ["adopted", req.name, req.code, req.confidence, req.industry_name or "", req.position, req.advice or "", req.target_price, req.stop_loss, req.reason or ""],
        )

    @app.get("/api/stocks/{stock_id}", response_model=StockResponse)
    async def get_stock(stock_id: int, user_id: int = Depends(_require_real_user)):
        return _get_item("stocks", stock_id, user_id)

    @app.put("/api/stocks/{stock_id}", response_model=StockResponse)
    async def update_stock(stock_id: int, req: StockUpdate, user_id: int = Depends(_require_real_user)):
        data = {k: v for k, v in req.model_dump().items() if v is not None}
        return _update_item("stocks", stock_id, user_id, data)

    @app.delete("/api/stocks/{stock_id}")
    async def delete_stock(stock_id: int, user_id: int = Depends(_require_real_user)):
        return _soft_delete("stocks", stock_id, user_id)

    # --- Dashboard ---
    @app.get("/api/dashboard", response_model=DashboardResponse)
    async def get_dashboard(user_id: int = Depends(_require_real_user)):
        with get_db() as conn:
            stats = {
                "trends": _count_by_status(conn, "trends", user_id),
                "industries": _count_by_status(conn, "industries", user_id),
                "stocks": _count_by_status(conn, "stocks", user_id),
            }
            recently = _get_recently_updated(conn, user_id, limit=5)

        # Latest runs from filesystem (reuse existing data dir)
        runs: list[dict] = []
        try:
            from src.core.config import get_data_dir
            runs_dir = get_data_dir() / "runs"
            if runs_dir.exists():
                for d in sorted(runs_dir.iterdir(), key=lambda x: x.name, reverse=True)[:5]:
                    if d.is_dir():
                        runs.append({"run_id": d.name})
        except Exception:
            pass

        return {"stats": stats, "recently_updated": recently, "latest_runs": runs}
