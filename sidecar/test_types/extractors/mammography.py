"""
Mammography measurement extraction.

Extracts BI-RADS category and related findings from mammography reports.
"""

from __future__ import annotations

import re
from typing import Optional

from api.analysis_models import (
    AbnormalityDirection,
    ParsedMeasurement,
    SeverityStatus,
)


MAMMOGRAPHY_REFERENCE_RANGES = {
    "BIRADS": {
        "normal_max": 2,
        "unit": "",
        "source": "ACR BI-RADS 5th Edition",
    },
}


MAMMOGRAPHY_GLOSSARY = {
    "BI-RADS": (
        "Breast Imaging Reporting and Data System — a standardized way to "
        "describe mammogram findings and recommend next steps."
    ),
    "BI-RADS 0": "Incomplete — additional imaging needed for a complete assessment.",
    "BI-RADS 1": "Negative — no significant findings. Routine screening recommended.",
    "BI-RADS 2": (
        "Benign — non-cancerous finding such as a simple cyst. "
        "Routine screening recommended."
    ),
    "BI-RADS 3": (
        "Probably Benign — very low probability of cancer (<2%). "
        "Short-interval follow-up recommended."
    ),
    "BI-RADS 4": (
        "Suspicious — abnormality that may be cancer. Biopsy recommended. "
        "Subdivided into 4A (low), 4B (moderate), 4C (high suspicion)."
    ),
    "BI-RADS 5": (
        "Highly Suggestive of Malignancy — high probability of cancer (>95%). "
        "Biopsy strongly recommended."
    ),
    "BI-RADS 6": "Known Biopsy-Proven Malignancy — cancer confirmed by prior biopsy.",
    "Calcifications": (
        "Small calcium deposits in breast tissue. Most are benign, "
        "but certain patterns may require further evaluation."
    ),
    "Mass": (
        "A three-dimensional space-occupying lesion. Described by shape, "
        "margin, and density to assess likelihood of being benign or malignant."
    ),
    "Architectural distortion": (
        "An abnormal arrangement of breast tissue that may indicate an "
        "underlying abnormality."
    ),
    "Asymmetry": (
        "A difference in the appearance of corresponding areas of breast tissue. "
        "May be normal or require further evaluation."
    ),
}


def _classify_birads(category: int) -> tuple[SeverityStatus, AbnormalityDirection, str]:
    """Classify BI-RADS category.

    Categories:
    0 - Incomplete (needs additional imaging)
    1 - Negative (normal)
    2 - Benign (normal)
    3 - Probably Benign (<2% cancer risk) - mildly abnormal
    4 - Suspicious (2-95% cancer risk) - moderately abnormal
    5 - Highly Suggestive of Malignancy (>95%) - severely abnormal
    6 - Known Malignancy - severely abnormal
    """
    if category == 0:
        # Incomplete - needs more imaging
        return SeverityStatus.UNDETERMINED, AbnormalityDirection.NORMAL, "1-2 (normal)"
    elif category in (1, 2):
        # Normal or benign
        return SeverityStatus.NORMAL, AbnormalityDirection.NORMAL, "1-2 (normal)"
    elif category == 3:
        # Probably benign - short interval follow-up
        return SeverityStatus.MILDLY_ABNORMAL, AbnormalityDirection.ABOVE_NORMAL, "1-2 (normal)"
    elif category == 4:
        # Suspicious - biopsy recommended
        return SeverityStatus.MODERATELY_ABNORMAL, AbnormalityDirection.ABOVE_NORMAL, "1-2 (normal)"
    elif category in (5, 6):
        # Highly suspicious or known malignancy
        return SeverityStatus.SEVERELY_ABNORMAL, AbnormalityDirection.ABOVE_NORMAL, "1-2 (normal)"
    else:
        return SeverityStatus.UNDETERMINED, AbnormalityDirection.NORMAL, "1-2 (normal)"


def extract_mammography_measurements(
    text: str, gender: Optional[str] = None
) -> list[ParsedMeasurement]:
    """Extract mammography findings from report text.

    Looks for:
    - BI-RADS category (0-6)
    - Subcategories (4A, 4B, 4C)
    """
    measurements: list[ParsedMeasurement] = []

    # BI-RADS patterns - multiple formats
    # "BI-RADS Category 3", "BIRADS: 4", "BI-RADS 2", "Category 4A"
    birads_patterns = [
        r"bi[- ]?rads\s*(?:category|cat\.?)?\s*[:\s]*([0-6])(?:\s*([abc]))?",
        r"birads\s*[:\s]*([0-6])(?:\s*([abc]))?",
        r"(?:assessment|category)\s*[:\s]*bi[- ]?rads\s*([0-6])(?:\s*([abc]))?",
        r"(?:final\s+)?assessment\s*[:\s]*([0-6])(?:\s*([abc]))?",
    ]

    found_birads = False
    for pattern in birads_patterns:
        for match in re.finditer(pattern, text.lower()):
            try:
                category = int(match.group(1))
                subcategory = match.group(2).upper() if match.group(2) else None

                status, direction, ref_range = _classify_birads(category)

                # Build display name
                if subcategory:
                    name = f"BI-RADS {category}{subcategory}"
                    display_value = float(f"{category}.{ord(subcategory) - ord('A') + 1}")
                else:
                    name = f"BI-RADS {category}"
                    display_value = float(category)

                measurements.append(
                    ParsedMeasurement(
                        name=name,
                        abbreviation="BIRADS",
                        value=display_value,
                        unit="",
                        status=status,
                        direction=direction,
                        reference_range=ref_range,
                        raw_text=match.group(0),
                        page_number=None,
                    )
                )
                found_birads = True
                break  # Only take first match per pattern
            except (ValueError, IndexError):
                continue

        if found_birads:
            break  # Only need one BI-RADS value

    return measurements
