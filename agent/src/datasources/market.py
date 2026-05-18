"""Market data: K-line bars and real-time quotes.

Primary source: mootdx (TCP).
Fallback for daily K-line: baostock.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from .base import (
    NoDataAvailableError,
    baostock_session,
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
    """Fetch K-line bars.  Primary: mootdx, fallback (daily only): baostock."""
    code = normalize_code(code)
    cache_key = f"kline:{code}:{period}:{count}:{start_date}:{end_date}"
    cached = cache_kline.get(cache_key)
    if cached is not None:
        return cached

    async def _primary() -> list[Bar]:
        return await _kline_mootdx(code, period, count)

    fb = None
    if period == "daily":
        async def _fb() -> list[Bar]:
            return await _kline_baostock(code, start_date, end_date, count)
        fb = _fb

    bars = await fallback(_primary, fb, label=f"get_kline({code},{period})")
    cache_kline.set(cache_key, bars)
    return bars


async def _kline_mootdx(code: str, period: str, count: int) -> list[Bar]:
    """Fetch K-line via mootdx TCP."""
    category = PERIOD_MAP.get(period)
    if category is None:
        raise ValueError(f"mootdx does not support period {period!r}")

    client = get_mootdx_client()
    market = mootdx_market(code)
    symbol = to_mootdx_code(code)

    df = client.bars(symbol=symbol, category=category, offset=count, market=market)
    if df is None or df.empty:
        raise NoDataAvailableError(f"mootdx returned empty kline for {code}")

    # mootdx pitfall: datetime in both index and column
    if "datetime" in df.columns:
        df = df.drop(columns=["datetime"])
    df = df.reset_index()

    bars: list[Bar] = []
    for _, row in df.iterrows():
        dt_val = row.get("datetime") or row.get("date", "")
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


async def _kline_baostock(
    code: str,
    start_date: str | None,
    end_date: str | None,
    count: int,
) -> list[Bar]:
    """Fetch daily K-line via baostock (fallback)."""
    bs_code = to_baostock_code(code)
    today = datetime.now().strftime("%Y-%m-%d")
    sd = start_date or "1990-01-01"
    ed = end_date or today

    async with baostock_session() as bs:
        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,open,high,low,close,volume,amount,turn",
            start_date=sd,
            end_date=ed,
            frequency="d",
            adjustflag="3",  # no adjustment
        )
        rows = []
        while rs.error_code == "0" and rs.next():
            rows.append(rs.get_row_data())

    if not rows:
        raise NoDataAvailableError(f"baostock returned empty kline for {code}")

    # Take last `count` rows
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

    result = await _quotes_mootdx([code])
    if code not in result:
        raise NoDataAvailableError(f"No quote data for {code}")
    q = result[code]
    cache_quote.set(cache_key, q)
    return q


async def get_quotes(codes: list[str]) -> dict[str, Quote]:
    """Batch real-time quotes (mootdx only)."""
    normalized = [normalize_code(c) for c in codes]
    # Check cache first, collect uncached
    cached: dict[str, Quote] = {}
    uncached: list[str] = []
    for c in normalized:
        entry = cache_quote.get(f"quote:{c}")
        if entry is not None:
            cached[c] = entry
        else:
            uncached.append(c)

    if uncached:
        fresh = await _quotes_mootdx(uncached)
        for c, q in fresh.items():
            cache_quote.set(f"quote:{c}", q)
        cached.update(fresh)

    return cached


async def _quotes_mootdx(codes: list[str]) -> dict[str, Quote]:
    """Fetch real-time quotes from mootdx."""
    client = get_mootdx_client()
    symbols = [to_mootdx_code(c) for c in codes]
    market_map = {to_mootdx_code(c): c for c in codes}

    df = client.quotes(symbol=symbols)
    if df is None or df.empty:
        raise NoDataAvailableError(f"mootdx returned empty quotes for {codes}")

    result: dict[str, Quote] = {}
    for _, row in df.iterrows():
        # mootdx returns "code" column (plain 6-digit), not "symbol"
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
