"""Shared infrastructure for fact table modules."""

from __future__ import annotations

import sqlite3
from typing import Dict, Optional

from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from src.db import get_db

_bearer = HTTPBearer(auto_error=False)

# Target type → table name
TABLE_MAP: Dict[str, str] = {"trend": "trends", "industry": "industries", "stock": "stocks"}

# Allowed payload fields per target type (prevents writing to id, user_id, etc.)
ALLOWED_FIELDS: Dict[str, set] = {
    "trend": {"title", "level", "confidence", "evidence"},
    "industry": {"name", "confidence", "reason", "research_report", "recommended_stocks"},
    "stock": {"name", "code", "confidence", "industry_name", "position", "advice", "target_price", "stop_loss", "reason"},
}

# Status → SQL filter fragment
_STATUS_MAP: Dict[Optional[str], str] = {
    "active": "AND status IN ('proposed','adopted')",
    "proposed": "AND status = 'proposed'",
    "adopted": "AND status = 'adopted'",
    "rejected": "AND status = 'rejected'",
    "removed": "AND status = 'removed'",
    None: "AND status != 'removed'",
}


def status_filter(status: Optional[str]) -> str:
    return _STATUS_MAP.get(status, _STATUS_MAP[None])


async def require_jwt(
    request: Request,
    cred: Optional[HTTPAuthorizationCredentials] = Security(_bearer),
) -> int:
    from src.auth.middleware import require_jwt_auth
    return await require_jwt_auth(request, cred)


async def require_real_user(user_id: int = Depends(require_jwt)) -> int:
    if user_id == 0:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user_id


def get_conn(conn: Optional[sqlite3.Connection] = None):
    """Return a context manager for the connection.

    If conn is provided (e.g. from a shared transaction), yield it directly.
    Otherwise open a new connection with auto-commit.
    """
    if conn is not None:
        return _PassthroughConn(conn)
    return get_db()


class _PassthroughConn:
    """Context manager that yields an existing connection without closing it."""
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *args):
        pass
