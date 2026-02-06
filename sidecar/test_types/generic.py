"""
Generic test type handler for reports without a specialized parser.

Provides keyword-based detection and basic section extraction from raw text.
Measurements are left to the LLM to interpret from the report text, unless
an optional measurement_extractor is provided.
"""

from __future__ import annotations

import re
from typing import Callable, Optional

from api.models import ExtractionResult
from api.analysis_models import ParsedMeasurement, ParsedReport, ReportSection
from test_types.base import BaseTestType

# Type alias for measurement extractor functions
MeasurementExtractor = Callable[[str, Optional[str]], list[ParsedMeasurement]]


class GenericTestType(BaseTestType):
    """A reusable handler for test types that lack specialized parsing.

    Instantiated with an ID, display name, and keywords. Performs:
    - Keyword-based detection (same pattern as existing handlers)
    - Section extraction (FINDINGS, IMPRESSION, CONCLUSION, etc.)
    - Optional measurement extraction via provided extractor function
    - Optional reference ranges and glossary
    """

    def __init__(
        self,
        test_type_id: str,
        display_name: str,
        keywords: list[str],
        specialty: str = "cardiology",
        category: str = "other",
        measurement_extractor: MeasurementExtractor | None = None,
        reference_ranges: dict | None = None,
        glossary: dict[str, str] | None = None,
    ):
        self._test_type_id = test_type_id
        self._display_name = display_name
        self._keywords = keywords
        self._specialty = specialty
        self._category = category
        self._measurement_extractor = measurement_extractor
        self._reference_ranges = reference_ranges or {}
        self._glossary = glossary or {}

    @property
    def test_type_id(self) -> str:
        return self._test_type_id

    @property
    def display_name(self) -> str:
        return self._display_name

    @property
    def keywords(self) -> list[str]:
        return self._keywords

    @property
    def category(self) -> str:
        return self._category

    def detect(self, extraction_result: ExtractionResult) -> float:
        """Keyword matching against full_text (case-insensitive).

        Score: 0.0 if no keywords match, up to 1.0 based on number of keyword hits.
        """
        text = extraction_result.full_text.lower()
        hits = sum(1 for kw in self._keywords if kw.lower() in text)

        if hits == 0:
            return 0.0

        # Scale: 1 hit = 0.3, 2 hits = 0.5, 3+ hits = 0.6+, caps at 1.0
        score = min(1.0, 0.2 + hits * 0.15)
        return score

    def parse(
        self,
        extraction_result: ExtractionResult,
        gender: str | None = None,
        age: int | None = None,
    ) -> ParsedReport:
        """Extract sections and findings from text.

        If a measurement_extractor was provided, use it to extract measurements;
        otherwise leave measurements empty for the LLM to handle.
        """
        text = extraction_result.full_text
        sections = self._extract_sections(text)
        findings = self._extract_findings(text)
        detection_confidence = self.detect(extraction_result)

        # Use measurement extractor if provided
        measurements: list[ParsedMeasurement] = []
        if self._measurement_extractor is not None:
            measurements = self._measurement_extractor(text, gender)

        return ParsedReport(
            test_type=self._test_type_id,
            test_type_display=self._display_name,
            detection_confidence=detection_confidence,
            measurements=measurements,
            sections=sections,
            findings=findings,
            warnings=[],
        )

    def get_reference_ranges(self) -> dict:
        return self._reference_ranges

    def get_glossary(self) -> dict[str, str]:
        return self._glossary

    def get_prompt_context(self, extraction_result: ExtractionResult | None = None) -> dict:
        return {
            "specialty": self._specialty,
            "test_type": self._test_type_id,
            "test_type_hint": self._display_name,
            "category": self._category,
        }

    def _extract_sections(self, text: str) -> list[ReportSection]:
        """Split report text into labeled sections using common headers."""
        section_headers = [
            r"FINDINGS",
            r"IMPRESSION",
            r"CONCLUSION",
            r"INDICATION",
            r"TECHNIQUE",
            r"COMPARISON",
            r"CLINICAL\s+(?:HISTORY|INFORMATION|CONTEXT)",
            r"HISTORY",
            r"PROCEDURE",
            r"RESULTS",
            r"INTERPRETATION",
            r"SUMMARY",
            r"MEASUREMENTS",
            r"REPORT",
            r"EXAMINATION",
            r"DESCRIPTION",
        ]

        combined = "|".join(f"({p})" for p in section_headers)
        header_re = re.compile(
            r"(?:^|\n)\s*(" + combined + r")\s*[:\-]?\s*",
            re.IGNORECASE | re.MULTILINE,
        )

        matches = list(header_re.finditer(text))
        sections: list[ReportSection] = []

        for i, match in enumerate(matches):
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            section_name = match.group(1).strip().rstrip(":-").strip()
            content = text[start:end].strip()
            if content:
                sections.append(
                    ReportSection(
                        name=section_name.upper(),
                        content=content,
                    )
                )

        return sections

    def _extract_findings(self, text: str) -> list[str]:
        """Extract conclusion/findings/impression lines."""
        findings: list[str] = []
        findings_re = re.compile(
            r"(?:CONCLUSION|IMPRESSION|SUMMARY|FINDINGS)\s*[:\-]?\s*\n"
            r"([\s\S]*?)(?:\n\s*\n|\Z)",
            re.IGNORECASE,
        )
        for match in findings_re.finditer(text):
            block = match.group(1).strip()
            lines = re.split(r"\n\s*(?:\d+[\.\)]\s*|[-*]\s*)", block)
            for line in lines:
                line = line.strip()
                if line and len(line) > 10:
                    findings.append(line)

        return findings
