"""Dashboard endpoint: stats, recently updated, latest runs."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import Depends, FastAPI
from pydantic import BaseModel, field_validator

from src.db import get_db
from .base import require_real_user


class RecentlyUpdatedItem(BaseModel):
    type: str
    id: int
    title: str
    confidence: int = 5
    updated_at: str | None = None

    @field_validator("confidence", mode="before")
    @classmethod
    def _coerce_confidence(cls, v):
        return int(v)


class DashboardResponse(BaseModel):
    stats: Dict[str, Dict[str, int]]
    recently_updated: List[RecentlyUpdatedItem]
    latest_runs: List[Dict[str, Any]]
    pending_proposals: Dict[str, int] = {}


def _count_by_status(conn, table: str, user_id: int) -> dict[str, int]:
    rows = conn.execute(
        f"SELECT status, COUNT(*) as cnt FROM {table} WHERE user_id = ? GROUP BY status",
        (user_id,),
    ).fetchall()
    return {r["status"]: r["cnt"] for r in rows}


def _get_recently_updated(conn, user_id: int, limit: int = 5) -> list[dict]:
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


def register_routes(app: FastAPI) -> None:
    @app.get("/api/dashboard", response_model=DashboardResponse)
    async def get_dashboard(user_id: int = Depends(require_real_user)):
        with get_db() as conn:
            stats = {
                "trends": _count_by_status(conn, "trends", user_id),
                "industries": _count_by_status(conn, "industries", user_id),
                "stocks": _count_by_status(conn, "stocks", user_id),
            }
            recently = _get_recently_updated(conn, user_id, limit=5)
            proposal_rows = conn.execute(
                "SELECT target_type, COUNT(*) as cnt FROM proposals "
                "WHERE user_id = ? AND status = 'pending' GROUP BY target_type",
                (user_id,),
            ).fetchall()
            pending_proposals = {r["target_type"]: r["cnt"] for r in proposal_rows}

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

        return {"stats": stats, "recently_updated": recently, "latest_runs": runs, "pending_proposals": pending_proposals}
