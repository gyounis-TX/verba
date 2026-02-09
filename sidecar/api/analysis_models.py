from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SeverityStatus(str, Enum):
    NORMAL = "normal"
    MILDLY_ABNORMAL = "mildly_abnormal"
    MODERATELY_ABNORMAL = "moderately_abnormal"
    SEVERELY_ABNORMAL = "severely_abnormal"
    CRITICAL = "critical"  # Panic/critical values requiring immediate attention
    UNDETERMINED = "undetermined"


class AbnormalityDirection(str, Enum):
    NORMAL = "normal"
    ABOVE_NORMAL = "above_normal"
    BELOW_NORMAL = "below_normal"


class PriorValue(BaseModel):
    value: float
    time_label: str


class ParsedMeasurement(BaseModel):
    name: str
    abbreviation: str
    value: float
    unit: str
    status: SeverityStatus = SeverityStatus.UNDETERMINED
    direction: AbnormalityDirection = AbnormalityDirection.NORMAL
    reference_range: Optional[str] = None
    prior_values: list[PriorValue] = Field(default_factory=list)
    raw_text: str = ""
    page_number: Optional[int] = None


class ReportSection(BaseModel):
    name: str
    content: str
    page_number: Optional[int] = None


class ParsedReport(BaseModel):
    test_type: str
    test_type_display: str
    detection_confidence: float = Field(ge=0.0, le=1.0)
    measurements: list[ParsedMeasurement] = Field(default_factory=list)
    sections: list[ReportSection] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    secondary_test_types: list[str] = Field(default_factory=list)


class CompoundSegmentInfo(BaseModel):
    start_page: int
    end_page: int
    detected_type: Optional[str] = None
    confidence: float = 0.0
    char_count: int = 0


class DetectTypeResponse(BaseModel):
    test_type: Optional[str] = None
    confidence: float = 0.0
    available_types: list[dict] = Field(default_factory=list)
    detection_method: str = "keyword"   # "keyword" | "llm" | "none"
    llm_attempted: bool = False
    is_compound: bool = False
    compound_segments: list[CompoundSegmentInfo] = Field(default_factory=list)


class DetectTypeRequest(BaseModel):
    extraction_result: dict
    user_hint: Optional[str] = None


class ParseRequest(BaseModel):
    extraction_result: dict
    test_type: Optional[str] = None
