"""Fetch K-line (OHLCV candlestick) data for a stock."""

from __future__ import annotations

import json
from typing import Any

from src.agent.tools import BaseTool
from src.datasources import get_kline
from src.datasources.base import NoDataAvailableError, normalize_code
from src.tools._async_compat import run_async


class FetchKLineTool(BaseTool):
    name = "fetch_kline"
    description = (
        "Fetch OHLCV K-line/candlestick bars for a stock. "
        "Returns date, open, high, low, close, volume, amount per bar, "
        "plus a summary (latest price, period high/low, avg volume, change %)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Stock code (6-digit, e.g. '600519'). Also accepts sh600519, 600519.SH etc.",
            },
            "period": {
                "type": "string",
                "enum": ["daily", "weekly", "monthly", "1min", "5min", "15min", "30min", "60min"],
                "description": "K-line period (default: daily)",
                "default": "daily",
            },
            "count": {
                "type": "integer",
                "description": "Number of bars to return (default: 120, max: 500)",
                "default": 120,
            },
            "start_date": {
                "type": "string",
                "description": "Start date YYYY-MM-DD (optional, overrides count if both start and end provided)",
            },
            "end_date": {
                "type": "string",
                "description": "End date YYYY-MM-DD (optional, defaults to today)",
            },
        },
        "required": ["code"],
    }
    repeatable = True
    is_readonly = True

    @classmethod
    def check_available(cls) -> bool:
        for mod in ("mootdx.quotes", "baostock"):
            try:
                __import__(mod)
                return True
            except ImportError:
                continue
        return False

    def execute(self, **kwargs: Any) -> str:
        code = kwargs.get("code", "")
        if not code:
            return _err("code is required")

        try:
            code = normalize_code(code)
        except (ValueError, IndexError):
            return _err(f"Invalid stock code: {code}")

        period = kwargs.get("period", "daily")
        count = min(int(kwargs.get("count", 120)), 500)
        start_date = kwargs.get("start_date")
        end_date = kwargs.get("end_date")

        try:
            bars = run_async(get_kline(code, period=period, start_date=start_date, end_date=end_date, count=count))
        except NoDataAvailableError:
            return _err(f"No K-line data available for {code}")
        except Exception as exc:
            return _err(str(exc))

        if not bars:
            return _err(f"No K-line data returned for {code}")

        dicts = [b.to_dict() for b in bars]
        first, last = dicts[0], dicts[-1]
        closes = [b["close"] for b in dicts]
        change_pct = round((last["close"] - first["close"]) / first["close"] * 100, 2) if first["close"] else 0.0

        return json.dumps(
            {
                "status": "ok",
                "code": code,
                "period": period,
                "count": len(dicts),
                "date_range": [first["date"], last["date"]],
                "bars": dicts,
                "summary": {
                    "latest_close": last["close"],
                    "period_high": max(b["high"] for b in dicts),
                    "period_low": min(b["low"] for b in dicts),
                    "avg_volume": round(sum(b["volume"] for b in dicts) / len(dicts), 2),
                    "change_pct": change_pct,
                },
            },
            ensure_ascii=False,
            default=str,
        )


def _err(msg: str) -> str:
    return json.dumps({"status": "error", "error": msg}, ensure_ascii=False)
