"""Valuation data: current snapshot and historical series.

Primary source: baostock.
Fallback: Tencent Finance HTTP API.
"""

from __future__ import annotations

import logging
import urllib.request
from datetime import datetime
from typing import Any

from .base import (
    NoDataAvailableError,
    baostock_session,
    cache_valuation,
    fallback,
    normalize_code,
    to_baostock_code,
    to_tencent_code,
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
        return await _valuation_baostock(code)

    async def _fb() -> Valuation:
        return await _valuation_tencent(code)

    val = await fallback(_primary, _fb, label=f"get_valuation({code})")
    cache_valuation.set(cache_key, val)
    return val


async def _valuation_baostock(code: str) -> Valuation:
    """Fetch latest valuation from baostock."""
    bs_code = to_baostock_code(code)
    today = datetime.now().strftime("%Y-%m-%d")

    async with baostock_session() as bs:
        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,peTTM,pbMRQ,psTTM,turn,tradestatus",
            start_date=today,
            end_date=today,
            frequency="d",
            adjustflag="3",
        )
        rows = []
        while rs.error_code == "0" and rs.next():
            rows.append(rs.get_row_data())

    # If today has no data (e.g. non-trading day), try recent days
    if not rows:
        async with baostock_session() as bs:
            rs = bs.query_history_k_data_plus(
                bs_code,
                "date,peTTM,pbMRQ,psTTM",
                start_date="2020-01-01",
                end_date=today,
                frequency="d",
                adjustflag="3",
            )
            all_rows = []
            while rs.error_code == "0" and rs.next():
                all_rows.append(rs.get_row_data())
            if all_rows:
                rows = [all_rows[-1]]

    if not rows:
        raise NoDataAvailableError(f"baostock: no valuation for {code}")

    r = rows[0]
    return Valuation(
        pe_ttm=float(r[1]) if r[1] else 0,
        pb=float(r[2]) if r[2] else 0,
        ps_ttm=float(r[3]) if r[3] else 0,
    )


async def _valuation_tencent(code: str) -> Valuation:
    """Fetch valuation from Tencent Finance HTTP API.

    Returns ~ separated 88 fields, GBK encoded.
    Key fields: 39=PE(TTM), 46=PB, 44=总市值(亿), 45=流通市值(亿),
                47=涨停价, 48=跌停价, 52=PE(静态).
    """
    tcode = to_tencent_code(code)
    url = f"https://qt.gtimg.cn/q={tcode}"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0")
    resp = urllib.request.urlopen(req, timeout=10)
    data = resp.read().decode("gbk")

    for line in data.strip().split(";"):
        if not line.strip() or "=" not in line or '"' not in line:
            continue
        vals = line.split('"')[1].split("~")
        if len(vals) < 53:
            continue
        return Valuation(
            pe_ttm=float(vals[39]) if vals[39] else 0,
            pe_static=float(vals[52]) if vals[52] else 0,
            pb=float(vals[46]) if vals[46] else 0,
            total_mv=float(vals[44]) if vals[44] else 0,
            circ_mv=float(vals[45]) if vals[45] else 0,
            turnover=float(vals[38]) if vals[38] else 0,
            limit_up=float(vals[47]) if vals[47] else 0,
            limit_down=float(vals[48]) if vals[48] else 0,
        )

    raise NoDataAvailableError(f"Tencent Finance: no valuation for {code}")


# ---------------------------------------------------------------------------
# Historical valuation
# ---------------------------------------------------------------------------

async def get_valuation_history(
    code: str,
    start_date: str,
    end_date: str,
) -> list[ValuationPoint]:
    """Historical PE/PB/PS series from baostock."""
    code = normalize_code(code)
    bs_code = to_baostock_code(code)

    async with baostock_session() as bs:
        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,peTTM,pbMRQ,psTTM",
            start_date=start_date,
            end_date=end_date,
            frequency="d",
            adjustflag="3",
        )
        rows = []
        while rs.error_code == "0" and rs.next():
            rows.append(rs.get_row_data())

    if not rows:
        raise NoDataAvailableError(
            f"baostock: no valuation history for {code} ({start_date}~{end_date})"
        )

    points: list[ValuationPoint] = []
    for r in rows:
        points.append(ValuationPoint(
            date=str(r[0]),
            pe_ttm=float(r[1]) if r[1] else 0,
            pb=float(r[2]) if r[2] else 0,
            ps_ttm=float(r[3]) if r[3] else 0,
        ))
    return points
