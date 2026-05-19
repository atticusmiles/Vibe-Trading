"""Fetch real-time quote and valuation snapshot for a stock."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from src.agent.tools import BaseTool
from src.datasources import get_quote, get_valuation
from src.datasources.base import NoDataAvailableError, normalize_code
from src.tools._async_compat import run_async


class FetchQuoteTool(BaseTool):
    name = "fetch_quote"
    description = (
        "Fetch real-time price quote and current valuation for a stock. "
        "Returns price, change, volume, PE, PB, market cap, turnover rate etc."
    )
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Stock code (6-digit, e.g. '600519')",
            },
        },
        "required": ["code"],
    }
    repeatable = True
    is_readonly = True

    @classmethod
    def check_available(cls) -> bool:
        try:
            from mootdx.quotes import Quotes  # noqa: F401

            return True
        except ImportError:
            return False

    def execute(self, **kwargs: Any) -> str:
        code = kwargs.get("code", "")
        if not code:
            return _err("code is required")

        try:
            code = normalize_code(code)
        except (ValueError, IndexError):
            return _err(f"Invalid stock code: {code}")

        async def _fetch():
            return await asyncio.gather(
                get_quote(code),
                get_valuation(code),
                return_exceptions=True,
            )

        try:
            quote_result, val_result = run_async(_fetch())
        except Exception as exc:
            return _err(str(exc))

        payload: dict[str, Any] = {"status": "ok", "code": code}

        # Quote
        if isinstance(quote_result, Exception):
            payload["quote"] = None
            payload["quote_error"] = str(quote_result)
        else:
            q = quote_result.to_dict()
            for key in (
                "bid1_price", "bid1_vol", "bid2_price", "bid2_vol",
                "bid3_price", "bid3_vol", "bid4_price", "bid4_vol",
                "bid5_price", "bid5_vol", "ask1_price", "ask1_vol",
                "ask2_price", "ask2_vol", "ask3_price", "ask3_vol",
                "ask4_price", "ask4_vol", "ask5_price", "ask5_vol",
            ):
                q.pop(key, None)
            payload["quote"] = q

        # Valuation
        if isinstance(val_result, Exception):
            payload["valuation"] = None
            payload["valuation_error"] = str(val_result)
        else:
            payload["valuation"] = val_result.to_dict()

        return json.dumps(payload, ensure_ascii=False, default=str)


def _err(msg: str) -> str:
    return json.dumps({"status": "error", "error": msg}, ensure_ascii=False)
