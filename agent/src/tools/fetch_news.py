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
        "With 'code', returns stock-specific news for that stock. "
        "With 'codes' (array), returns news for multiple stocks in one call. "
        "With 'keyword', searches news by that keyword. "
        "With 'keywords' (array), searches news for multiple keywords in one call. "
        "With mode='digest', returns daily news digests. "
        "Without any param, returns recent market-wide news."
    )
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Single stock code (optional, mutually exclusive with 'codes').",
            },
            "codes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Multiple stock codes to fetch in one batch (optional).",
            },
            "keyword": {
                "type": "string",
                "description": "Single keyword to search (optional, mutually exclusive with 'keywords').",
            },
            "keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Multiple keywords to search in one batch (optional).",
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
                "description": "Max news items per stock/keyword (default: 10, max: 50)",
                "default": 10,
            },
        },
        "required": [],
    }
    repeatable = True
    is_readonly = True

    def execute(self, **kwargs: Any) -> str:
        codes = kwargs.get("codes")
        keywords = kwargs.get("keywords")
        code = kwargs.get("code")
        keyword = kwargs.get("keyword")
        mode = kwargs.get("mode")
        days = kwargs.get("days")
        limit = min(int(kwargs.get("limit", 10)), 50)

        try:
            if codes:
                return self._batch_stock_news(codes, limit)
            if keywords:
                return self._batch_search(keywords, limit)
            if code:
                return self._stock_news(code, limit)
            if keyword:
                return self._search(keyword, limit)
            if mode == "digest":
                return self._digest(days)
            return self._recent(limit, days)
        except Exception as exc:
            return _err(str(exc))

    def _batch_stock_news(self, codes: list[str], limit: int) -> str:
        results = []
        for c in codes:
            c = normalize_code(c)
            items = run_async(search_stock_news(c, limit=limit))
            results.append({
                "code": c,
                "count": len(items),
                "news": [_trim(item.to_dict()) for item in items],
            })
        return json.dumps(
            {"status": "ok", "mode": "batch_stock", "results": results},
            ensure_ascii=False, default=str,
        )

    def _batch_search(self, keywords: list[str], limit: int) -> str:
        results = []
        for kw in keywords:
            items = run_async(search_news(kw, limit=limit))
            results.append({
                "keyword": kw,
                "count": len(items),
                "news": [_trim(item.to_dict()) for item in items],
            })
        return json.dumps(
            {"status": "ok", "mode": "batch_search", "results": results},
            ensure_ascii=False,
        )

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
