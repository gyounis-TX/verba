"""Pydantic models for template CRUD endpoints."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class TemplateCreateRequest(BaseModel):
    """Request body for POST /templates."""

    name: str = Field(..., min_length=1, max_length=100)
    test_type: Optional[str] = None
    tone: Optional[str] = None
    structure_instructions: Optional[str] = None
    closing_text: Optional[str] = None


class TemplateUpdateRequest(BaseModel):
    """Request body for PATCH /templates/{id}."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    test_type: Optional[str] = None
    tone: Optional[str] = None
    structure_instructions: Optional[str] = None
    closing_text: Optional[str] = None


class TemplateResponse(BaseModel):
    """Single template response."""

    id: int
    name: str
    test_type: Optional[str] = None
    tone: Optional[str] = None
    structure_instructions: Optional[str] = None
    closing_text: Optional[str] = None
    created_at: str
    updated_at: str


class TemplateListResponse(BaseModel):
    """List of templates."""

    items: list[TemplateResponse]
    total: int
