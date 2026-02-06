from __future__ import annotations

import re

from api.models import ExtractionResult
from api.analysis_models import ParsedMeasurement, ParsedReport, ReportSection
from test_types.base import BaseTestType
from .glossary import VENOUS_GLOSSARY
from .measurements import extract_measurements
from .reference_ranges import REFERENCE_RANGES, classify_measurement


class VenousDopplerHandler(BaseTestType):

    @property
    def test_type_id(self) -> str:
        return "venous_duplex"

    @property
    def display_name(self) -> str:
        return "Lower Extremity Venous Duplex Scan"

    @property
    def keywords(self) -> list[str]:
        return [
            "venous duplex",
            "venous ultrasound",
            "venous color duplex",
            "dvt",
            "deep vein thrombosis",
            "venous reflux",
            "saphenous vein",
            "gsv",
            "greater saphenous",
            "lesser saphenous",
            "compressibility",
            "augmentation",
            "reflux time",
            "93970",
            "93971",
        ]

    @property
    def category(self) -> str:
        return "vascular"

    def detect(self, extraction_result: ExtractionResult) -> float:
        text = extraction_result.full_text.lower()

        strong_keywords = [
            "venous color duplex",
            "venous duplex scan",
            "lower extremity venous",
            "venous ultrasound",
            "duplex scan of extremity veins",
        ]
        moderate_keywords = [
            "deep vein thrombosis",
            "dvt",
            "venous reflux",
            "greater saphenous vein",
            "gsv prox",
            "gsv mid",
            "gsv dist",
            "reflux time",
            "compressibility",
            "augmentation",
            "93970",
            "93971",
            "saphenous",
        ]
        weak_keywords = [
            "venous",
            "vein",
            "reflux",
            "phasic",
            "spontaneous flow",
            "compression",
        ]

        strong_count = sum(1 for k in strong_keywords if k in text)
        moderate_count = sum(1 for k in moderate_keywords if k in text)
        weak_count = sum(1 for k in weak_keywords if k in text)

        if strong_count > 0:
            base = 0.8
        elif moderate_count >= 3:
            base = 0.5
        elif moderate_count >= 1:
            base = 0.3
        else:
            base = 0.0

        bonus = min(0.2, moderate_count * 0.05 + weak_count * 0.02)
        return min(1.0, base + bonus)

    def parse(
        self,
        extraction_result: ExtractionResult,
        gender: str | None = None,
        age: int | None = None,
    ) -> ParsedReport:
        text = extraction_result.full_text
        warnings: list[str] = []

        raw_measurements = extract_measurements(text, extraction_result.pages)

        parsed_measurements: list[ParsedMeasurement] = []
        for m in raw_measurements:
            classification = classify_measurement(m.abbreviation, m.value)
            parsed_measurements.append(
                ParsedMeasurement(
                    name=m.name,
                    abbreviation=m.abbreviation,
                    value=m.value,
                    unit=m.unit,
                    status=classification.status,
                    direction=classification.direction,
                    reference_range=classification.reference_range_str,
                    raw_text=m.raw_text,
                    page_number=m.page_number,
                )
            )

        sections = self._extract_sections(text)
        findings = self._extract_findings(text)

        if not parsed_measurements:
            warnings.append(
                "No measurements could be extracted. "
                "The report format may not be supported."
            )

        detection_confidence = self.detect(extraction_result)

        return ParsedReport(
            test_type=self.test_type_id,
            test_type_display=self.display_name,
            detection_confidence=detection_confidence,
            measurements=parsed_measurements,
            sections=sections,
            findings=findings,
            warnings=warnings,
        )

    def get_reference_ranges(self) -> dict:
        return {
            abbr: {
                "normal_min": rr.normal_min,
                "normal_max": rr.normal_max,
                "unit": rr.unit,
                "source": rr.source,
            }
            for abbr, rr in REFERENCE_RANGES.items()
        }

    def get_glossary(self) -> dict[str, str]:
        return VENOUS_GLOSSARY

    def get_prompt_context(self, extraction_result: ExtractionResult | None = None) -> dict:
        return {
            "specialty": "vascular medicine / cardiology",
            "test_type": "venous_duplex",
            "category": "vascular",
            "guidelines": "SVS/AVF Clinical Practice Guidelines",
            "explanation_style": (
                "Explain whether any blood clots (DVT) were found. "
                "Interpret the reflux times and vein diameters, explaining "
                "what they mean for venous health. Discuss compressibility "
                "and flow patterns. Compare right and left legs. "
                "Explain findings in plain language. Avoid jargon."
            ),
        }

    def _extract_sections(self, text: str) -> list[ReportSection]:
        section_headers = [
            r"(?:FINDINGS?:?\s*)?RIGHT\s+LEG",
            r"(?:FINDINGS?:?\s*)?LEFT\s+LEG",
            r"FINDINGS?",
            r"IMPRESSION[S]?|CONCLUSION[S]?|INTERPRETATION|SUMMARY",
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
                    ReportSection(name=section_name.upper(), content=content)
                )

        return sections

    def _extract_findings(self, text: str) -> list[str]:
        findings: list[str] = []
        findings_re = re.compile(
            r"(?:CONCLUSION[S]?|IMPRESSION[S]?|SUMMARY|INTERPRETATION)"
            r"\s*[:\-]?\s*\n([\s\S]*?)(?:\n\s*\n|\Z)",
            re.IGNORECASE,
        )
        for match in findings_re.finditer(text):
            block = match.group(1).strip()
            lines = re.split(r"\n\s*(?:\d+[\.\)]\s*|[-*\u2022]\s*)", block)
            for line in lines:
                line = line.strip()
                if line and len(line) > 10:
                    findings.append(line)
        return findings
