"""Tests for auth middleware: _is_local_client with ipaddress validation, require_user dependency."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest


class TestIsLocalClient:
    def _make_request(self, client_host: str, forwarded_for: str = "") -> SimpleNamespace:
        return SimpleNamespace(
            client=SimpleNamespace(host=client_host),
            headers={} if not forwarded_for else {"x-forwarded-for": forwarded_for},
        )

    def test_loopback_ipv4(self):
        from src.auth.middleware import _is_local_client

        assert _is_local_client(self._make_request("127.0.0.1"))

    def test_loopback_ipv6(self):
        from src.auth.middleware import _is_local_client

        assert _is_local_client(self._make_request("::1"))

    def test_localhost_string(self):
        from src.auth.middleware import _is_local_client

        assert _is_local_client(self._make_request("localhost"))

    def test_testclient(self):
        from src.auth.middleware import _is_local_client

        assert _is_local_client(self._make_request("testclient"))

    def test_127_subnet(self):
        from src.auth.middleware import _is_local_client

        assert _is_local_client(self._make_request("127.0.0.99"))

    def test_remote_ip_rejected(self):
        from src.auth.middleware import _is_local_client

        assert not _is_local_client(self._make_request("203.0.113.10"))

    def test_docker_bridge_range_accepted(self, monkeypatch):
        monkeypatch.setenv("VIBE_TRADING_TRUST_DOCKER_LOOPBACK", "1")
        from src.auth.middleware import _is_local_client

        req = self._make_request("10.0.0.1", forwarded_for="172.16.0.5")
        assert _is_local_client(req)

    def test_docker_bridge_upper_bound_accepted(self, monkeypatch):
        monkeypatch.setenv("VIBE_TRADING_TRUST_DOCKER_LOOPBACK", "1")
        from src.auth.middleware import _is_local_client

        req = self._make_request("10.0.0.1", forwarded_for="172.31.255.255")
        assert _is_local_client(req)

    def test_172_outside_docker_range_rejected(self, monkeypatch):
        """172.1.x.x and 172.32.x.x should NOT be trusted."""
        monkeypatch.setenv("VIBE_TRADING_TRUST_DOCKER_LOOPBACK", "1")
        from src.auth.middleware import _is_local_client

        req = self._make_request("10.0.0.1", forwarded_for="172.1.0.1")
        assert not _is_local_client(req)

    def test_172_32_rejected(self, monkeypatch):
        monkeypatch.setenv("VIBE_TRADING_TRUST_DOCKER_LOOPBACK", "1")
        from src.auth.middleware import _is_local_client

        req = self._make_request("10.0.0.1", forwarded_for="172.32.0.1")
        assert not _is_local_client(req)

    def test_forwarded_for_loopback(self, monkeypatch):
        monkeypatch.setenv("VIBE_TRADING_TRUST_DOCKER_LOOPBACK", "1")
        from src.auth.middleware import _is_local_client

        req = self._make_request("10.0.0.1", forwarded_for="127.0.0.1")
        assert _is_local_client(req)

    def test_forwarded_for_without_env_var_rejected(self, monkeypatch):
        monkeypatch.delenv("VIBE_TRADING_TRUST_DOCKER_LOOPBACK", raising=False)
        from src.auth.middleware import _is_local_client

        req = self._make_request("10.0.0.1", forwarded_for="172.16.0.5")
        assert not _is_local_client(req)

    def test_malformed_forwarded_for_rejected(self, monkeypatch):
        monkeypatch.setenv("VIBE_TRADING_TRUST_DOCKER_LOOPBACK", "1")
        from src.auth.middleware import _is_local_client

        req = self._make_request("10.0.0.1", forwarded_for="not-an-ip")
        assert not _is_local_client(req)

    def test_forwarded_for_multiple_ips(self, monkeypatch):
        """Should use the first IP in the x-forwarded-for list."""
        monkeypatch.setenv("VIBE_TRADING_TRUST_DOCKER_LOOPBACK", "1")
        from src.auth.middleware import _is_local_client

        req = self._make_request("10.0.0.1", forwarded_for="172.16.0.5, 10.0.0.1")
        assert _is_local_client(req)

    def test_unknown_client_host(self):
        from src.auth.middleware import _is_local_client

        req = SimpleNamespace(client=None, headers={})
        assert not _is_local_client(req)


class TestRequireUser:
    """Test that require_user dependency rejects dev-mode user_id==0."""

    def test_dev_mode_user_id_zero_rejected(self, tmp_path, monkeypatch):
        """Without JWT_SECRET, local client gets user_id=0, which require_user must reject."""
        import os

        import pytest
        from fastapi.testclient import TestClient

        monkeypatch.delenv("JWT_SECRET", raising=False)
        monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
        monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
        from src.core import config

        monkeypatch.setattr(config, "get_data_dir", lambda: tmp_path / "data")

        # Reimport api_server to pick up the env change
        import importlib

        import api_server

        importlib.reload(api_server)
        from src.db import init_db

        init_db()

        client = TestClient(api_server.app, client=("127.0.0.1", 50000))
        # /auth/me uses require_user which should reject user_id==0
        res = client.get("/auth/me")
        assert res.status_code == 401
