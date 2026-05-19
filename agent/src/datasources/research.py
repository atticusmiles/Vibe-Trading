"""Research data: consensus EPS forecasts and research report listings.

Sources:
- get_consensus_eps: THS (basic.10jqka.com.cn) HTML parsing
- get_research_reports: Eastmoney report API
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any

import requests

from .base import NoDataAvailableError, _UA, _safe_float, cache_news, normalize_code

logger = logging.getLogger(__name__)

REPORT_API = "https://reportapi.eastmoney.com/report/list"


# ---------------------------------------------------------------------------
# Consensus EPS
# ---------------------------------------------------------------------------

async def get_consensus_eps(code: str) -> dict[str, Any]:
    """Consensus EPS forecast from THS."""
    code = normalize_code(code)
    cache_key = f"eps:{code}"
    cached = cache_news.get(cache_key)
    if cached is not None:
        return cached

    result = await asyncio.to_thread(_ths_consensus_eps_sync, code)
    cache_news.set(cache_key, result, ttl=3600)
    return result


def _ths_consensus_eps_sync(code: str) -> dict[str, Any]:
    """Parse THS consensus EPS from embedded JSON data in worth.html."""
    url = f"https://basic.10jqka.com.cn/new/{code}/worth.html"
    headers = {
        "User-Agent": _UA,
        "Referer": "https://basic.10jqka.com.cn/",
    }
    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
    except requests.RequestException as exc:
        raise NoDataAvailableError(f"THS: request failed for {code}: {exc}") from exc
    if "utf-8" in r.headers.get("Content-Type", "").lower():
        r.encoding = "utf-8"
    else:
        r.encoding = r.apparent_encoding or "gbk"

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

    actual_list = [{"year": row[0], "eps": _safe_float(row[1]), "net_profit": _safe_float(row[2])} for row in actual]
    forecast_list = [{"year": row[0], "eps": _safe_float(row[1]), "net_profit": _safe_float(row[2])} for row in forecast]

    result: dict[str, Any] = {
        "code": code,
        "actual": actual_list,
        "forecast": forecast_list,
    }

    if forecast_list:
        result["eps_mean"] = forecast_list[0]["eps"]
        result["forecast_year"] = forecast_list[0]["year"]

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

    reports = await asyncio.to_thread(_eastmoney_reports_sync, code, limit)
    cache_news.set(cache_key, reports, ttl=1800)
    return reports


def _eastmoney_reports_sync(code: str, limit: int) -> list[dict[str, Any]]:
    """Fetch reports from eastmoney reportapi."""
    max_pages = max(1, (limit + 99) // 100)

    with requests.Session() as session:
        session.headers.update({
            "User-Agent": _UA,
            "Referer": "https://data.eastmoney.com/",
        })

        all_records: list[dict[str, Any]] = []

        for page in range(1, max_pages + 1):
            params = {
                "industryCode": "*", "pageSize": "100", "industry": "*",
                "rating": "*", "ratingChange": "*",
                "beginTime": "2000-01-01", "endTime": "2030-01-01",
                "pageNo": str(page), "fields": "", "qType": "0",
                "orgCode": "", "code": code, "rcode": "",
                "p": str(page), "pageNum": str(page), "pageNumber": str(page),
            }
            try:
                r = session.get(REPORT_API, params=params, timeout=30)
                r.raise_for_status()
            except requests.RequestException as exc:
                raise NoDataAvailableError(f"Eastmoney API request failed: {exc}") from exc
            d = r.json()
            rows = d.get("data") or []
            if not rows:
                break

            for rec in rows:
                pub = rec.get("publishDate")
                if isinstance(pub, str):
                    date = pub[:10]
                else:
                    date = ""
                all_records.append({
                    "title": rec.get("title", ""),
                    "org": rec.get("orgSName", ""),
                    "rating": rec.get("emRatingName", ""),
                    "predicted_pe": _safe_float(rec.get("predictNextTwoYearPe", 0)),
                    "date": date,
                    "eps_this_year": _safe_float(rec.get("predictThisYearEps")),
                    "eps_next_year": _safe_float(rec.get("predictNextYearEps")),
                    "info_code": rec.get("infoCode", ""),
                })

            if page >= (d.get("TotalPage", 1) or 1):
                break

            time.sleep(0.3)

    if not all_records:
        raise NoDataAvailableError(f"eastmoney: no research reports for {code}")

    return all_records[:limit]
