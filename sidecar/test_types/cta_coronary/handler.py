from __future__ import annotations

import re

from api.models import ExtractionResult
from api.analysis_models import ParsedMeasurement, ParsedReport, ReportSection
from test_types.base import BaseTestType, split_text_zones, keyword_zone_weight
from .glossary import CTA_GLOSSARY
from .measurements import extract_measurements
from .reference_ranges import REFERENCE_RANGES, classify_measurement


class CTACoronaryHandler(BaseTestType):

    @property
    def test_type_id(self) -> str:
        return "cta_coronary"

    @property
    def display_name(self) -> str:
        return "CTA Coronary"

    @property
    def keywords(self) -> list[str]:
        return [
            "cta coronary",
            "coronary cta",
            "ct coronary angiography",
            "coronary ct angiography",
            "cardiac ct angiography",
            "ccta",
            "calcium score",
            "agatston",
            "coronary artery calcium",
            "cac score",
            "coronary stenosis",
            "plaque burden",
            "coronary arteries",
            "left main",
            "lad",
            "lcx",
            "rca",
            "ct fractional flow reserve",
            "ct-ffr",
        ]

    @property
    def category(self) -> str:
        return "cardiac"

    def detect(self, extraction_result: ExtractionResult) -> float:
        """Keyword-based detection with tiered scoring and positional weighting.

        Keywords in the report title/header count more than keywords in the
        comparison section (which may reference a different modality).
        """
        title, comparison, body = split_text_zones(extraction_result.full_text)

        strong_keywords = [
            "cta coronary",
            "coronary cta",
            "ct coronary angiography",
            "coronary ct angiography",
            "cardiac ct angiography",
            "ccta",
        ]
        moderate_keywords = [
            "calcium score",
            "agatston",
            "coronary artery calcium",
            "cac score",
            "coronary stenosis",
            "plaque burden",
            "coronary arteries",
            "left main",
            "lad",
            "lcx",
            "rca",
            "ct fractional flow reserve",
            "ct-ffr",
        ]
        weak_keywords = [
            "contrast enhanced",
            "gated ct",
            "prospective gating",
            "retrospective gating",
            "coronary",
            "stenosis",
            "plaque",
        ]

        # Negative keywords -- if these appear in title/body this is likely
        # a different cardiac study, not a CTA coronary.
        negative_keywords = [
            "cardiac mri",
            "echocardiogram",
            "catheterization",
            "angiogram",
        ]

        # Positional weighting: strong keywords in comparison-only don't
        # count as strong (e.g. "Comparison: CTA Coronary on ...").
        strong_title_or_body = 0
        strong_comparison_only = 0
        for k in strong_keywords:
            w = keyword_zone_weight(k, title, comparison, body)
            if w >= 1.0:
                strong_title_or_body += 1
            elif w > 0:
                strong_comparison_only += 1

        moderate_count = sum(1 for k in moderate_keywords
                            if keyword_zone_weight(k, title, comparison, body) >= 1.0)
        weak_count = sum(1 for k in weak_keywords
                         if keyword_zone_weight(k, title, comparison, body) >= 1.0)

        # Only title/body strong keywords earn the 0.7 base
        if strong_title_or_body > 0:
            base = 0.7
        elif moderate_count >= 3:
            base = 0.4
        elif moderate_count >= 1:
            base = 0.2
        elif strong_comparison_only > 0:
            # "cta coronary" only in comparison -- very weak signal
            base = 0.15
        else:
            base = 0.0

        bonus = min(0.3, moderate_count * 0.05 + weak_count * 0.02)
        score = min(1.0, base + bonus)

        # Negative penalty -- only count negative terms in title/body
        neg_count = sum(1 for k in negative_keywords
                        if keyword_zone_weight(k, title, comparison, body) >= 1.0)
        if neg_count > 0:
            score *= max(0.0, 1.0 - neg_count * 0.3)

        return score

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
        return CTA_GLOSSARY

    def get_prompt_context(self, extraction_result: ExtractionResult | None = None) -> dict:
        return {
            "specialty": "cardiology",
            "test_type": "cta_coronary",
            "category": "cardiac",
            "guidelines": "SCCT 2022 Guidelines for Coronary CTA",
            "explanation_style": (
                "Explain each measurement in plain language. "
                "Compare to normal ranges. Highlight any abnormalities. "
                "Avoid medical jargon where possible."
            ),
            "interpretation_rules": (
                "Report calcium score (Agatston) and percentile first, "
                "then each vessel (left main, LAD, LCx, RCA) with stenosis "
                "severity and plaque type (calcified, non-calcified, mixed). "
                "Classify stenosis per CAD-RADS."
            ),
        }

    def _extract_sections(self, text: str) -> list[ReportSection]:
        """Split report text into labeled sections."""
        section_headers = [
            r"CALCIUM\s+SCORE|CAC",
            r"LEFT\s+MAIN|LM\b",
            r"LEFT\s+ANTERIOR\s+DESCENDING|LAD\b",
            r"LEFT\s+CIRCUMFLEX|LCX\b|LCx\b",
            r"RIGHT\s+CORONARY|RCA\b",
            r"BYPASS\s+GRAFT",
            r"NON[- ]?CORONARY|EXTRACARDIAC",
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
