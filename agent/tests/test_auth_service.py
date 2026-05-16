"""Tests for auth service: password hashing, JWT token lifecycle, secret validation."""

import os
import time

import jwt as pyjwt
import pytest


@pytest.fixture(autouse=True)
def _set_jwt_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-key-at-least-32-characters-long")


class TestPasswordHashing:
    def test_verify_correct_password(self):
        from src.auth.service import hash_password, verify_password

        hashed = hash_password("mypassword123")
        assert verify_password("mypassword123", hashed)

    def test_verify_wrong_password(self):
        from src.auth.service import hash_password, verify_password

        hashed = hash_password("mypassword123")
        assert not verify_password("wrongpassword", hashed)

    def test_verify_corrupted_hash_returns_false(self):
        from src.auth.service import verify_password

        # Corrupted/empty hash should not crash, just return False
        assert not verify_password("anypassword", "")
        assert not verify_password("anypassword", "not-a-bcrypt-hash")
        assert not verify_password("anypassword", "$2b$12$invalidhash")

    def test_verify_none_hash_returns_false(self):
        from src.auth.service import verify_password

        with pytest.raises((TypeError, AttributeError)):
            verify_password("anypassword", None)

    def test_different_passwords_different_hashes(self):
        from src.auth.service import hash_password

        h1 = hash_password("password1")
        h2 = hash_password("password2")
        assert h1 != h2

    def test_same_password_different_hashes(self):
        from src.auth.service import hash_password

        h1 = hash_password("samepass")
        h2 = hash_password("samepass")
        assert h1 != h2  # bcrypt salts are random


class TestJWTToken:
    def test_create_and_decode(self):
        from src.auth.service import create_token, decode_token

        token = create_token(42)
        payload = decode_token(token)
        assert payload["sub"] == "42"
        assert "exp" in payload

    def test_expired_token_raises(self):
        from src.auth.service import _get_jwt_secret

        secret = _get_jwt_secret()
        expired = pyjwt.encode({"sub": "1", "exp": int(time.time()) - 10}, secret, algorithm="HS256")

        from src.auth.service import decode_token

        with pytest.raises(pyjwt.ExpiredSignatureError):
            decode_token(expired)

    def test_invalid_signature_raises(self):
        bad_token = pyjwt.encode({"sub": "1", "exp": int(time.time()) + 3600}, "wrong-secret", algorithm="HS256")

        from src.auth.service import decode_token

        with pytest.raises(Exception):
            decode_token(bad_token)


class TestJWTSecretValidation:
    def test_minimum_length_enforced(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", "short")
        from src.auth.service import _get_jwt_secret

        with pytest.raises(RuntimeError, match="at least 32 characters"):
            _get_jwt_secret()

    def test_empty_secret_raises(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", "")
        from src.auth.service import _get_jwt_secret

        with pytest.raises(RuntimeError, match="not set"):
            _get_jwt_secret()

    def test_missing_secret_raises(self, monkeypatch):
        monkeypatch.delenv("JWT_SECRET", raising=False)
        from src.auth.service import _get_jwt_secret

        with pytest.raises(RuntimeError, match="not set"):
            _get_jwt_secret()

    def test_valid_long_secret_accepted(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", "a" * 32)
        from src.auth.service import _get_jwt_secret

        assert len(_get_jwt_secret()) == 32
