"""
DEXA (Bone Density) measurement extraction.

Extracts T-scores, Z-scores, and BMD values from DEXA bone density reports.
Uses WHO classification for osteoporosis diagnosis.
"""

from __future__ import annotations

import re
from typing import Optional

from api.analysis_models import (
    AbnormalityDirection,
    ParsedMeasurement,
    SeverityStatus,
)


# Reference ranges based on WHO classification
DEXA_REFERENCE_RANGES = {
    "T_SCORE_SPINE": {
        "normal_min": -1.0,
        "unit": "",
        "source": "WHO Classification",
    },
    "T_SCORE_FEMORAL_NECK": {
        "normal_min": -1.0,
        "unit": "",
        "source": "WHO Classification",
    },
    "T_SCORE_TOTAL_HIP": {
        "normal_min": -1.0,
        "unit": "",
        "source": "WHO Classification",
    },
    "T_SCORE": {
        "normal_min": -1.0,
        "unit": "",
        "source": "WHO Classification",
    },
    "Z_SCORE": {
        "normal_min": -2.0,
        "unit": "",
        "source": "Age-matched reference",
    },
}


DEXA_GLOSSARY = {
    "T-score": (
        "Compares your bone density to the average healthy young adult. "
        "A score of 0 means your bone density equals the average. "
        "Negative numbers mean lower bone density."
    ),
    "Z-score": (
        "Compares your bone density to others of your age, sex, and body size. "
        "Useful for identifying if low bone density may be due to something other than aging."
    ),
    "BMD": (
        "Bone Mineral Density — a measure of how much calcium and other minerals "
        "are in a section of bone."
    ),
    "Osteopenia": (
        "Bone density lower than normal but not low enough to be osteoporosis. "
        "T-score between -1.0 and -2.5."
    ),
    "Osteoporosis": (
        "A condition where bones become weak and brittle. "
        "T-score of -2.5 or lower."
    ),
    "Lumbar spine": "The lower back region of the spine (L1-L4).",
    "Femoral neck": "The narrow section of the thigh bone just below the ball of the hip joint.",
    "Total hip": "The entire hip region including femoral neck and greater trochanter.",
}


def _classify_t_score(value: float) -> tuple[SeverityStatus, AbnormalityDirection, str]:
    """Classify T-score using WHO criteria.

    WHO Classification:
    - T-score >= -1.0: Normal
    - T-score -1.0 to -2.5: Osteopenia (mildly abnormal)
    - T-score <= -2.5: Osteoporosis (moderately abnormal)
    - T-score <= -2.5 with fracture: Severe osteoporosis
    """
    if value >= -1.0:
        return SeverityStatus.NORMAL, AbnormalityDirection.NORMAL, ">= -1.0"
    elif value > -2.5:
        return SeverityStatus.MILDLY_ABNORMAL, AbnormalityDirection.BELOW_NORMAL, ">= -1.0"
    else:
        return SeverityStatus.MODERATELY_ABNORMAL, AbnormalityDirection.BELOW_NORMAL, ">= -1.0"


def _classify_z_score(value: float) -> tuple[SeverityStatus, AbnormalityDirection, str]:
    """Classify Z-score.

    Z-score < -2.0 may indicate secondary cause of bone loss.
    """
    if value >= -2.0:
        return SeverityStatus.NORMAL, AbnormalityDirection.NORMAL, ">= -2.0"
    else:
        return SeverityStatus.MILDLY_ABNORMAL, AbnormalityDirection.BELOW_NORMAL, ">= -2.0"


def extract_dexa_measurements(
    text: str, gender: Optional[str] = None
) -> list[ParsedMeasurement]:
    """Extract DEXA bone density measurements from report text.

    Looks for:
    - Site-specific T-scores (spine, femoral neck, total hip)
    - Generic T-scores
    - Z-scores
    - BMD values (g/cm2)
    """
    measurements: list[ParsedMeasurement] = []
    text_lower = text.lower()

    # Site-specific T-score patterns
    site_patterns = [
        # Lumbar spine
        (
            r"(?:lumbar\s+spine|l1[- ]?l4|spine)\s*(?:t[- ]?score|t\s*=)\s*[:\s]*(-?\d+\.?\d*)",
            "Lumbar Spine T-Score",
            "T_SCORE_SPINE",
        ),
        # Femoral neck
        (
            r"(?:femoral\s+neck|fem\.?\s*neck)\s*(?:t[- ]?score|t\s*=)\s*[:\s]*(-?\d+\.?\d*)",
            "Femoral Neck T-Score",
            "T_SCORE_FEMORAL_NECK",
        ),
        # Total hip
        (
            r"(?:total\s+hip|hip)\s*(?:t[- ]?score|t\s*=)\s*[:\s]*(-?\d+\.?\d*)",
            "Total Hip T-Score",
            "T_SCORE_TOTAL_HIP",
        ),
    ]

    for pattern, name, abbrev in site_patterns:
        matches = re.finditer(pattern, text_lower, re.IGNORECASE)
        for match in matches:
            try:
                value = float(match.group(1))
                status, direction, ref_range = _classify_t_score(value)
                measurements.append(
                    ParsedMeasurement(
                        name=name,
                        abbreviation=abbrev,
                        value=value,
                        unit="",
                        status=status,
                        direction=direction,
                        reference_range=ref_range,
                        raw_text=match.group(0),
                        page_number=None,
                    )
                )
            except ValueError:
                continue

    # Generic T-score pattern (if no site-specific found)
    if not any(m.abbreviation.startswith("T_SCORE") for m in measurements):
        t_score_pattern = r"t[- ]?score\s*[:\s]*(-?\d+\.?\d*)"
        for match in re.finditer(t_score_pattern, text_lower):
            try:
                value = float(match.group(1))
                status, direction, ref_range = _classify_t_score(value)
                measurements.append(
                    ParsedMeasurement(
                        name="T-Score",
                        abbreviation="T_SCORE",
                        value=value,
                        unit="",
                        status=status,
                        direction=direction,
                        reference_range=ref_range,
                        raw_text=match.group(0),
                        page_number=None,
                    )
                )
            except ValueError:
                continue

    # Z-score pattern
    z_score_pattern = r"z[- ]?score\s*[:\s]*(-?\d+\.?\d*)"
    for match in re.finditer(z_score_pattern, text_lower):
        try:
            value = float(match.group(1))
            status, direction, ref_range = _classify_z_score(value)
            measurements.append(
                ParsedMeasurement(
                    name="Z-Score",
                    abbreviation="Z_SCORE",
                    value=value,
                    unit="",
                    status=status,
                    direction=direction,
                    reference_range=ref_range,
                    raw_text=match.group(0),
                    page_number=None,
                )
            )
        except ValueError:
            continue

    # BMD pattern (g/cm2)
    bmd_pattern = r"bmd\s*[:\s]*(\d+\.?\d*)\s*(?:g/cm2|g/cm²)?"
    for match in re.finditer(bmd_pattern, text_lower):
        try:
            value = float(match.group(1))
            # BMD alone doesn't have standard thresholds without T-score context
            measurements.append(
                ParsedMeasurement(
                    name="Bone Mineral Density",
                    abbreviation="BMD",
                    value=value,
                    unit="g/cm²",
                    status=SeverityStatus.UNDETERMINED,
                    direction=AbnormalityDirection.NORMAL,
                    reference_range="Varies by site and demographics",
                    raw_text=match.group(0),
                    page_number=None,
                )
            )
        except ValueError:
            continue

    return measurements
