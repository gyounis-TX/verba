"""
Persistent settings store backed by SQLite + OS keychain.

Same public API as Phase 4: get_settings, update_settings, get_api_key_for_provider.
"""

from __future__ import annotations

import json

from api.explain_models import AppSettings, ExplanationVoiceEnum, LiteracyLevelEnum, LLMProviderEnum, PhysicianNameSourceEnum, SettingsUpdate
from storage.database import get_db
from storage.keychain import get_keychain

# Non-secret settings stored in SQLite
_DB_KEYS = ("llm_provider", "claude_model", "openai_model", "literacy_level", "specialty", "practice_name", "include_key_findings", "include_measurements", "tone_preference", "detail_preference", "quick_reasons", "next_steps_options", "explanation_voice", "name_drop", "physician_name_source", "custom_physician_name", "practice_providers", "short_comment_char_limit")
# Keys that store JSON-encoded lists
_JSON_LIST_KEYS = {"quick_reasons", "next_steps_options", "practice_providers"}
# Secret keys stored in OS keychain
_SECRET_KEYS = ("claude_api_key", "openai_api_key")


def get_settings() -> AppSettings:
    """Return current settings (loaded fresh from SQLite + keychain)."""
    db = get_db()
    keychain = get_keychain()

    all_db = db.get_all_settings()

    def _load_json_list(key: str) -> list[str]:
        raw = all_db.get(key)
        if not raw:
            return []
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []

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
        else LiteracyLevelEnum.GRADE_8,
        specialty=all_db.get("specialty"),
        practice_name=all_db.get("practice_name"),
        include_key_findings=all_db.get("include_key_findings", "true") != "false",
        include_measurements=all_db.get("include_measurements", "true") != "false",
        tone_preference=int(all_db.get("tone_preference", "3")),
        detail_preference=int(all_db.get("detail_preference", "3")),
        quick_reasons=_load_json_list("quick_reasons"),
        next_steps_options=_load_json_list("next_steps_options") if "next_steps_options" in all_db else [
            "Will follow this over time",
            "We will contact you to discuss next steps",
        ],
        explanation_voice=ExplanationVoiceEnum(all_db["explanation_voice"])
        if "explanation_voice" in all_db
        else ExplanationVoiceEnum.THIRD_PERSON,
        name_drop=all_db.get("name_drop", "true") != "false",
        physician_name_source=PhysicianNameSourceEnum(all_db["physician_name_source"])
        if "physician_name_source" in all_db
        else PhysicianNameSourceEnum.AUTO_EXTRACT,
        custom_physician_name=all_db.get("custom_physician_name"),
        practice_providers=_load_json_list("practice_providers"),
        short_comment_char_limit=None
        if all_db.get("short_comment_char_limit") == "none"
        else int(all_db["short_comment_char_limit"])
        if "short_comment_char_limit" in all_db
        else 1000,
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
            if key == "short_comment_char_limit":
                db.set_setting(key, "none" if val is None else str(val))
            elif val is None:
                db.delete_setting(key)
            elif key in _JSON_LIST_KEYS:
                db.set_setting(key, json.dumps(val))
            elif isinstance(val, bool):
                db.set_setting(key, "true" if val else "false")
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
