"""News data: recent news, stock news, keyword search, daily digests, and sync.

Public interfaces:
- get_recent_news: query news_raw table (DB, last 7 days)
- search_stock_news: per-stock news (CLS search → eastmoney)
- search_news: CLS keyword search API
- get_news_digest: daily digests from DB
- NewsSyncService: background CLS news sync (realtime poll + startup backfill)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from .base import (
    NoDataAvailableError,
    _UA,
    cache_news,
    fallback,
    normalize_code,
)

logger = logging.getLogger(__name__)

SHANGHAI_TZ = timezone(timedelta(hours=8))

_POLL_INTERVAL = 30
_BACKFILL_MAX_DAYS = 3
_BACKFILL_DELAY = 1.0


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class NewsItem:
    """Single news article."""

    __slots__ = ("source_id", "title", "content", "time", "level", "source")

    def __init__(self, **kwargs: Any) -> None:
        self.source_id = kwargs.get("source_id", "")
        self.title = kwargs.get("title", "")
        self.content = kwargs.get("content", "")
        self.time = kwargs.get("time", "")
        self.level = kwargs.get("level", "")
        self.source = kwargs.get("source", "")

    def to_dict(self) -> dict[str, Any]:
        return {s: getattr(self, s) for s in self.__slots__}

    def to_db_row(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "content": self.content,
            "level": self.level,
            "source": self.source,
            "published_at": self.time,
            "fetched_at": datetime.now(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        }


# ===========================================================================
# Public interfaces
# ===========================================================================

# ---------------------------------------------------------------------------
# Recent news (from DB)
# ---------------------------------------------------------------------------

def _query_recent_news_sync(
    start_date: str,
    end_date: str,
    title: str | None,
    news_id: int | None,
    fields: str,
    limit: int,
) -> list[dict[str, Any]]:
    from src.db.database import get_db

    _SELECT_COLUMNS = {
        "title": "id, source_id, title, source, published_at",
        "content": "id, source_id, content, source, published_at",
        "all": "id, source_id, title, content, level, source, published_at",
    }
    select = _SELECT_COLUMNS.get(fields, _SELECT_COLUMNS["all"])

    sql = f"SELECT {select} FROM news_raw WHERE published_at >= ? AND published_at <= ?"
    params: list[Any] = [start_date, end_date]

    if news_id is not None:
        sql += " AND id = ?"
        params.append(news_id)
    if title:
        sql += " AND title LIKE ?"
        params.append(f"%{title}%")

    sql += " ORDER BY published_at DESC LIMIT ?"
    params.append(limit)

    with get_db() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


async def get_recent_news(
    start_date: str | None = None,
    end_date: str | None = None,
    title: str | None = None,
    news_id: int | None = None,
    fields: str = "all",
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Query recent news from news_raw table (last 7 days by default)."""
    today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    sd = start_date or week_ago
    ed = end_date or today

    return await asyncio.to_thread(
        _query_recent_news_sync, sd, ed, title, news_id, fields, limit,
    )


# ---------------------------------------------------------------------------
# Stock news (online search)
# ---------------------------------------------------------------------------

async def search_stock_news(code: str, limit: int = 20) -> list[NewsItem]:
    """Individual stock news.  Primary: CLS search, fallback: eastmoney."""
    code = normalize_code(code)
    cache_key = f"stock_news:{code}:{limit}"
    cached = cache_news.get(cache_key)
    if cached is not None:
        return cached

    async def _primary() -> list[NewsItem]:
        return await _cls_search_news(code, "", limit)

    async def _fb() -> list[NewsItem]:
        return await _eastmoney_stock_news(code, limit)

    items = await fallback(_primary, _fb, label=f"search_stock_news({code})")
    cache_news.set(cache_key, items)
    return items


# ---------------------------------------------------------------------------
# CLS keyword search (online)
# ---------------------------------------------------------------------------

_CLS_CATEGORIES = frozenset({
    "", "red", "announcement", "fund", "hk_us", "watch", "remind",
})


async def search_news(
    keyword: str,
    category: str = "",
    limit: int = 20,
) -> list[NewsItem]:
    """Search CLS news by keyword via POST API."""
    if category not in _CLS_CATEGORIES:
        raise ValueError(f"Invalid category {category!r}, expected one of {sorted(_CLS_CATEGORIES)}")
    cache_key = f"search_news:{keyword}:{category}:{limit}"
    cached = cache_news.get(cache_key)
    if cached is not None:
        return cached

    items = await _cls_search_news(keyword, category, limit)
    cache_news.set(cache_key, items, ttl=120)
    return items


# ---------------------------------------------------------------------------
# News digest (from DB)
# ---------------------------------------------------------------------------

def _query_news_digest_sync(
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    from src.db.database import get_db

    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, user_id, digest_date, content, summary, created_at "
            "FROM news_digests "
            "WHERE digest_date >= ? AND digest_date <= ? "
            "ORDER BY digest_date DESC",
            (start_date, end_date),
        ).fetchall()
        return [
            {
                "id": r["id"],
                "user_id": r["user_id"],
                "digest_date": r["digest_date"],
                "content": r["content"],
                "summary": r["summary"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]


async def get_news_digest(
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    """Read daily news digests from news_digests table."""
    today = datetime.now().strftime("%Y-%m-%d")
    days_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    sd = start_date or days_ago
    ed = end_date or today

    return await asyncio.to_thread(_query_news_digest_sync, sd, ed)


# ===========================================================================
# News sync service
# ===========================================================================

class NewsSyncService:
    """Background CLS news sync — realtime poll + startup backfill."""

    def __init__(self) -> None:
        self._backfill_target: int = 0
        self._tasks: list[asyncio.Task] = []
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    async def start(self) -> None:
        """Start realtime polling and backfill."""
        now = int(_time.time())
        seven_days_ago = now - _BACKFILL_MAX_DAYS * 86400

        latest = await asyncio.to_thread(self._load_latest_ctime)
        # Always backfill at least to seven_days_ago; INSERT OR IGNORE dedupes
        self._backfill_target = seven_days_ago

        self._running = True
        self._tasks = [
            asyncio.create_task(self._realtime_loop(), name="news-realtime"),
            asyncio.create_task(self._backfill(), name="news-backfill"),
        ]
        logger.info(
            "NewsSyncService started (backfill_target=%d, db_latest=%d)",
            self._backfill_target, latest or 0,
        )

    async def stop(self) -> None:
        """Cancel all sync tasks."""
        self._running = False
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("NewsSyncService stopped")

    # ------------------------------------------------------------------
    # DB helpers (sync, called via asyncio.to_thread)
    # ------------------------------------------------------------------

    @staticmethod
    def _load_latest_ctime() -> int | None:
        """Return unix timestamp of the latest record in news_raw, or None."""
        from src.db.database import get_db

        with get_db() as conn:
            row = conn.execute("SELECT MAX(published_at) as mx FROM news_raw").fetchone()
            if not row or not row["mx"]:
                return None
            try:
                dt = datetime.strptime(row["mx"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=SHANGHAI_TZ)
                return int(dt.timestamp())
            except (ValueError, TypeError):
                return None

    @staticmethod
    def _save_rows(rows: list[dict]) -> None:
        from src.db.database import get_db

        if not rows:
            return
        with get_db() as conn:
            conn.executemany(
                "INSERT INTO news_raw "
                "(source_id, title, content, level, source, published_at, fetched_at) "
                "VALUES (:source_id, :title, :content, :level, :source, :published_at, :fetched_at) "
                "ON CONFLICT(source_id, source) DO UPDATE SET "
                "title=excluded.title, content=excluded.content",
                rows,
            )

    # ------------------------------------------------------------------
    # Real-time polling (reuses _cls_telegraph)
    # ------------------------------------------------------------------

    async def _realtime_loop(self) -> None:
        while self._running:
            try:
                items = await _cls_telegraph(limit=50)
                if items:
                    await asyncio.to_thread(self._save_rows, [it.to_db_row() for it in items])
                    logger.info("Realtime: %d items fetched", len(items))
            except Exception:
                logger.exception("Realtime poll error")
            await asyncio.sleep(_POLL_INTERVAL)

    # ------------------------------------------------------------------
    # Backfill (reuses _cls_search_news)
    # ------------------------------------------------------------------

    async def _backfill(self) -> None:
        now = int(_time.time())
        target = self._backfill_target

        if target >= now - 60:
            logger.info("Backfill skipped (DB is up to date)")
            return

        logger.info(
            "Backfill started: %s → %s",
            datetime.fromtimestamp(now, tz=SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M"),
            datetime.fromtimestamp(target, tz=SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M"),
        )

        batch_time: int | None = None
        target_str = datetime.fromtimestamp(target, tz=SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M:%S")
        total = 0

        while self._running:
            try:
                items = await _cls_search_news("", "", limit=50, start_time=batch_time)
            except NoDataAvailableError:
                logger.warning("Backfill: CLS search returned no results, stopping")
                break
            if not items:
                break

            try:
                await asyncio.to_thread(self._save_rows, [it.to_db_row() for it in items])
            except Exception:
                logger.exception("Backfill: failed to save batch")
            total += len(items)

            oldest_time = items[-1].time
            if not oldest_time or len(oldest_time) < 19:
                break
            if oldest_time <= target_str or len(items) < 50:
                break

            try:
                dt = datetime.strptime(oldest_time, "%Y-%m-%d %H:%M:%S").replace(tzinfo=SHANGHAI_TZ)
                batch_time = int(dt.timestamp())
            except (ValueError, TypeError):
                break

            await asyncio.sleep(_BACKFILL_DELAY)

        logger.info("Backfill complete: %d items synced", total)


# ===========================================================================
# Internal implementations (sync workers + async wrappers)
# ===========================================================================

def _cls_telegraph_sync(limit: int, last_time: int | None = None) -> list[NewsItem]:
    """Fetch CLS telegraph list with sign verification (sync, runs in thread)."""
    url = "https://www.cls.cn/nodeapi/telegraphList"
    current_time = last_time if last_time is not None else int(_time.time())
    base_params = {
        "app": "CailianpressWeb",
        "category": "",
        "lastTime": current_time,
        "last_time": current_time,
        "os": "web",
        "refresh_type": "1",
        "rn": str(min(limit, 2000)),
        "sv": "7.7.5",
    }

    query_str = requests.Request("GET", url, params=base_params).prepare().url.split("?", 1)[-1]
    sha1 = hashlib.sha1(query_str.encode("utf-8")).hexdigest()
    sign = hashlib.md5(sha1.encode()).hexdigest()

    params = {**base_params, "sign": sign}
    headers = {
        "User-Agent": _UA,
        "Referer": "https://www.cls.cn/telegraph",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json;charset=utf-8",
    }

    r = requests.get(url, params=params, headers=headers, timeout=10)
    r.encoding = "utf-8"
    try:
        r.raise_for_status()
    except requests.RequestException as exc:
        raise NoDataAvailableError(f"CLS telegraph request failed: {exc}") from exc
    d = r.json()

    items: list[NewsItem] = []
    for item in d.get("data", {}).get("roll_data", []):
        ctime = item.get("ctime", "")
        if isinstance(ctime, (int, float)) and ctime:
            dt = datetime.fromtimestamp(ctime, tz=SHANGHAI_TZ)
            time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        else:
            continue

        items.append(NewsItem(
            source_id=str(item.get("id", "")),
            title=item.get("title", "") or item.get("brief", ""),
            content=item.get("content", "") or item.get("brief", ""),
            time=time_str,
            level=item.get("level", ""),
            source="cls",
        ))

    if not items:
        raise NoDataAvailableError("cls.cn: empty telegraph list")
    return items[:limit]


async def _cls_telegraph(limit: int, last_time: int | None = None) -> list[NewsItem]:
    return await asyncio.to_thread(_cls_telegraph_sync, limit, last_time)


_CLS_SEARCH_URL = "https://www.cls.cn/api/csw"
_CLS_SEARCH_SV = "8.4.6"


def _cls_search_news_sync(
    keyword: str,
    category: str,
    limit: int,
    start_time: int | None = None,
) -> list[NewsItem]:
    """CLS keyword search with sign verification and auto-pagination (sync, runs in thread)."""
    base_params = {"app": "CailianpressWeb", "os": "web", "sv": _CLS_SEARCH_SV}
    query_str = requests.Request("GET", _CLS_SEARCH_URL, params=base_params).prepare().url.split("?", 1)[-1]
    sha1 = hashlib.sha1(query_str.encode("utf-8")).hexdigest()
    sign = hashlib.md5(sha1.encode()).hexdigest()

    params = {**base_params, "sign": sign}
    headers = {
        "User-Agent": _UA,
        "Referer": "https://www.cls.cn/",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json;charset=utf-8",
    }

    items: list[NewsItem] = []
    last_time = start_time if start_time is not None else int(_time.time())
    pages = max(1, (limit + 9) // 10)

    for pi in range(pages):
        if pi > 0:
            _time.sleep(0.3)  # rate limit protection between pages
        body = {
            "lastTime": last_time,
            "keyword": keyword,
            "category": category,
            "os": "web",
            "os": "web",
            "sv": _CLS_SEARCH_SV,
            "app": "CailianpressWeb",
        }
        r = requests.post(_CLS_SEARCH_URL, params=params, json=body, headers=headers, timeout=15)
        r.encoding = "utf-8"
        try:
            r.raise_for_status()
        except requests.RequestException as exc:
            raise NoDataAvailableError(f"CLS search request failed: {exc}") from exc
        d = r.json()

        page_items = d.get("list") or []
        if not page_items:
            break

        for item in page_items:
            ctime = item.get("ctime", 0)
            if isinstance(ctime, (int, float)) and ctime:
                dt = datetime.fromtimestamp(ctime, tz=SHANGHAI_TZ)
                time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            else:
                time_str = str(ctime)

            items.append(NewsItem(
                source_id=str(item.get("id", "")),
                title=re.sub(r"<[^>]+>", "", item.get("title", "")),
                content=re.sub(r"<[^>]+>", "", item.get("content", "")),
                time=time_str,
                level=item.get("level", ""),
                source="cls",
            ))

        last_ctime = page_items[-1].get("ctime", 0)
        if not last_ctime or last_ctime >= last_time:
            break
        last_time = last_ctime

    if not items:
        raise NoDataAvailableError(f"cls.cn search: no results for {keyword!r}")
    return items[:limit]


async def _cls_search_news(
    keyword: str,
    category: str,
    limit: int,
    start_time: int | None = None,
) -> list[NewsItem]:
    return await asyncio.to_thread(_cls_search_news_sync, keyword, category, limit, start_time)


def _eastmoney_stock_news_sync(code: str, limit: int) -> list[NewsItem]:
    """Eastmoney stock news via JSONP API (sync, runs in thread)."""
    cb = "jQuery_news"
    url = "https://search-api-web.eastmoney.com/search/jsonp"
    inner_params = json.dumps({
        "uid": "",
        "keyword": code,
        "type": ["cmsArticleWebOld"],
        "client": "web",
        "clientType": "web",
        "clientVersion": "curr",
        "param": {"cmsArticleWebOld": {
            "searchScope": "default", "sort": "default",
            "pageIndex": 1, "pageSize": limit, "preTag": "", "postTag": "",
        }},
    }, separators=(",", ":"))
    params = {"cb": cb, "param": inner_params}
    headers = {"User-Agent": _UA, "Referer": "https://so.eastmoney.com/"}

    r = requests.get(url, params=params, headers=headers, timeout=15)
    try:
        r.raise_for_status()
    except requests.RequestException as exc:
        raise NoDataAvailableError(f"eastmoney stock news request failed: {exc}") from exc
    text = r.text
    try:
        # JSONP: cb({...})
        start = text.index("(") + 1
        depth = 1
        for i in range(start, len(text)):
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
                if depth == 0:
                    json_str = text[start:i]
                    break
        else:
            raise ValueError("unbalanced parentheses")
    except (ValueError, IndexError):
        raise NoDataAvailableError(f"eastmoney: invalid JSONP response for {code}")
    d = json.loads(json_str)

    items: list[NewsItem] = []
    articles = d.get("result", {}).get("cmsArticleWebOld", {}).get("list", [])
    for a in articles:
        title = re.sub(r"<[^>]+>", "", a.get("title", ""))
        date_str = a.get("date", "")
        items.append(NewsItem(
            source_id=f"em_{date_str}_{hashlib.sha256(title.encode()).hexdigest()[:24]}",
            title=title,
            content=re.sub(r"<[^>]+>", "", a.get("content", ""))[:200],
            time=date_str,
            source="eastmoney",
        ))

    if not items:
        raise NoDataAvailableError(f"eastmoney: no news for {code}")
    return items


async def _eastmoney_stock_news(code: str, limit: int) -> list[NewsItem]:
    return await asyncio.to_thread(_eastmoney_stock_news_sync, code, limit)
