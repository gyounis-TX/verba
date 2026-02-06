from __future__ import annotations

import re

from api.models import ExtractionResult
from api.analysis_models import ParsedMeasurement, ParsedReport, ReportSection
from test_types.base import BaseTestType
from .glossary import ECHO_GLOSSARY
from .measurements import extract_measurements
from .reference_ranges import REFERENCE_RANGES, classify_measurement


class EchocardiogramHandler(BaseTestType):

    @property
    def test_type_id(self) -> str:
        return "echocardiogram"

    @property
    def display_name(self) -> str:
        return "Echocardiogram"

    @property
    def keywords(self) -> list[str]:
        return [
            "echocardiogram",
            "echocardiography",
            "transthoracic",
            "transesophageal",
            "2d echo",
            "doppler",
            "ejection fraction",
            "lvef",
            "left ventricle",
            "left ventricular",
            "mitral valve",
            "aortic valve",
            "tricuspid",
            "diastolic function",
            "wall motion",
            "lvidd",
            "lvids",
            "ivsd",
            "lvpwd",
        ]

    @property
    def category(self) -> str:
        return "cardiac"

    def detect(self, extraction_result: ExtractionResult) -> float:
        """Keyword-based detection with tiered scoring."""
        text = extraction_result.full_text.lower()

        strong_keywords = [
            "echocardiogram",
            "echocardiography",
            "transthoracic echocardiogram",
            "transesophageal echocardiogram",
            "2d echo",
        ]
        moderate_keywords = [
            "ejection fraction",
            "lvef",
            "left ventricular",
            "diastolic function",
            "wall motion",
            "lvidd",
            "lvids",
            "mitral valve",
            "aortic valve",
            "tricuspid valve",
            "e/a ratio",
            "e/e'",
            "rvsp",
        ]
        weak_keywords = [
            "left ventricle",
            "right ventricle",
            "left atrium",
            "pericardial",
            "doppler",
            "regurgitation",
            "stenosis",
        ]

        strong_count = sum(1 for k in strong_keywords if k in text)
        moderate_count = sum(1 for k in moderate_keywords if k in text)
        weak_count = sum(1 for k in weak_keywords if k in text)

        if strong_count > 0:
            base = 0.7
        elif moderate_count >= 3:
            base = 0.4
        elif moderate_count >= 1:
            base = 0.2
        else:
            base = 0.0

        bonus = min(0.3, moderate_count * 0.05 + weak_count * 0.02)
        return min(1.0, base + bonus)

    def parse(
        self,
        extraction_result: ExtractionResult,
        gender: str | None = None,
        age: int | None = None,
    ) -> ParsedReport:
        """Extract structured measurements, sections, and findings."""
        text = extraction_result.full_text
        warnings: list[str] = []

        raw_measurements = extract_measurements(text, extraction_result.pages)

        parsed_measurements: list[ParsedMeasurement] = []
        for m in raw_measurements:
            classification = classify_measurement(m.abbreviation, m.value, gender)
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
        return ECHO_GLOSSARY

    def get_prompt_context(self, extraction_result: ExtractionResult | None = None) -> dict:
        return {
            "specialty": "cardiology",
            "test_type": "echocardiogram",
            "category": "cardiac",
            "guidelines": "ASE 2015 Chamber Quantification Guidelines",
            "explanation_style": (
                "Explain each measurement in plain language. "
                "Compare to normal ranges. Highlight any abnormalities. "
                "Avoid medical jargon where possible."
            ),
            "interpretation_rules": (
                "Organize findings in this order: LV systolic function first, "
                "then diastolic function, then chamber sizes, then valvular "
                "findings, then right heart, then pericardium."
            ),
        }

    def _extract_sections(self, text: str) -> list[ReportSection]:
        """Split report text into labeled sections."""
        section_headers = [
            r"LEFT\s+VENTRICLE|LV\s+DIMENSIONS?",
            r"RIGHT\s+VENTRICLE|RV\b",
            r"LEFT\s+ATRIUM|LA\b",
            r"RIGHT\s+ATRIUM|RA\b",
            r"AORTIC\s+(?:ROOT|VALVE)",
            r"MITRAL\s+VALVE",
            r"TRICUSPID\s+VALVE",
            r"PULMON(?:ARY|IC)\s+VALVE",
            r"PERICARDI(?:UM|AL)",
            r"DIASTOLIC\s+FUNCTION",
            r"WALL\s+MOTION",
            r"CONCLUSION|IMPRESSION|SUMMARY|FINDINGS",
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
