"""JWT authentication middleware for FastAPI."""

from __future__ import annotations

import ipaddress
import logging
import os

import jwt
from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.auth.service import decode_token

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)

_DOCKER_BRIDGE = ipaddress.ip_network("172.16.0.0/12")


def _is_local_client(request: Request) -> bool:
    client_host = request.client.host if request.client else "unknown"
    if client_host in ("127.0.0.1", "::1", "localhost", "testclient"):
        return True
    try:
        if ipaddress.ip_address(client_host).is_loopback:
            return True
    except ValueError:
        pass
    if os.environ.get("VIBE_TRADING_TRUST_DOCKER_LOOPBACK"):
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            try:
                ip = ipaddress.ip_address(forwarded.split(",")[0].strip())
                if ip.is_loopback or ip in _DOCKER_BRIDGE:
                    return True
            except ValueError:
                pass
    return False


async def require_jwt_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> int:
    """Validate JWT Bearer token and return user_id.

    Falls back to loopback-only access in dev mode (no JWT_SECRET set).
    """
    token = credentials.credentials if credentials else None

    if not token:
        if not os.environ.get("JWT_SECRET", "").strip():
            if _is_local_client(request):
                return 0
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_id = payload.get("sub")
    try:
        return int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")


async def require_event_stream_jwt_auth(
    request: Request,
    token: str | None = Query(None, alias="token"),
) -> int:
    """Validate JWT for SSE endpoints via ``?token=`` query parameter."""
    if not token:
        if not os.environ.get("JWT_SECRET", "").strip():
            if _is_local_client(request):
                return 0
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    try:
        payload = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user_id = payload.get("sub")
    try:
        return int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")


def get_current_user_id(request: Request) -> int:
    """Extract user_id stored in request.state by the middleware."""
    return getattr(request.state, "user_id", 0)
