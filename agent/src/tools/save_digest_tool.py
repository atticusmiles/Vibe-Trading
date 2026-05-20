"""save_digest tool: write a news digest to news_digests table."""

from __future__ import annotations

import json
from typing import Any

from src.agent.tools import BaseTool


class SaveDigestTool(BaseTool):
    name = "save_digest"
    description = (
        "Save a news digest for a given date. "
        "Use this after analyzing news to persist the summary."
    )
    parameters = {
        "type": "object",
        "properties": {
            "digest_date": {
                "type": "string",
                "description": "Date in YYYY-MM-DD format.",
            },
            "summary": {
                "type": "string",
                "description": "Brief 2-3 sentence summary of the day's market.",
            },
            "content": {
                "type": "string",
                "description": "Full Markdown digest content.",
            },
        },
        "required": ["digest_date", "summary", "content"],
    }
    repeatable = True
    is_readonly = False

    def execute(self, **kwargs: Any) -> str:
        digest_date = kwargs.get("digest_date", "").strip()
        summary = kwargs.get("summary", "").strip()
        content = kwargs.get("content", "").strip()

        if not digest_date or not summary or not content:
            return _err("digest_date, summary, and content are required")

        user_id = _parse_int(kwargs.get("_user_id"))
        if not user_id:
            user_id = 1

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
            {"status": "ok", "digest_id": digest_id, "digest_date": digest_date},
            ensure_ascii=False,
        )


def _parse_int(val: Any) -> int:
    if isinstance(val, int):
        return val
    if isinstance(val, str) and val.strip().isdigit():
        return int(val)
    return 0


def _err(msg: str) -> str:
    return json.dumps({"status": "error", "error": msg}, ensure_ascii=False)
