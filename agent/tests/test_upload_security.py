"""Security regression tests for upload file type restrictions."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

os.environ["JWT_SECRET"] = "test-secret-key-at-least-32-characters-long"

import api_server


@pytest.fixture(autouse=True)
def _setup_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("JWT_SECRET", "test-secret-key-at-least-32-characters-long")
    from src.core import config
    monkeypatch.setattr(config, "get_data_dir", lambda: tmp_path / "data")
    from src.db import init_db
    init_db()
    yield


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(api_server, "UPLOADS_DIR", tmp_path)
    tc = TestClient(api_server.app, client=("127.0.0.1", 50000))
    # Register + login to get JWT
    tc.post("/auth/register", json={"username": "uploadsecuser", "password": "password123"})
    res = tc.post("/auth/login", json={"username": "uploadsecuser", "password": "password123"})
    tc._upload_token = res.json()["access_token"]
    return tc


def _auth(client: TestClient) -> dict:
    return {"Authorization": f"Bearer {client._upload_token}"}


@pytest.mark.parametrize(
    "filename",
    [
        "payload.py",
        "run.sh",
        "config.yaml",
        "config.yml",
        "template.j2",
        "Dockerfile",
    ],
)
def test_upload_blocks_executable_adjacent_files(
    client: TestClient,
    tmp_path: Path,
    filename: str,
) -> None:
    response = client.post(
        "/upload",
        files={"file": (filename, b"content", "application/octet-stream")},
        headers=_auth(client),
    )

    assert response.status_code == 400
    assert not any(p.is_file() for p in tmp_path.iterdir())
