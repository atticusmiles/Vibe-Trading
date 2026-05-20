"""Fetch news: stock-specific, keyword search, digest read/write, or recent market-wide."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from src.agent.tools import BaseTool
from src.datasources import get_news_digest, get_recent_news, search_news, search_stock_news
from src.datasources.base import normalize_code
from src.tools._async_compat import run_async

_MAX_CONTENT = 300


class FetchNewsTool(BaseTool):
    name = "fetch_news"
    description = (
        "Fetch or manage news. "
        "With a stock code, returns stock-specific news. "
        "With a keyword, searches news by keyword. "
        "With mode='digest', returns daily news digests. "
        "With mode='save_digest', saves a news digest. "
        "Without either, returns recent market-wide news."
    )
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Stock code for stock-specific news (optional).",
            },
            "keyword": {
                "type": "string",
                "description": "Keyword to search news (optional, used when code is not provided).",
            },
            "mode": {
                "type": "string",
                "description": "'digest' reads daily summaries.",
                "enum": ["digest"],
            },
            "days": {
                "type": "integer",
                "description": "Number of days to look back (default: 7 for recent, 60 for digest).",
            },
            "limit": {
                "type": "integer",
                "description": "Max news items to return (default: 10, max: 50)",
                "default": 10,
            },
        },
        "required": [],
    }
    repeatable = True
    is_readonly = True

    def execute(self, **kwargs: Any) -> str:
        code = kwargs.get("code")
        keyword = kwargs.get("keyword")
        mode = kwargs.get("mode")
        days = kwargs.get("days")
        limit = min(int(kwargs.get("limit", 10)), 50)

        try:
            if code:
                return self._stock_news(code, limit)
            if keyword:
                return self._search(keyword, limit)
            if mode == "digest":
                return self._digest(days)
            return self._recent(limit, days)
        except Exception as exc:
            return _err(str(exc))

    def _stock_news(self, code: str, limit: int) -> str:
        code = normalize_code(code)
        items = run_async(search_stock_news(code, limit=limit))
        news = [_trim(item.to_dict()) for item in items]
        return json.dumps(
            {"status": "ok", "code": code, "count": len(news), "news": news},
            ensure_ascii=False, default=str,
        )

    def _search(self, keyword: str, limit: int) -> str:
        items = run_async(search_news(keyword, limit=limit))
        news = [_trim(item.to_dict()) for item in items]
        return json.dumps(
            {"status": "ok", "mode": "search", "keyword": keyword, "count": len(news), "news": news},
            ensure_ascii=False,
        )

    def _recent(self, limit: int, days: int | None = None) -> str:
        sd, ed = _date_range(days or 7)
        rows = run_async(get_recent_news(start_date=sd, end_date=ed, limit=limit))
        news = [_trim(r) for r in rows]
        return json.dumps(
            {"status": "ok", "mode": "recent", "days": days or 7, "count": len(news), "news": news},
            ensure_ascii=False,
        )

    def _digest(self, days: int | None = None) -> str:
        sd, ed = _date_range(days or 60)
        rows = run_async(get_news_digest(start_date=sd, end_date=ed))
        return json.dumps(
            {"status": "ok", "mode": "digest", "days": days or 60, "count": len(rows), "digests": rows},
            ensure_ascii=False,
        )



def _date_range(days: int) -> tuple[str, str]:
    now = datetime.now()
    start = (now - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    end = now.strftime("%Y-%m-%d %H:%M:%S")
    return start, end


def _trim(item: dict) -> dict:
    content = item.get("content", "")
    if content and len(content) > _MAX_CONTENT:
        item["content"] = content[:_MAX_CONTENT] + "..."
    return item


def _err(msg: str) -> str:
    return json.dumps({"status": "error", "error": msg}, ensure_ascii=False)
