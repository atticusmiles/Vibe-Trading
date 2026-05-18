"""Integration tests for datasources layer — verifies actual data retrieval.

All tests require network access. Marked with @pytest.mark.integration.
Run:  pytest agent/tests/test_datasources.py -m integration -v --timeout=60
Skip: pytest -m "not integration"
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest

# ---------------------------------------------------------------------------
# Fixtures: well-known stock codes covering all boards
# ---------------------------------------------------------------------------

SH_MAIN = "600519"   # 贵州茅台 — 上海主板
SZ_MAIN = "000001"   # 平安银行 — 深圳主板
SZ_GEM = "300476"    # 胜宏科技 — 创业板
SH_STAR = "688017"   # 绿的谐波 — 科创板


# Helper to run async tests
def run_async(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ===========================================================================
# market.py — get_kline / get_quote / get_quotes
# ===========================================================================

@pytest.mark.integration
class TestKline:
    def test_daily_kline_mootdx(self):
        from src.datasources.market import get_kline

        bars = run_async(get_kline(SH_MAIN, period="daily", count=10))
        assert len(bars) > 0
        bar = bars[-1]
        assert bar.date
        assert bar.close > 0
        assert bar.high >= bar.low
        assert bar.volume >= 0

    def test_daily_kline_shenzhen(self):
        from src.datasources.market import get_kline

        bars = run_async(get_kline(SZ_MAIN, period="daily", count=5))
        assert len(bars) > 0
        assert bars[-1].close > 0

    def test_weekly_kline(self):
        from src.datasources.market import get_kline

        bars = run_async(get_kline(SH_MAIN, period="weekly", count=5))
        assert len(bars) > 0

    def test_kline_with_date_range(self):
        from src.datasources.market import get_kline

        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        bars = run_async(get_kline(SH_MAIN, period="daily", start_date=start, end_date=end, count=60))
        assert len(bars) > 0


@pytest.mark.integration
class TestQuote:
    def test_single_quote(self):
        from src.datasources.market import get_quote

        q = run_async(get_quote(SH_MAIN))
        d = q.to_dict()
        assert d["price"] > 0 or d["pre_close"] > 0  # may be after hours
        assert "bid1_price" in d

    def test_batch_quotes(self):
        from src.datasources.market import get_quotes

        result = run_async(get_quotes([SH_MAIN, SZ_MAIN]))
        assert len(result) == 2
        for code in (SH_MAIN, SZ_MAIN):
            assert code in result
            assert result[code].to_dict()["price"] >= 0


# ===========================================================================
# valuation.py — get_valuation / get_valuation_history
# ===========================================================================

@pytest.mark.integration
class TestValuation:
    def test_valuation_snapshot(self):
        from src.datasources.valuation import get_valuation

        val = run_async(get_valuation(SH_MAIN))
        d = val.to_dict()
        # PE/PB should be positive for 茅台
        assert d["pe_ttm"] > 0 or d["pb"] > 0

    def test_valuation_history(self):
        from src.datasources.valuation import get_valuation_history

        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
        points = run_async(get_valuation_history(SH_MAIN, start, end))
        assert len(points) > 0
        assert points[0].date >= start
        assert points[-1].date <= end


# ===========================================================================
# fundamental.py — get_financial_snapshot / get_financial_statements / get_f10 / get_industry
# ===========================================================================

@pytest.mark.integration
class TestFundamental:
    def test_financial_snapshot_mootdx(self):
        from src.datasources.fundamental import get_financial_snapshot

        snap = run_async(get_financial_snapshot(SH_MAIN))
        assert "eps" in snap or "raw" in snap
        if snap.get("eps"):
            assert snap["eps"] != 0

    def test_financial_snapshot_gem(self):
        from src.datasources.fundamental import get_financial_snapshot

        snap = run_async(get_financial_snapshot(SZ_GEM))
        assert isinstance(snap, dict)

    def test_financial_statements_income(self):
        from src.datasources.fundamental import get_financial_statements

        year = datetime.now().year - 1
        rows = run_async(get_financial_statements(SH_MAIN, year, 4, "income"))
        assert len(rows) > 0
        assert isinstance(rows[0], dict)

    def test_financial_statements_balance(self):
        from src.datasources.fundamental import get_financial_statements

        year = datetime.now().year - 1
        rows = run_async(get_financial_statements(SH_MAIN, year, 4, "balance"))
        assert len(rows) > 0

    def test_f10(self):
        from src.datasources.fundamental import get_f10

        data = run_async(get_f10(SH_MAIN, category="公司概况"))
        assert "公司概况" in data
        assert len(data["公司概况"]) > 0

    def test_industry(self):
        from src.datasources.fundamental import get_industry

        info = run_async(get_industry(SH_MAIN))
        assert "industry" in info
        assert info["industry"]  # should not be empty


# ===========================================================================
# news.py — get_flash_news / get_stock_news
# ===========================================================================

@pytest.mark.integration
class TestNews:
    def test_flash_news_cls(self):
        from src.datasources.news import get_flash_news

        items = run_async(get_flash_news(limit=10))
        assert len(items) > 0
        assert items[0].title or items[0].content
        assert items[0].time

    def test_stock_news(self):
        from src.datasources.news import get_stock_news

        items = run_async(get_stock_news(SH_MAIN, limit=5))
        assert len(items) > 0
        assert items[0].title


# ===========================================================================
# research.py — get_consensus_eps / get_research_reports
# ===========================================================================

@pytest.mark.integration
class TestResearch:
    def test_consensus_eps(self):
        from src.datasources.research import get_consensus_eps

        result = run_async(get_consensus_eps(SH_MAIN))
        assert "code" in result
        assert result["code"] == SH_MAIN

    def test_research_reports(self):
        from src.datasources.research import get_research_reports

        reports = run_async(get_research_reports(SH_MAIN, limit=5))
        assert len(reports) > 0
        assert reports[0]["title"]
        assert reports[0]["date"]


# ===========================================================================
# base.py — normalize_code / fallback / baostock_session
# ===========================================================================

class TestNormalizeCode:  # unit test, no network needed
    def test_plain_code(self):
        from src.datasources.base import normalize_code

        assert normalize_code("600519") == "600519"

    def test_sh_prefix(self):
        from src.datasources.base import normalize_code

        assert normalize_code("sh600519") == "600519"

    def test_dot_suffix(self):
        from src.datasources.base import normalize_code

        assert normalize_code("600519.SH") == "600519"

    def test_upper_prefix(self):
        from src.datasources.base import normalize_code

        assert normalize_code("SZ000001") == "000001"

    def test_invalid_raises(self):
        from src.datasources.base import normalize_code

        with pytest.raises(ValueError):
            normalize_code("INVALID")


class TestTTLCache:  # unit test
    def test_set_and_get(self):
        from src.datasources.base import TTLCache

        c = TTLCache(default_ttl=60)
        c.set("k", "v")
        assert c.get("k") == "v"

    def test_expired(self):
        from src.datasources.base import TTLCache

        c = TTLCache(default_ttl=0.01)
        c.set("k", "v")
        import time
        time.sleep(0.02)
        assert c.get("k") is None

    def test_clear(self):
        from src.datasources.base import TTLCache

        c = TTLCache()
        c.set("k", "v")
        c.clear()
        assert c.get("k") is None


@pytest.mark.integration
class TestBaostockSession:
    def test_login_logout(self):
        from src.datasources.base import baostock_session

        async def _test():
            async with baostock_session() as bs:
                rs = bs.query_history_k_data_plus(
                    "sh.600519", "date,close",
                    start_date="2025-01-01",
                    end_date="2025-01-10",
                    frequency="d", adjustflag="3",
                )
                rows = []
                while rs.error_code == "0" and rs.next():
                    rows.append(rs.get_row_data())
                return rows

        rows = run_async(_test())
        assert len(rows) > 0


@pytest.mark.integration
class TestFallback:
    def test_primary_succeeds(self):
        from src.datasources.base import fallback

        async def _test():
            return await fallback(lambda: _async_ret(42), label="test")
        assert run_async(_test()) == 42

    def test_fallback_used(self):
        from src.datasources.base import fallback

        async def _test():
            return await fallback(
                primary_fn=lambda: _async_raise("fail"),
                fallback_fn=lambda: _async_ret("ok"),
                label="test",
            )
        assert run_async(_test()) == "ok"

    def test_both_fail(self):
        from src.datasources.base import fallback, NoDataAvailableError

        async def _test():
            return await fallback(
                primary_fn=lambda: _async_raise("p"),
                fallback_fn=lambda: _async_raise("f"),
                label="test",
            )
        with pytest.raises(NoDataAvailableError):
            run_async(_test())


# --- helpers ---

async def _async_ret(val):
    return val

async def _async_raise(msg):
    raise RuntimeError(msg)
