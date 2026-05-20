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
                "description": "'digest' reads daily summaries, 'save_digest' writes one.",
                "enum": ["digest", "save_digest"],
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
            "digest_date": {
                "type": "string",
                "description": "Date for save_digest mode (YYYY-MM-DD).",
            },
            "summary": {
                "type": "string",
                "description": "Brief summary for save_digest mode (2-3 sentences).",
            },
            "content": {
                "type": "string",
                "description": "Full Markdown digest content for save_digest mode.",
            },
        },
        "required": [],
    }
    repeatable = True
    is_readonly = False

    def execute(self, **kwargs: Any) -> str:
        code = kwargs.get("code")
        keyword = kwargs.get("keyword")
        mode = kwargs.get("mode")
        days = kwargs.get("days")
        limit = min(int(kwargs.get("limit", 10)), 50)

        try:
            if mode == "save_digest":
                return self._save_digest(kwargs)
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

    def _save_digest(self, kwargs: dict[str, Any]) -> str:
        digest_date = (kwargs.get("digest_date") or "").strip()
        summary = (kwargs.get("summary") or "").strip()
        content = (kwargs.get("content") or "").strip()

        if not digest_date or not summary or not content:
            return _err("digest_date, summary, and content are required for save_digest")

        user_id = _parse_int(kwargs.get("_user_id")) or 1

        from src.db.database import get_db

        with get_db() as conn:
            cursor = conn.execute(
                "INSERT INTO news_digests (user_id, digest_date, content, summary) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(user_id, digest_date) DO UPDATE SET "
                "content=excluded.content, summary=excluded.summary",
                (user_id, digest_date, content, summary),
            )
            digest_id = cursor.lastrowid

        return json.dumps(
            {"status": "ok", "mode": "save_digest", "digest_id": digest_id, "digest_date": digest_date},
            ensure_ascii=False,
        )


def _parse_int(val: Any) -> int:
    if isinstance(val, int):
        return val
    if isinstance(val, str) and val.strip().isdigit():
        return int(val)
    return 0


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
