"""Valuation data: current snapshot, historical series, and percentile ranking.

Primary source: baostock.
Fallback: Tencent Finance HTTP API.
"""

from __future__ import annotations

import asyncio
import logging
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from typing import Any

from .base import (
    NoDataAvailableError,
    _UA,
    _safe_float,
    baostock_lock,
    cache_valuation,
    fallback,
    normalize_code,
    to_baostock_code,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class Valuation:
    """Current valuation snapshot."""

    __slots__ = (
        "pe_ttm", "pe_static", "pb", "ps_ttm",
        "total_mv", "circ_mv", "turnover",
        "limit_up", "limit_down",
    )

    def __init__(self, **kwargs: Any) -> None:
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot, 0))

    def to_dict(self) -> dict[str, Any]:
        return {s: getattr(self, s) for s in self.__slots__}


class ValuationPoint:
    """Single point in a valuation history series."""

    __slots__ = ("date", "pe_ttm", "pb", "ps_ttm")

    def __init__(self, date: str, pe_ttm: float, pb: float, ps_ttm: float) -> None:
        self.date = date
        self.pe_ttm = pe_ttm
        self.pb = pb
        self.ps_ttm = ps_ttm

    def to_dict(self) -> dict[str, Any]:
        return {"date": self.date, "pe_ttm": self.pe_ttm, "pb": self.pb, "ps_ttm": self.ps_ttm}


# ---------------------------------------------------------------------------
# Current valuation
# ---------------------------------------------------------------------------

async def get_valuation(code: str) -> Valuation:
    """Current valuation snapshot.  Primary: baostock, fallback: Tencent Finance."""
    code = normalize_code(code)
    cache_key = f"val:{code}"
    cached = cache_valuation.get(cache_key)
    if cached is not None:
        return cached

    async def _primary() -> Valuation:
        return await asyncio.to_thread(_baostock_valuation_sync, code)

    async def _fb() -> Valuation:
        return await asyncio.to_thread(_tencent_valuation_sync, code)

    val = await fallback(_primary, _fb, label=f"get_valuation({code})")
    cache_valuation.set(cache_key, val)
    return val


def _baostock_valuation_sync(code: str) -> Valuation:
    """Fetch latest valuation from baostock (runs in thread)."""
    import baostock as bs

    bs_code = to_baostock_code(code)
    today = datetime.now().strftime("%Y-%m-%d")

    with baostock_lock:
        lg = bs.login()
        if lg.error_code != "0":
            raise NoDataAvailableError(f"baostock login failed: {lg.error_msg}")
        try:
            rows = _bs_query_k_data(bs, bs_code, "date,peTTM,pbMRQ,psTTM,turn,tradestatus", today, today)
            if not rows:
                # Try the last 30 days instead of querying all the way back to 2020
                fallback_start = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
                rows = _bs_query_k_data(bs, bs_code, "date,peTTM,pbMRQ,psTTM", fallback_start, today)
                if rows:
                    rows = [rows[-1]]
        finally:
            bs.logout()

    if not rows:
        raise NoDataAvailableError(f"baostock: no valuation for {code}")

    r = rows[0]
    return Valuation(
        pe_ttm=_safe_float(r[1]),
        pb=_safe_float(r[2]),
        ps_ttm=_safe_float(r[3]),
    )


def _tencent_valuation_sync(code: str) -> Valuation:
    """Fetch valuation from Tencent Finance HTTP API (runs in thread)."""
    from .base import to_tencent_code

    tcode = to_tencent_code(code)
    url = f"https://qt.gtimg.cn/q={tcode}"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", _UA)

    try:
        resp = urllib.request.urlopen(req, timeout=10)
    except (urllib.error.URLError, OSError) as exc:
        raise NoDataAvailableError(f"Tencent Finance HTTP error for {code}: {exc}") from exc

    raw = resp.read()
    try:
        data = raw.decode("gbk")
    except UnicodeDecodeError:
        data = raw.decode("utf-8", errors="replace")

    for line in data.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line:
            continue
        # Verify the response line matches the requested ticker
        prefix = line.split("=", 1)[0].strip().lower()
        if tcode.lower() not in prefix:
            continue
        vals = line.split('"')[1].split("~")
        if len(vals) < 53:
            continue
        return Valuation(
            pe_ttm=_safe_float(vals[39]),
            pe_static=_safe_float(vals[52]),
            pb=_safe_float(vals[46]),
            total_mv=_safe_float(vals[44]),
            circ_mv=_safe_float(vals[45]),
            turnover=_safe_float(vals[38]),
            limit_up=_safe_float(vals[47]),
            limit_down=_safe_float(vals[48]),
        )

    raise NoDataAvailableError(f"Tencent Finance: no valuation for {code}")


# ---------------------------------------------------------------------------
# Historical valuation
# ---------------------------------------------------------------------------

async def get_valuation_history(
    code: str,
    months: int = 1,
) -> list[ValuationPoint]:
    """Historical PE/PB/PS series from baostock."""
    code = normalize_code(code)
    cache_key = f"val_hist:{code}:{months}"
    cached = cache_valuation.get(cache_key)
    if cached is not None:
        return cached

    bs_code = to_baostock_code(code)
    today = datetime.now()
    end_date = today.strftime("%Y-%m-%d")
    start_date = (today - timedelta(days=months * 31)).strftime("%Y-%m-%d")

    rows = await asyncio.to_thread(_bs_query_k_data_sync, bs_code, start_date, end_date)

    if not rows:
        raise NoDataAvailableError(
            f"baostock: no valuation history for {code} ({start_date}~{end_date})"
        )

    points: list[ValuationPoint] = []
    for r in rows:
        points.append(ValuationPoint(
            date=str(r[0]),
            pe_ttm=_safe_float(r[1]),
            pb=_safe_float(r[2]),
            ps_ttm=_safe_float(r[3]),
        ))
    cache_valuation.set(cache_key, points)
    return points


# ---------------------------------------------------------------------------
# Valuation percentile
# ---------------------------------------------------------------------------

async def get_valuation_percentile(
    code: str,
    months: int = 60,
) -> dict[str, Any]:
    """Current valuation percentile rank over historical data.

    Fetches `months` months of daily PE/PB/PS from baostock, then calculates
    what percentile the latest value falls at (e.g. pe_percentile=80 means
    80% of historical days had PE lower than today).
    """
    code = normalize_code(code)
    cache_key = f"val_pct:{code}:{months}"
    cached = cache_valuation.get(cache_key)
    if cached is not None:
        return cached

    bs_code = to_baostock_code(code)
    today = datetime.now()
    end = today.strftime("%Y-%m-%d")
    start = (today - timedelta(days=months * 31)).strftime("%Y-%m-%d")

    rows = await asyncio.to_thread(_bs_query_k_data_sync, bs_code, start, end)

    if not rows:
        raise NoDataAvailableError(
            f"baostock: no valuation data for {code} percentile calc"
        )

    pe_vals, pb_vals, ps_vals = [], [], []
    for r in rows:
        for vals, idx in ((pe_vals, 1), (pb_vals, 2), (ps_vals, 3)):
            try:
                v = float(r[idx])
                if v != 0:
                    vals.append(v)
            except (ValueError, TypeError, IndexError):
                pass

    if not pe_vals and not pb_vals and not ps_vals:
        raise NoDataAvailableError(f"baostock: all valuation values empty for {code}")

    latest_pe = next((v for v in reversed(pe_vals) if v != 0), None)
    latest_pb = next((v for v in reversed(pb_vals) if v != 0), None)
    latest_ps = next((v for v in reversed(ps_vals) if v != 0), None)

    def _pct(arr: list[float], current: float | None) -> float | None:
        if current is None or not arr:
            return None
        valid = [x for x in arr if x != 0]
        if not valid:
            return None
        return round(sum(1 for x in valid if x < current) / len(valid) * 100, 1)

    result = {
        "pe_ttm": latest_pe,
        "pb": latest_pb,
        "ps_ttm": latest_ps,
        "pe_percentile": _pct(pe_vals, latest_pe),
        "pb_percentile": _pct(pb_vals, latest_pb),
        "ps_percentile": _pct(ps_vals, latest_ps),
        "sample_count": len(rows),
        "start_date": rows[0][0],
        "end_date": rows[-1][0],
    }
    cache_valuation.set(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# Shared baostock query helpers (sync, run in thread)
# ---------------------------------------------------------------------------

def _bs_query_k_data(bs, code: str, fields: str, start: str, end: str) -> list:
    """Run a baostock k-data query and return all rows."""
    rs = bs.query_history_k_data_plus(
        code, fields,
        start_date=start, end_date=end,
        frequency="d", adjustflag="3",
    )
    rows = []
    while rs.error_code == "0" and rs.next():
        rows.append(rs.get_row_data())
    if not rows and rs.error_code != "0":
        logger.warning("baostock query error %s: %s", rs.error_code, rs.error_msg)
    return rows


def _bs_query_k_data_sync(bs_code: str, start: str, end: str) -> list:
    """Login, query k-data, logout — runs in thread."""
    import baostock as bs

    with baostock_lock:
        lg = bs.login()
        if lg.error_code != "0":
            raise NoDataAvailableError(f"baostock login failed: {lg.error_msg}")
        try:
            return _bs_query_k_data(bs, bs_code, "date,peTTM,pbMRQ,psTTM", start, end)
        finally:
            bs.logout()
