"""Mootdx loader: TCP-based real-time and historical A-share data.

Uses mootdx (通达信协议) for fast, no-auth OHLCV data via TCP.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

import pandas as pd

from backtest.loaders.base import validate_date_range
from backtest.loaders.registry import register

logger = logging.getLogger(__name__)

_INTERVAL_MAP = {
    "1D": 4,
    "1W": 5,
    "1M": 6,
    "1min": 7,
    "5min": 8,
    "15min": 9,
    "30min": 10,
    "60min": 11,
}


def _to_mootdx_code(code: str) -> str:
    """Convert standard code (600519.SH) to plain 6-digit string."""
    return code.split(".")[0]


def _mootdx_market(code: str) -> int:
    digits = _to_mootdx_code(code)
    return 1 if digits.startswith(("6", "9")) else 0


@register
class DataLoader:
    """Mootdx OHLCV loader (free, no auth, TCP-based)."""

    name = "mootdx"
    markets = {"a_share"}
    requires_auth = False

    def is_available(self) -> bool:
        try:
            from mootdx.quotes import Quotes  # noqa: F401
            return True
        except ImportError:
            return False

    def __init__(self) -> None:
        from mootdx.quotes import Quotes
        self._client = Quotes.factory(market="std")

    def fetch(
        self,
        codes: List[str],
        start_date: str,
        end_date: str,
        *,
        interval: str = "1D",
        fields: Optional[List[str]] = None,
    ) -> Dict[str, pd.DataFrame]:
        validate_date_range(start_date, end_date)
        category = _INTERVAL_MAP.get(interval, 4)

        result: Dict[str, pd.DataFrame] = {}
        for code in codes:
            try:
                df = self._fetch_one(code, category, start_date, end_date)
                if df is not None and not df.empty:
                    result[code] = df
            except Exception as exc:
                logger.warning("mootdx failed for %s: %s", code, exc)
        return result

    def _fetch_one(
        self, code: str, category: int, start_date: str, end_date: str,
    ) -> Optional[pd.DataFrame]:
        symbol = _to_mootdx_code(code)
        market = _mootdx_market(code)

        df = self._client.bars(
            symbol=symbol, category=category,
            offset=800, market=market,
        )
        if df is None or df.empty:
            return None

        if "datetime" in df.columns:
            df = df.drop(columns=["datetime"])
        df = df.reset_index()

        if "datetime" in df.columns:
            df = df.rename(columns={"datetime": "trade_date"})
        elif "date" in df.columns:
            df = df.rename(columns={"date": "trade_date"})

        df["trade_date"] = pd.to_datetime(df["trade_date"])
        df = df.set_index("trade_date").sort_index()

        col_map = {"open": "open", "high": "high", "low": "low", "close": "close"}
        if "vol" in df.columns:
            col_map["vol"] = "volume"
        elif "volume" in df.columns:
            col_map["volume"] = "volume"
        df = df.rename(columns=col_map)

        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        available = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
        df = df[available].dropna(subset=["open", "high", "low", "close"])
        if "volume" not in df.columns:
            df["volume"] = 0.0

        return df.loc[start_date:end_date]
