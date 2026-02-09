"""Pydantic models for the /analyze/explain and /settings endpoints."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from api.analysis_models import ParsedReport, SeverityStatus


class LLMProviderEnum(str, Enum):
    CLAUDE = "claude"
    OPENAI = "openai"
    BEDROCK = "bedrock"


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


class FooterTypeEnum(str, Enum):
    EXPLIFY_BRANDING = "explify_branding"
    AI_DISCLAIMER = "ai_disclaimer"
    CUSTOM = "custom"
    NONE = "none"


# --- Request ---


class ExplainRequest(BaseModel):
    """Request body for POST /analyze/explain."""

    extraction_result: dict
    test_type: Optional[str] = None
    literacy_level: LiteracyLevelEnum = LiteracyLevelEnum.GRADE_8
    provider: Optional[LLMProviderEnum] = None
    api_key: Optional[str] = None
    clinical_context: Optional[str] = None
    template_id: Optional[int] = None
    shared_template_sync_id: Optional[str] = None
    refinement_instruction: Optional[str] = None
    tone_preference: Optional[int] = Field(default=None, ge=1, le=5)
    detail_preference: Optional[int] = Field(default=None, ge=1, le=5)
    next_steps: Optional[list[str]] = None
    short_comment: Optional[bool] = None
    sms_summary: Optional[bool] = None
    explanation_voice: Optional[ExplanationVoiceEnum] = None
    name_drop: Optional[bool] = None
    physician_name_override: Optional[str] = None
    include_key_findings: Optional[bool] = None
    include_measurements: Optional[bool] = None
    patient_age: Optional[int] = None
    patient_gender: Optional[str] = None
    deep_analysis: Optional[bool] = None
    high_anxiety_mode: Optional[bool] = None
    anxiety_level: Optional[int] = Field(default=None, ge=0, le=3)
    quick_reasons: Optional[list[str]] = None
    use_analogies: Optional[bool] = None
    include_lifestyle_recommendations: Optional[bool] = None
    avoid_openings: Optional[list[str]] = None
    batch_prior_summaries: Optional[list[dict]] = None
    quick_normal: Optional[bool] = None


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
    severity_score: Optional[float] = None
    tone_auto_adjusted: bool = False


# --- Settings ---


class AppSettings(BaseModel):
    """In-memory settings (Phase 4). SQLite + keychain in Phase 6."""

    llm_provider: LLMProviderEnum = LLMProviderEnum.CLAUDE
    claude_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_region: str = "us-east-1"
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
    short_comment_char_limit: Optional[int] = Field(default=1000, ge=500, le=5000)
    sms_summary_enabled: bool = False
    sms_summary_char_limit: int = Field(default=300, ge=100, le=500)
    default_comment_mode: str = "short"
    footer_type: FooterTypeEnum = FooterTypeEnum.EXPLIFY_BRANDING
    custom_footer_text: Optional[str] = None
    use_analogies: bool = True
    include_lifestyle_recommendations: bool = True
    custom_phrases: list[str] = Field(default_factory=list)
    severity_adaptive_tone: bool = True
    humanization_level: int = Field(default=3, ge=1, le=5)


class SettingsUpdate(BaseModel):
    """Partial update for settings."""

    llm_provider: Optional[LLMProviderEnum] = None
    claude_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_region: Optional[str] = None
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
    short_comment_char_limit: Optional[int] = Field(default=None, ge=500, le=5000)
    sms_summary_enabled: Optional[bool] = None
    sms_summary_char_limit: Optional[int] = Field(default=None, ge=100, le=500)
    default_comment_mode: Optional[str] = None
    footer_type: Optional[FooterTypeEnum] = None
    custom_footer_text: Optional[str] = None
    use_analogies: Optional[bool] = None
    include_lifestyle_recommendations: Optional[bool] = None
    custom_phrases: Optional[list[str]] = None
    severity_adaptive_tone: Optional[bool] = None
    humanization_level: Optional[int] = Field(default=None, ge=1, le=5)
