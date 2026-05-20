"""Background scheduler and news pipeline.

Provides:
- APScheduler integration with FastAPI lifespan
- Daily news digest generation (LLM summary of CLS telegraph)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

SHANGHAI_TZ = timezone(timedelta(hours=8))


def create_scheduler():
    """Create an AsyncIOScheduler instance."""
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.jobstores.memory import MemoryJobStore

    return AsyncIOScheduler(
        jobstores={"default": MemoryJobStore()},
        timezone=SHANGHAI_TZ,
        job_defaults={"coalesce": True, "max_instances": 1},
    )


async def generate_daily_digest(target_date: str | None = None) -> dict[str, Any] | None:
    """Generate a daily news digest for the given date using LLM.

    Reads all news_raw entries for the target date, sends them to the LLM
    for summarization, and stores the result in news_digests.

    Args:
        target_date: YYYY-MM-DD format, defaults to yesterday.

    Returns:
        The saved digest dict, or None if no news found.
    """
    from src.db.database import get_db

    if target_date is None:
        yesterday = (datetime.now(SHANGHAI_TZ) - timedelta(days=1)).strftime("%Y-%m-%d")
        target_date = yesterday

    start = f"{target_date} 00:00:00"
    end = f"{target_date} 23:59:59"

    with get_db() as conn:
        rows = conn.execute(
            "SELECT title, content, level, source, published_at FROM news_raw "
            "WHERE published_at >= ? AND published_at <= ? "
            "ORDER BY published_at ASC",
            (start, end),
        ).fetchall()

    if not rows:
        logger.info("No news found for %s, skipping digest", target_date)
        return None

    # Build news text for LLM
    news_text_parts = []
    for r in rows:
        news_text_parts.append(f"[{r['published_at']}] [{r['level'] or 'N/A'}] {r['title']}")
        if r["content"]:
            news_text_parts.append(f"  {r['content'][:200]}")
    news_text = "\n".join(news_text_parts)

    # Truncate to avoid token overflow (~4k chars ≈ ~2k tokens)
    if len(news_text) > 8000:
        news_text = news_text[:8000] + "\n... (truncated)"

    prompt = (
        "你是一名专业财经分析师。请根据以下当日财经新闻快讯，生成一份结构化的每日市场总结。\n\n"
        "要求：\n"
        "1. 用 Markdown 格式输出\n"
        "2. 包含：市场概览（2-3句话）、重点事件（3-5条）、板块影响分析\n"
        "3. 用 2-3 句话总结当日市场情绪和关键看点作为 summary\n"
        "4. 输出格式：先 summary（纯文本），然后空一行，接着是完整 Markdown 正文作为 content\n\n"
        f"日期：{target_date}\n"
        f"新闻条数：{len(rows)}\n\n"
        "--- 新闻内容 ---\n{news_text}"
    )

    try:
        from src.providers.llm import build_llm
        llm = build_llm()
        response = llm.invoke(prompt)
        full_text = response.content if hasattr(response, "content") else str(response)
    except Exception:
        logger.exception("LLM call failed for digest %s", target_date)
        full_text = f"（LLM 生成失败，共 {len(rows)} 条新闻）"

    # Split into summary and content
    parts = full_text.split("\n\n", 1)
    summary = parts[0].strip() if len(parts) >= 1 else ""
    content = parts[1].strip() if len(parts) >= 2 else full_text

    # Save to DB
    from src.db.database import get_db as get_db2
    with get_db2() as conn:
        cursor = conn.execute(
            "INSERT INTO news_digests (user_id, digest_date, content, summary) "
            "VALUES (1, ?, ?, ?) "
            "ON CONFLICT(user_id, digest_date) DO UPDATE SET "
            "content=excluded.content, summary=excluded.summary",
            (target_date, content, summary),
        )
        digest_id = cursor.lastrowid

    logger.info("Digest saved for %s (id=%d, %d news items)", target_date, digest_id, len(rows))
    return {"id": digest_id, "digest_date": target_date, "summary": summary}


async def _scheduled_digest_job() -> None:
    """Scheduled job: generate yesterday's digest at the configured time."""
    try:
        result = await generate_daily_digest()
        if result:
            logger.info("Scheduled digest generated: %s", result["digest_date"])
    except Exception:
        logger.exception("Scheduled digest job failed")


def setup_scheduler(app_state: dict[str, Any] | None = None) -> Any:
    """Create and configure the scheduler with jobs.

    Returns the scheduler instance (not started).
    """
    sched = create_scheduler()

    # Daily digest at 8:00 AM Shanghai time
    sched.add_job(
        _scheduled_digest_job,
        "cron",
        hour=8,
        minute=0,
        id="daily_digest",
        replace_existing=True,
    )

    # Clean up old news (> 7 days) at 3:00 AM
    sched.add_job(
        _cleanup_old_news,
        "cron",
        hour=3,
        minute=0,
        id="cleanup_news",
        replace_existing=True,
    )

    return sched


def _cleanup_old_news() -> None:
    """Delete news_raw entries older than 7 days."""
    from src.db.database import get_db

    cutoff = (datetime.now(SHANGHAI_TZ) - timedelta(days=7)).strftime("%Y-%m-%d 00:00:00")
    with get_db() as conn:
        result = conn.execute("DELETE FROM news_raw WHERE published_at < ?", (cutoff,))
        logger.info("Cleaned up %d old news records (before %s)", result.rowcount, cutoff)
