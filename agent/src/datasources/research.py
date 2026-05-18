"""Research data: consensus EPS forecasts and research report listings.

Sources:
- get_consensus_eps: THS (basic.10jqka.com.cn) HTML parsing
- get_research_reports: Eastmoney report API
"""

from __future__ import annotations

import logging
import time
from typing import Any

import pandas as pd
import requests

from .base import NoDataAvailableError, cache_news, normalize_code

logger = logging.getLogger(__name__)

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
REPORT_API = "https://reportapi.eastmoney.com/report/list"


# ---------------------------------------------------------------------------
# Consensus EPS
# ---------------------------------------------------------------------------

async def get_consensus_eps(code: str) -> dict[str, Any]:
    """Consensus EPS forecast from THS.

    Returns warning when org_count < 3 (insufficient coverage).
    """
    code = normalize_code(code)
    cache_key = f"eps:{code}"
    cached = cache_news.get(cache_key)
    if cached is not None:
        return cached

    result = await _consensus_eps_ths(code)
    cache_news.set(cache_key, result, ttl=3600)
    return result


async def _consensus_eps_ths(code: str) -> dict[str, Any]:
    """Parse THS consensus EPS from HTML table."""
    url = f"https://basic.10jqka.com.cn/new/{code}/worth.html"
    headers = {
        "User-Agent": UA,
        "Referer": "https://basic.10jqka.com.cn/",
    }
    r = requests.get(url, headers=headers, timeout=15)
    r.encoding = "gbk"

    dfs = pd.read_html(r.text)
    target_df = None
    for df in dfs:
        cols = [str(c) for c in df.columns]
        if any("每股收益" in c or "均值" in c for c in cols):
            target_df = df
            break

    if target_df is None or target_df.empty:
        raise NoDataAvailableError(f"THS: no EPS forecast for {code}")

    # Extract latest year row
    first_row = target_df.iloc[0]
    cols = [str(c) for c in target_df.columns]

    result: dict[str, Any] = {"code": code, "years": []}

    for _, row in target_df.iterrows():
        row_dict = {}
        for c in cols:
            row_dict[c] = row[c]
        result["years"].append(row_dict)

    # Try to find mean value and org count from column names
    mean_col = next((c for c in cols if "均值" in c), None)
    org_col = next((c for c in cols if "机构" in c or "预测机构" in c), None)

    if mean_col:
        try:
            result["eps_mean"] = float(first_row[mean_col])
        except (ValueError, TypeError):
            result["eps_mean"] = 0
    if org_col:
        try:
            result["org_count"] = int(first_row[org_col])
        except (ValueError, TypeError):
            result["org_count"] = 0

    # Warning for insufficient coverage
    org_count = result.get("org_count", 0)
    if org_count < 3:
        result["warning"] = "机构覆盖不足，数据不可信"

    return result


# ---------------------------------------------------------------------------
# Research reports
# ---------------------------------------------------------------------------

async def get_research_reports(code: str, limit: int = 10) -> list[dict[str, Any]]:
    """Research report list from Eastmoney."""
    code = normalize_code(code)
    cache_key = f"reports:{code}:{limit}"
    cached = cache_news.get(cache_key)
    if cached is not None:
        return cached

    reports = await _reports_eastmoney(code, limit)
    cache_news.set(cache_key, reports, ttl=1800)
    return reports


async def _reports_eastmoney(code: str, limit: int) -> list[dict[str, Any]]:
    """Fetch reports from eastmoney reportapi."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": UA,
        "Referer": "https://data.eastmoney.com/",
    })

    all_records: list[dict[str, Any]] = []
    max_pages = max(1, (limit // 100) + 1)

    for page in range(1, max_pages + 1):
        params = {
            "industryCode": "*", "pageSize": "100", "industry": "*",
            "rating": "*", "ratingChange": "*",
            "beginTime": "2000-01-01", "endTime": "2030-01-01",
            "pageNo": str(page), "fields": "", "qType": "0",
            "orgCode": "", "code": code, "rcode": "",
            "p": str(page), "pageNum": str(page), "pageNumber": str(page),
        }
        r = session.get(REPORT_API, params=params, timeout=30)
        d = r.json()
        rows = d.get("data") or []
        if not rows:
            break

        for rec in rows:
            all_records.append({
                "title": rec.get("title", ""),
                "org": rec.get("orgSName", ""),
                "rating": rec.get("emRatingName", ""),
                "target_price": rec.get("predictNextTwoYearPe", 0),
                "date": (rec.get("publishDate") or "")[:10],
                "eps_this_year": rec.get("predictThisYearEps"),
                "eps_next_year": rec.get("predictNextYearEps"),
                "info_code": rec.get("infoCode", ""),
            })

        if page >= (d.get("TotalPage", 1) or 1):
            break
        time.sleep(0.3)

    if not all_records:
        raise NoDataAvailableError(f"eastmoney: no research reports for {code}")

    return all_records[:limit]
