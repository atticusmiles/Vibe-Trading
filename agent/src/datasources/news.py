"""News data: CLS telegraph, stock news, and daily digests.

Sources:
- get_flash_news: self-crawl cls.cn (primary) → akshare (fallback)
- get_stock_news: akshare eastmoney source
- get_news_digest: reads from news_digests table
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from .base import (
    NoDataAvailableError,
    cache_news,
    fallback,
    normalize_code,
)

logger = logging.getLogger(__name__)

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
SHANGHAI_TZ = timezone(timedelta(hours=8))


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

class NewsItem:
    """Single news article."""

    __slots__ = ("title", "content", "time", "level", "source")

    def __init__(self, **kwargs: Any) -> None:
        self.title = kwargs.get("title", "")
        self.content = kwargs.get("content", "")
        self.time = kwargs.get("time", "")
        self.level = kwargs.get("level", "")
        self.source = kwargs.get("source", "")

    def to_dict(self) -> dict[str, Any]:
        return {s: getattr(self, s) for s in self.__slots__}


# ---------------------------------------------------------------------------
# Flash news (CLS telegraph)
# ---------------------------------------------------------------------------

async def get_flash_news(limit: int = 30) -> list[NewsItem]:
    """Real-time CLS telegraph.  Primary: self-crawl, fallback: akshare."""
    cache_key = f"flash_news:{limit}"
    cached = cache_news.get(cache_key)
    if cached is not None:
        return cached

    async def _primary() -> list[NewsItem]:
        return await _flash_news_cls(limit)

    async def _fb() -> list[NewsItem]:
        return await _flash_news_akshare(limit)

    items = await fallback(_primary, _fb, label="get_flash_news")
    cache_news.set(cache_key, items)
    return items


async def _flash_news_cls(limit: int) -> list[NewsItem]:
    """Self-crawl CLS telegraph: cls.cn/nodeapi/telegraphList."""
    url = "https://www.cls.cn/nodeapi/telegraphList"
    params = {"rn": str(limit), "page": "1"}
    headers = {"User-Agent": UA, "Referer": "https://www.cls.cn/"}

    r = requests.get(url, params=params, headers=headers, timeout=10)
    d = r.json()

    items: list[NewsItem] = []
    for item in d.get("data", {}).get("roll_data", []):
        ctime = item.get("ctime", "")
        if isinstance(ctime, (int, float)):
            dt = datetime.fromtimestamp(ctime, tz=SHANGHAI_TZ)
            time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        else:
            time_str = str(ctime)

        items.append(NewsItem(
            title=item.get("title", "") or item.get("brief", ""),
            content=item.get("content", "") or item.get("brief", ""),
            time=time_str,
            level=item.get("level", ""),
            source="cls",
        ))

    if not items:
        raise NoDataAvailableError("cls.cn: empty telegraph list")
    return items[:limit]


async def _flash_news_akshare(limit: int) -> list[NewsItem]:
    """Fallback: akshare CLS source."""
    try:
        import akshare as ak
    except ImportError:
        raise NoDataAvailableError("akshare not installed")

    df = ak.stock_info_global_cls(symbol="全部")
    if df is None or df.empty:
        raise NoDataAvailableError("akshare: empty CLS data")

    items: list[NewsItem] = []
    for _, row in df.head(limit).iterrows():
        items.append(NewsItem(
            title=str(row.get("标题", "")),
            content=str(row.get("内容", "")),
            time=str(row.get("发布时间", "")),
            level=str(row.get("等级", "")),
            source="akshare_cls",
        ))
    return items


# ---------------------------------------------------------------------------
# Stock news
# ---------------------------------------------------------------------------

async def get_stock_news(code: str, limit: int = 20) -> list[NewsItem]:
    """Individual stock news.  Primary: eastmoney JSONP, fallback: akshare."""
    code = normalize_code(code)
    cache_key = f"stock_news:{code}:{limit}"
    cached = cache_news.get(cache_key)
    if cached is not None:
        return cached

    async def _primary() -> list[NewsItem]:
        return await _stock_news_eastmoney(code, limit)

    async def _fb() -> list[NewsItem]:
        return await _stock_news_akshare(code, limit)

    items = await fallback(_primary, _fb, label=f"get_stock_news({code})")
    cache_news.set(cache_key, items)
    return items


async def _stock_news_eastmoney(code: str, limit: int) -> list[NewsItem]:
    """Eastmoney stock news via JSONP API."""
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
    headers = {"User-Agent": UA, "Referer": "https://so.eastmoney.com/"}

    r = requests.get(url, params=params, headers=headers, timeout=15)

    # Parse JSONP
    text = r.text
    json_str = text[text.index("(") + 1 : text.rindex(")")]
    d = json.loads(json_str)

    items: list[NewsItem] = []
    articles = d.get("result", {}).get("cmsArticleWebOld", {}).get("list", [])
    for a in articles:
        items.append(NewsItem(
            title=re.sub(r"<[^>]+>", "", a.get("title", "")),
            content=re.sub(r"<[^>]+>", "", a.get("content", ""))[:200],
            time=a.get("date", ""),
            source=a.get("mediaName", ""),
        ))

    if not items:
        raise NoDataAvailableError(f"eastmoney: no news for {code}")
    return items


async def _stock_news_akshare(code: str, limit: int) -> list[NewsItem]:
    """Fallback: akshare eastmoney stock news."""
    try:
        import akshare as ak
    except ImportError:
        raise NoDataAvailableError("akshare not installed")

    df = ak.stock_news_em(symbol=code)
    if df is None or df.empty:
        raise NoDataAvailableError(f"akshare: no news for {code}")

    items: list[NewsItem] = []
    for _, row in df.head(limit).iterrows():
        items.append(NewsItem(
            title=str(row.get("新闻标题", "")),
            content=str(row.get("新闻内容", ""))[:200],
            time=str(row.get("发布时间", "")),
            source=str(row.get("文章来源", "")),
        ))
    return items


# ---------------------------------------------------------------------------
# News digest (reads from DB)
# ---------------------------------------------------------------------------

async def get_news_digest(
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    """Read daily news digests from news_digests table.

    start_date defaults to 7 days ago, end_date defaults to today.
    Returns list sorted by date descending.
    """
    import sqlite3

    from .migrations import DB_PATH

    today = datetime.now().strftime("%Y-%m-%d")
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    sd = start_date or week_ago
    ed = end_date or today

    db_path = DB_PATH
    if not db_path.exists():
        return []

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, user_id, digest_date, content, summary, created_at "
            "FROM news_digests "
            "WHERE digest_date >= ? AND digest_date <= ? "
            "ORDER BY digest_date DESC",
            (sd, ed),
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
    finally:
        conn.close()
