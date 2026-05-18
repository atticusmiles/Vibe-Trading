"""E2E tests: full research API lifecycle via TestClient.

Covers: auth → trends/industries/stocks CRUD → proposals create/adopt/reject/cancel
→ dashboard → cooldown → user isolation.
"""

import json
import os

import pytest
from fastapi.testclient import TestClient

os.environ["JWT_SECRET"] = "test-secret-key-at-least-32-characters-long"
os.environ["ENCRYPTION_KEY"] = "a" * 64

import api_server
from src.db import init_db

app = api_server.app


@pytest.fixture(autouse=True)
def _setup_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("JWT_SECRET", "test-secret-key-at-least-32-characters-long")
    monkeypatch.setenv("ENCRYPTION_KEY", "a" * 64)
    from src.core import config
    monkeypatch.setattr(config, "get_data_dir", lambda: tmp_path / "data")
    init_db()
    yield


@pytest.fixture
def client():
    return TestClient(app, client=("127.0.0.1", 50001))


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _register_and_login(client, username="testuser", password="Test1234"):
    client.post("/auth/register", json={"username": username, "password": password})
    res = client.post("/auth/login", json={"username": username, "password": password})
    return res.json()["access_token"]


# ============================================================================
# Trends CRUD
# ============================================================================

class TestTrendsAPI:
    def test_create_and_list(self, client):
        token = _register_and_login(client)
        h = _auth(token)

        res = client.post("/api/trends", json={"title": "AI 轮动"}, headers=h)
        assert res.status_code == 201
        assert res.json()["title"] == "AI 轮动"
        assert res.json()["status"] == "adopted"

        res = client.get("/api/trends", headers=h)
        assert res.status_code == 200
        assert len(res.json()) == 1
        assert res.json()[0]["title"] == "AI 轮动"

    def test_create_with_fields(self, client):
        token = _register_and_login(client)
        h = _auth(token)

        res = client.post("/api/trends", json={
            "title": "新能源", "level": "long-term", "confidence": 8, "evidence": "政策",
        }, headers=h)
        assert res.status_code == 201
        body = res.json()
        assert body["level"] == "long-term"
        assert body["confidence"] == 8

    def test_update(self, client):
        token = _register_and_login(client)
        h = _auth(token)

        r = client.post("/api/trends", json={"title": "旧"}, headers=h)
        tid = r.json()["id"]

        res = client.put(f"/api/trends/{tid}", json={"title": "新", "confidence": 9}, headers=h)
        assert res.status_code == 200
        assert res.json()["title"] == "新"
        assert res.json()["confidence"] == 9

    def test_delete(self, client):
        token = _register_and_login(client)
        h = _auth(token)

        r = client.post("/api/trends", json={"title": "删除测试"}, headers=h)
        tid = r.json()["id"]

        res = client.delete(f"/api/trends/{tid}", headers=h)
        assert res.status_code == 200
        assert res.json()["status"] == "removed"

        items = client.get("/api/trends", headers=h).json()
        assert not any(t["id"] == tid for t in items)

    def test_status_filter(self, client):
        token = _register_and_login(client)
        h = _auth(token)

        client.post("/api/trends", json={"title": "已采纳"}, headers=h)
        r = client.post("/api/trends", json={"title": "待审"}, headers=h)
        tid = r.json()["id"]
        client.put(f"/api/trends/{tid}", json={"status": "proposed"}, headers=h)

        adopted = client.get("/api/trends?status=adopted", headers=h).json()
        proposed = client.get("/api/trends?status=proposed", headers=h).json()
        assert len(adopted) == 1
        assert len(proposed) == 1

    def test_duplicate_title_409(self, client):
        token = _register_and_login(client)
        h = _auth(token)
        client.post("/api/trends", json={"title": "唯一"}, headers=h)
        res = client.post("/api/trends", json={"title": "唯一"}, headers=h)
        assert res.status_code == 409

    def test_not_found_404(self, client):
        token = _register_and_login(client)
        h = _auth(token)
        res = client.get("/api/trends/9999", headers=h)
        assert res.status_code == 404


# ============================================================================
# Industries CRUD
# ============================================================================

class TestIndustriesAPI:
    def test_create_and_get(self, client):
        token = _register_and_login(client)
        h = _auth(token)

        res = client.post("/api/industries", json={
            "name": "半导体", "confidence": 7, "recommended_stocks": ["600519", "000858"],
        }, headers=h)
        assert res.status_code == 201
        body = res.json()
        assert body["name"] == "半导体"
        assert body["recommended_count"] == 2

        got = client.get(f"/api/industries/{body['id']}", headers=h)
        assert got.status_code == 200
        assert got.json()["name"] == "半导体"

    def test_update_recommended_stocks(self, client):
        token = _register_and_login(client)
        h = _auth(token)

        r = client.post("/api/industries", json={"name": "新能源"}, headers=h)
        iid = r.json()["id"]

        res = client.put(f"/api/industries/{iid}", json={
            "recommended_stocks": ["SH600000"],
        }, headers=h)
        assert res.status_code == 200
        assert res.json()["recommended_count"] == 1
        assert json.loads(res.json()["recommended_stocks"]) == ["SH600000"]

    def test_delete(self, client):
        token = _register_and_login(client)
        h = _auth(token)

        r = client.post("/api/industries", json={"name": "待删"}, headers=h)
        res = client.delete(f"/api/industries/{r.json()['id']}", headers=h)
        assert res.status_code == 200
        assert res.json()["status"] == "removed"


# ============================================================================
# Stocks CRUD
# ============================================================================

class TestStocksAPI:
    def test_create_and_get(self, client):
        token = _register_and_login(client)
        h = _auth(token)

        res = client.post("/api/stocks", json={
            "name": "贵州茅台", "code": "600519", "confidence": 9,
            "industry_name": "白酒", "target_price": 2000.0,
        }, headers=h)
        assert res.status_code == 201
        body = res.json()
        assert body["code"] == "600519"
        assert body["target_price"] == 2000.0

    def test_duplicate_code_409(self, client):
        token = _register_and_login(client)
        h = _auth(token)
        client.post("/api/stocks", json={"name": "茅台", "code": "600519"}, headers=h)
        res = client.post("/api/stocks", json={"name": "茅台2", "code": "600519"}, headers=h)
        assert res.status_code == 409

    def test_update_advice(self, client):
        token = _register_and_login(client)
        h = _auth(token)

        r = client.post("/api/stocks", json={"name": "测试", "code": "000001"}, headers=h)
        sid = r.json()["id"]

        res = client.put(f"/api/stocks/{sid}", json={"advice": "加仓", "confidence": 8}, headers=h)
        assert res.status_code == 200
        assert res.json()["advice"] == "加仓"
        assert res.json()["confidence"] == 8

    def test_delete(self, client):
        token = _register_and_login(client)
        h = _auth(token)

        r = client.post("/api/stocks", json={"name": "删除股", "code": "300001"}, headers=h)
        res = client.delete(f"/api/stocks/{r.json()['id']}", headers=h)
        assert res.status_code == 200
        assert res.json()["status"] == "removed"


# ============================================================================
# Proposals lifecycle
# ============================================================================

class TestProposalsAPI:
    def test_create_proposal_trend(self, client):
        token = _register_and_login(client)
        h = _auth(token)

        res = client.post("/api/proposals", json={
            "target_type": "trend",
            "action": "create",
            "title": "新趋势提案",
            "confidence": 7,
            "payload": json.dumps({"title": "AI 算力", "level": "short-term"}),
        }, headers=h)
        assert res.status_code == 201
        body = res.json()
        assert body["status"] == "pending"
        assert body["target_type"] == "trend"
        assert body["action"] == "create"
        assert body["target_id"] > 0

    def test_create_proposal_industry(self, client):
        token = _register_and_login(client)
        h = _auth(token)

        res = client.post("/api/proposals", json={
            "target_type": "industry",
            "action": "create",
            "title": "新行业提案",
            "confidence": 6,
            "payload": json.dumps({"name": "量子计算"}),
        }, headers=h)
        assert res.status_code == 201
        assert res.json()["status"] == "pending"

    def test_create_proposal_stock(self, client):
        token = _register_and_login(client)
        h = _auth(token)

        res = client.post("/api/proposals", json={
            "target_type": "stock",
            "action": "create",
            "title": "新股票提案",
            "confidence": 8,
            "payload": json.dumps({"name": "宁德时代", "code": "300750"}),
        }, headers=h)
        assert res.status_code == 201
        assert res.json()["status"] == "pending"

    def test_adopt_create_proposal(self, client):
        token = _register_and_login(client)
        h = _auth(token)

        # Create a proposal
        r = client.post("/api/proposals", json={
            "target_type": "trend", "action": "create",
            "title": "采纳测试", "confidence": 7,
            "payload": json.dumps({"title": "采纳趋势"}),
        }, headers=h)
        pid = r.json()["id"]
        target_id = r.json()["target_id"]

        # Adopt it
        res = client.post(f"/api/proposals/{pid}/adopt", headers=h)
        assert res.status_code == 200
        assert res.json()["status"] == "adopted"

        # Verify the trend is now adopted
        trend = client.get(f"/api/trends/{target_id}", headers=h)
        assert trend.json()["status"] == "adopted"

    def test_reject_create_proposal(self, client):
        token = _register_and_login(client)
        h = _auth(token)

        r = client.post("/api/proposals", json={
            "target_type": "trend", "action": "create",
            "title": "否决测试", "confidence": 3,
            "payload": json.dumps({"title": "否决趋势"}),
        }, headers=h)
        pid = r.json()["id"]
        target_id = r.json()["target_id"]

        res = client.post(f"/api/proposals/{pid}/reject", headers=h)
        assert res.status_code == 200
        assert res.json()["status"] == "rejected"

        trend = client.get(f"/api/trends/{target_id}", headers=h)
        assert trend.json()["status"] == "rejected"

    def test_cancel_create_proposal(self, client):
        token = _register_and_login(client)
        h = _auth(token)

        r = client.post("/api/proposals", json={
            "target_type": "trend", "action": "create",
            "title": "取消测试", "confidence": 5,
            "payload": json.dumps({"title": "取消趋势"}),
        }, headers=h)
        pid = r.json()["id"]

        res = client.post(f"/api/proposals/{pid}/cancel", headers=h)
        assert res.status_code == 200
        assert res.json()["status"] == "cancelled"

    def test_update_proposal_lifecycle(self, client):
        token = _register_and_login(client)
        h = _auth(token)

        # Create an adopted trend first
        r = client.post("/api/trends", json={"title": "已有趋势", "confidence": 5}, headers=h)
        tid = r.json()["id"]

        # Propose an update
        r = client.post("/api/proposals", json={
            "target_type": "trend", "action": "update",
            "target_id": tid, "title": "更新提案",
            "confidence": 8,
            "payload": json.dumps({"confidence": 9, "evidence": "新证据"}),
        }, headers=h)
        assert r.status_code == 201
        pid = r.json()["id"]
        assert r.json()["original_payload"] is not None

        # Adopt
        res = client.post(f"/api/proposals/{pid}/adopt", headers=h)
        assert res.status_code == 200

        trend = client.get(f"/api/trends/{tid}", headers=h)
        assert trend.json()["confidence"] == 9
        assert trend.json()["evidence"] == "新证据"

    def test_delete_proposal_lifecycle(self, client):
        token = _register_and_login(client)
        h = _auth(token)

        # Create an adopted stock
        r = client.post("/api/stocks", json={"name": "测试股", "code": "000002"}, headers=h)
        sid = r.json()["id"]

        # Propose deletion
        r = client.post("/api/proposals", json={
            "target_type": "stock", "action": "delete",
            "target_id": sid, "title": "删除提案",
            "confidence": 6, "payload": "{}",
        }, headers=h)
        assert r.status_code == 201
        pid = r.json()["id"]

        # Adopt → stock should be removed
        res = client.post(f"/api/proposals/{pid}/adopt", headers=h)
        assert res.status_code == 200

        stock = client.get(f"/api/stocks/{sid}", headers=h)
        assert stock.json()["status"] == "removed"  # soft-deleted

    def test_list_proposals_with_filters(self, client):
        token = _register_and_login(client)
        h = _auth(token)

        client.post("/api/proposals", json={
            "target_type": "trend", "action": "create",
            "title": "提案A", "confidence": 5,
            "payload": json.dumps({"title": "列表A"}),
        }, headers=h)
        client.post("/api/proposals", json={
            "target_type": "stock", "action": "create",
            "title": "提案B", "confidence": 7,
            "payload": json.dumps({"name": "列表股", "code": "600001"}),
        }, headers=h)

        # Filter by type
        res = client.get("/api/proposals?type=trend", headers=h)
        assert res.status_code == 200
        assert res.json()["total"] == 1

        # Filter by status
        res = client.get("/api/proposals?status=pending", headers=h)
        assert res.json()["total"] == 2

        # All
        res = client.get("/api/proposals", headers=h)
        assert res.json()["total"] == 2

    def test_get_proposal_by_id(self, client):
        token = _register_and_login(client)
        h = _auth(token)

        r = client.post("/api/proposals", json={
            "target_type": "trend", "action": "create",
            "title": "单条查询", "confidence": 5,
            "payload": json.dumps({"title": "查询趋势"}),
        }, headers=h)
        pid = r.json()["id"]

        res = client.get(f"/api/proposals/{pid}", headers=h)
        assert res.status_code == 200
        assert res.json()["title"] == "单条查询"

    def test_double_adopt_409(self, client):
        token = _register_and_login(client)
        h = _auth(token)

        r = client.post("/api/proposals", json={
            "target_type": "trend", "action": "create",
            "title": "重复采纳", "confidence": 5,
            "payload": json.dumps({"title": "双采纳"}),
        }, headers=h)
        pid = r.json()["id"]

        client.post(f"/api/proposals/{pid}/adopt", headers=h)
        res = client.post(f"/api/proposals/{pid}/adopt", headers=h)
        assert res.status_code == 409

    def test_invalid_payload_400(self, client):
        token = _register_and_login(client)
        h = _auth(token)

        res = client.post("/api/proposals", json={
            "target_type": "trend", "action": "create",
            "title": "坏JSON", "confidence": 5,
            "payload": "not-json{{",
        }, headers=h)
        assert res.status_code == 400

    def test_update_without_target_id_400(self, client):
        token = _register_and_login(client)
        h = _auth(token)

        res = client.post("/api/proposals", json={
            "target_type": "trend", "action": "update",
            "title": "无目标", "confidence": 5,
            "payload": json.dumps({"title": "无目标更新"}),
        }, headers=h)
        assert res.status_code == 400

    def test_empty_payload_400(self, client):
        token = _register_and_login(client)
        h = _auth(token)

        res = client.post("/api/proposals", json={
            "target_type": "trend", "action": "create",
            "title": "空载荷", "confidence": 5,
            "payload": json.dumps({"id": 99, "user_id": 1}),
        }, headers=h)
        assert res.status_code == 400


# ============================================================================
# Confidence-based eviction (E2E)
# ============================================================================

class TestProposalEvictionE2E:
    def test_higher_confidence_replaces_pending(self, client):
        token = _register_and_login(client)
        h = _auth(token)

        # Create a trend + low-confidence update proposal
        r = client.post("/api/trends", json={"title": "驱逐测试", "confidence": 5}, headers=h)
        tid = r.json()["id"]

        r1 = client.post("/api/proposals", json={
            "target_type": "trend", "action": "update",
            "target_id": tid, "title": "低置信",
            "confidence": 3, "payload": json.dumps({"confidence": 3}),
        }, headers=h)
        assert r1.status_code == 201

        # Higher confidence should auto-evict the old one
        r2 = client.post("/api/proposals", json={
            "target_type": "trend", "action": "update",
            "target_id": tid, "title": "高置信",
            "confidence": 8, "payload": json.dumps({"confidence": 9}),
        }, headers=h)
        assert r2.status_code == 201

        # Old proposal should be rejected
        old = client.get(f"/api/proposals/{r1.json()['id']}", headers=h)
        assert old.json()["status"] == "rejected"

    def test_lower_confidence_409(self, client):
        token = _register_and_login(client)
        h = _auth(token)

        r = client.post("/api/trends", json={"title": "冲突测试", "confidence": 5}, headers=h)
        tid = r.json()["id"]

        client.post("/api/proposals", json={
            "target_type": "trend", "action": "update",
            "target_id": tid, "title": "高置信",
            "confidence": 9, "payload": json.dumps({"confidence": 9}),
        }, headers=h)

        res = client.post("/api/proposals", json={
            "target_type": "trend", "action": "update",
            "target_id": tid, "title": "低置信",
            "confidence": 3, "payload": json.dumps({"confidence": 3}),
        }, headers=h)
        assert res.status_code == 409


# ============================================================================
# Dashboard
# ============================================================================

class TestDashboardAPI:
    def test_empty_dashboard(self, client):
        token = _register_and_login(client)
        h = _auth(token)

        res = client.get("/api/dashboard", headers=h)
        assert res.status_code == 200
        body = res.json()
        assert body["stats"]["trends"] == {}
        assert body["recently_updated"] == []
        assert body["pending_proposals"] == {}

    def test_dashboard_with_data(self, client):
        token = _register_and_login(client)
        h = _auth(token)

        client.post("/api/trends", json={"title": "仪表盘趋势"}, headers=h)
        client.post("/api/industries", json={"name": "仪表盘行业"}, headers=h)

        res = client.get("/api/dashboard", headers=h)
        assert res.status_code == 200
        body = res.json()
        assert body["stats"]["trends"].get("adopted") == 1
        assert body["stats"]["industries"].get("adopted") == 1

        # Create a pending proposal
        client.post("/api/proposals", json={
            "target_type": "stock", "action": "create",
            "title": "仪表盘提案", "confidence": 5,
            "payload": json.dumps({"name": "测试", "code": "000003"}),
        }, headers=h)

        res = client.get("/api/dashboard", headers=h)
        assert res.json()["pending_proposals"].get("stock") == 1


# ============================================================================
# Auth enforcement
# ============================================================================

class TestResearchAuthEnforcement:
    def test_trends_require_auth(self, client):
        assert client.get("/api/trends").status_code == 401
        assert client.post("/api/trends", json={"title": "x"}).status_code == 401

    def test_proposals_require_auth(self, client):
        assert client.get("/api/proposals").status_code == 401

    def test_dashboard_requires_auth(self, client):
        assert client.get("/api/dashboard").status_code == 401


# ============================================================================
# User isolation
# ============================================================================

class TestResearchUserIsolation:
    def test_trends_isolation(self, client):
        t1 = _register_and_login(client, "iso_user_a")
        t2 = _register_and_login(client, "iso_user_b")
        h1, h2 = _auth(t1), _auth(t2)

        client.post("/api/trends", json={"title": "A的趋势"}, headers=h1)
        client.post("/api/trends", json={"title": "B的趋势"}, headers=h2)

        a_trends = client.get("/api/trends", headers=h1).json()
        b_trends = client.get("/api/trends", headers=h2).json()
        assert len(a_trends) == 1
        assert a_trends[0]["title"] == "A的趋势"
        assert len(b_trends) == 1
        assert b_trends[0]["title"] == "B的趋势"

    def test_proposals_isolation(self, client):
        t1 = _register_and_login(client, "iso_pa")
        t2 = _register_and_login(client, "iso_pb")
        h1, h2 = _auth(t1), _auth(t2)

        client.post("/api/proposals", json={
            "target_type": "trend", "action": "create",
            "title": "PA的提案", "confidence": 5,
            "payload": json.dumps({"title": "隔离趋势"}),
        }, headers=h1)

        a_props = client.get("/api/proposals", headers=h1).json()
        b_props = client.get("/api/proposals", headers=h2).json()
        assert a_props["total"] == 1
        assert b_props["total"] == 0

    def test_cannot_adopt_others_proposal(self, client):
        t1 = _register_and_login(client, "iso_adopt_a")
        t2 = _register_and_login(client, "iso_adopt_b")
        h1, h2 = _auth(t1), _auth(t2)

        r = client.post("/api/proposals", json={
            "target_type": "trend", "action": "create",
            "title": "别人的提案", "confidence": 5,
            "payload": json.dumps({"title": "隔离采纳"}),
        }, headers=h1)
        pid = r.json()["id"]

        res = client.post(f"/api/proposals/{pid}/adopt", headers=h2)
        assert res.status_code == 404
