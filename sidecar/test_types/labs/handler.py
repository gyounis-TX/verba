from __future__ import annotations

import re

from api.models import ExtractionResult
from api.analysis_models import ParsedMeasurement, ParsedReport, PriorValue, ReportSection
from test_types.base import BaseTestType
from .glossary import LAB_GLOSSARY
from .measurements import extract_measurements
from .reference_ranges import REFERENCE_RANGES, classify_measurement


class LabResultsHandler(BaseTestType):

    @property
    def test_type_id(self) -> str:
        return "lab_results"

    @property
    def display_name(self) -> str:
        return "Blood Lab Results"

    @property
    def keywords(self) -> list[str]:
        return [
            "laboratory results",
            "lab results",
            "complete blood count",
            "comprehensive metabolic panel",
            "basic metabolic panel",
            "lipid panel",
            "cbc",
            "cmp",
            "bmp",
            "glucose",
            "creatinine",
            "hemoglobin",
            "hematocrit",
            "cholesterol",
            "triglycerides",
            "tsh",
            "hba1c",
            "ferritin",
            "blood test", "blood work", "blood panel",
            "serum chemistry", "coagulation", "pt/inr",
            "vitamin d", "vitamin b12", "troponin", "bnp",
            "psa", "sed rate", "esr", "crp", "hemogram",
        ]

    @property
    def category(self) -> str:
        return "lab"

    def detect(self, extraction_result: ExtractionResult) -> float:
        """Keyword-based detection with tiered scoring."""
        text = extraction_result.full_text.lower()

        strong_keywords = [
            "laboratory results",
            "lab results",
            "lab report",
            "complete blood count",
            "comprehensive metabolic panel",
            "basic metabolic panel",
            "lipid panel",
            "chemistry panel",
            "metabolic panel",
            "thyroid panel",
            "iron studies",
            "hematology",
            "haematology",
            "cbc with differential",
            "complete haemogram",
            "complete hemogram",
        ]
        moderate_keywords = [
            "cbc",
            "cmp",
            "bmp",
            "glucose",
            "creatinine",
            "hemoglobin",
            "haemoglobin",
            "hematocrit",
            "haematocrit",
            "wbc",
            "rbc",
            "potassium",
            "sodium",
            "cholesterol",
            "triglycerides",
            "tsh",
            "hba1c",
            "a1c",
            "alt",
            "ast",
            "bun",
            "egfr",
            "ferritin",
            "albumin",
            "bilirubin",
            "platelet",
            "hdl",
            "ldl",
            "alkaline phosphatase",
            "haemogram",
            "leucocyte",
            "erythrocyte",
        ]
        weak_keywords = [
            "mg/dl",
            "g/dl",
            "meq/l",
            "k/ul",
            "u/l",
            "ng/ml",
            "ng/dl",
            "gm/dl",
            "gm/ dl",
            "reference range",
            "flag",
            "abnormal",
            "out of range",
            "/cumm",
            "lakh/",
        ]

        # Negative keywords — if these appear the report is likely imaging/radiology,
        # not a blood lab.  Penalise heavily so the correct handler (or the
        # "unknown type" path) wins instead.
        imaging_keywords = [
            "calcium score",
            "agatston",
            "coronary artery calcium",
            "coronary calcium",
            "ct scan",
            "ct chest",
            "computed tomography",
            "axial images",
            "non-contrast",
            "gated ct",
            "cardiac ct",
            "hounsfield",
            "lung fields",
            "pulmonary",
            "cardiac mri",
            "echocardiogram",
            "ultrasound",
            "doppler",
            "x-ray",
            "xray",
            "radiograph",
            "mri",
            "magnetic resonance",
            "nuclear medicine",
            "perfusion",
            "angiography",
            "catheterization",
        ]
        imaging_count = sum(1 for k in imaging_keywords if k in text)

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
        score = min(1.0, base + bonus)

        # Heavily penalise when imaging keywords are present
        if imaging_count > 0:
            score = score * max(0.0, 1.0 - imaging_count * 0.3)

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

        raw_measurements = extract_measurements(
            text, extraction_result.pages, extraction_result.tables
        )

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
                    prior_values=[
                        PriorValue(value=pv.value, time_label=pv.time_label)
                        for pv in m.prior_values
                    ],
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
        return LAB_GLOSSARY

    def get_prompt_context(self, extraction_result: ExtractionResult | None = None) -> dict:
        return {
            "specialty": "laboratory medicine",
            "test_type": "blood_lab_results",
            "category": "lab",
            "guidelines": "Standard clinical laboratory reference ranges for adult patients",
            "explanation_style": (
                "Group related analytes (kidney: BUN+Creatinine+eGFR; "
                "liver: AST+ALT+ALP+Bilirubin; blood sugar: Glucose+HbA1c). "
                "Highlight abnormal values. For borderline values, note they may not "
                "be clinically significant. When multiple related values are abnormal, "
                "explain the pattern (e.g., low iron+low ferritin+high TIBC = iron deficiency).\n\n"
                "IMPORTANT: Ignore any pre-printed interpretations, suggestions, or "
                "recommendations from the lab report PDF itself. The lab often prints "
                "automated boilerplate like 'High LDL — consider lifestyle changes' or "
                "'Desirable: <200'. Your interpretation must come solely from the "
                "structured measurements and their statuses provided below, not from "
                "the lab's own commentary."
            ),
            "interpretation_rules": (
                "Group findings by organ system: kidney function first (BUN, "
                "Creatinine, eGFR), then liver panel (AST, ALT, ALP, Bilirubin), "
                "then glucose metabolism (Glucose, A1C), then lipids (Cholesterol, "
                "LDL, HDL, Triglycerides), then thyroid (TSH, T4), then iron "
                "studies (Iron, Ferritin, TIBC), then CBC (WBC, RBC, HGB, HCT, "
                "Platelets, MCV)."
            ),
        }

    def _extract_sections(self, text: str) -> list[ReportSection]:
        """Split report text into labeled sections.

        NOTE: We deliberately exclude COMMENT / INTERPRETATION / NOTE /
        IMPRESSION / ADVISED headers. Lab PDFs often print automated
        interpretations and suggestions (e.g. "High LDL — consider lifestyle
        changes") that should NOT be forwarded to the LLM. The physician
        wants Explify's own clinical interpretation, not the lab's boilerplate.
        """
        section_headers = [
            r"CHEMISTRY|CHEM\s+PANEL",
            r"HA?EMATOLOGY",
            r"(?:COMPLETE\s+)?(?:BLOOD\s+COUNT|HA?EMOGRAM)|CBC",
            r"(?:COMPREHENSIVE|BASIC)\s+METABOLIC\s+PANEL|CMP|BMP",
            r"LIPID\s+(?:PANEL|PROFILE)",
            r"THYROID\s+(?:PANEL|FUNCTION|STUDIES)",
            r"IRON\s+STUDIES|IRON\s+PANEL",
            r"LIVER\s+(?:FUNCTION|PANEL|ENZYMES)|HEPATIC\s+(?:FUNCTION|PANEL)",
            r"RENAL\s+(?:FUNCTION|PANEL)|KIDNEY\s+FUNCTION",
            r"URINALYSIS|UA\b",
            r"DIFFERENTIAL\s+LE[U]?COCYTE\s+COUNT",
            r"PERIPHERAL\s+SMEAR",
            # Clinical context sections — forwarded to LLM for richer interpretation
            r"INDICATION(?:S)?(?:\s+FOR\s+(?:TEST|STUDY|PROCEDURE))?",
            r"REASON\s+FOR\s+(?:TEST|STUDY|ORDER|REFERRAL)",
            r"CLINICAL\s+(?:HISTORY|INDICATION|INFORMATION|CONTEXT)",
            r"CONCLUSION(?:S)?",
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

    def _extract_findings(self, _text: str) -> list[str]:
        """Lab PDFs often print automated interpretations and suggestions
        (e.g. "High LDL — consider lifestyle changes"). These should NOT be
        forwarded to the LLM — the physician wants Explify's own clinical
        interpretation based on the structured measurements, not the lab's
        boilerplate. Return empty list.
        """
        return []
