"""Fundamental data: financial snapshot, statements, F10, industry classification.

Sources:
- get_financial_snapshot: baostock (26 fields from 4 APIs, supports historical quarters)
- get_financial_statements: baostock (primary) → sina (fallback)
- get_f10: mootdx only
- get_industry: baostock only
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

import requests

from .base import (
    NoDataAvailableError,
    _UA,
    TTLCache,
    baostock_lock,
    fallback,
    get_mootdx_client,
    normalize_code,
    to_baostock_code,
    to_mootdx_code,
    to_tencent_code,
)

cache_snapshot = TTLCache(default_ttl=300.0)
cache_statements = TTLCache(default_ttl=600.0)
cache_f10 = TTLCache(default_ttl=3600.0)
cache_industry = TTLCache(default_ttl=86400.0)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Financial snapshot
# ---------------------------------------------------------------------------

async def get_financial_snapshot(
    code: str,
    year: int | None = None,
    quarter: int | None = None,
) -> dict[str, Any]:
    """Quarterly financial snapshot from baostock (26 fields from 4 APIs).

    Args:
        code: stock code (e.g. '600519')
        year: report year, defaults to current year
        quarter: report quarter (1-4), defaults to current quarter with auto-fallback
    """
    code = normalize_code(code)
    cache_key = f"snapshot:{code}:{year}:{quarter}"
    cached = cache_snapshot.get(cache_key)
    if cached is not None:
        return cached

    result = await asyncio.to_thread(_baostock_snapshot_sync, code, year, quarter)
    cache_snapshot.set(cache_key, result)
    return result


# baostock field mapping: {query_method: {baostock_field: english_name}}
_BAOSTOCK_SNAPSHOT_MAP = {
    "query_profit_data": {
        "roeAvg": "roe",
        "npMargin": "net_margin",
        "gpMargin": "gross_margin",
        "netProfit": "net_profit",
        "epsTTM": "eps_ttm",
        "MBRevenue": "main_business_revenue",
        "totalShare": "total_shares",
        "liqaShare": "float_shares",
    },
    "query_balance_data": {
        "currentRatio": "current_ratio",
        "quickRatio": "quick_ratio",
        "cashRatio": "cash_ratio",
        "YOYLiability": "yoy_liability",
        "liabilityToAsset": "debt_ratio",
        "assetToEquity": "asset_to_equity",
    },
    "query_cash_flow_data": {
        "CAToAsset": "current_asset_ratio",
        "NCAToAsset": "non_current_asset_ratio",
        "tangibleAssetToAsset": "tangible_asset_ratio",
        "ebitToInterest": "ebit_to_interest",
        "CFOToOR": "cfo_to_revenue",
        "CFOToNP": "cfo_to_profit",
        "CFOToGr": "cfo_to_gross",
    },
    "query_growth_data": {
        "YOYEquity": "yoy_equity",
        "YOYAsset": "yoy_assets",
        "YOYNI": "yoy_net_income",
        "YOYEPSBasic": "yoy_eps",
        "YOYPNI": "yoy_parent_net_income",
    },
}


def _baostock_snapshot_sync(
    code: str,
    year: int | None,
    quarter: int | None,
) -> dict[str, Any]:
    """Fetch quarterly snapshot from baostock (sync, runs in thread)."""
    import baostock as bs

    bs_code = to_baostock_code(code)
    today = datetime.now().strftime("%Y-%m-%d")
    default_year = int(today[:4])
    default_quarter = min((int(today[5:7]) - 1) // 3 + 1, 4)

    y = year if year is not None else default_year
    q = quarter if quarter is not None else default_quarter

    quarters_to_try = _quarter_fallback(y, q) if quarter is None else [(y, q)]

    result: dict[str, Any] = {}

    with baostock_lock:
        lg = bs.login()
        if lg.error_code != "0":
            raise NoDataAvailableError(f"baostock login failed: {lg.error_msg}")
        try:
            for cy, cq in quarters_to_try:
                for method_name, field_map in _BAOSTOCK_SNAPSHOT_MAP.items():
                    fn = getattr(bs, method_name, None)
                    if fn is None:
                        continue
                    rs = fn(code=bs_code, year=cy, quarter=cq)
                    fields = rs.fields
                    rows = []
                    while rs.error_code == "0" and rs.next():
                        rows.append(rs.get_row_data())
                    if not rows:
                        continue
                    row_dict = dict(zip(fields, rows[0]))
                    for bs_field, en_name in field_map.items():
                        val = row_dict.get(bs_field)
                        if val is not None and val != "":
                            try:
                                result[en_name] = float(val)
                            except (ValueError, TypeError):
                                pass
                if result:
                    break
        finally:
            bs.logout()

    if not result:
        raise NoDataAvailableError(f"baostock: no snapshot data for {code} {y}Q{q}")
    return result


def _quarter_fallback(year: int, quarter: int) -> list[tuple[int, int]]:
    """Generate (year, quarter) pairs to try, most recent first (up to 4 back)."""
    pairs = []
    y, q = year, quarter
    for _ in range(4):
        pairs.append((y, q))
        q -= 1
        if q == 0:
            q = 4
            y -= 1
    return pairs


# ---------------------------------------------------------------------------
# Financial statements
# ---------------------------------------------------------------------------

_REPORT_TYPE_BAOSTOCK = {
    "balance": "query_balance_data",
    "income": "query_profit_data",
    "cashflow": "query_cash_flow_data",
}


async def get_financial_statements(
    code: str,
    year: int,
    quarter: int,
    report_type: str,
) -> list[dict[str, Any]]:
    """Full financial statement.  Primary: baostock, fallback: sina."""
    code = normalize_code(code)
    method_name = _REPORT_TYPE_BAOSTOCK.get(report_type)
    if not method_name:
        raise ValueError(f"Unknown report_type: {report_type!r}")

    cache_key = f"stmts:{code}:{year}:{quarter}:{report_type}"
    cached = cache_statements.get(cache_key)
    if cached is not None:
        return cached

    async def _primary() -> list[dict[str, Any]]:
        return await asyncio.to_thread(_baostock_statements_sync, code, year, quarter, method_name)

    async def _fb() -> list[dict[str, Any]]:
        return await asyncio.to_thread(_sina_statements_sync, code, year, quarter, report_type)

    result = await fallback(_primary, _fb, label=f"get_financial_statements({code},{report_type})")
    cache_statements.set(cache_key, result)
    return result


def _baostock_statements_sync(
    code: str, year: int, quarter: int, method_name: str,
) -> list[dict[str, Any]]:
    """Fetch from baostock (sync, runs in thread)."""
    import baostock as bs

    bs_code = to_baostock_code(code)

    with baostock_lock:
        lg = bs.login()
        if lg.error_code != "0":
            raise NoDataAvailableError(f"baostock login failed: {lg.error_msg}")
        try:
            fn = getattr(bs, method_name)
            rs = fn(code=bs_code, year=year, quarter=quarter)
            rows = []
            while rs.error_code == "0" and rs.next():
                row_dict = dict(zip(rs.fields, rs.get_row_data()))
                rows.append(row_dict)
        finally:
            bs.logout()

    if not rows:
        raise NoDataAvailableError(
            f"baostock: no data for {code} {year}Q{quarter}"
        )
    return rows


def _sina_statements_sync(
    code: str, year: int, quarter: int, report_type: str,
) -> list[dict[str, Any]]:
    """Fallback: fetch from sina finance, filter by year/quarter (sync, runs in thread)."""
    _SINA_TYPE_MAP = {"balance": "fzb", "income": "lrb", "cashflow": "llb"}
    sina_type = _SINA_TYPE_MAP.get(report_type, "lrb")
    paper_code = to_tencent_code(code)

    url = "https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022"
    params = {
        "paperCode": paper_code,
        "source": sina_type,
        "type": "0",
        "page": "1",
        "num": "20",
    }
    try:
        r = requests.get(url, params=params, headers={"User-Agent": _UA}, timeout=(5, 15))
        r.raise_for_status()
    except requests.RequestException as exc:
        raise NoDataAvailableError(f"sina: request failed for {code}: {exc}") from exc
    try:
        d = r.json()
    except requests.JSONDecodeError as exc:
        raise NoDataAvailableError(f"sina: invalid JSON for {code}") from exc

    result = d.get("result", {}).get("data", {})
    items = result.get(sina_type, [])
    if not isinstance(items, list) or not items:
        raise NoDataAvailableError(f"sina: no {report_type} data for {code}")

    q_end = f"{year}-{quarter * 3:02}-30"
    matched = [
        item for item in items
        if any(
            str(item.get(k, "")).startswith(q_end[:7])
            for k in ("报告日", "报告期", "reportDate")
        )
    ]
    if not matched:
        raise NoDataAvailableError(
            f"sina: no {report_type} data for {code} {year}Q{quarter}"
        )
    return matched


# ---------------------------------------------------------------------------
# F10
# ---------------------------------------------------------------------------

async def get_f10(code: str, category: str = "all") -> dict[str, Any]:
    """F10 company data from mootdx (9 categories)."""
    code = normalize_code(code)
    cache_key = f"f10:{code}:{category}"
    cached = cache_f10.get(cache_key)
    if cached is not None:
        return cached

    result = await asyncio.to_thread(_mootdx_f10_sync, code, category)
    cache_f10.set(cache_key, result)
    return result


def _mootdx_f10_sync(code: str, category: str) -> dict[str, Any]:
    """Fetch F10 data from mootdx (sync, runs in thread)."""
    client = get_mootdx_client()
    symbol = to_mootdx_code(code)

    categories = [
        "最新提示", "公司概况", "财务分析",
        "股东研究", "股本结构", "资本运作",
        "业内点评", "行业分析", "公司大事",
    ]

    if category != "all" and category in categories:
        categories = [category]

    result: dict[str, Any] = {}
    for cat in categories:
        text = client.F10(symbol=symbol, name=cat)
        result[cat] = text or ""

    if not any(result.values()):
        raise NoDataAvailableError(f"mootdx F10: no data for {code}")
    return result


# ---------------------------------------------------------------------------
# Industry classification
# ---------------------------------------------------------------------------

async def get_industry(code: str) -> dict[str, str]:
    """Shenwan industry classification from baostock."""
    code = normalize_code(code)
    cache_key = f"industry:{code}"
    cached = cache_industry.get(cache_key)
    if cached is not None:
        return cached

    result = await asyncio.to_thread(_baostock_industry_sync, code)
    cache_industry.set(cache_key, result)
    return result


def _baostock_industry_sync(code: str) -> dict[str, str]:
    """Fetch industry from baostock (sync, runs in thread)."""
    import baostock as bs

    bs_code = to_baostock_code(code)

    with baostock_lock:
        lg = bs.login()
        if lg.error_code != "0":
            raise NoDataAvailableError(f"baostock login failed: {lg.error_msg}")
        fields = None
        rows = []
        try:
            rs = bs.query_stock_industry(code=bs_code)
            fields = rs.fields
            while rs.error_code == "0" and rs.next():
                rows.append(rs.get_row_data())
        finally:
            bs.logout()

    if not rows:
        raise NoDataAvailableError(f"baostock: no industry for {code}")

    row_dict = dict(zip(fields, rows[0]))
    return {
        "industry": row_dict.get("industry", ""),
        "classification": row_dict.get("industryClassification", ""),
        "update_date": row_dict.get("updateDate", ""),
    }
