"""AES-256-GCM encryption service for sensitive fields.

Encrypts/decrypts JSON fields named ``key``, ``secret``, or ``app_secret``.
Storage format: ``enc:base64_nonce:base64_ciphertext:base64_tag``
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

_SENSITIVE_KEYS = {"key", "secret", "app_secret"}
_PREFIX = "enc:"


def _get_encryption_key() -> bytes | None:
    raw = os.environ.get("ENCRYPTION_KEY", "").strip()
    if not raw:
        return None
    if len(raw) != 64:
        raise ValueError(
            f"ENCRYPTION_KEY must be 64 hex characters (32 bytes), got {len(raw)}"
        )
    try:
        return bytes.fromhex(raw)
    except ValueError as e:
        raise ValueError(f"ENCRYPTION_KEY is not valid hex: {e}") from e


def is_encryption_available() -> bool:
    try:
        return _get_encryption_key() is not None
    except ValueError:
        return False


def is_encrypted(value: str) -> bool:
    return isinstance(value, str) and value.startswith(_PREFIX)


def encrypt_value(plaintext: str) -> str:
    key = _get_encryption_key()
    if key is None:
        raise RuntimeError("ENCRYPTION_KEY not set — cannot encrypt")
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext_with_tag = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    ciphertext = ciphertext_with_tag[:-16]
    tag = ciphertext_with_tag[-16:]
    parts = [base64.b64encode(nonce).decode(), base64.b64encode(ciphertext).decode(), base64.b64encode(tag).decode()]
    return f"{_PREFIX}{':'.join(parts)}"


def decrypt_value(encrypted: str) -> str:
    if not is_encrypted(encrypted):
        return encrypted
    key = _get_encryption_key()
    if key is None:
        raise RuntimeError("ENCRYPTION_KEY not set — cannot decrypt")
    payload = encrypted[len(_PREFIX):]
    parts = payload.split(":")
    if len(parts) != 3:
        raise ValueError(f"Invalid encrypted format: expected 3 parts, got {len(parts)}")
    nonce = base64.b64decode(parts[0])
    ciphertext = base64.b64decode(parts[1])
    tag = base64.b64decode(parts[2])
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext + tag, None)
    return plaintext.decode("utf-8")


def encrypt_sensitive_fields(data: Any) -> Any:
    """Recursively encrypt sensitive fields (key, secret, app_secret) in a JSON structure."""
    if isinstance(data, dict):
        result = {}
        for k, v in data.items():
            if k in _SENSITIVE_KEYS and isinstance(v, str) and not is_encrypted(v):
                result[k] = encrypt_value(v)
            else:
                result[k] = encrypt_sensitive_fields(v)
        return result
    if isinstance(data, list):
        return [encrypt_sensitive_fields(item) for item in data]
    return data


def decrypt_sensitive_fields(data: Any) -> Any:
    """Recursively decrypt sensitive fields (key, secret, app_secret) in a JSON structure."""
    if isinstance(data, dict):
        result = {}
        for k, v in data.items():
            if k in _SENSITIVE_KEYS and isinstance(v, str) and is_encrypted(v):
                try:
                    result[k] = decrypt_value(v)
                except Exception:
                    result[k] = v
            else:
                result[k] = decrypt_sensitive_fields(v)
        return result
    if isinstance(data, list):
        return [decrypt_sensitive_fields(item) for item in data]
    return data
