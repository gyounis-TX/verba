"""
Regex-based measurement extraction for transesophageal echocardiogram (TEE) reports.

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
    # --- LV Function ---
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
    # --- LAA ---
    MeasurementDef(
        name="LAA Emptying Velocity",
        abbreviation="LAA_vel",
        unit="cm/s",
        patterns=[
            rf"(?i)LAA.*velocity{_SEP}{_NUM}\s*(?:cm\/s|m\/s)?",
            rf"(?i)LAA.*emptying{_SEP}{_NUM}\s*(?:cm\/s|m\/s)?",
            rf"(?i)appendage.*velocity{_SEP}{_NUM}\s*(?:cm\/s|m\/s)?",
        ],
        value_min=10.0,
        value_max=100.0,
    ),
    # --- Left Atrium ---
    MeasurementDef(
        name="LA Area",
        abbreviation="LA_area",
        unit="cm2",
        patterns=[
            rf"(?i)LA\s+area{_SEP}{_NUM}\s*(?:cm2|cm\u00b2)?",
            rf"(?i)left\s+atrial\s+area{_SEP}{_NUM}\s*(?:cm2|cm\u00b2)?",
        ],
        value_min=5.0,
        value_max=40.0,
    ),
    MeasurementDef(
        name="LA Volume Index",
        abbreviation="LAVI",
        unit="mL/m2",
        patterns=[
            rf"(?i)(?:LA\s+volume\s+index|LAVI){_SEP}{_NUM}\s*(?:ml\/m2|mL\/m2|ml\/m\u00b2)?",
            rf"(?i)left\s+atrial\s+volume\s+index{_SEP}{_NUM}",
        ],
        value_min=10.0,
        value_max=80.0,
    ),
    # --- Valvular ---
    MeasurementDef(
        name="Aortic Valve Area",
        abbreviation="AVA",
        unit="cm2",
        patterns=[
            rf"(?i)(?:aortic\s+valve\s+area|AVA){_SEP}{_NUM}\s*(?:cm2|cm\u00b2)?",
        ],
        value_min=0.3,
        value_max=5.0,
    ),
    MeasurementDef(
        name="Mitral Valve Area",
        abbreviation="MV_area",
        unit="cm2",
        patterns=[
            rf"(?i)mitral\s+valve\s+area{_SEP}{_NUM}\s*(?:cm2|cm\u00b2)?",
            rf"(?i)MVA{_SEP}{_NUM}\s*(?:cm2|cm\u00b2)?",
        ],
        value_min=0.5,
        value_max=6.0,
    ),
    MeasurementDef(
        name="Mean AV Gradient",
        abbreviation="AV_gradient_mean",
        unit="mmHg",
        patterns=[
            rf"(?i)mean.*gradient{_SEP}{_NUM}\s*(?:mmHg)?",
            rf"(?i)AV.*mean.*gradient{_SEP}{_NUM}\s*(?:mmHg)?",
        ],
        value_min=2.0,
        value_max=80.0,
    ),
    MeasurementDef(
        name="Peak AV Gradient",
        abbreviation="AV_gradient_peak",
        unit="mmHg",
        patterns=[
            rf"(?i)peak.*gradient{_SEP}{_NUM}\s*(?:mmHg)?",
            rf"(?i)AV.*peak.*gradient{_SEP}{_NUM}\s*(?:mmHg)?",
        ],
        value_min=5.0,
        value_max=150.0,
    ),
    # --- Aortic Root ---
    MeasurementDef(
        name="Aortic Root Diameter",
        abbreviation="AoRoot",
        unit="cm",
        patterns=[
            rf"(?i)aort(?:a|ic)\s+(?:root|sinus){_SEP}{_NUM}\s*(?:cm|mm)?",
            rf"(?i)sinus\s+(?:of\s+)?valsalva{_SEP}{_NUM}\s*(?:cm|mm)?",
            rf"(?i)Ao\s+root{_SEP}{_NUM}\s*(?:cm|mm)?",
        ],
        value_min=1.0,
        value_max=6.0,
    ),
    MeasurementDef(
        name="Ascending Aorta",
        abbreviation="Ascending_Ao",
        unit="cm",
        patterns=[
            rf"(?i)ascending\s+aorta{_SEP}{_NUM}\s*(?:cm|mm)?",
            rf"(?i)ascending\s+aortic.*diam{_SEP}{_NUM}\s*(?:cm|mm)?",
        ],
        value_min=1.5,
        value_max=6.0,
    ),
    # --- Hemodynamics ---
    MeasurementDef(
        name="RV Systolic Pressure",
        abbreviation="RVSP",
        unit="mmHg",
        patterns=[
            rf"(?i)RVSP{_SEP}{_NUM}\s*(?:mmHg)?",
            rf"(?i)(?:RV|right\s+ventricular)\s+systolic\s+pressure{_SEP}{_NUM}\s*(?:mmHg)?",
            rf"(?i)(?:PA|pulmonary\s+artery)\s+systolic\s+pressure{_SEP}{_NUM}\s*(?:mmHg)?",
            rf"(?i)PASP{_SEP}{_NUM}\s*(?:mmHg)?",
        ],
        value_min=10.0,
        value_max=120.0,
    ),
    MeasurementDef(
        name="TAPSE",
        abbreviation="TAPSE",
        unit="cm",
        patterns=[
            rf"(?i)TAPSE{_SEP}{_NUM}\s*(?:cm|mm)?",
            rf"(?i)tricuspid\s+annular\s+plane\s+systolic\s+excursion{_SEP}{_NUM}",
        ],
        value_min=0.5,
        value_max=4.0,
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
