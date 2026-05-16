"""Phase 2 crypto tests: AES-256-GCM encrypt/decrypt, sensitive field detection, ENCRYPTION_KEY validation."""

import pytest


@pytest.fixture(autouse=True)
def _set_encryption_key(monkeypatch):
    monkeypatch.setenv("ENCRYPTION_KEY", "a" * 64)


class TestEncryptDecrypt:
    def test_roundtrip(self):
        from src.crypto import encrypt_value, decrypt_value

        plaintext = "sk-or-v1-secret-api-key-12345"
        encrypted = encrypt_value(plaintext)
        assert encrypted.startswith("enc:")
        assert encrypted != plaintext
        assert decrypt_value(encrypted) == plaintext

    def test_different_nonce_each_time(self):
        from src.crypto import encrypt_value

        encrypted1 = encrypt_value("same-value")
        encrypted2 = encrypt_value("same-value")
        assert encrypted1 != encrypted2

    def test_is_encrypted(self):
        from src.crypto import is_encrypted, encrypt_value

        assert not is_encrypted("plain-text")
        assert is_encrypted(encrypt_value("secret"))


class TestSensitiveFields:
    def test_encrypt_key_field(self):
        from src.crypto import encrypt_sensitive_fields, decrypt_sensitive_fields

        data = {"label": "OpenRouter", "key": "sk-xxx", "base_url": "https://example.com"}
        encrypted = encrypt_sensitive_fields(data)
        assert encrypted["label"] == "OpenRouter"
        assert encrypted["key"].startswith("enc:")
        assert encrypted["base_url"] == "https://example.com"

        decrypted = decrypt_sensitive_fields(encrypted)
        assert decrypted["key"] == "sk-xxx"

    def test_encrypt_secret_field(self):
        from src.crypto import encrypt_sensitive_fields, decrypt_sensitive_fields

        data = {"feishu": {"app_id": "id123", "app_secret": "secret-val"}}
        encrypted = encrypt_sensitive_fields(data)
        assert encrypted["feishu"]["app_id"] == "id123"
        assert encrypted["feishu"]["app_secret"].startswith("enc:")

        decrypted = decrypt_sensitive_fields(encrypted)
        assert decrypted["feishu"]["app_secret"] == "secret-val"

    def test_nested_encrypt(self):
        from src.crypto import encrypt_sensitive_fields, decrypt_sensitive_fields

        data = {
            "llm_provider": {"key": "sk-abc", "model": "gpt-4"},
            "tushare": {"key": "token123"},
        }
        encrypted = encrypt_sensitive_fields(data)
        assert encrypted["llm_provider"]["key"].startswith("enc:")
        assert encrypted["tushare"]["key"].startswith("enc:")
        assert encrypted["llm_provider"]["model"] == "gpt-4"

        decrypted = decrypt_sensitive_fields(encrypted)
        assert decrypted["llm_provider"]["key"] == "sk-abc"
        assert decrypted["tushare"]["key"] == "token123"

    def test_no_encryption_key_raises(self, monkeypatch):
        monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
        from src.crypto.service import encrypt_value

        with pytest.raises(RuntimeError, match="ENCRYPTION_KEY not set"):
            encrypt_value("test")


class TestEncryptionKeyValidation:
    def test_valid_key(self):
        from src.crypto import is_encryption_available

        assert is_encryption_available()

    def test_missing_key(self, monkeypatch):
        monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
        from src.crypto import is_encryption_available

        assert not is_encryption_available()

    def test_wrong_length_key(self, monkeypatch):
        monkeypatch.setenv("ENCRYPTION_KEY", "abc123")
        from src.crypto import is_encryption_available

        assert not is_encryption_available()

    def test_not_hex_key(self, monkeypatch):
        monkeypatch.setenv("ENCRYPTION_KEY", "z" * 64)
        from src.crypto import is_encryption_available

        assert not is_encryption_available()
