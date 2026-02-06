from __future__ import annotations

from abc import ABC, abstractmethod

from api.models import ExtractionResult
from api.analysis_models import ParsedReport


class BaseTestType(ABC):
    """Abstract base class for medical test type handlers."""

    @property
    @abstractmethod
    def test_type_id(self) -> str:
        """Unique identifier, e.g., 'echocardiogram'."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name, e.g., 'Echocardiogram'."""
        ...

    @property
    @abstractmethod
    def keywords(self) -> list[str]:
        """Keywords for auto-detection from extracted text."""
        ...

    @abstractmethod
    def detect(self, extraction_result: ExtractionResult) -> float:
        """Return confidence score 0.0-1.0 that this is the right test type."""
        ...

    @abstractmethod
    def parse(
        self,
        extraction_result: ExtractionResult,
        gender: str | None = None,
        age: int | None = None,
    ) -> ParsedReport:
        """Parse extraction result into structured report.

        Args:
            extraction_result: The extracted text/data from the report
            gender: Patient gender for sex-specific reference ranges (optional)
            age: Patient age for age-specific reference ranges (optional)
        """
        ...

    @abstractmethod
    def get_reference_ranges(self) -> dict:
        """Return reference ranges for this test type."""
        ...

    @abstractmethod
    def get_glossary(self) -> dict[str, str]:
        """Map medical terms to plain English definitions."""
        ...

    @property
    def category(self) -> str:
        """Category for grouping in UI (e.g., 'cardiac', 'imaging_ct').
        Override in subclass; defaults to 'other'."""
        return "other"

    def get_prompt_context(self, extraction_result: ExtractionResult | None = None) -> dict:
        """Additional context for LLM prompt construction (Phase 4).
        Default returns empty dict; override in subclass."""
        return {}

    def get_metadata(self) -> dict:
        """Return metadata for listing in registry."""
        return {
            "test_type_id": self.test_type_id,
            "display_name": self.display_name,
            "keywords": self.keywords,
            "category": self.category,
        }
