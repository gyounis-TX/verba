"""Tests for the KeychainManager."""

from unittest.mock import patch, MagicMock

import pytest

from storage.keychain import KeychainManager


class TestKeychainAvailable:
    """Tests when OS keyring is available (mocked)."""

    @pytest.fixture
    def manager(self):
        mock_keyring = MagicMock()
        mock_keyring.get_credential.return_value = None
        with patch("storage.keychain._keyring_module", mock_keyring):
            mgr = KeychainManager()
            assert mgr._available is True
            yield mgr, mock_keyring

    def test_set_and_get(self, manager):
        mgr, mock_keyring = manager
        mock_keyring.get_password.return_value = "sk-test123"
        mgr.set_key("claude_api_key", "sk-test123")
        mock_keyring.set_password.assert_called_once_with(
            "verba", "claude_api_key", "sk-test123"
        )
        result = mgr.get_key("claude_api_key")
        assert result == "sk-test123"

    def test_delete(self, manager):
        mgr, mock_keyring = manager
        mgr.delete_key("claude_api_key")
        mock_keyring.delete_password.assert_called_once_with(
            "verba", "claude_api_key"
        )

    def test_convenience_methods(self, manager):
        mgr, mock_keyring = manager
        mock_keyring.get_password.return_value = "key123"
        assert mgr.get_claude_key() == "key123"
        assert mgr.get_openai_key() == "key123"

        mgr.set_claude_key("ck")
        mock_keyring.set_password.assert_called_with("verba", "claude_api_key", "ck")

        mgr.set_openai_key("ok")
        mock_keyring.set_password.assert_called_with("verba", "openai_api_key", "ok")


class TestKeychainUnavailable:
    """Tests when OS keyring is not available (fallback to in-memory)."""

    @pytest.fixture
    def manager(self):
        mock_keyring = MagicMock()
        mock_keyring.get_credential.side_effect = Exception("No keyring backend")
        with patch("storage.keychain._keyring_module", mock_keyring):
            mgr = KeychainManager()
            assert mgr._available is False
            yield mgr

    def test_fallback_set_and_get(self, manager):
        manager.set_key("claude_api_key", "sk-fallback")
        assert manager.get_key("claude_api_key") == "sk-fallback"

    def test_fallback_get_missing(self, manager):
        assert manager.get_key("nonexistent") is None

    def test_fallback_delete(self, manager):
        manager.set_key("key", "val")
        manager.delete_key("key")
        assert manager.get_key("key") is None

    def test_fallback_delete_nonexistent(self, manager):
        # Should not raise
        manager.delete_key("nonexistent")
