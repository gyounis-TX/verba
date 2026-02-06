from __future__ import annotations

import re

from api.models import ExtractionResult
from api.analysis_models import ParsedMeasurement, ParsedReport, ReportSection
from test_types.base import BaseTestType
from .glossary import STRESS_GLOSSARY
from .measurements import extract_measurements
from .reference_ranges import REFERENCE_RANGES, classify_measurement


class StressTestHandler(BaseTestType):

    @property
    def test_type_id(self) -> str:
        return "stress_test"

    @property
    def display_name(self) -> str:
        return "Stress Test"

    @property
    def keywords(self) -> list[str]:
        return [
            "stress test",
            "exercise stress",
            "treadmill test",
            "exercise tolerance test",
            "bruce protocol",
            "modified bruce",
            "exercise treadmill",
            "cardiac stress",
            "exercise ecg",
            "exercise ekg",
            "exercise electrocardiogram",
            "graded exercise test",
            "mets",
            "peak heart rate",
            "target heart rate",
            "st depression",
            "st segment",
            "duke treadmill",
            "chronotropic",
            "rate pressure product",
            "exercise capacity",
        ]

    @property
    def category(self) -> str:
        return "cardiac"

    def detect(self, extraction_result: ExtractionResult) -> float:
        """Keyword-based detection with tiered scoring."""
        text = extraction_result.full_text.lower()

        strong_keywords = [
            "stress test",
            "exercise stress test",
            "exercise treadmill test",
            "exercise tolerance test",
            "treadmill stress",
            "cardiac stress test",
            "exercise stress echocardiogram",
            "bruce protocol",
            "modified bruce protocol",
            "graded exercise test",
            "exercise ecg",
            "exercise ekg",
            "exercise electrocardiogram",
            "treadmill exercise test",
        ]
        moderate_keywords = [
            "mets achieved",
            "mets attained",
            "metabolic equivalents",
            "peak heart rate",
            "target heart rate",
            "max predicted heart rate",
            "mphr",
            "% predicted",
            "st depression",
            "st elevation",
            "st segment changes",
            "st changes",
            "duke treadmill score",
            "rate pressure product",
            "double product",
            "chronotropic",
            "exercise capacity",
            "exercise duration",
            "treadmill time",
            "exercise stage",
            "recovery phase",
            "peak exercise",
        ]
        weak_keywords = [
            "treadmill",
            "bruce",
            "angina",
            "chest pain during exercise",
            "dyspnea on exertion",
            "exercise",
            "mets",
            "arrhythmia",
            "pvcs",
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
        return STRESS_GLOSSARY

    _PHARMA_AGENTS = ["lexiscan", "adenosine", "regadenoson"]

    def _is_pharmacological(self, text: str) -> bool:
        """Return True if the report mentions a pharmacological stress agent."""
        lower = text.lower()
        return any(agent in lower for agent in self._PHARMA_AGENTS)

    def get_prompt_context(self, extraction_result: ExtractionResult | None = None) -> dict:
        text = extraction_result.full_text if extraction_result else ""
        is_pharma = self._is_pharmacological(text)

        if is_pharma:
            explanation_style = (
                "This is a pharmacological stress test (not exercise-based). "
                "IMPORTANT pharmacological stress rules:\n"
                "- Do NOT mention heart rate response to stress AT ALL. "
                "Heart rate response to exercise is invalid with pharmacological "
                "stress. Do NOT say anything like 'your heart rate response was "
                "lower than expected' or 'reaching X% of predicted maximum'. "
                "Do NOT comment on target heart rate, predicted maximum "
                "heart rate, or % of max predicted heart rate. The predicted "
                "maximum heart rate calculation does not apply because heart "
                "rate does not increase significantly with pharmacological stress.\n"
                "- Do NOT state that the heart rate response may limit "
                "interpretation of the EKG stress test. That caveat only "
                "applies to exercise-based tests.\n"
                "- If the test is inconclusive due to ST/T wave abnormalities, "
                "simply state that without attributing it to heart rate response.\n"
                "Focus on perfusion findings, wall motion, ejection fraction, "
                "ECG changes, and overall interpretation "
                "(normal, abnormal, equivocal). "
                "Explain what the results mean for the patient's heart health."
            )
        else:
            explanation_style = (
                "Focus on exercise capacity (METs), heart rate response "
                "(% of max predicted), blood pressure response, ECG changes "
                "(ST depression/elevation), and overall interpretation "
                "(positive, negative, equivocal, non-diagnostic). "
                "Comment on whether the patient reached target heart rate "
                "only because they exercised on a treadmill. "
                "Explain what the results mean for the patient's heart health."
            )

        return {
            "specialty": "cardiology",
            "test_type": "pharmacological_stress_test" if is_pharma else "exercise_stress_test",
            "category": "cardiac",
            "guidelines": "ACC/AHA 2002 Guideline Update for Exercise Testing",
            "explanation_style": explanation_style,
        }

    def _extract_sections(self, text: str) -> list[ReportSection]:
        """Split report text into labeled sections."""
        section_headers = [
            r"INDICATION|REASON\s+FOR\s+(?:TEST|STUDY)",
            r"PROTOCOL|EXERCISE\s+PROTOCOL|PROCEDURE",
            r"BASELINE|RESTING|PRE[- ]?EXERCISE",
            r"EXERCISE\s+(?:DATA|RESPONSE|RESULTS|PHASE)",
            r"HEMODYNAMIC\s+(?:DATA|RESPONSE)",
            r"ECG\s+(?:FINDINGS|CHANGES|RESPONSE|INTERPRETATION)",
            r"EKG\s+(?:FINDINGS|CHANGES|RESPONSE|INTERPRETATION)",
            r"ELECTROCARDIOGRAPHIC\s+(?:FINDINGS|CHANGES|RESPONSE)",
            r"ST\s+(?:SEGMENT\s+)?(?:ANALYSIS|CHANGES)",
            r"SYMPTOMS|SYMPTOM\s+RESPONSE",
            r"ARRHYTHMIA|RHYTHM",
            r"RECOVERY|POST[- ]?EXERCISE",
            r"CONCLUSION|IMPRESSION|SUMMARY|INTERPRETATION|FINDINGS",
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
        """Extract conclusion/impression/interpretation lines."""
        findings: list[str] = []
        findings_re = re.compile(
            r"(?:CONCLUSION|IMPRESSION|SUMMARY|INTERPRETATION|FINDINGS)\s*[:\-]?\s*\n"
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
