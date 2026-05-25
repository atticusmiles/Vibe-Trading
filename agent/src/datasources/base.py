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
import threading
import time
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
    timeout: float = 10,
) -> Any:
    """Try *primary_fn* (with *timeout*); on failure try *fallback_fn*.

    Returns the result of whichever succeeds.  Raises ``NoDataAvailableError``
    when both fail (or when no fallback is provided).
    """
    try:
        return await asyncio.wait_for(primary_fn(), timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning("%s: primary timed out (%.0fs)", label, timeout)
    except Exception as exc:
        logger.warning("%s: primary failed (%s), trying fallback", label, exc)

    if not fallback_fn:
        raise NoDataAvailableError(f"{label}: primary failed after {timeout}s")
    try:
        return await asyncio.wait_for(fallback_fn(), timeout=timeout)
    except asyncio.TimeoutError:
        raise NoDataAvailableError(f"{label}: both primary and fallback timed out ({timeout}s)")
    except Exception as fb_exc:
        raise NoDataAvailableError(
            f"{label}: primary and fallback both failed ({fb_exc})"
        ) from fb_exc


# ---------------------------------------------------------------------------
# TTLCache (simple in-memory)
# ---------------------------------------------------------------------------

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


class TTLCache:
    """Keyed TTL cache backed by a plain dict. Thread-safe."""

    _MAX_ENTRIES = 10000

    def __init__(self, default_ttl: float = 30.0) -> None:
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self.default_ttl = default_ttl

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if time.monotonic() > expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        with self._lock:
            if len(self._store) >= self._MAX_ENTRIES:
                now = time.monotonic()
                self._store = {k: v for k, v in self._store.items() if v[0] > now}
                if len(self._store) >= self._MAX_ENTRIES:
                    sorted_items = sorted(self._store.items(), key=lambda kv: kv[1][0])
                    self._store = dict(sorted_items[self._MAX_ENTRIES // 2:])
            self._store[key] = (time.monotonic() + (ttl or self.default_ttl), value)

    def clear(self) -> None:
        with self._lock:
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
_CODE_RE = re.compile(r"^([shszbjSHSZBJ]{0,2})[.]?(\d{6})$")


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
    prefix = "sh" if c.startswith(("6", "9")) else ("bj" if c.startswith(("4", "8")) else "sz")
    return f"{prefix}.{c}"


def to_tencent_code(code: str) -> str:
    """Convert to Tencent Finance format: ``sh600519`` / ``sz000001``."""
    c = normalize_code(code)
    prefix = "sh" if c.startswith(("6", "9")) else ("bj" if c.startswith(("4", "8")) else "sz")
    return f"{prefix}{c}"


def mootdx_market(code: str) -> int:
    """Return mootdx market number: 0=深圳, 1=上海."""
    c = normalize_code(code)
    return 1 if c.startswith(("6", "9")) else 0


def _safe_float(v: Any) -> float:
    """Convert to float, returning 0.0 on failure."""
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


# ---------------------------------------------------------------------------
# mootdx client helper
# ---------------------------------------------------------------------------

_client: Any = None
_client_lock = threading.Lock()


def get_mootdx_client():
    """Create a mootdx Quotes client (TCP).

    Returns a cached client, creating a new one on first call or when
    the cached client is unhealthy. Thread-safe.
    """
    from mootdx.quotes import Quotes

    with _client_lock:
        global _client
        if _client is not None:
            try:
                # Verify the client is alive by checking its server attribute
                if getattr(_client, "server", None):
                    return _client
            except Exception:
                pass
        _client = Quotes.factory(market="std")
        return _client


# ---------------------------------------------------------------------------
# baostock session
# ---------------------------------------------------------------------------

baostock_lock = threading.RLock()
"""Serialize all baostock login/query/logout sequences (global singleton session)."""


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
