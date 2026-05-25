"""SearXNG web search tool: privacy-friendly metasearch engine API.

Replaces the old DuckDuckGo-based web_search tool. Uses SearXNG which
is accessible from China without network issues.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from src.agent.tools import BaseTool

_BASE_URL = "https://search.niotech.cc"
_TIMEOUT = 20


class SearXNGSearchTool(BaseTool):
    """Search the web via SearXNG metasearch engine."""

    name = "web_search"

    @classmethod
    def check_available(cls) -> bool:
        return True

    description = (
        "Search the web via SearXNG metasearch engine. Returns top results "
        "with title, URL, and snippet. Supports pagination, time range "
        "filtering, and language selection."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return (default 5, max 10)",
                "default": 5,
            },
            "pageno": {
                "type": "integer",
                "description": "Search page number (starts at 1)",
                "default": 1,
            },
            "time_range": {
                "type": "string",
                "description": "Filter results by time range: day, month, or year",
                "enum": ["day", "month", "year"],
            },
            "language": {
                "type": "string",
                "description": "Language code for results (e.g. zh-CN, en). Default: all",
                "default": "all",
            },
        },
        "required": ["query"],
    }
    repeatable = True

    def execute(self, **kwargs: Any) -> str:
        query = kwargs["query"]
        max_results = min(int(kwargs.get("max_results", 5)), 10)
        pageno = int(kwargs.get("pageno", 1))
        language = kwargs.get("language", "all")

        params: dict[str, Any] = {
            "format": "json",
            "q": query,
            "pageno": pageno,
        }
        if language and language != "all":
            params["language"] = language
        time_range = kwargs.get("time_range")
        if time_range in ("day", "month", "year"):
            params["time_range"] = time_range

        try:
            with httpx.Client(timeout=_TIMEOUT) as client:
                resp = client.get(
                    f"{_BASE_URL}/search",
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()

            raw = data.get("results", [])
            results = [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("content", ""),
                    "engine": r.get("engine", ""),
                }
                for r in raw[:max_results]
            ]
            suggestions = data.get("suggestions", [])
            payload: dict[str, Any] = {
                "status": "ok",
                "query": query,
                "results": results,
            }
            if suggestions:
                payload["suggestions"] = suggestions
            return json.dumps(payload, ensure_ascii=False)
        except httpx.TimeoutException:
            return json.dumps(
                {"status": "error", "error": "Search request timed out"},
                ensure_ascii=False,
            )
        except httpx.HTTPStatusError as exc:
            return json.dumps(
                {"status": "error", "error": f"Search API returned {exc.response.status_code}"},
                ensure_ascii=False,
            )
        except Exception as exc:
            return json.dumps(
                {"status": "error", "error": str(exc)},
                ensure_ascii=False,
            )
