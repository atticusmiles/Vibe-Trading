"""Unit tests for research CRUD functions: trends, industries, stocks."""

from __future__ import annotations

import json
import sqlite3
import pytest

from src.db import get_db, init_db
from src.research.trends import create_trend, delete_trend, get_trend, list_trends, update_trend
from src.research.industries import (
    create_industry, delete_industry, get_industry, list_industries, update_industry,
)
from src.research.stocks import create_stock, delete_stock, get_stock, list_stocks, update_stock


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    from src.core import config
    monkeypatch.setattr(config, "get_data_dir", lambda: tmp_path / "data")
    init_db()
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, username, password_hash) VALUES (1, 'test', 'x')"
        )


USER = 1


# ============================================================================
# Trends
# ============================================================================

class TestTrends:
    def test_create_and_get(self):
        r = create_trend(USER, "AI 基础设施轮动", level="long-term", confidence=8, evidence="政策支持")
        assert r["id"] > 0
        assert r["title"] == "AI 基础设施轮动"
        assert r["level"] == "long-term"
        assert r["confidence"] == 8
        assert r["status"] == "adopted"

        got = get_trend(r["id"], USER)
        assert got["title"] == r["title"]

    def test_create_with_status_proposed(self):
        r = create_trend(USER, "测试趋势", status="proposed")
        assert r["status"] == "proposed"

    def test_create_duplicate_title_409(self):
        create_trend(USER, "唯一标题")
        with pytest.raises(Exception):  # HTTPException 409
            create_trend(USER, "唯一标题")

    def test_list_with_status_filter(self):
        create_trend(USER, "趋势A", status="adopted")
        create_trend(USER, "趋势B", status="proposed")
        adopted = list_trends(USER, "adopted")
        proposed = list_trends(USER, "proposed")
        assert len(adopted) == 1
        assert len(proposed) == 1
        assert adopted[0]["title"] == "趋势A"

    def test_update(self):
        r = create_trend(USER, "旧标题", confidence=3)
        updated = update_trend(r["id"], USER, title="新标题", confidence=9)
        assert updated["title"] == "新标题"
        assert updated["confidence"] == 9

    def test_update_status(self):
        r = create_trend(USER, "状态测试", status="proposed")
        updated = update_trend(r["id"], USER, status="adopted")
        assert updated["status"] == "adopted"

    def test_update_no_fields_400(self):
        r = create_trend(USER, "测试")
        with pytest.raises(Exception):
            update_trend(r["id"], USER)

    def test_update_not_found_404(self):
        with pytest.raises(Exception):
            update_trend(9999, USER, title="不存在")

    def test_delete_soft(self):
        r = create_trend(USER, "待删除")
        result = delete_trend(r["id"], USER)
        assert result["status"] == "removed"
        # Should not appear in default list (excludes removed)
        items = list_trends(USER)
        assert not any(i["id"] == r["id"] for i in items)

    def test_delete_not_found(self):
        with pytest.raises(Exception):
            delete_trend(9999, USER)

    def test_get_not_found(self):
        with pytest.raises(Exception):
            get_trend(9999, USER)

    def test_user_isolation(self):
        create_trend(USER, "用户1的趋势")
        with pytest.raises(Exception):
            get_trend(1, 999)  # different user

    def test_shared_conn(self):
        """CRUD functions should work with an external connection."""
        with get_db() as conn:
            r = create_trend(USER, "共享连接", conn=conn)
            assert r["id"] > 0
            got = get_trend(r["id"], USER, conn=conn)
            assert got["title"] == "共享连接"


# ============================================================================
# Industries
# ============================================================================

class TestIndustries:
    def test_create_and_get(self):
        r = create_industry(USER, "半导体", confidence=7, reason="国产替代",
                            recommended_stocks=["600519", "000858"])
        assert r["name"] == "半导体"
        assert r["confidence"] == 7
        assert r["recommended_count"] == 2

    def test_create_with_status_proposed(self):
        r = create_industry(USER, "新能源", status="proposed")
        assert r["status"] == "proposed"

    def test_list(self):
        create_industry(USER, "行业A", status="adopted")
        create_industry(USER, "行业B", status="proposed")
        all_items = list_industries(USER)
        assert len(all_items) == 2

    def test_update(self):
        r = create_industry(USER, "旧行业")
        updated = update_industry(r["id"], USER, name="新行业", confidence=9)
        assert updated["name"] == "新行业"
        assert updated["confidence"] == 9

    def test_update_recommended_stocks(self):
        r = create_industry(USER, "有推荐")
        updated = update_industry(r["id"], USER, recommended_stocks=["SH600000"])
        assert updated["recommended_count"] == 1
        # Verify JSON stored correctly
        raw = json.loads(updated["recommended_stocks"])
        assert raw == ["SH600000"]

    def test_delete(self):
        r = create_industry(USER, "待删除行业")
        result = delete_industry(r["id"], USER)
        assert result["status"] == "removed"

    def test_shared_conn(self):
        with get_db() as conn:
            r = create_industry(USER, "共享连接行业", conn=conn)
            assert r["id"] > 0


# ============================================================================
# Stocks
# ============================================================================

class TestStocks:
    def test_create_and_get(self):
        r = create_stock(USER, "贵州茅台", "600519", confidence=9,
                         industry_name="白酒", target_price=2000.0)
        assert r["name"] == "贵州茅台"
        assert r["code"] == "600519"
        assert r["target_price"] == 2000.0

    def test_create_with_status_proposed(self):
        r = create_stock(USER, "测试股", "000001", status="proposed")
        assert r["status"] == "proposed"

    def test_create_duplicate_code_409(self):
        create_stock(USER, "贵州茅台", "600519")
        with pytest.raises(Exception):
            create_stock(USER, "茅台2", "600519")

    def test_list(self):
        create_stock(USER, "股票A", "SH600000")
        create_stock(USER, "股票B", "SH601318")
        items = list_stocks(USER)
        assert len(items) == 2

    def test_update(self):
        r = create_stock(USER, "旧名字", "000001", confidence=5)
        updated = update_stock(r["id"], USER, name="新名字", confidence=8, advice="加仓")
        assert updated["name"] == "新名字"
        assert updated["confidence"] == 8
        assert updated["advice"] == "加仓"

    def test_delete(self):
        r = create_stock(USER, "待删除", "300001")
        result = delete_stock(r["id"], USER)
        assert result["status"] == "removed"

    def test_get_not_found(self):
        with pytest.raises(Exception):
            get_stock(9999, USER)

    def test_shared_conn(self):
        with get_db() as conn:
            r = create_stock(USER, "共享股", "688001", conn=conn)
            assert r["id"] > 0
