"""Phase 2 user config API tests: preferences, api-keys, settings, ENCRYPTION_KEY missing 503."""

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
    from src.core import config
    monkeypatch.setattr(config, "get_data_dir", lambda: tmp_path / "data")
    init_db()
    yield


@pytest.fixture
def client():
    return TestClient(app, client=("127.0.0.1", 50000))


@pytest.fixture
def authed(client):
    """Register + login, return (client, token)."""
    client.post("/auth/register", json={"username": "cfguser", "password": "password123"})
    res = client.post("/auth/login", json={"username": "cfguser", "password": "password123"})
    token = res.json()["access_token"]
    return client, token


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


class TestPreferences:
    def test_get_default_empty(self, authed):
        client, token = authed
        res = client.get("/api/user/preferences", headers=_headers(token))
        assert res.status_code == 200
        assert res.json() == {}

    def test_put_and_get(self, authed):
        client, token = authed
        prefs = {"investment_style": "价值投资", "risk_appetite": "稳健型"}
        res = client.put("/api/user/preferences", json=prefs, headers=_headers(token))
        assert res.status_code == 200

        res = client.get("/api/user/preferences", headers=_headers(token))
        assert res.status_code == 200
        assert res.json()["investment_style"] == "价值投资"


class TestApiKeys:
    def test_get_default_empty(self, authed):
        client, token = authed
        res = client.get("/api/user/api-keys", headers=_headers(token))
        assert res.status_code == 200
        assert res.json() == {}

    def test_put_encrypts_key_and_get_decrypts(self, authed):
        client, token = authed
        keys = {"llm_provider": {"key": "sk-secret-key", "label": "OpenRouter"}}
        res = client.put("/api/user/api-keys", json=keys, headers=_headers(token))
        assert res.status_code == 200

        # GET should return decrypted plaintext
        res = client.get("/api/user/api-keys", headers=_headers(token))
        assert res.status_code == 200
        data = res.json()
        assert data["llm_provider"]["key"] == "sk-secret-key"
        assert data["llm_provider"]["label"] == "OpenRouter"

    def test_put_without_encryption_key_returns_503(self, authed, monkeypatch):
        monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
        client, token = authed
        keys = {"llm_provider": {"key": "sk-secret"}}
        res = client.put("/api/user/api-keys", json=keys, headers=_headers(token))
        assert res.status_code == 503


class TestSettings:
    def test_get_default_empty(self, authed):
        client, token = authed
        res = client.get("/api/user/settings", headers=_headers(token))
        assert res.status_code == 200
        assert res.json() == {}

    def test_put_encrypts_app_secret(self, authed):
        client, token = authed
        settings = {"news_archive_time": "08:00", "feishu": {"app_secret": "my-feishu-secret"}}
        res = client.put("/api/user/settings", json=settings, headers=_headers(token))
        assert res.status_code == 200

        # GET should return decrypted
        res = client.get("/api/user/settings", headers=_headers(token))
        assert res.status_code == 200
        data = res.json()
        assert data["news_archive_time"] == "08:00"
        assert data["feishu"]["app_secret"] == "my-feishu-secret"

    def test_unauthenticated_returns_401(self, client):
        res = client.get("/api/user/preferences")
        assert res.status_code == 401
