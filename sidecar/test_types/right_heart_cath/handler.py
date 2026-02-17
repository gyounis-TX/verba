from __future__ import annotations

import re

from api.models import ExtractionResult
from api.analysis_models import ParsedMeasurement, ParsedReport, ReportSection
from test_types.base import BaseTestType, split_text_zones, keyword_zone_weight
from .glossary import RHC_GLOSSARY
from .measurements import extract_measurements
from .reference_ranges import REFERENCE_RANGES, classify_measurement


class RightHeartCathHandler(BaseTestType):

    @property
    def test_type_id(self) -> str:
        return "right_heart_cath"

    @property
    def display_name(self) -> str:
        return "Right Heart Catheterization"

    @property
    def keywords(self) -> list[str]:
        return [
            "right heart catheterization",
            "right heart cath",
            "swan-ganz",
            "swan ganz",
            "pulmonary artery catheterization",
            "pulmonary capillary wedge",
            "pcwp",
            "cardiac output",
            "cardiac index",
            "pulmonary vascular resistance",
            "pvr",
            "transpulmonary gradient",
            "fick",
            "thermodilution",
            "mixed venous",
            "pa pressure",
            "pulmonary artery pressure",
            "right atrial pressure",
            "wedge pressure",
            "mean pa",
            "diastolic pa",
            "systolic pa",
            "oxygen saturation",
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
            "right heart catheterization",
            "right heart cath",
            "swan-ganz",
            "swan ganz",
            "pulmonary artery catheterization",
        ]
        moderate_keywords = [
            "pulmonary capillary wedge",
            "pcwp",
            "cardiac output",
            "cardiac index",
            "pulmonary vascular resistance",
            "pvr",
            "transpulmonary gradient",
            "fick",
            "thermodilution",
            "mixed venous",
            "pa pressure",
            "pulmonary artery pressure",
            "right atrial pressure",
        ]
        weak_keywords = [
            "wedge pressure",
            "mean pa",
            "diastolic pa",
            "systolic pa",
            "oxygen saturation",
        ]

        # Left heart cath terms -- if these appear, this is likely a left
        # heart cath or coronary angiogram, not an isolated RHC.
        lhc_negatives = [
            "coronary angiogram",
            "coronary angiography",
            "lvedp",
            "ventriculogram",
            "pci",
            "stent",
        ]

        # Positional weighting: strong keywords in comparison-only don't
        # count as strong (e.g. "Comparison: Right heart cath on ...").
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
            # "right heart cath" only in comparison -- very weak signal
            base = 0.15
        else:
            base = 0.0

        bonus = min(0.3, moderate_count * 0.05 + weak_count * 0.02)
        score = min(1.0, base + bonus)

        # LHC negative penalty -- only count LHC terms in title/body
        lhc_count = sum(1 for k in lhc_negatives
                        if keyword_zone_weight(k, title, comparison, body) >= 1.0)
        if lhc_count > 0:
            score *= max(0.0, 1.0 - lhc_count * 0.3)

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
        return RHC_GLOSSARY

    def get_prompt_context(self, extraction_result: ExtractionResult | None = None) -> dict:
        return {
            "specialty": "cardiology/pulmonary",
            "test_type": "right_heart_catheterization",
            "category": "cardiac",
            "guidelines": "ESC/ERS 2022 Pulmonary Hypertension Guidelines",
            "explanation_style": (
                "Explain each measurement in plain language. "
                "Compare to normal ranges. Highlight any abnormalities. "
                "Avoid medical jargon where possible."
            ),
            "interpretation_rules": (
                "Report RA pressure first, then PA pressures "
                "(systolic/diastolic/mean), then PCWP, then cardiac "
                "output/index, then PVR. Classify pulmonary hypertension "
                "if mPAP > 20 mmHg."
            ),
        }

    def _extract_sections(self, text: str) -> list[ReportSection]:
        """Split report text into labeled sections."""
        section_headers = [
            r"RIGHT\s+ATRIUM|RA\s+PRESSURE",
            r"PULMONARY\s+ARTERY|PA\s+PRESSURE",
            r"WEDGE|PCWP|PAWP",
            r"CARDIAC\s+OUTPUT",
            r"OXYGEN\s+SATURATION|O2\s+SAT",
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
