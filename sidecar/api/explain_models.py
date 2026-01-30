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
    GRADE_12 = "grade_12"
    CLINICAL = "clinical"


class ExplanationVoiceEnum(str, Enum):
    FIRST_PERSON = "first_person"
    THIRD_PERSON = "third_person"


class PhysicianNameSourceEnum(str, Enum):
    AUTO_EXTRACT = "auto_extract"
    CUSTOM = "custom"
    GENERIC = "generic"


# --- Request ---


class ExplainRequest(BaseModel):
    """Request body for POST /analyze/explain."""

    extraction_result: dict
    test_type: Optional[str] = None
    literacy_level: LiteracyLevelEnum = LiteracyLevelEnum.GRADE_8
    provider: LLMProviderEnum = LLMProviderEnum.CLAUDE
    api_key: Optional[str] = None
    clinical_context: Optional[str] = None
    template_id: Optional[int] = None
    refinement_instruction: Optional[str] = None
    tone_preference: Optional[int] = Field(default=None, ge=1, le=5)
    detail_preference: Optional[int] = Field(default=None, ge=1, le=5)
    next_steps: Optional[list[str]] = None
    short_comment: Optional[bool] = None
    explanation_voice: Optional[ExplanationVoiceEnum] = None
    name_drop: Optional[bool] = None
    physician_name_override: Optional[str] = None


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
    physician_name: Optional[str] = None
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
    literacy_level: LiteracyLevelEnum = LiteracyLevelEnum.GRADE_8
    specialty: Optional[str] = None
    practice_name: Optional[str] = None
    include_key_findings: bool = True
    include_measurements: bool = True
    tone_preference: int = Field(default=3, ge=1, le=5)
    detail_preference: int = Field(default=3, ge=1, le=5)
    quick_reasons: list[str] = Field(default_factory=list)
    next_steps_options: list[str] = Field(
        default_factory=lambda: [
            "Will follow this over time",
            "We will contact you to discuss next steps",
        ]
    )
    explanation_voice: ExplanationVoiceEnum = ExplanationVoiceEnum.THIRD_PERSON
    name_drop: bool = True
    physician_name_source: PhysicianNameSourceEnum = PhysicianNameSourceEnum.AUTO_EXTRACT
    custom_physician_name: Optional[str] = None
    practice_providers: list[str] = Field(default_factory=list)
    short_comment_char_limit: Optional[int] = Field(default=1000, ge=500, le=4000)


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
    include_key_findings: Optional[bool] = None
    include_measurements: Optional[bool] = None
    tone_preference: Optional[int] = Field(default=None, ge=1, le=5)
    detail_preference: Optional[int] = Field(default=None, ge=1, le=5)
    quick_reasons: Optional[list[str]] = None
    next_steps_options: Optional[list[str]] = None
    explanation_voice: Optional[ExplanationVoiceEnum] = None
    name_drop: Optional[bool] = None
    physician_name_source: Optional[PhysicianNameSourceEnum] = None
    custom_physician_name: Optional[str] = None
    practice_providers: Optional[list[str]] = None
    short_comment_char_limit: Optional[int] = Field(default=None, ge=500, le=4000)
