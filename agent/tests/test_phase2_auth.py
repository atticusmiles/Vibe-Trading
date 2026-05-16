"""Phase 2 auth tests: register, login, JWT, 409 conflict, 401, data isolation."""

import os
import pytest
from fastapi.testclient import TestClient

# Ensure JWT_SECRET is set before importing api_server
os.environ["JWT_SECRET"] = "test-secret-key-at-least-32-characters-long"
os.environ["ENCRYPTION_KEY"] = "a" * 64  # 32 bytes hex

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


def _register(client, username="testuser", password="password123"):
    return client.post("/auth/register", json={"username": username, "password": password})


def _login(client, username="testuser", password="password123"):
    return client.post("/auth/login", json={"username": username, "password": password})


class TestRegister:
    def test_register_success(self, client):
        res = _register(client)
        assert res.status_code == 201
        data = res.json()
        assert data["username"] == "testuser"
        assert "id" in data
        assert "created_at" in data

    def test_register_duplicate_username_409(self, client):
        _register(client)
        res = _register(client)
        assert res.status_code == 409
        assert "already exists" in res.json()["detail"]

    def test_register_short_username(self, client):
        res = client.post("/auth/register", json={"username": "ab", "password": "password123"})
        assert res.status_code == 422

    def test_register_short_password(self, client):
        res = client.post("/auth/register", json={"username": "testuser", "password": "short"})
        assert res.status_code == 422


class TestLogin:
    def test_login_success(self, client):
        _register(client)
        res = _login(client)
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == 86400

    def test_login_wrong_password(self, client):
        _register(client)
        res = _login(client, password="wrongpassword")
        assert res.status_code == 401

    def test_login_nonexistent_user(self, client):
        res = _login(client, username="nobody")
        assert res.status_code == 401


class TestAuthMe:
    def test_me_success(self, client):
        _register(client)
        token = _login(client).json()["access_token"]
        res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        data = res.json()
        assert data["username"] == "testuser"
        assert "preferences" in data

    def test_me_no_token(self, client):
        res = client.get("/auth/me")
        assert res.status_code == 401


class TestChangePassword:
    def test_change_password_success(self, client):
        _register(client)
        token = _login(client).json()["access_token"]
        res = client.put(
            "/auth/password",
            json={"old_password": "password123", "new_password": "newpassword456"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200

        # Login with new password
        login_res = _login(client, password="newpassword456")
        assert login_res.status_code == 200

    def test_change_password_wrong_old(self, client):
        _register(client)
        token = _login(client).json()["access_token"]
        res = client.put(
            "/auth/password",
            json={"old_password": "wrongpassword", "new_password": "newpassword456"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 400


class TestDataIsolation:
    def test_users_cannot_see_others_data(self, client):
        _register(client, "userA", "password123")
        _register(client, "userB", "password123")

        token_a = _login(client, "userA", "password123").json()["access_token"]
        token_b = _login(client, "userB", "password123").json()["access_token"]

        # User A sets preferences
        res = client.put(
            "/api/user/preferences",
            json={"investment_style": "value"},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert res.status_code == 200

        # User B should see empty preferences
        res = client.get("/api/user/preferences", headers={"Authorization": f"Bearer {token_b}"})
        assert res.status_code == 200
        assert res.json() == {}

        # User A should see their preferences
        res = client.get("/api/user/preferences", headers={"Authorization": f"Bearer {token_a}"})
        assert res.status_code == 200
        assert res.json()["investment_style"] == "value"
