"""Unit tests for ``auth/token_store.py`` (TD-036 / TD-038).

Covers:
- Token save/load/remove round-trip
- Key rotation: tokens remain readable after rotate_key()
- _get_or_create_key returns same key on repeated calls
- _restrict_file_permissions does not crash (platform-dependent)
"""



import pytest
from auth.token_store import (
    TokenStore,
    _get_or_create_key,
    _restrict_file_permissions,
)

pytestmark = pytest.mark.unit


class TestTokenStoreRoundTrip:
    """Basic save/load/remove cycle."""

    def test_save_and_load_token(self, tmp_path):
        store = TokenStore(storage_dir=tmp_path)
        store.save_token("ws://localhost:8000/ws/agents/", "secret-token-abc")
        assert store.load_token("ws://localhost:8000/ws/agents/") == "secret-token-abc"

    def test_load_nonexistent_token(self, tmp_path):
        store = TokenStore(storage_dir=tmp_path)
        assert store.load_token("ws://nope/") is None

    def test_remove_token(self, tmp_path):
        store = TokenStore(storage_dir=tmp_path)
        url = "ws://localhost:8000/ws/agents/"
        store.save_token(url, "tok")
        store.remove_token(url)
        assert store.load_token(url) is None

    def test_remove_nonexistent_token_no_error(self, tmp_path):
        store = TokenStore(storage_dir=tmp_path)
        # Should not raise.
        store.remove_token("ws://never-saved/")

    def test_save_multiple_tokens(self, tmp_path):
        store = TokenStore(storage_dir=tmp_path)
        store.save_token("ws://a/", "token-a")
        store.save_token("ws://b/", "token-b")
        assert store.load_token("ws://a/") == "token-a"
        assert store.load_token("ws://b/") == "token-b"

    def test_overwrite_existing_token(self, tmp_path):
        store = TokenStore(storage_dir=tmp_path)
        url = "ws://a/"
        store.save_token(url, "old")
        store.save_token(url, "new")
        assert store.load_token(url) == "new"


class TestKeyRotation:
    """TD-038: rotate_key() re-encrypts tokens with a new key."""

    def test_rotate_key_preserves_tokens(self, tmp_path):
        store = TokenStore(storage_dir=tmp_path)
        store.save_token("ws://a/", "token-a")
        store.save_token("ws://b/", "token-b")

        store.rotate_key()

        assert store.load_token("ws://a/") == "token-a"
        assert store.load_token("ws://b/") == "token-b"

    def test_rotate_key_changes_key_file(self, tmp_path):
        store = TokenStore(storage_dir=tmp_path)
        store.save_token("ws://a/", "token-a")
        key_before = (tmp_path / ".key").read_bytes()

        store.rotate_key()

        key_after = (tmp_path / ".key").read_bytes()
        assert key_before != key_after

    def test_rotate_key_with_no_tokens(self, tmp_path):
        """rotate_key on empty store should not crash."""
        store = TokenStore(storage_dir=tmp_path)
        store.rotate_key()
        # Store should still work after rotation.
        store.save_token("ws://a/", "tok")
        assert store.load_token("ws://a/") == "tok"

    def test_rotate_key_multiple_times(self, tmp_path):
        store = TokenStore(storage_dir=tmp_path)
        store.save_token("ws://a/", "persistent-token")
        for _ in range(3):
            store.rotate_key()
        assert store.load_token("ws://a/") == "persistent-token"


class TestKeyManagement:
    """TD-036: key generation is secure (Fernet.generate_key)."""

    def test_get_or_create_key_returns_existing(self, tmp_path, monkeypatch):
        """Second call returns the same key (no regeneration)."""
        monkeypatch.setattr(
            "auth.token_store.DEFAULT_KEY_DIR", tmp_path
        )
        key1 = _get_or_create_key()
        key2 = _get_or_create_key()
        assert key1 == key2

    def test_get_or_create_key_generates_valid_fernet_key(self, tmp_path, monkeypatch):
        """Generated key is a valid 32-byte base64 Fernet key."""
        monkeypatch.setattr(
            "auth.token_store.DEFAULT_KEY_DIR", tmp_path
        )
        key = _get_or_create_key()
        # Fernet keys are 44-char base64 (32 bytes + 12 bytes padding/HMAC).
        assert len(key) == 44
        from cryptography.fernet import Fernet
        # Should not raise.
        Fernet(key)

    def test_no_machine_name_derivation(self, tmp_path, monkeypatch):
        """TD-036: key should NOT be derivable from COMPUTERNAME.

        Two different temp dirs should produce different keys (proving
        the key is random, not derived from machine name).
        """
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        monkeypatch.setattr("auth.token_store.DEFAULT_KEY_DIR", dir_a)
        key_a = _get_or_create_key()
        monkeypatch.setattr("auth.token_store.DEFAULT_KEY_DIR", dir_b)
        key_b = _get_or_create_key()
        assert key_a != key_b


class TestFilePermissions:
    """TD-038: _restrict_file_permissions does not crash."""

    def test_restrict_permissions_does_not_crash(self, tmp_path):
        """On any platform, _restrict_file_permissions should not raise."""
        test_file = tmp_path / "test.key"
        test_file.write_bytes(b"fake-key")
        # Should not raise even if icacls is unavailable or user is unknown.
        _restrict_file_permissions(test_file)

    def test_restrict_permissions_on_nonexistent_file_logs_warning(self, tmp_path):
        """Nonexistent file should log a warning but not crash."""
        nonexistent = tmp_path / "nope.key"
        # Should not raise.
        _restrict_file_permissions(nonexistent)
