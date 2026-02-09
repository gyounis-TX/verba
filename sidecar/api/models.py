from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class PageType(str, Enum):
    TEXT = "text"
    SCANNED = "scanned"
    MIXED = "mixed"


class InputMode(str, Enum):
    PDF = "pdf"
    TEXT = "text"
    IMAGE = "image"


class PageDetection(BaseModel):
    page_number: int
    page_type: PageType
    char_count: int
    confidence: float = Field(ge=0.0, le=1.0)


class DetectionResult(BaseModel):
    overall_type: PageType
    total_pages: int
    pages: list[PageDetection]


class ExtractedTable(BaseModel):
    page_number: int
    table_index: int
    headers: list[str]
    rows: list[list[str]]


class PageExtractionResult(BaseModel):
    page_number: int
    text: str
    extraction_method: str
    confidence: float = Field(ge=0.0, le=1.0)
    char_count: int


class ExtractionResult(BaseModel):
    input_mode: InputMode
    full_text: str
    pages: list[PageExtractionResult]
    tables: list[ExtractedTable]
    detection: Optional[DetectionResult] = None
    total_pages: int
    total_chars: int
    filename: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)
    emr_source: Optional[str] = None          # "vidistar", "epic", "cerner", etc.
    emr_source_confidence: float = 0.0


class ExtractionError(BaseModel):
    error: str
    detail: Optional[str] = None
