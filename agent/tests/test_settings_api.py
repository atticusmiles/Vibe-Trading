"""Regression tests for user settings API endpoints (preferences, system, password)."""

from __future__ import annotations

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


@pytest.fixture
def authed(client):
    """Register + login, return (client, token)."""
    client.post("/auth/register", json={"username": "settingsuser", "password": "password123"})
    res = client.post("/auth/login", json={"username": "settingsuser", "password": "password123"})
    token = res.json()["access_token"]
    return client, token


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


class TestPreferencesEndpoint:
    def test_get_default_empty(self, authed):
        client, token = authed
        res = client.get("/api/user/settings/preferences", headers=_headers(token))
        assert res.status_code == 200
        assert res.json() == {}

    def test_put_and_get(self, authed):
        client, token = authed
        prefs = {"investment_style": "价值投资", "risk_appetite": "稳健型"}
        res = client.put("/api/user/settings/preferences", json=prefs, headers=_headers(token))
        assert res.status_code == 200

        res = client.get("/api/user/settings/preferences", headers=_headers(token))
        assert res.status_code == 200
        assert res.json()["investment_style"] == "价值投资"


class TestSystemSettingsEndpoint:
    def test_get_default_empty(self, authed):
        client, token = authed
        res = client.get("/api/user/settings/system", headers=_headers(token))
        assert res.status_code == 200
        assert res.json() == {}

    def test_put_encrypts_app_secret(self, authed):
        client, token = authed
        settings = {"news_archive_time": "08:00", "feishu": {"app_secret": "my-feishu-secret"}}
        res = client.put("/api/user/settings/system", json=settings, headers=_headers(token))
        assert res.status_code == 200

        res = client.get("/api/user/settings/system", headers=_headers(token))
        assert res.status_code == 200
        data = res.json()
        assert data["news_archive_time"] == "08:00"
        assert data["feishu"]["app_secret"] == "my-feishu-secret"


class TestAuthRequired:
    def test_preferences_requires_auth(self, client):
        res = client.get("/api/user/settings/preferences")
        assert res.status_code in {401, 403}

    def test_system_settings_requires_auth(self, client):
        res = client.get("/api/user/settings/system")
        assert res.status_code in {401, 403}

    def test_remote_client_rejected(self):
        remote = TestClient(app, client=("203.0.113.10", 50000))
        res = remote.get("/api/user/settings/preferences")
        assert res.status_code in {401, 403}
