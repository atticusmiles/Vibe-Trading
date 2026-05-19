"""Fetch analyst consensus EPS and research reports for a stock."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from src.agent.tools import BaseTool
from src.datasources import get_consensus_eps, get_research_reports
from src.datasources.base import normalize_code
from src.tools._async_compat import run_async


class FetchResearchTool(BaseTool):
    name = "fetch_research"
    description = (
        "Fetch analyst consensus EPS forecasts and recent research reports for a stock. "
        "Returns actual vs forecast EPS, analyst coverage count, and report listings with ratings."
    )
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Stock code (6-digit, e.g. '600519')",
            },
            "include_reports": {
                "type": "boolean",
                "description": "Include recent research report listings (default: true)",
                "default": True,
            },
            "report_limit": {
                "type": "integer",
                "description": "Max research reports to return (default: 5, max: 20)",
                "default": 5,
            },
        },
        "required": ["code"],
    }
    repeatable = True
    is_readonly = True

    def execute(self, **kwargs: Any) -> str:
        code = kwargs.get("code", "")
        if not code:
            return _err("code is required")

        try:
            code = normalize_code(code)
        except (ValueError, IndexError):
            return _err(f"Invalid stock code: {code}")

        include_reports = kwargs.get("include_reports", True)
        report_limit = min(int(kwargs.get("report_limit", 5)), 20)

        try:
            if include_reports:
                eps_result, reports_result = run_async(
                    asyncio.gather(
                        get_consensus_eps(code),
                        get_research_reports(code, limit=report_limit),
                        return_exceptions=True,
                    )
                )
            else:
                eps_result = run_async(get_consensus_eps(code))
                reports_result = None
        except Exception as exc:
            return _err(str(exc))

        payload: dict[str, Any] = {"status": "ok", "code": code}

        if isinstance(eps_result, Exception):
            payload["consensus_eps"] = None
            payload["eps_error"] = str(eps_result)
        else:
            payload["consensus_eps"] = eps_result

        if reports_result is not None:
            if isinstance(reports_result, Exception):
                payload["reports"] = None
                payload["reports_error"] = str(reports_result)
            else:
                payload["reports"] = reports_result

        return json.dumps(payload, ensure_ascii=False, default=str)


def _err(msg: str) -> str:
    return json.dumps({"status": "error", "error": msg}, ensure_ascii=False)
