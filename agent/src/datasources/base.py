"""Shared infrastructure for the datasources layer.

Provides:
- Exception classes (DataSourceError, NoDataAvailableError)
- Generic fallback helper
- TTLCache for request deduplication
- normalize_code for ticker format conversion
- baostock_session context manager
"""

from __future__ import annotations

import logging
import re
import time
from contextlib import asynccontextmanager
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class DataSourceError(Exception):
    """Base exception for data source failures."""


class NoDataAvailableError(DataSourceError):
    """Raised when both primary and fallback sources fail."""


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------

async def fallback(
    primary_fn: Callable[[], Any],
    fallback_fn: Callable[[], Any] | None = None,
    *,
    label: str = "",
) -> Any:
    """Try *primary_fn*; on failure try *fallback_fn*.

    Returns the result of whichever succeeds.  Raises ``NoDataAvailableError``
    when both fail (or when no fallback is provided).
    """
    try:
        return await primary_fn()
    except Exception as exc:
        if not fallback_fn:
            raise NoDataAvailableError(f"{label}: primary source failed — {exc}") from exc
        logger.warning("%s: primary failed (%s), trying fallback", label, exc)
        try:
            return await fallback_fn()
        except Exception as fb_exc:
            raise NoDataAvailableError(
                f"{label}: primary ({exc}) and fallback ({fb_exc}) both failed"
            ) from fb_exc


# ---------------------------------------------------------------------------
# TTLCache (simple in-memory)
# ---------------------------------------------------------------------------

class TTLCache:
    """Keyed TTL cache backed by a plain dict. Not thread-safe."""

    def __init__(self, default_ttl: float = 30.0) -> None:
        self._store: dict[str, tuple[float, Any]] = {}
        self.default_ttl = default_ttl

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        self._store[key] = (time.monotonic() + (ttl or self.default_ttl), value)

    def clear(self) -> None:
        self._store.clear()


# Module-level caches with different TTLs
cache_quote = TTLCache(default_ttl=15.0)    # real-time quotes: 15s
cache_kline = TTLCache(default_ttl=300.0)   # historical kline: 5min
cache_valuation = TTLCache(default_ttl=60.0) # valuation: 1min
cache_news = TTLCache(default_ttl=300.0)    # news: 5min


# ---------------------------------------------------------------------------
# Code normalization
# ---------------------------------------------------------------------------

# Accepts: 600519 / sh600519 / SH600519 / 600519.SH / 600519.sh / SH.600519
_CODE_RE = re.compile(r"^([shszSHSZ]{0,2})[.]?(\d{6})$")


def normalize_code(code: str) -> str:
    """Normalize a ticker to plain 6-digit string.

    >>> normalize_code("sh600519")
    '600519'
    >>> normalize_code("600519.SH")
    '600519'
    """
    code = code.strip()
    m = _CODE_RE.match(code)
    if m:
        return m.group(2)
    # Fallback: strip non-digits and hope for the best
    digits = re.sub(r"\D", "", code)
    if len(digits) == 6:
        return digits
    raise ValueError(f"Invalid stock code: {code!r}")


def to_mootdx_code(code: str) -> str:
    """Return the 6-digit code for mootdx (same as normalize_code)."""
    return normalize_code(code)


def to_baostock_code(code: str) -> str:
    """Convert to baostock format: ``sh.600519`` / ``sz.000001``."""
    c = normalize_code(code)
    prefix = "sh" if c.startswith(("6", "9")) else ("bj" if c.startswith("8") else "sz")
    return f"{prefix}.{c}"


def to_tencent_code(code: str) -> str:
    """Convert to Tencent Finance format: ``sh600519`` / ``sz000001``."""
    c = normalize_code(code)
    prefix = "sh" if c.startswith(("6", "9")) else ("bj" if c.startswith("8") else "sz")
    return f"{prefix}{c}"


def mootdx_market(code: str) -> int:
    """Return mootdx market number: 0=深圳, 1=上海."""
    c = normalize_code(code)
    return 1 if c.startswith(("6", "9")) else 0


# ---------------------------------------------------------------------------
# mootdx client helper
# ---------------------------------------------------------------------------

_client = None


def get_mootdx_client():
    """Create a mootdx Quotes client (TCP).

    Caches the client instance. On first call or when the cached
    client becomes unhealthy, creates a new one (no bestip scan).
    """
    global _client
    from mootdx.quotes import Quotes

    if _client is not None:
        try:
            if _client.server and len(_client.server) == 2:
                return _client
        except Exception:
            pass
        _client = None

    _client = Quotes.factory(market="std")
    return _client


# ---------------------------------------------------------------------------
# baostock session
# ---------------------------------------------------------------------------

@asynccontextmanager
async def baostock_session():
    """Async context manager wrapping baostock login/logout."""
    import baostock as bs

    rs = bs.login()
    if rs.error_code != "0":
        raise DataSourceError(f"baostock login failed: {rs.error_msg}")
    try:
        yield bs
    finally:
        bs.logout()


# ---------------------------------------------------------------------------
# Period helpers
# ---------------------------------------------------------------------------

PERIOD_MAP: dict[str, int] = {
    "daily": 4,
    "weekly": 5,
    "monthly": 6,
    "1min": 7,
    "5min": 8,
    "15min": 9,
    "30min": 10,
    "60min": 11,
}

BAOSTOCK_PERIOD_MAP: dict[str, str] = {
    "daily": "d",
    "weekly": "w",
    "monthly": "m",
}
