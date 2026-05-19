"""Fetch financial data: quarterly snapshot or full statements."""

from __future__ import annotations

import json
from typing import Any

from src.agent.tools import BaseTool
from src.datasources import get_financial_snapshot, get_financial_statements
from src.datasources.base import NoDataAvailableError, normalize_code
from src.tools._async_compat import run_async


class FetchFinancialTool(BaseTool):
    name = "fetch_financial"
    description = (
        "Fetch financial data for a stock. "
        "Default returns a quarterly snapshot (EPS, ROE, margins, growth, etc.). "
        "Set report_type to 'balance', 'income', or 'cashflow' for full statements."
    )
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Stock code (6-digit, e.g. '600519')",
            },
            "report_type": {
                "type": "string",
                "enum": ["snapshot", "balance", "income", "cashflow"],
                "description": "'snapshot' (default) for key metrics, or a full statement type",
                "default": "snapshot",
            },
            "year": {
                "type": "integer",
                "description": "Report year (for statement reports, defaults to current year)",
            },
            "quarter": {
                "type": "integer",
                "enum": [1, 2, 3, 4],
                "description": "Report quarter 1-4 (for statement reports)",
            },
        },
        "required": ["code"],
    }
    repeatable = True
    is_readonly = True

    @classmethod
    def check_available(cls) -> bool:
        try:
            import baostock  # noqa: F401

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

        report_type = kwargs.get("report_type", "snapshot")

        try:
            if report_type == "snapshot":
                return self._snapshot(code, kwargs)
            return self._statement(code, report_type, kwargs)
        except NoDataAvailableError:
            return _err(f"No financial data available for {code}")
        except Exception as exc:
            return _err(str(exc))

    def _snapshot(self, code: str, kwargs: dict) -> str:
        year = kwargs.get("year")
        quarter = kwargs.get("quarter")
        data = run_async(
            get_financial_snapshot(
                code,
                year=int(year) if year is not None else None,
                quarter=int(quarter) if quarter is not None else None,
            )
        )
        return json.dumps(
            {"status": "ok", "code": code, "report_type": "snapshot", "data": data},
            ensure_ascii=False,
            default=str,
        )

    def _statement(self, code: str, report_type: str, kwargs: dict) -> str:
        import datetime

        year = int(kwargs.get("year", datetime.date.today().year))
        quarter = kwargs.get("quarter")
        if quarter is None:
            return _err("quarter is required for statement reports (1-4)")
        quarter = int(quarter)

        rows = run_async(get_financial_statements(code, year, quarter, report_type))
        truncated = len(rows) > 5
        return json.dumps(
            {
                "status": "ok",
                "code": code,
                "report_type": report_type,
                "year": year,
                "quarter": quarter,
                "rows": len(rows),
                "data": rows[:5],
                "truncated": truncated,
            },
            ensure_ascii=False,
            default=str,
        )


def _err(msg: str) -> str:
    return json.dumps({"status": "error", "error": msg}, ensure_ascii=False)
