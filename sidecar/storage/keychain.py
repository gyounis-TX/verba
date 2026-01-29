"""OS keychain integration for secure API key storage."""

from __future__ import annotations

import logging

try:
    import keyring as _keyring_module
except ImportError:
    _keyring_module = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

_SERVICE_NAME = "verba"


class KeychainManager:
    """Store and retrieve API keys via OS keychain, with in-memory fallback."""

    def __init__(self) -> None:
        self._available = False
        self._fallback: dict[str, str] = {}
        if _keyring_module is not None:
            try:
                _keyring_module.get_credential(_SERVICE_NAME, None)
                self._available = True
                logger.info("OS keychain is available")
            except Exception:
                logger.warning(
                    "OS keychain unavailable; API keys will be stored in memory only"
                )
        else:
            logger.warning(
                "keyring package not installed; API keys will be stored in memory only"
            )

    def get_key(self, name: str) -> str | None:
        if self._available and _keyring_module is not None:
            try:
                return _keyring_module.get_password(_SERVICE_NAME, name)
            except Exception:
                pass
        return self._fallback.get(name)

    def set_key(self, name: str, value: str) -> None:
        if self._available and _keyring_module is not None:
            try:
                _keyring_module.set_password(_SERVICE_NAME, name, value)
                return
            except Exception:
                logger.warning("Failed to write to keychain; using fallback")
        self._fallback[name] = value

    def delete_key(self, name: str) -> None:
        if self._available and _keyring_module is not None:
            try:
                _keyring_module.delete_password(_SERVICE_NAME, name)
                return
            except Exception:
                pass
        self._fallback.pop(name, None)

    # Convenience methods

    def get_claude_key(self) -> str | None:
        return self.get_key("claude_api_key")

    def set_claude_key(self, value: str) -> None:
        self.set_key("claude_api_key", value)

    def get_openai_key(self) -> str | None:
        return self.get_key("openai_api_key")

    def set_openai_key(self, value: str) -> None:
        self.set_key("openai_api_key", value)


_keychain_instance: KeychainManager | None = None


def get_keychain() -> KeychainManager:
    """Return the module-level KeychainManager singleton."""
    global _keychain_instance
    if _keychain_instance is None:
        _keychain_instance = KeychainManager()
    return _keychain_instance
