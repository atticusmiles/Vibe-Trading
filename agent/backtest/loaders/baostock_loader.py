"""Baostock loader: free, no-auth A-share historical data via baostock.

Baostock provides daily/weekly/monthly K-line data for Shanghai and Shenzhen
markets. Sessions are serialized through a global lock (baostock requirement).
"""

from __future__ import annotations

import logging
import threading
from typing import Dict, List, Optional

import pandas as pd

from backtest.loaders.base import validate_date_range
from backtest.loaders.registry import register

logger = logging.getLogger(__name__)

_PERIOD_MAP = {"1D": "d", "1W": "w", "1M": "m"}

_lock = threading.Lock()


def _to_bs_code(code: str) -> str:
    """Convert standard code (600519.SH) to baostock format (sh.600519)."""
    digits = code.split(".")[0]
    prefix = "sh" if digits.startswith(("6", "9")) else ("bj" if digits.startswith(("4", "8")) else "sz")
    return f"{prefix}.{digits}"


@register
class DataLoader:
    """Baostock OHLCV loader (free, no auth)."""

    name = "baostock"
    markets = {"a_share"}
    requires_auth = False

    def is_available(self) -> bool:
        try:
            import baostock  # noqa: F401
            return True
        except ImportError:
            return False

    def __init__(self) -> None:
        pass

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
        frequency = _PERIOD_MAP.get(interval, "d")

        result: Dict[str, pd.DataFrame] = {}
        for code in codes:
            try:
                df = self._fetch_one(code, start_date, end_date, frequency)
                if df is not None and not df.empty:
                    result[code] = df
            except Exception as exc:
                logger.warning("baostock failed for %s: %s", code, exc)
        return result

    def _fetch_one(
        self, code: str, start_date: str, end_date: str, frequency: str,
    ) -> Optional[pd.DataFrame]:
        import baostock as bs

        bs_code = _to_bs_code(code)

        with _lock:
            lg = bs.login()
            if lg.error_code != "0":
                raise RuntimeError(f"baostock login failed: {lg.error_msg}")
            try:
                rs = bs.query_history_k_data_plus(
                    bs_code,
                    "date,open,high,low,close,volume,amount,turn",
                    start_date=start_date,
                    end_date=end_date,
                    frequency=frequency,
                    adjustflag="3",
                )
                rows = []
                while rs.error_code == "0" and rs.next():
                    rows.append(rs.get_row_data())
            finally:
                bs.logout()

        if not rows:
            return None

        df = pd.DataFrame(rows, columns=["trade_date", "open", "high", "low", "close", "volume", "amount", "turn"])
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        df = df.set_index("trade_date").sort_index()

        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df[["open", "high", "low", "close", "volume"]].dropna(subset=["open", "high", "low", "close"])
        return df
