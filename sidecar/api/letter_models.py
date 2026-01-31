"""Pydantic models for the /letters endpoints."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class LetterGenerateRequest(BaseModel):
    """Request body for POST /letters/generate."""

    prompt: str = Field(..., min_length=1, max_length=5000)
    letter_type: str = Field(
        default="general",
        description="Type of content: 'explanation', 'question', 'letter', or 'general'.",
    )


class LetterResponse(BaseModel):
    """Single letter record."""

    id: int
    created_at: str
    prompt: str
    content: str
    letter_type: str
    liked: bool = False
    model_used: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    sync_id: Optional[str] = None
    updated_at: Optional[str] = None


class LetterUpdateRequest(BaseModel):
    """Request body for PUT /letters/{id}."""

    content: str = Field(..., min_length=1)


class LetterLikeRequest(BaseModel):
    """Request body for PUT /letters/{id}/like."""

    liked: bool


class LetterListResponse(BaseModel):
    """List of letters."""

    items: list[LetterResponse]
    total: int


class LetterDeleteResponse(BaseModel):
    """Response for DELETE /letters/{id}."""

    deleted: bool
    id: int
