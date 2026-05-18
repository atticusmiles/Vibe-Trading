"""Fundamental data: financial snapshot, statements, F10, industry classification.

Sources:
- get_financial_snapshot: mootdx (primary) → baostock (fallback)
- get_financial_statements: baostock (primary) → sina (fallback)
- get_f10: mootdx only
- get_industry: baostock only
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import requests

from .base import (
    NoDataAvailableError,
    baostock_session,
    fallback,
    get_mootdx_client,
    normalize_code,
    to_baostock_code,
    to_mootdx_code,
)

logger = logging.getLogger(__name__)

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


# ---------------------------------------------------------------------------
# Financial snapshot
# ---------------------------------------------------------------------------

async def get_financial_snapshot(code: str) -> dict[str, Any]:
    """Latest quarterly financial snapshot (37 fields from mootdx or baostock assembly)."""
    code = normalize_code(code)

    async def _primary() -> dict[str, Any]:
        return await _snapshot_mootdx(code)

    async def _fb() -> dict[str, Any]:
        return await _snapshot_baostock(code)

    return await fallback(_primary, _fb, label=f"get_financial_snapshot({code})")


async def _snapshot_mootdx(code: str) -> dict[str, Any]:
    """Fetch 37-field quarterly snapshot via mootdx."""
    client = get_mootdx_client()
    symbol = to_mootdx_code(code)

    df = client.finance(symbol=symbol)
    if df is None or df.empty:
        raise NoDataAvailableError(f"mootdx: no financial snapshot for {code}")

    row = df.iloc[0]
    return {
        "eps": float(row.get("eps", 0) or 0),
        "bvps": float(row.get("bvps", 0) or 0),
        "roe": float(row.get("roe", 0) or 0),
        "net_profit": float(row.get("profit", 0) or 0),
        "revenue": float(row.get("income", 0) or 0),
        "total_shares": float(row.get("zongguben", 0) or 0),
        "float_shares": float(row.get("liutongguben", 0) or 0),
        "per_undistributed": float(row.get("meiguweifeipeili", 0) or 0),
        "per_reserve": float(row.get("meigugongjijin", 0) or 0),
        "per_net_asset": float(row.get("meigujingzichan", 0) or 0),
        "report_date": str(row.name) if hasattr(row, "name") else "",
        "raw": {k: row.get(k) for k in row.index},
    }


async def _snapshot_baostock(code: str) -> dict[str, Any]:
    """Assemble snapshot from baostock profit + balance data."""
    bs_code = to_baostock_code(code)
    today = datetime.now().strftime("%Y-%m-%d")
    year = int(today[:4])
    quarter = (int(today[5:7]) - 1) // 3 + 1
    if quarter > 4:
        quarter = 4

    result: dict[str, Any] = {}

    async with baostock_session() as bs:
        # Profit data
        rs = bs.query_profit_data(code=bs_code, year=year, quarter=quarter)
        profit_rows = []
        while rs.error_code == "0" and rs.next():
            profit_rows.append(rs.get_row_data())
        if profit_rows:
            r = profit_rows[0]
            fields = rs.fields
            row_dict = dict(zip(fields, r))
            result["eps"] = float(row_dict.get("eps", 0) or 0)
            result["roe"] = float(row_dict.get("roeAvg", 0) or 0)
            result["net_profit"] = float(row_dict.get("npParentCompanyOwners", 0) or 0)
            result["revenue"] = float(row_dict.get("totalOperateIncome", 0) or 0)

        # Balance data
        rs2 = bs.query_balance_data(code=bs_code, year=year, quarter=quarter)
        balance_rows = []
        while rs2.error_code == "0" and rs2.next():
            balance_rows.append(rs2.get_row_data())
        if balance_rows:
            r2 = balance_rows[0]
            fields2 = rs2.fields
            row_dict2 = dict(zip(fields2, r2))
            result["bvps"] = float(row_dict2.get("perBps", 0) or 0)
            result["total_shares"] = float(row_dict2.get("totalShare", 0) or 0)
            result["float_shares"] = float(row_dict2.get("liquidShare", 0) or 0)

    if not result:
        raise NoDataAvailableError(f"baostock: no financial snapshot for {code}")
    return result


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

    async def _primary() -> list[dict[str, Any]]:
        return await _statements_baostock(code, year, quarter, report_type)

    async def _fb() -> list[dict[str, Any]]:
        return await _statements_sina(code, year, quarter, report_type)

    return await fallback(_primary, _fb, label=f"get_financial_statements({code},{report_type})")


async def _statements_baostock(
    code: str, year: int, quarter: int, report_type: str,
) -> list[dict[str, Any]]:
    bs_code = to_baostock_code(code)
    method_name = _REPORT_TYPE_BAOSTOCK.get(report_type)
    if not method_name:
        raise ValueError(f"Unknown report_type: {report_type!r}")

    async with baostock_session() as bs:
        fn = getattr(bs, method_name)
        rs = fn(code=bs_code, year=year, quarter=quarter)
        rows = []
        while rs.error_code == "0" and rs.next():
            row_dict = dict(zip(rs.fields, rs.get_row_data()))
            rows.append(row_dict)

    if not rows:
        raise NoDataAvailableError(
            f"baostock: no {report_type} data for {code} {year}Q{quarter}"
        )
    return rows


async def _statements_sina(
    code: str, year: int, quarter: int, report_type: str,
) -> list[dict[str, Any]]:
    """Fallback: fetch from sina finance, filter by year/quarter."""
    _SINA_TYPE_MAP = {"balance": "fzb", "income": "lrb", "cashflow": "llb"}
    sina_type = _SINA_TYPE_MAP.get(report_type, "lrb")
    prefix = "sh" if code.startswith("6") else "sz"
    paper_code = f"{prefix}{code}"

    url = "https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022"
    params = {
        "paperCode": paper_code,
        "source": sina_type,
        "type": "0",
        "page": "1",
        "num": "20",
    }
    r = requests.get(url, params=params, headers={"User-Agent": UA}, timeout=15)
    d = r.json()

    result = d.get("result", {}).get("data", {})
    items = result.get(sina_type, [])
    if not isinstance(items, list) or not items:
        raise NoDataAvailableError(f"sina: no {report_type} data for {code}")

    # Filter by report period: quarter end dates are 0331/0630/0930/1231
    q_end = f"{year}-{quarter * 3:02}-30"
    matched = [
        item for item in items
        if any(
            str(item.get(k, "")).startswith(q_end[:7])
            for k in ("报告日", "报告期", "reportDate")
        )
    ]
    return matched if matched else items[:1]


# ---------------------------------------------------------------------------
# F10
# ---------------------------------------------------------------------------

async def get_f10(code: str, category: str = "all") -> dict[str, Any]:
    """F10 company data from mootdx (9 categories)."""
    code = normalize_code(code)
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
    bs_code = to_baostock_code(code)

    async with baostock_session() as bs:
        rs = bs.query_stock_industry(code=bs_code)
        rows = []
        while rs.error_code == "0" and rs.next():
            rows.append(rs.get_row_data())

    if not rows:
        raise NoDataAvailableError(f"baostock: no industry for {code}")

    fields = rs.fields
    row_dict = dict(zip(fields, rows[0]))
    return {
        "industry": row_dict.get("industry", ""),
        "classification": row_dict.get("industryClassification", ""),
        "update_date": row_dict.get("updateDate", ""),
    }
