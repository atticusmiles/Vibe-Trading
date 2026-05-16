"""E2E test: full auth lifecycle across all settings endpoints and password change."""

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
    return TestClient(app, client=("127.0.0.1", 50000))


def _auth_header(token):
    return {"Authorization": f"Bearer {token}"}


class TestFullAuthLifecycle:
    """Register → login → set preferences → set API keys → set system settings
    → verify all persisted → change password → login with new password → verify data intact."""

    def test_complete_lifecycle(self, client):
        # 1. Register
        res = client.post("/auth/register", json={"username": "e2euser", "password": "OldPass123"})
        assert res.status_code == 201
        user_id = res.json()["id"]

        # 2. Login
        res = client.post("/auth/login", json={"username": "e2euser", "password": "OldPass123"})
        assert res.status_code == 200
        token = res.json()["access_token"]
        headers = _auth_header(token)

        # 3. /auth/me returns correct user
        res = client.get("/auth/me", headers=headers)
        assert res.status_code == 200
        assert res.json()["username"] == "e2euser"

        # 4. Set preferences
        prefs = {
            "investment_style": "量化交易",
            "risk_appetite": "激进型",
            "focus_markets": ["A股", "美股"],
            "focus_industries": ["科技", "消费"],
            "holding_period": "中线",
            "capital_scale": "50~100万",
            "stock_invest_total": 800000,
            "avoid_targets": ["ST股"],
            "custom_notes": "Test E2E lifecycle",
        }
        res = client.put("/api/user/settings/preferences", json=prefs, headers=headers)
        assert res.status_code == 200

        # 5. Set API keys (with encryption)
        api_keys = {
            "llm_provider": {
                "base_url": "https://api.example.com/v1",
                "model": "gpt-4",
                "key": "sk-e2e-secret-key-12345",
            },
            "generation": {
                "temperature": 0.7,
                "timeout_seconds": 120,
                "max_retries": 3,
            },
            "tushare": {"key": "tushare-e2e-token"},
        }
        res = client.put("/api/user/settings/apikeys", json=api_keys, headers=headers)
        assert res.status_code == 200

        # 6. Set system settings (with encrypted app_secret)
        settings = {
            "news_archive_time": "09:00",
            "sentinel_interval": 30,
            "proposal_limits": {"trend": 5, "industry": 8, "stock": 15},
            "feishu": {"app_id": "cli_test", "app_secret": "feishu-secret"},
        }
        res = client.put("/api/user/settings/system", json=settings, headers=headers)
        assert res.status_code == 200

        # 7. Verify all data persisted correctly
        # Preferences
        res = client.get("/api/user/settings/preferences", headers=headers)
        assert res.status_code == 200
        got_prefs = res.json()
        assert got_prefs["investment_style"] == "量化交易"
        assert got_prefs["focus_markets"] == ["A股", "美股"]
        assert got_prefs["stock_invest_total"] == 800000

        # API keys (decrypted)
        res = client.get("/api/user/settings/apikeys", headers=headers)
        assert res.status_code == 200
        got_keys = res.json()
        assert got_keys["llm_provider"]["key"] == "sk-e2e-secret-key-12345"
        assert got_keys["llm_provider"]["base_url"] == "https://api.example.com/v1"
        assert got_keys["generation"]["temperature"] == 0.7
        assert got_keys["tushare"]["key"] == "tushare-e2e-token"

        # System settings (decrypted)
        res = client.get("/api/user/settings/system", headers=headers)
        assert res.status_code == 200
        got_settings = res.json()
        assert got_settings["news_archive_time"] == "09:00"
        assert got_settings["sentinel_interval"] == 30
        assert got_settings["proposal_limits"]["trend"] == 5
        assert got_settings["feishu"]["app_secret"] == "feishu-secret"

        # 8. Change password
        res = client.put(
            "/auth/password",
            json={"old_password": "OldPass123", "new_password": "NewPass456"},
            headers=headers,
        )
        assert res.status_code == 200

        # 9. Login with new password
        res = client.post("/auth/login", json={"username": "e2euser", "password": "NewPass456"})
        assert res.status_code == 200
        new_token = res.json()["access_token"]
        new_headers = _auth_header(new_token)

        # 10. Verify data still intact after password change
        res = client.get("/api/user/settings/preferences", headers=new_headers)
        assert res.status_code == 200
        assert res.json()["investment_style"] == "量化交易"

        res = client.get("/api/user/settings/apikeys", headers=new_headers)
        assert res.status_code == 200
        assert res.json()["llm_provider"]["key"] == "sk-e2e-secret-key-12345"

        res = client.get("/api/user/settings/system", headers=new_headers)
        assert res.status_code == 200
        assert res.json()["feishu"]["app_secret"] == "feishu-secret"

        # 11. Old password should no longer work
        res = client.post("/auth/login", json={"username": "e2euser", "password": "OldPass123"})
        assert res.status_code == 401


class TestEndpointAuthEnforcement:
    """Verify /correlation and /skills require authentication."""

    def test_correlation_requires_auth(self, client):
        res = client.get("/correlation?codes=BTC-USDT,ETH-USDT&days=30")
        assert res.status_code == 401

    def test_skills_requires_auth(self, client):
        res = client.get("/skills")
        assert res.status_code == 401

    def test_correlation_with_auth(self, client):
        client.post("/auth/register", json={"username": "apiuser", "password": "password123"})
        token = client.post("/auth/login", json={"username": "apiuser", "password": "password123"}).json()["access_token"]
        # May fail with 400/500 due to missing data loaders in test, but should NOT be 401
        res = client.get("/correlation?codes=BTC-USDT,ETH-USDT&days=30", headers=_auth_header(token))
        assert res.status_code != 401

    def test_skills_with_auth(self, client):
        client.post("/auth/register", json={"username": "apiuser2", "password": "password123"})
        token = client.post("/auth/login", json={"username": "apiuser2", "password": "password123"}).json()["access_token"]
        res = client.get("/skills", headers=_auth_header(token))
        assert res.status_code == 200


class TestMultipleUsersIsolation:
    """Verify two users have completely separate data stores."""

    def test_cross_user_settings_isolation(self, client):
        # Register two users
        client.post("/auth/register", json={"username": "alice", "password": "password123"})
        client.post("/auth/register", json={"username": "bob", "password": "password123"})

        token_a = client.post("/auth/login", json={"username": "alice", "password": "password123"}).json()["access_token"]
        token_b = client.post("/auth/login", json={"username": "bob", "password": "password123"}).json()["access_token"]

        ha = _auth_header(token_a)
        hb = _auth_header(token_b)

        # Alice sets preferences
        client.put("/api/user/settings/preferences", json={"investment_style": "value", "capital_scale": "100万以上"}, headers=ha)
        client.put("/api/user/settings/apikeys", json={"llm_provider": {"key": "alice-secret-key", "model": "gpt-4"}}, headers=ha)
        client.put("/api/user/settings/system", json={"sentinel_interval": 15, "feishu": {"app_secret": "alice-feishu"}}, headers=ha)

        # Bob sets different preferences
        client.put("/api/user/settings/preferences", json={"investment_style": "成长投资"}, headers=hb)

        # Verify Alice's data is intact and private
        res_a = client.get("/api/user/settings/preferences", headers=ha)
        assert res_a.json()["investment_style"] == "value"
        assert res_a.json()["capital_scale"] == "100万以上"

        res_a_keys = client.get("/api/user/settings/apikeys", headers=ha)
        assert res_a_keys.json()["llm_provider"]["key"] == "alice-secret-key"

        res_a_settings = client.get("/api/user/settings/system", headers=ha)
        assert res_a_settings.json()["sentinel_interval"] == 15
        assert res_a_settings.json()["feishu"]["app_secret"] == "alice-feishu"

        # Verify Bob sees only his own data
        res_b = client.get("/api/user/settings/preferences", headers=hb)
        assert res_b.json()["investment_style"] == "成长投资"
        assert "capital_scale" not in res_b.json()

        res_b_keys = client.get("/api/user/settings/apikeys", headers=hb)
        assert res_b_keys.json() == {}

        res_b_settings = client.get("/api/user/settings/system", headers=hb)
        assert res_b_settings.json() == {}
