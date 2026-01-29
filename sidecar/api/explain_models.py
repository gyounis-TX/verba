"""Pydantic models for the /analyze/explain and /settings endpoints."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from api.analysis_models import ParsedReport, SeverityStatus


class LLMProviderEnum(str, Enum):
    CLAUDE = "claude"
    OPENAI = "openai"


class LiteracyLevelEnum(str, Enum):
    GRADE_4 = "grade_4"
    GRADE_6 = "grade_6"
    GRADE_8 = "grade_8"
    CLINICAL = "clinical"


# --- Request ---


class ExplainRequest(BaseModel):
    """Request body for POST /analyze/explain."""

    extraction_result: dict
    test_type: Optional[str] = None
    literacy_level: LiteracyLevelEnum = LiteracyLevelEnum.GRADE_6
    provider: LLMProviderEnum = LLMProviderEnum.CLAUDE
    api_key: Optional[str] = None
    clinical_context: Optional[str] = None
    template_id: Optional[int] = None


# --- Response sub-models ---


class MeasurementExplanation(BaseModel):
    abbreviation: str
    value: float
    unit: str
    status: SeverityStatus
    plain_language: str


class FindingExplanation(BaseModel):
    finding: str
    severity: str  # "normal", "mild", "moderate", "severe", "informational"
    explanation: str


class ExplanationResult(BaseModel):
    overall_summary: str
    measurements: list[MeasurementExplanation] = Field(default_factory=list)
    key_findings: list[FindingExplanation] = Field(default_factory=list)
    questions_for_doctor: list[str] = Field(default_factory=list)
    disclaimer: str = ""


# --- Full response envelope ---


class ExplainResponse(BaseModel):
    """Full response from POST /analyze/explain."""

    explanation: ExplanationResult
    parsed_report: ParsedReport
    validation_warnings: list[str] = Field(default_factory=list)
    phi_categories_found: list[str] = Field(default_factory=list)
    model_used: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


# --- Settings ---


class AppSettings(BaseModel):
    """In-memory settings (Phase 4). SQLite + keychain in Phase 6."""

    llm_provider: LLMProviderEnum = LLMProviderEnum.CLAUDE
    claude_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    claude_model: Optional[str] = None
    openai_model: Optional[str] = None
    literacy_level: LiteracyLevelEnum = LiteracyLevelEnum.GRADE_6
    specialty: Optional[str] = None
    practice_name: Optional[str] = None


class SettingsUpdate(BaseModel):
    """Partial update for settings."""

    llm_provider: Optional[LLMProviderEnum] = None
    claude_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    claude_model: Optional[str] = None
    openai_model: Optional[str] = None
    literacy_level: Optional[LiteracyLevelEnum] = None
    specialty: Optional[str] = None
    practice_name: Optional[str] = None
