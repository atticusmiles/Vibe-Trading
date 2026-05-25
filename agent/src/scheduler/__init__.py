"""Background scheduler and news pipeline.

Provides:
- APScheduler integration with FastAPI lifespan
- Daily news digest generation (LLM summary of CLS telegraph)
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

SHANGHAI_TZ = timezone(timedelta(hours=8))


# ── Scheduler configuration (overridable via environment variables) ──
# Cron expressions: minute hour day month day_of_week (Shanghai TZ)
_DIGEST_CRON = os.getenv("SCHEDULER_DIGEST_CRON", "0 1 * * *")
_CLEANUP_NEWS_CRON = os.getenv("SCHEDULER_CLEANUP_NEWS_CRON", "0 3 * * *")
_SCAN_TRENDS_CRON = os.getenv("SCHEDULER_SCAN_TRENDS_CRON", "30 8 * * *")
_SCAN_INDUSTRIES_CRON = os.getenv("SCHEDULER_SCAN_INDUSTRIES_CRON", "0 9 * * *")
_SCAN_STOCKS_CRON = os.getenv("SCHEDULER_SCAN_STOCKS_CRON", "30 9 * * *")
_REFRESH_TRENDS_CRON = os.getenv("SCHEDULER_REFRESH_TRENDS_CRON", "0 10 * * *")
_REFRESH_INDUSTRIES_CRON = os.getenv("SCHEDULER_REFRESH_INDUSTRIES_CRON", "30 10 * * *")
_REFRESH_STOCKS_CRON = os.getenv("SCHEDULER_REFRESH_STOCKS_CRON", "0 11 * * *")
_AUTO_RESEARCH_CRON = os.getenv("SCHEDULER_AUTO_RESEARCH_CRON", "30 11 * * *")

# Research thresholds
_MAX_AUTO_RESEARCH_CONCURRENT = int(os.getenv("SCHEDULER_AUTO_RESEARCH_CONCURRENT", "4"))
_RESEARCH_TIMEOUT_MINUTES = int(os.getenv("SCHEDULER_RESEARCH_TIMEOUT_MINUTES", "30"))

# Data retention
_NEWS_RETENTION_DAYS = int(os.getenv("SCHEDULER_NEWS_RETENTION_DAYS", "7"))
_REJECTED_WINDOW_DAYS = int(os.getenv("SCHEDULER_REJECTED_WINDOW_DAYS", "7"))
_REFRESH_CUTOFF_HOURS = int(os.getenv("SCHEDULER_REFRESH_CUTOFF_HOURS", "24"))


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
        f"--- 新闻内容 ---\n{news_text}"
    )

    try:
        from src.providers.llm import build_llm
        llm = build_llm()
        response = await asyncio.to_thread(llm.invoke, prompt)
        full_text = response.content if hasattr(response, "content") else str(response)
        # Strip thinking tags from thinking-preview models (e.g. MiniMax)
        import re as _re
        full_text = _re.sub(r'<think>.*?</think>', '', full_text, flags=_re.DOTALL).strip()
    except Exception:
        logger.exception("LLM call failed for digest %s", target_date)
        return None

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
    """Scheduled job: generate yesterday's digest using preset prompt."""
    target_date = (datetime.now(SHANGHAI_TZ) - timedelta(days=1)).strftime("%Y-%m-%d")
    try:
        result = await generate_daily_digest_from_preset(target_date)
        if result:
            logger.info("Digest generated for %s", result["digest_date"])
    except Exception:
        logger.exception("Scheduled digest job failed")


async def generate_daily_digest_from_preset(
    target_date: str | None = None,
) -> dict[str, Any] | None:
    """Generate a news digest: load prompt from YAML, call LLM, write to DB.

    Args:
        target_date: YYYY-MM-DD format, defaults to yesterday.

    Returns:
        The saved digest dict, or None if no news found.
    """
    if target_date is None:
        target_date = (datetime.now(SHANGHAI_TZ) - timedelta(days=1)).strftime("%Y-%m-%d")

    # 1. Fetch news for target date
    from src.db.database import get_db

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

    news_text_parts = []
    for r in rows:
        news_text_parts.append(f"[{r['published_at']}] [{r['level'] or 'N/A'}] {r['title']}")
        if r["content"]:
            news_text_parts.append(f"  {r['content'][:200]}")
    news_text = "\n".join(news_text_parts)
    if len(news_text) > 8000:
        news_text = news_text[:8000] + "\n... (truncated)"

    # 2. Load prompt from preset YAML
    import yaml as _yaml
    from pathlib import Path

    preset_path = Path(__file__).resolve().parent.parent / "swarm" / "presets" / "digest_news.yaml"
    try:
        with open(preset_path, "r", encoding="utf-8") as f:
            preset = _yaml.safe_load(f)
        prompt = preset["prompt_template"].replace("{news_content}", news_text).replace(
            "{digest_date}", target_date
        ).replace("{news_count}", str(len(rows)))
    except Exception:
        logger.warning("Failed to load digest_news preset, using inline prompt")
        prompt = (
            "你是一名专业财经分析师。请根据以下当日财经新闻快讯，生成一份结构化的每日市场总结。\n\n"
            "要求：\n1. 用 Markdown 格式输出\n"
            "2. 包含：市场概览（2-3句话）、重点事件（3-5条）、板块影响分析\n"
            "3. 用 2-3 句话总结当日市场情绪和关键看点作为 summary\n"
            "4. 输出格式：先 summary（纯文本），然后空一行，接着是完整 Markdown 正文作为 content\n\n"
            f"日期：{target_date}\n新闻条数：{len(rows)}\n\n--- 新闻内容 ---\n{news_text}"
        )

    # 3. Call LLM (async thread to avoid blocking event loop)
    try:
        from src.providers.llm import build_llm
        llm = build_llm()
        response = await asyncio.to_thread(llm.invoke, prompt)
        full_text = response.content if hasattr(response, "content") else str(response)
        # Strip thinking tags from thinking-preview models (e.g. MiniMax)
        import re as _re
        full_text = _re.sub(r'<think>.*?</think>', '', full_text, flags=_re.DOTALL).strip()
    except Exception:
        logger.exception("LLM call failed for digest %s", target_date)
        full_text = f"（LLM 生成失败，共 {len(rows)} 条新闻）"

    # 4. Split summary and content
    parts = full_text.split("\n\n", 1)
    summary = parts[0].strip() if len(parts) >= 1 else ""
    content = parts[1].strip() if len(parts) >= 2 else full_text

    # 5. Write to DB
    with get_db() as conn:
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
        if r["abstract"]:
            parts.append(f"摘要: {r['abstract']}")
        if r["research_report"]:
            parts.append(f"报告摘要: {r['research_report'][:500]}...")
    return "\n\n".join(parts)


def _build_existing_candidates(target_type: str) -> str:
    """Build a list of existing research_candidates for dedup in scan prompts.

    Includes active candidates (pending/researching/proposed) and recently
    rejected (passed) ones within 7 days, so scanners don't re-propose them.
    """
    from datetime import datetime as _dt
    from src.db.database import get_db as _get_db

    week_ago = (_dt.now(SHANGHAI_TZ) - timedelta(days=_REJECTED_WINDOW_DAYS)).strftime("%Y-%m-%d 00:00:00")
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT name, status, initial_score, source_context FROM research_candidates "
            "WHERE target_type = ? AND ("
            "  status IN ('pending', 'researching', 'proposed')"
            "  OR (status = 'passed' AND updated_at >= ?)"
            ") ORDER BY created_at DESC LIMIT 100",
            (target_type, week_ago),
        ).fetchall()
    if not rows:
        return "(无)"
    return "\n".join(
        f"- [{r['status']}] {r['name']} (评分:{r['initial_score']}) {r['source_context'] or ''}"
        for r in rows
    )


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
    candidates = _build_existing_candidates("trend")
    _run_preset("scan_trends", {
        "market": "A股",
        "existing_trends": existing,
        "existing_candidates": candidates,
    })


def _scan_industries_job() -> None:
    """Scheduled job: scan for industries based on active trends."""
    trend_ctx = _build_trend_context()
    existing = _build_existing_list("industry")
    candidates = _build_existing_candidates("industry")
    _run_preset("scan_industries", {
        "trend_context": trend_ctx,
        "existing_industries": existing,
        "existing_trends": _build_existing_list("trend"),
        "existing_candidates": candidates,
    })


def _scan_stocks_job() -> None:
    """Scheduled job: scan for stocks based on active industries."""
    details = _build_industry_details()
    existing = _build_existing_list("stock")
    portfolio = _build_current_portfolio()
    candidates = _build_existing_candidates("stock")
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
        "existing_candidates": candidates,
    })


def _refresh_entities_job(target_type: str) -> None:
    """Refresh (保鲜) proposed/adopted entities by creating temp candidates and running research."""
    import json as _json

    table_map = {"trend": "trends", "industry": "industries", "stock": "stocks"}
    table = table_map[target_type]

    with get_db() as conn:
        cutoff = (datetime.now(SHANGHAI_TZ) - timedelta(hours=_REFRESH_CUTOFF_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
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
            conn.execute(
                "UPDATE research_candidates SET status = 'researching' WHERE id = ?",
                (cand_id,),
            )

        # Build user_vars
        user_vars = {
            "candidate_names": _json.dumps([name], ensure_ascii=False),
            "candidate_info": _json.dumps({"name": name, "source_context": "保鲜刷新", "initial_score": row["confidence"]}, ensure_ascii=False),
            "existing_proposals": _build_existing_proposals(target_type),
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

        real_run_id = _run_preset(preset_name, user_vars)
        if real_run_id:
            with get_db() as conn:
                conn.execute(
                    "UPDATE research_candidates SET research_run_id = ? WHERE id = ?",
                    (real_run_id, cand_id),
                )


_PRESET_MAP = {
    "trend": "research_trends",
    "industry": "research_industries",
    "stock": "research_stocks",
}


def _build_existing_proposals(target_type: str) -> str:
    """Build a summary of existing pending proposals for the given target type.

    Injected into research presets so the manager agent can judge content overlap
    and avoid creating duplicate proposals even when names differ.
    """
    from src.db.database import get_db as _get_db
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT id, title, summary, confidence, target_id, action, created_at "
            "FROM proposals WHERE target_type = ? AND status = 'pending' "
            "ORDER BY created_at DESC LIMIT 20",
            (target_type,),
        ).fetchall()
    if not rows:
        return "(无待审批提案)"
    parts = []
    for r in rows:
        parts.append(
            f"- [#{r['id']}] {r['title']} "
            f"(action={r['action']}, target_id={r['target_id']}, "
            f"置信度={r['confidence']}, 创建={r['created_at'][:10]})\n"
            f"  摘要: {r['summary'] or '(无)'}"
        )
    return "\n".join(parts)


def _auto_research_pending_job() -> None:
    """Periodically pick up pending candidates and auto-trigger research."""
    import json as _json

    from src.db.database import get_db as _get_db
    from src.swarm.runtime import SwarmRuntime
    from src.swarm.store import SwarmStore
    from src.core.config import get_swarm_dir

    # ── Timeout: reset stuck researching candidates (>N min) ──
    store = SwarmStore(base_dir=get_swarm_dir())
    cutoff = datetime.now(SHANGHAI_TZ) - timedelta(minutes=_RESEARCH_TIMEOUT_MINUTES)
    with _get_db() as conn:
        stuck = conn.execute(
            "SELECT id, name, target_type, research_run_id, updated_at "
            "FROM research_candidates WHERE status = 'researching'"
        ).fetchall()
    for s in stuck:
        updated = s["updated_at"]
        # Parse ISO timestamp (handles both '2026-05-21T14:09:17+00:00' and '2026-05-21 14:09:17')
        if isinstance(updated, str):
            try:
                updated = datetime.fromisoformat(updated)
            except ValueError:
                updated = datetime.strptime(updated, "%Y-%m-%d %H:%M:%S")
        if updated.tzinfo is None:
            from datetime import timezone as _tz
            updated = updated.replace(tzinfo=_tz.utc)
        # Convert to Shanghai time for comparison
        if updated.astimezone(SHANGHAI_TZ) > cutoff:
            continue  # still within timeout window
        run_info = ""
        if s["research_run_id"]:
            run = store.load_run(s["research_run_id"])
            if run is not None and run.status.value not in ("completed", "failed", "cancelled"):
                # Swarm run still claims to be running but it's been too long.
                # Mark it as failed so the candidate slot is freed.
                try:
                    store.save_run(run.model_copy(update={"status": "failed", "error": f"Timeout: stuck in running state >{_RESEARCH_TIMEOUT_MINUTES} min"}))
                except Exception:
                    pass
                run_info = f"status was {run.status.value}"
            else:
                run_info = run.status.value if run else "not_found"
        with _get_db() as conn:
            conn.execute(
                "UPDATE research_candidates SET status = 'pending', "
                "research_run_id = NULL WHERE id = ?",
                (s["id"],),
            )
        logger.warning(
            "Reset stuck candidate %s/%s (run %s, %s) — timeout >%d min",
            s["target_type"], s["name"], s["research_run_id"] or "none", run_info,
            _RESEARCH_TIMEOUT_MINUTES,
        )

    # ── Zombie run scan: runs marked "running" but >N min old ──
    now = datetime.now(SHANGHAI_TZ)
    zombie_threshold = now - timedelta(minutes=_RESEARCH_TIMEOUT_MINUTES)
    for run_dir in sorted(store.base_dir.glob("swarm-*")):
        run_id = run_dir.name
        try:
            run = store.load_run(run_id)
        except Exception:
            continue
        if run is None or run.status.value != "running":
            continue
        try:
            created = datetime.fromisoformat(run.created_at)
        except (ValueError, TypeError, AttributeError):
            continue
        if created.tzinfo is None:
            from datetime import timezone as _tz
            created = created.replace(tzinfo=_tz.utc)
        if created.astimezone(SHANGHAI_TZ) > zombie_threshold:
            continue
        try:
            store.save_run(run.model_copy(update={
                "status": "failed",
                "error": f"Zombie: run stuck >{_RESEARCH_TIMEOUT_MINUTES} min without progress",
            }))
        except Exception:
            logger.warning("Failed to save zombie run %s", run_id, exc_info=True)
            continue
        with _get_db() as conn:
            conn.execute(
                "UPDATE research_candidates SET status = 'pending', research_run_id = NULL "
                "WHERE research_run_id = ? AND status = 'researching'",
                (run_id,),
            )
        logger.warning("Zombie run %s reset (created=%s, >30 min)", run_id, run.created_at[:19])

    with _get_db() as conn:
        researching_count = conn.execute(
            "SELECT COUNT(*) FROM research_candidates WHERE status = 'researching'"
        ).fetchone()[0]

    available = _MAX_AUTO_RESEARCH_CONCURRENT - researching_count
    if available <= 0:
        return

    with _get_db() as conn:
        rows = conn.execute(
            "SELECT id, target_type, name, code, source_context, initial_score "
            "FROM research_candidates WHERE status = 'pending' "
            "ORDER BY initial_score DESC, created_at ASC LIMIT ?",
            (available,),
        ).fetchall()

    if not rows:
        return

    runtime = SwarmRuntime(store=store)

    for row in rows:
        preset_name = _PRESET_MAP.get(row["target_type"])
        if not preset_name:
            logger.warning("No research preset for target_type=%s, skipping %s", row["target_type"], row["name"])
            continue

        with _get_db() as conn:
            updated = conn.execute(
                "UPDATE research_candidates SET status = 'researching', "
                "updated_at = datetime('now') "
                "WHERE id = ? AND status = 'pending'",
                (row["id"],),
            ).rowcount
            if not updated:
                continue

        candidate_info = _json.dumps({
            "name": row["name"],
            "code": row["code"],
            "source_context": row["source_context"],
            "initial_score": row["initial_score"],
        }, ensure_ascii=False)

        user_vars = {
            "candidate_names": _json.dumps([row["name"]], ensure_ascii=False),
            "candidate_info": candidate_info,
            "existing_proposals": _build_existing_proposals(row["target_type"]),
            "_user_id": "1",
        }

        try:
            run = runtime.start_run(preset_name, user_vars)
            # Write the actual swarm run ID so frontend can connect to the event stream
            with _get_db() as conn:
                conn.execute(
                    "UPDATE research_candidates SET research_run_id = ? WHERE id = ?",
                    (run.id, row["id"]),
                )
            logger.info("Auto-research started: %s (preset=%s, run=%s)", row["name"], preset_name, run.id)
        except Exception:
            logger.exception("Auto-research failed for %s", row["name"])
            with _get_db() as conn:
                conn.execute(
                    "UPDATE research_candidates SET status = 'pending', "
                    "research_run_id = NULL WHERE id = ?",
                    (row["id"],),
                )


def setup_scheduler(app_state: dict[str, Any] | None = None) -> Any:
    """Create and configure the scheduler with jobs.

    Returns the scheduler instance (not started).
    """
    import uuid as _uuid
    from apscheduler.triggers.cron import CronTrigger

    sched = create_scheduler()

    # Daily digest
    sched.add_job(
        _scheduled_digest_job,
        CronTrigger.from_crontab(_DIGEST_CRON, timezone=SHANGHAI_TZ),
        id="daily_digest",
        replace_existing=True,
    )

    # Clean up old news
    sched.add_job(
        _cleanup_old_news,
        CronTrigger.from_crontab(_CLEANUP_NEWS_CRON, timezone=SHANGHAI_TZ),
        id="cleanup_news",
        replace_existing=True,
    )

    # Research engine: scan jobs
    sched.add_job(
        _scan_trends_job,
        CronTrigger.from_crontab(_SCAN_TRENDS_CRON, timezone=SHANGHAI_TZ),
        id="scan_trends", replace_existing=True,
    )
    sched.add_job(
        _scan_industries_job,
        CronTrigger.from_crontab(_SCAN_INDUSTRIES_CRON, timezone=SHANGHAI_TZ),
        id="scan_industries", replace_existing=True,
    )
    sched.add_job(
        _scan_stocks_job,
        CronTrigger.from_crontab(_SCAN_STOCKS_CRON, timezone=SHANGHAI_TZ),
        id="scan_stocks", replace_existing=True,
    )

    # Auto-research pending candidates
    sched.add_job(
        _auto_research_pending_job,
        CronTrigger.from_crontab(_AUTO_RESEARCH_CRON, timezone=SHANGHAI_TZ),
        id="auto_research_pending", replace_existing=True,
    )

    # Refresh (保鲜) jobs
    sched.add_job(
        lambda: _refresh_entities_job("trend"),
        CronTrigger.from_crontab(_REFRESH_TRENDS_CRON, timezone=SHANGHAI_TZ),
        id="refresh_trends", replace_existing=True,
    )
    sched.add_job(
        lambda: _refresh_entities_job("industry"),
        CronTrigger.from_crontab(_REFRESH_INDUSTRIES_CRON, timezone=SHANGHAI_TZ),
        id="refresh_industries", replace_existing=True,
    )
    sched.add_job(
        lambda: _refresh_entities_job("stock"),
        CronTrigger.from_crontab(_REFRESH_STOCKS_CRON, timezone=SHANGHAI_TZ),
        id="refresh_stocks", replace_existing=True,
    )

    return sched


def _cleanup_old_news() -> None:
    """Delete news_raw entries older than 7 days."""
    from src.db.database import get_db

    cutoff = (datetime.now(SHANGHAI_TZ) - timedelta(days=_NEWS_RETENTION_DAYS)).strftime("%Y-%m-%d 00:00:00")
    with get_db() as conn:
        result = conn.execute("DELETE FROM news_raw WHERE published_at < ?", (cutoff,))
        logger.info("Cleaned up %d old news records (before %s)", result.rowcount, cutoff)
