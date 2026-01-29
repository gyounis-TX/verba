"""Pydantic models for history and consent endpoints."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class HistoryCreateRequest(BaseModel):
    """Request body for POST /history."""

    test_type: str
    test_type_display: str
    filename: Optional[str] = None
    summary: str = Field(..., max_length=200)
    full_response: dict[str, Any]


class HistoryListItem(BaseModel):
    """Lightweight history entry (no full_response)."""

    id: int
    created_at: str
    test_type: str
    test_type_display: str
    filename: Optional[str] = None
    summary: str


class HistoryListResponse(BaseModel):
    """Paginated history list."""

    items: list[HistoryListItem]
    total: int
    offset: int
    limit: int


class HistoryDetailResponse(BaseModel):
    """Single history record with full_response."""

    id: int
    created_at: str
    test_type: str
    test_type_display: str
    filename: Optional[str] = None
    summary: str
    full_response: dict[str, Any]


class HistoryDeleteResponse(BaseModel):
    """Response for DELETE /history/{id}."""

    deleted: bool
    id: int


class ConsentStatusResponse(BaseModel):
    """Response for GET /consent."""

    consent_given: bool
