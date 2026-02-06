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
    tone_preference: Optional[int] = None
    detail_preference: Optional[int] = None


class HistoryListItem(BaseModel):
    """Lightweight history entry (no full_response)."""

    id: int
    created_at: str
    test_type: str
    test_type_display: str
    filename: Optional[str] = None
    summary: str
    liked: bool = False
    sync_id: Optional[str] = None
    updated_at: Optional[str] = None


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
    liked: bool = False
    full_response: dict[str, Any]
    sync_id: Optional[str] = None
    updated_at: Optional[str] = None
    edited_text: Optional[str] = None


class HistoryDeleteResponse(BaseModel):
    """Response for DELETE /history/{id}."""

    deleted: bool
    id: int


class HistoryLikeRequest(BaseModel):
    """Request body for PATCH /history/{id}/like."""

    liked: bool


class HistoryLikeResponse(BaseModel):
    """Response for PATCH /history/{id}/like."""

    id: int
    liked: bool


class ConsentStatusResponse(BaseModel):
    """Response for GET /consent."""

    consent_given: bool
