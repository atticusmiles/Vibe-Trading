"""Market data: K-line bars and real-time quotes.

K-line: baostock (primary) → mootdx (fallback).
Real-time quotes: mootdx only.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from .base import (
    NoDataAvailableError,
    baostock_lock,
    cache_kline,
    cache_quote,
    fallback,
    get_mootdx_client,
    mootdx_market,
    normalize_code,
    to_baostock_code,
    to_mootdx_code,
    PERIOD_MAP,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class Bar:
    """Single OHLCV bar."""

    __slots__ = ("date", "open", "high", "low", "close", "volume", "amount")

    def __init__(
        self, date: str, open: float, high: float, low: float,
        close: float, volume: float, amount: float,
    ) -> None:
        self.date = date
        self.open = open
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume
        self.amount = amount

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "amount": self.amount,
        }


class Quote:
    """Real-time quote snapshot."""

    __slots__ = (
        "price", "change", "change_pct", "volume", "amount",
        "open", "high", "low", "pre_close",
        "bid1_price", "bid1_vol", "bid2_price", "bid2_vol",
        "bid3_price", "bid3_vol", "bid4_price", "bid4_vol",
        "bid5_price", "bid5_vol",
        "ask1_price", "ask1_vol", "ask2_price", "ask2_vol",
        "ask3_price", "ask3_vol", "ask4_price", "ask4_vol",
        "ask5_price", "ask5_vol",
    )

    def __init__(self, **kwargs: Any) -> None:
        for slot in self.__slots__:
            setattr(self, slot, kwargs.get(slot, 0))

    def to_dict(self) -> dict[str, Any]:
        return {s: getattr(self, s) for s in self.__slots__}


# ---------------------------------------------------------------------------
# K-line
# ---------------------------------------------------------------------------

async def get_kline(
    code: str,
    period: str = "daily",
    start_date: str | None = None,
    end_date: str | None = None,
    count: int = 120,
) -> list[Bar]:
    """Fetch K-line bars.  Primary: baostock (daily), fallback: mootdx."""
    code = normalize_code(code)
    cache_key = f"kline:{code}:{period}:{count}:{start_date}:{end_date}"
    cached = cache_kline.get(cache_key)
    if cached is not None:
        return cached

    if period == "daily":
        async def _primary() -> list[Bar]:
            return await asyncio.to_thread(_baostock_kline_sync, code, start_date, end_date, count)

        async def _fb() -> list[Bar]:
            return await asyncio.to_thread(_mootdx_kline_sync, code, period, count)

        bars = await fallback(_primary, _fb, label=f"get_kline({code},{period})")
    else:
        bars = await asyncio.to_thread(_mootdx_kline_sync, code, period, count)

    cache_kline.set(cache_key, bars)
    return bars


def _mootdx_kline_sync(code: str, period: str, count: int) -> list[Bar]:
    """Fetch K-line via mootdx TCP (sync, runs in thread)."""
    category = PERIOD_MAP.get(period)
    if category is None:
        raise ValueError(f"mootdx does not support period {period!r}")

    client = get_mootdx_client()
    market = mootdx_market(code)
    symbol = to_mootdx_code(code)

    df = client.bars(symbol=symbol, category=category, offset=count, market=market)
    if df is None or df.empty:
        raise NoDataAvailableError(f"mootdx returned empty kline for {code}")

    # mootdx returns datetime in both index and column — drop column, then reset
    if "datetime" in df.columns:
        df = df.drop(columns=["datetime"])
    df = df.reset_index()
    if "datetime" in df.columns:
        df = df.rename(columns={"datetime": "date"})

    bars: list[Bar] = []
    for _, row in df.iterrows():
        dt_val = row.get("date", "")
        if isinstance(dt_val, datetime):
            dt_str = dt_val.strftime("%Y-%m-%d")
        else:
            dt_str = str(dt_val)
        bars.append(Bar(
            date=dt_str,
            open=float(row.get("open", 0)),
            high=float(row.get("high", 0)),
            low=float(row.get("low", 0)),
            close=float(row.get("close", 0)),
            volume=float(row.get("vol", 0) or row.get("volume", 0)),
            amount=float(row.get("amount", 0)),
        ))
    return bars


def _baostock_kline_sync(
    code: str,
    start_date: str | None,
    end_date: str | None,
    count: int,
) -> list[Bar]:
    """Fetch daily K-line via baostock (sync, runs in thread)."""
    import baostock as bs

    bs_code = to_baostock_code(code)
    today = datetime.now()
    ed = end_date or today.strftime("%Y-%m-%d")
    sd = start_date or (today - timedelta(days=count * 2)).strftime("%Y-%m-%d")

    with baostock_lock:
        lg = bs.login()
        if lg.error_code != "0":
            raise NoDataAvailableError(f"baostock login failed: {lg.error_msg}")
        try:
            rs = bs.query_history_k_data_plus(
                bs_code,
                "date,open,high,low,close,volume,amount,turn",
                start_date=sd,
                end_date=ed,
                frequency="d",
                adjustflag="3",
            )
            rows = []
            while rs.error_code == "0" and rs.next():
                rows.append(rs.get_row_data())
            if not rows and rs.error_code != "0":
                logger.warning("baostock query failed for %s: %s %s", code, rs.error_code, rs.error_msg)
        finally:
            bs.logout()

    if not rows:
        raise NoDataAvailableError(f"baostock returned empty kline for {code}")

    rows = rows[-count:]
    bars: list[Bar] = []
    for r in rows:
        bars.append(Bar(
            date=str(r[0]),
            open=float(r[1]) if r[1] else 0,
            high=float(r[2]) if r[2] else 0,
            low=float(r[3]) if r[3] else 0,
            close=float(r[4]) if r[4] else 0,
            volume=float(r[5]) if r[5] else 0,
            amount=float(r[6]) if r[6] else 0,
        ))
    return bars


# ---------------------------------------------------------------------------
# Real-time quotes
# ---------------------------------------------------------------------------

async def get_quote(code: str) -> Quote:
    """Real-time quote for a single stock (mootdx only)."""
    code = normalize_code(code)
    cache_key = f"quote:{code}"
    cached = cache_quote.get(cache_key)
    if cached is not None:
        return cached

    result = await _mootdx_quotes([code])
    if code not in result:
        raise NoDataAvailableError(f"No quote data for {code}")
    q = result[code]
    cache_quote.set(cache_key, q)
    return q


async def get_quotes(codes: list[str]) -> dict[str, Quote]:
    """Batch real-time quotes (mootdx only)."""
    normalized = [normalize_code(c) for c in codes]
    cached: dict[str, Quote] = {}
    uncached: list[str] = []
    for c in normalized:
        entry = cache_quote.get(f"quote:{c}")
        if entry is not None:
            cached[c] = entry
        else:
            uncached.append(c)

    if uncached:
        fresh = await _mootdx_quotes(uncached)
        for c, q in fresh.items():
            cache_quote.set(f"quote:{c}", q)
        cached.update(fresh)

    return cached


async def _mootdx_quotes(codes: list[str]) -> dict[str, Quote]:
    return await asyncio.to_thread(_mootdx_quotes_sync, codes)


def _mootdx_quotes_sync(codes: list[str]) -> dict[str, Quote]:
    """Fetch real-time quotes from mootdx (sync, runs in thread)."""
    client = get_mootdx_client()
    symbols = [to_mootdx_code(c) for c in codes]
    market_map = {to_mootdx_code(c): c for c in codes}

    df = client.quotes(symbol=symbols)
    if df is None or df.empty:
        return {}

    result: dict[str, Quote] = {}
    for _, row in df.iterrows():
        stock_code = str(row.get("code", "") or row.get("symbol", ""))
        orig_code = market_map.get(stock_code, stock_code)
        pre_close = float(row.get("last_close", 0) or 0)
        price = float(row.get("price", 0) or 0)
        change = price - pre_close if pre_close else 0
        change_pct = (change / pre_close * 100) if pre_close else 0

        q = Quote(
            price=price,
            change=round(change, 3),
            change_pct=round(change_pct, 2),
            volume=float(row.get("vol", 0) or 0),
            amount=float(row.get("amount", 0) or 0),
            open=float(row.get("open", 0) or 0),
            high=float(row.get("high", 0) or 0),
            low=float(row.get("low", 0) or 0),
            pre_close=pre_close,
            bid1_price=float(row.get("bid1", 0) or 0),
            bid1_vol=float(row.get("bid_vol1", 0) or 0),
            bid2_price=float(row.get("bid2", 0) or 0),
            bid2_vol=float(row.get("bid_vol2", 0) or 0),
            bid3_price=float(row.get("bid3", 0) or 0),
            bid3_vol=float(row.get("bid_vol3", 0) or 0),
            bid4_price=float(row.get("bid4", 0) or 0),
            bid4_vol=float(row.get("bid_vol4", 0) or 0),
            bid5_price=float(row.get("bid5", 0) or 0),
            bid5_vol=float(row.get("bid_vol5", 0) or 0),
            ask1_price=float(row.get("ask1", 0) or 0),
            ask1_vol=float(row.get("ask_vol1", 0) or 0),
            ask2_price=float(row.get("ask2", 0) or 0),
            ask2_vol=float(row.get("ask_vol2", 0) or 0),
            ask3_price=float(row.get("ask3", 0) or 0),
            ask3_vol=float(row.get("ask_vol3", 0) or 0),
            ask4_price=float(row.get("ask4", 0) or 0),
            ask4_vol=float(row.get("ask_vol4", 0) or 0),
            ask5_price=float(row.get("ask5", 0) or 0),
            ask5_vol=float(row.get("ask_vol5", 0) or 0),
        )
        result[orig_code] = q
    return result
