"""
Regex-based measurement extraction for CTA Coronary reports.

Uses a data-driven approach: each measurement is defined with multiple
regex patterns, sanity bounds, and metadata. Patterns use named capture
groups (?P<value>...) for the numeric value.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from api.models import PageExtractionResult


@dataclass
class RawMeasurement:
    name: str
    abbreviation: str
    value: float
    unit: str
    raw_text: str
    page_number: Optional[int] = None


@dataclass
class MeasurementDef:
    """Definition of a measurement to extract."""

    name: str
    abbreviation: str
    unit: str
    patterns: list[str]
    value_min: float = 0.0
    value_max: float = 999.0


_NUM = r"(?P<value>\d+\.?\d*)"
_SEP = r"[\s:=]+\s*"

MEASUREMENT_DEFS: list[MeasurementDef] = [
    # --- Coronary Artery Calcium ---
    MeasurementDef(
        name="Coronary Artery Calcium Score",
        abbreviation="CAC_score",
        unit="AU",
        patterns=[
            rf"(?i)Agatston{_SEP}{_NUM}",
            rf"(?i)calcium\s+score{_SEP}{_NUM}",
            rf"(?i)CAC\s+score{_SEP}{_NUM}",
            rf"(?i)total\s+calcium{_SEP}{_NUM}",
            rf"(?i)coronary\s+calcium{_SEP}{_NUM}",
        ],
        value_min=0.0,
        value_max=5000.0,
    ),
    MeasurementDef(
        name="CAC Percentile",
        abbreviation="CAC_percentile",
        unit="%",
        patterns=[
            rf"(?i)percentile{_SEP}{_NUM}\s*%?",
            rf"(?i)CAC.*percentile{_SEP}{_NUM}\s*%?",
        ],
        value_min=0.0,
        value_max=100.0,
    ),
    # --- Coronary Stenosis ---
    MeasurementDef(
        name="Left Main Stenosis",
        abbreviation="LM_stenosis",
        unit="%",
        patterns=[
            rf"(?i)left\s+main.*?{_NUM}\s*%",
            rf"(?i)LM.*stenosis.*?{_NUM}\s*%",
            rf"(?i)LMCA.*?{_NUM}\s*%",
        ],
        value_min=0.0,
        value_max=100.0,
    ),
    MeasurementDef(
        name="LAD Stenosis",
        abbreviation="LAD_stenosis",
        unit="%",
        patterns=[
            rf"(?i)LAD.*?{_NUM}\s*%",
            rf"(?i)LAD.*stenosis.*?{_NUM}\s*%",
            rf"(?i)left\s+anterior\s+descending.*?{_NUM}\s*%",
        ],
        value_min=0.0,
        value_max=100.0,
    ),
    MeasurementDef(
        name="LCx Stenosis",
        abbreviation="LCx_stenosis",
        unit="%",
        patterns=[
            rf"(?i)LCx.*?{_NUM}\s*%",
            rf"(?i)circumflex.*?{_NUM}\s*%",
            rf"(?i)LCx.*stenosis.*?{_NUM}\s*%",
        ],
        value_min=0.0,
        value_max=100.0,
    ),
    MeasurementDef(
        name="RCA Stenosis",
        abbreviation="RCA_stenosis",
        unit="%",
        patterns=[
            rf"(?i)RCA.*?{_NUM}\s*%",
            rf"(?i)right\s+coronary.*?{_NUM}\s*%",
            rf"(?i)RCA.*stenosis.*?{_NUM}\s*%",
        ],
        value_min=0.0,
        value_max=100.0,
    ),
    # --- LV Function (gated CT) ---
    MeasurementDef(
        name="Left Ventricular Ejection Fraction",
        abbreviation="LVEF",
        unit="%",
        patterns=[
            rf"(?i)(?:LVEF|EF){_SEP}{_NUM}\s*%?",
            rf"(?i)ejection\s+fraction{_SEP}{_NUM}\s*%?",
            rf"(?i)(?:LVEF|EF|ejection\s+fraction)\s+(?:is\s+|of\s+|estimated\s+(?:at\s+)?)?{_NUM}\s*%?",
        ],
        value_min=5.0,
        value_max=95.0,
    ),
    # --- CT-FFR ---
    MeasurementDef(
        name="CT-FFR",
        abbreviation="CT_FFR",
        unit="ratio",
        patterns=[
            rf"(?i)CT-FFR{_SEP}{_NUM}",
            rf"(?i)FFR.*CT{_SEP}{_NUM}",
            rf"(?i)FFRCT{_SEP}{_NUM}",
        ],
        value_min=0.0,
        value_max=1.0,
    ),
]

# EF range pattern: "LVEF 55-60%" or "EF: 55 - 60 %"
_EF_RANGE_RE = re.compile(
    r"(?i)(?:LVEF|EF|ejection\s+fraction)"
    r"[\s:=]+\s*"
    r"(\d+\.?\d*)\s*[-\u2013to]+\s*(\d+\.?\d*)\s*%?",
)


def extract_measurements(
    full_text: str,
    pages: list[PageExtractionResult],
) -> list[RawMeasurement]:
    """Extract all recognized measurements from the report text."""
    results: list[RawMeasurement] = []
    seen: set[str] = set()

    # Special case: EF range ("LVEF 55-60%") -> take midpoint
    ef_range_match = _EF_RANGE_RE.search(full_text)
    if ef_range_match:
        low = float(ef_range_match.group(1))
        high = float(ef_range_match.group(2))
        if 5.0 <= low <= 95.0 and 5.0 <= high <= 95.0 and low < high:
            midpoint = (low + high) / 2.0
            page_num = _find_page(ef_range_match.group(), pages)
            results.append(
                RawMeasurement(
                    name="Left Ventricular Ejection Fraction",
                    abbreviation="LVEF",
                    value=round(midpoint, 1),
                    unit="%",
                    raw_text=ef_range_match.group().strip(),
                    page_number=page_num,
                )
            )
            seen.add("LVEF")

    for mdef in MEASUREMENT_DEFS:
        if mdef.abbreviation in seen:
            continue

        for pattern in mdef.patterns:
            match = re.search(pattern, full_text)
            if match:
                try:
                    value = float(match.group("value"))
                except (ValueError, IndexError):
                    continue

                if not (mdef.value_min <= value <= mdef.value_max):
                    continue

                page_num = _find_page(match.group(), pages)
                results.append(
                    RawMeasurement(
                        name=mdef.name,
                        abbreviation=mdef.abbreviation,
                        value=value,
                        unit=mdef.unit,
                        raw_text=match.group().strip(),
                        page_number=page_num,
                    )
                )
                seen.add(mdef.abbreviation)
                break

    return results


def _find_page(
    snippet: str,
    pages: list[PageExtractionResult],
) -> Optional[int]:
    """Find which page contains the matched text snippet."""
    normalized = " ".join(snippet.split())
    for page in pages:
        page_normalized = " ".join(page.text.split())
        if normalized in page_normalized:
            return page.page_number
    return None
