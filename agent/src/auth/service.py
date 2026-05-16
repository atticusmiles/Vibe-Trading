"""Password hashing and JWT token management."""

from __future__ import annotations

import os
import time
from typing import Any

import bcrypt
import jwt

_JWT_EXPIRY_SECONDS = 86400  # 24 hours


def _get_jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET", "").strip()
    if not secret:
        raise RuntimeError("JWT_SECRET environment variable is not set")
    return secret


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_token(user_id: int) -> str:
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "exp": int(time.time()) + _JWT_EXPIRY_SECONDS,
    }
    return jwt.encode(payload, _get_jwt_secret(), algorithm="HS256")


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, _get_jwt_secret(), algorithms=["HS256"])
