"""Pydantic models for template CRUD endpoints."""

from __future__ import annotations

import json
from typing import Optional

from pydantic import BaseModel, Field, model_validator


def normalize_test_type_field(raw: str | None) -> list[str] | None:
    """Parse test_type column into a list of type strings.

    Handles:
    - None → None
    - '["echo","cardiac_mri"]' → ["echo", "cardiac_mri"]
    - 'echo' → ["echo"]
    - '' → None
    """
    if not raw:
        return None
    raw = raw.strip()
    if not raw:
        return None
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(v) for v in parsed if v]
        except (json.JSONDecodeError, TypeError):
            pass
    return [raw]


class TemplateCreateRequest(BaseModel):
    """Request body for POST /templates."""

    name: str = Field(..., min_length=1, max_length=100)
    test_type: Optional[str] = None
    test_types: Optional[list[str]] = None
    tone: Optional[str] = None
    structure_instructions: Optional[str] = None
    closing_text: Optional[str] = None
    is_default: Optional[bool] = False

    @model_validator(mode="after")
    def _sync_test_types(self) -> "TemplateCreateRequest":
        """If test_types provided, serialize to test_type. If only test_type, wrap."""
        if self.test_types is not None:
            filtered = [t for t in self.test_types if t]
            self.test_type = json.dumps(filtered) if filtered else None
            self.test_types = filtered or None
        elif self.test_type:
            self.test_types = normalize_test_type_field(self.test_type)
            if self.test_types:
                self.test_type = json.dumps(self.test_types)
        return self


class TemplateUpdateRequest(BaseModel):
    """Request body for PATCH /templates/{id}."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    test_type: Optional[str] = None
    test_types: Optional[list[str]] = None
    tone: Optional[str] = None
    structure_instructions: Optional[str] = None
    closing_text: Optional[str] = None
    is_default: Optional[bool] = None

    @model_validator(mode="after")
    def _sync_test_types(self) -> "TemplateUpdateRequest":
        """If test_types provided, serialize to test_type. If only test_type, wrap."""
        if self.test_types is not None:
            filtered = [t for t in self.test_types if t]
            self.test_type = json.dumps(filtered) if filtered else None
            self.test_types = filtered or None
        elif self.test_type:
            self.test_types = normalize_test_type_field(self.test_type)
            if self.test_types:
                self.test_type = json.dumps(self.test_types)
        return self


class TemplateResponse(BaseModel):
    """Single template response."""

    id: str | int
    name: str
    test_type: Optional[str] = None
    test_types: Optional[list[str]] = None
    tone: Optional[str] = None
    structure_instructions: Optional[str] = None
    closing_text: Optional[str] = None
    created_at: str
    updated_at: str
    sync_id: Optional[str] = None
    is_builtin: Optional[bool] = False
    is_default: Optional[bool] = False

    @model_validator(mode="after")
    def _populate_test_types(self) -> "TemplateResponse":
        """Populate test_types from raw test_type column."""
        if self.test_types is None:
            self.test_types = normalize_test_type_field(self.test_type)
        return self


class TemplateListResponse(BaseModel):
    """List of templates."""

    items: list[TemplateResponse]
    total: int
