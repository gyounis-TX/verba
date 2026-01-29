"""
Persistent settings store backed by SQLite + OS keychain.

Same public API as Phase 4: get_settings, update_settings, get_api_key_for_provider.
"""

from __future__ import annotations

from api.explain_models import AppSettings, LiteracyLevelEnum, LLMProviderEnum, SettingsUpdate
from storage.database import get_db
from storage.keychain import get_keychain

# Non-secret settings stored in SQLite
_DB_KEYS = ("llm_provider", "claude_model", "openai_model", "literacy_level", "specialty", "practice_name")
# Secret keys stored in OS keychain
_SECRET_KEYS = ("claude_api_key", "openai_api_key")


def get_settings() -> AppSettings:
    """Return current settings (loaded fresh from SQLite + keychain)."""
    db = get_db()
    keychain = get_keychain()

    all_db = db.get_all_settings()

    return AppSettings(
        llm_provider=LLMProviderEnum(all_db["llm_provider"])
        if "llm_provider" in all_db
        else LLMProviderEnum.CLAUDE,
        claude_api_key=keychain.get_claude_key(),
        openai_api_key=keychain.get_openai_key(),
        claude_model=all_db.get("claude_model"),
        openai_model=all_db.get("openai_model"),
        literacy_level=LiteracyLevelEnum(all_db["literacy_level"])
        if "literacy_level" in all_db
        else LiteracyLevelEnum.GRADE_6,
        specialty=all_db.get("specialty"),
        practice_name=all_db.get("practice_name"),
    )


def update_settings(update: SettingsUpdate) -> AppSettings:
    """Apply partial update and return new settings."""
    db = get_db()
    keychain = get_keychain()

    update_data = update.model_dump(exclude_unset=True)

    # Persist API keys in keychain
    if "claude_api_key" in update_data:
        val = update_data.pop("claude_api_key")
        if val is None:
            keychain.delete_key("claude_api_key")
        else:
            keychain.set_claude_key(val)
    if "openai_api_key" in update_data:
        val = update_data.pop("openai_api_key")
        if val is None:
            keychain.delete_key("openai_api_key")
        else:
            keychain.set_openai_key(val)

    # Persist non-secret settings in SQLite
    for key in _DB_KEYS:
        if key in update_data:
            val = update_data[key]
            if val is None:
                db.delete_setting(key)
            else:
                # Enums → store their value string
                db.set_setting(key, val.value if hasattr(val, "value") else str(val))

    return get_settings()


def get_api_key_for_provider(provider: str) -> str | None:
    """Get the API key for the given provider."""
    keychain = get_keychain()
    if provider == "claude":
        return keychain.get_claude_key()
    elif provider == "openai":
        return keychain.get_openai_key()
    return None
