"""Background scheduler and news pipeline.

Provides:
- APScheduler integration with FastAPI lifespan
- Daily news digest generation (LLM summary of CLS telegraph)
"""

from __future__ import annotations

import logging
import uuid
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
    """Scheduled job: generate yesterday's digest via digest_news preset."""
    target_date = (datetime.now(SHANGHAI_TZ) - timedelta(days=1)).strftime("%Y-%m-%d")
    run_id = _run_preset("digest_news", {"digest_date": target_date})
    if run_id:
        logger.info("Started digest_news preset for %s (run %s)", target_date, run_id)
    else:
        logger.error("Failed to start digest_news preset for %s", target_date)


def _run_preset(preset_name: str, user_vars: dict[str, str]) -> str | None:
    """Start a swarm run with the given preset and variables.

    Returns the run ID or None on failure.
    """
    try:
        from src.swarm.runtime import SwarmRuntime
        from src.swarm.store import SwarmStore
        from src.core.config import get_swarm_dir

        store = SwarmStore(base_dir=get_swarm_dir())
        runtime = SwarmRuntime(store=store)
        run = runtime.start_run(preset_name, user_vars)
        logger.info("Started preset %s run %s", preset_name, run.id)
        return run.id
    except Exception:
        logger.exception("Failed to start preset %s", preset_name)
        return None


def _build_trend_context() -> str:
    """Build trend context string from active trends + 60-day news digest."""
    import json as _json
    from src.db.database import get_db as _get_db

    parts = []
    with _get_db() as conn:
        trends = conn.execute(
            "SELECT title, status, confidence, evidence FROM trends "
            "WHERE status IN ('proposed', 'adopted') ORDER BY confidence DESC"
        ).fetchall()
        if trends:
            parts.append("## 活跃趋势")
            for t in trends:
                parts.append(f"- [{t['status']}] {t['title']} (置信度:{t['confidence']}) {t['evidence'] or ''}")

        # Get 60-day news digest
        rows = conn.execute(
            "SELECT digest_date, summary FROM news_digests "
            "ORDER BY digest_date DESC LIMIT 60"
        ).fetchall()
        if rows:
            parts.append("\n## 近期新闻摘要")
            for r in rows:
                parts.append(f"- {r['digest_date']}: {r['summary'] or ''}")

    return "\n".join(parts) if parts else "(无活跃趋势)"


def _build_existing_list(target_type: str) -> str:
    """Build a list of existing entities for the given target type."""
    table_map = {"trend": "trends", "industry": "industries", "stock": "stocks"}
    table = table_map.get(target_type)
    if not table:
        return "(无)"

    from src.db.database import get_db as _get_db
    with _get_db() as conn:
        if target_type == "trend":
            rows = conn.execute(
                "SELECT title, status, confidence FROM trends "
                "WHERE status IN ('proposed', 'adopted') ORDER BY updated_at DESC"
            ).fetchall()
            return "\n".join(f"- [{r['status']}] {r['title']} (置信度:{r['confidence']})" for r in rows) or "(无)"
        elif target_type == "industry":
            rows = conn.execute(
                "SELECT name, status, confidence, reason FROM industries "
                "WHERE status IN ('proposed', 'adopted') ORDER BY updated_at DESC"
            ).fetchall()
            return "\n".join(f"- [{r['status']}] {r['name']} (置信度:{r['confidence']}) {r['reason'] or ''}" for r in rows) or "(无)"
        elif target_type == "stock":
            rows = conn.execute(
                "SELECT name, code, status, confidence, position FROM stocks "
                "WHERE status IN ('proposed', 'adopted') ORDER BY updated_at DESC"
            ).fetchall()
            return "\n".join(f"- [{r['status']}] {r['name']}({r['code']}) 置信度:{r['confidence']} 仓位:{r['position'] or 0}" for r in rows) or "(无)"
    return "(无)"


def _build_industry_details() -> str:
    """Build industry details for stock scanning."""
    from src.db.database import get_db as _get_db
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT name, confidence, reason, research_report FROM industries "
            "WHERE status IN ('proposed', 'adopted') ORDER BY confidence DESC"
        ).fetchall()
    if not rows:
        return "(无已提案行业)"
    parts = []
    for r in rows:
        parts.append(f"### {r['name']} (置信度:{r['confidence']})")
        if r["reason"]:
            parts.append(f"理由: {r['reason']}")
        if r["research_report"]:
            parts.append(f"报告摘要: {r['research_report'][:500]}...")
    return "\n\n".join(parts)


def _build_current_portfolio() -> str:
    """Build current portfolio summary."""
    from src.db.database import get_db as _get_db
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT name, code, position, industry_name FROM stocks "
            "WHERE status IN ('proposed', 'adopted') AND position > 0"
        ).fetchall()
    if not rows:
        return "(空仓)"
    return "\n".join(f"- {r['name']}({r['code']}) 仓位:{r['position']:.1%} 行业:{r['industry_name'] or 'N/A'}" for r in rows)


def _scan_trends_job() -> None:
    """Scheduled job: scan for new trends."""
    existing = _build_existing_list("trend")
    _run_preset("scan_trends", {
        "market": "A股",
        "existing_trends": existing,
    })


def _scan_industries_job() -> None:
    """Scheduled job: scan for industries based on active trends."""
    trend_ctx = _build_trend_context()
    existing = _build_existing_list("industry")
    _run_preset("scan_industries", {
        "trend_context": trend_ctx,
        "existing_industries": existing,
        "existing_trends": _build_existing_list("trend"),
    })


def _scan_stocks_job() -> None:
    """Scheduled job: scan for stocks based on active industries."""
    details = _build_industry_details()
    existing = _build_existing_list("stock")
    portfolio = _build_current_portfolio()
    with get_db() as conn:
        names = conn.execute(
            "SELECT name FROM industries WHERE status IN ('proposed', 'adopted')"
        ).fetchall()
    industry_names = ", ".join(r["name"] for r in names) or "(无)"

    _run_preset("scan_stocks", {
        "industry_names": industry_names,
        "industry_details": details,
        "existing_stocks": existing,
        "current_portfolio": portfolio,
    })


def _refresh_entities_job(target_type: str) -> None:
    """Refresh (保鲜) proposed/adopted entities by creating temp candidates and running research."""
    import json as _json

    table_map = {"trend": "trends", "industry": "industries", "stock": "stocks"}
    table = table_map[target_type]

    with get_db() as conn:
        cutoff = (datetime.now(SHANGHAI_TZ) - timedelta(days=1)).strftime("%Y-%m-%d 00:00:00")
        if target_type == "trend":
            rows = conn.execute(
                "SELECT id, title, confidence, evidence FROM trends "
                "WHERE status IN ('proposed', 'adopted') AND updated_at < ?",
                (cutoff,),
            ).fetchall()
        elif target_type == "industry":
            rows = conn.execute(
                "SELECT id, name, confidence, reason FROM industries "
                "WHERE status IN ('proposed', 'adopted') AND updated_at < ?",
                (cutoff,),
            ).fetchall()
        elif target_type == "stock":
            rows = conn.execute(
                "SELECT id, name, code, confidence, industry_name FROM stocks "
                "WHERE status IN ('proposed', 'adopted') AND updated_at < ?",
                (cutoff,),
            ).fetchall()

    if not rows:
        logger.info("No %s entities to refresh", target_type)
        return

    preset_name = _PRESET_MAP[target_type]
    for row in rows:
        name = row["title"] if target_type == "trend" else row["name"]

        # Create a temporary candidate for the refresh run
        with get_db() as conn:
            try:
                conn.execute(
                    "INSERT INTO research_candidates "
                    "(target_type, name, code, source_context, initial_score, status, source_run_id) "
                    "VALUES (?, ?, ?, ?, ?, 'pending', 'refresh')",
                    (
                        target_type,
                        name,
                        row.get("code"),
                        f"保鲜刷新: {dict(row)}",
                        row["confidence"],
                    ),
                )
            except Exception:
                logger.debug("Candidate for %s/%s already exists today, skipping", target_type, name)
                continue

            cand = conn.execute(
                "SELECT id FROM research_candidates "
                "WHERE target_type = ? AND name = ? ORDER BY created_at DESC LIMIT 1",
                (target_type, name),
            ).fetchone()
            if not cand:
                continue

            cand_id = cand["id"]
            run_id = str(uuid.uuid4())
            conn.execute(
                "UPDATE research_candidates SET status = 'researching', research_run_id = ? WHERE id = ?",
                (run_id, cand_id),
            )

        # Build user_vars
        user_vars = {
            "candidate_names": _json.dumps([name], ensure_ascii=False),
            "candidate_info": _json.dumps({"name": name, "source_context": "保鲜刷新", "initial_score": row["confidence"]}, ensure_ascii=False),
            "_run_id": run_id,
            "_user_id": "1",
        }

        # Add existing entity context for conservative update policy
        if target_type == "trend":
            user_vars["existing_trend"] = _json.dumps(dict(row), ensure_ascii=False)
            user_vars["existing_trends"] = _build_existing_list("trend")
        elif target_type == "industry":
            user_vars["existing_industry"] = _json.dumps(dict(row), ensure_ascii=False)
            user_vars["existing_industries"] = _build_existing_list("industry")
        elif target_type == "stock":
            user_vars["existing_stock"] = _json.dumps(dict(row), ensure_ascii=False)
            user_vars["existing_stocks"] = _build_existing_list("stock")
            user_vars["current_portfolio"] = _build_current_portfolio()

        _run_preset(preset_name, user_vars)


_PRESET_MAP = {
    "trend": "research_trends",
    "industry": "research_industries",
    "stock": "research_stocks",
}


def setup_scheduler(app_state: dict[str, Any] | None = None) -> Any:
    """Create and configure the scheduler with jobs.

    Returns the scheduler instance (not started).
    """
    import uuid as _uuid

    sched = create_scheduler()

    # Daily digest at 1:00 AM Shanghai time
    sched.add_job(
        _scheduled_digest_job,
        "cron",
        hour=1,
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

    # Research engine: scan jobs
    sched.add_job(
        _scan_trends_job, "cron", hour=8, minute=30,
        id="scan_trends", replace_existing=True,
    )
    sched.add_job(
        _scan_industries_job, "cron", hour=9, minute=0,
        id="scan_industries", replace_existing=True,
    )
    sched.add_job(
        _scan_stocks_job, "cron", hour=9, minute=30,
        id="scan_stocks", replace_existing=True,
    )

    # Refresh (保鲜) jobs
    sched.add_job(
        lambda: _refresh_entities_job("trend"), "cron", hour=10, minute=0,
        id="refresh_trends", replace_existing=True,
    )
    sched.add_job(
        lambda: _refresh_entities_job("industry"), "cron", hour=10, minute=30,
        id="refresh_industries", replace_existing=True,
    )
    sched.add_job(
        lambda: _refresh_entities_job("stock"), "cron", hour=11, minute=0,
        id="refresh_stocks", replace_existing=True,
    )

    return sched


def _cleanup_old_news() -> None:
    """Delete news_raw entries older than 7 days."""
    from src.db.database import get_db

    cutoff = (datetime.now(SHANGHAI_TZ) - timedelta(days=7)).strftime("%Y-%m-%d 00:00:00")
    with get_db() as conn:
        result = conn.execute("DELETE FROM news_raw WHERE published_at < ?", (cutoff,))
        logger.info("Cleaned up %d old news records (before %s)", result.rowcount, cutoff)
