"""Research data: consensus EPS forecasts and research report listings.

Sources:
- get_consensus_eps: THS (basic.10jqka.com.cn) HTML parsing
- get_research_reports: Eastmoney report API
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

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
    """Parse THS consensus EPS from embedded JSON data in worth.html.

    THS renders data as JSON inside a hidden div:
    <div id="yjycData" class="none">[["2024","68.64","862.28","SJ"],...]</div>
    Each row: [year, EPS, net_profit_yi, type(SJ=actual/YC=forecast)]
    """
    url = f"https://basic.10jqka.com.cn/new/{code}/worth.html"
    headers = {
        "User-Agent": UA,
        "Referer": "https://basic.10jqka.com.cn/",
    }
    r = requests.get(url, headers=headers, timeout=15)
    r.encoding = "gbk"

    m = re.search(r'yjycData[^>]*>(.*?)</div>', r.text, re.DOTALL)
    if not m:
        raise NoDataAvailableError(f"THS: no EPS data for {code}")

    try:
        raw_data = json.loads(m.group(1).strip())
    except (json.JSONDecodeError, ValueError):
        raise NoDataAvailableError(f"THS: failed to parse EPS data for {code}")

    if not raw_data:
        raise NoDataAvailableError(f"THS: empty EPS data for {code}")

    actual = [r for r in raw_data if len(r) >= 4 and r[3] == "SJ"]
    forecast = [r for r in raw_data if len(r) >= 4 and r[3] == "YC"]

    actual_list = [{"year": r[0], "eps": float(r[1]), "net_profit": float(r[2])} for r in actual]
    forecast_list = [{"year": r[0], "eps": float(r[1]), "net_profit": float(r[2])} for r in forecast]

    result: dict[str, Any] = {
        "code": code,
        "actual": actual_list,
        "forecast": forecast_list,
    }

    if forecast_list:
        result["eps_mean"] = forecast_list[0]["eps"]
        result["forecast_year"] = forecast_list[0]["year"]

    # Extract org count from the summary text on the page
    org_match = re.search(r'(\d+)\s*家.*?（|(\d+)\s*家.*?机构|共有\s*(\d+)\s*家', r.text)
    org_count = int(next(g for g in org_match.groups() if g)) if org_match and any(org_match.groups()) else 0
    result["org_count"] = org_count

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
