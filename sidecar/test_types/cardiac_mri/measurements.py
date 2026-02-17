"""
Regex-based measurement extraction for cardiac MRI reports.

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
    # --- LV Volumes ---
    MeasurementDef(
        name="LV End-Diastolic Volume",
        abbreviation="LVEDV",
        unit="mL",
        patterns=[
            rf"(?i)LVEDV{_SEP}{_NUM}\s*(?:mL|ml)?",
            rf"(?i)LV\s+end[- ]?diastolic\s+volume{_SEP}{_NUM}\s*(?:mL|ml)?",
            rf"(?i)LV\s+EDV{_SEP}{_NUM}\s*(?:mL|ml)?",
        ],
        value_min=50.0,
        value_max=400.0,
    ),
    MeasurementDef(
        name="LV End-Systolic Volume",
        abbreviation="LVESV",
        unit="mL",
        patterns=[
            rf"(?i)LVESV{_SEP}{_NUM}\s*(?:mL|ml)?",
            rf"(?i)LV\s+end[- ]?systolic\s+volume{_SEP}{_NUM}\s*(?:mL|ml)?",
            rf"(?i)LV\s+ESV{_SEP}{_NUM}\s*(?:mL|ml)?",
        ],
        value_min=10.0,
        value_max=250.0,
    ),
    # --- LV Indexed Volumes ---
    MeasurementDef(
        name="LV End-Diastolic Volume Index",
        abbreviation="LVEDVi",
        unit="mL/m2",
        patterns=[
            rf"(?i)LVEDVi{_SEP}{_NUM}\s*(?:mL\/m2|ml\/m2|mL\/m\u00b2)?",
            rf"(?i)LVEDV\s+index{_SEP}{_NUM}\s*(?:mL\/m2|ml\/m2|mL\/m\u00b2)?",
            rf"(?i)LV\s+EDV\s+index{_SEP}{_NUM}\s*(?:mL\/m2|ml\/m2|mL\/m\u00b2)?",
        ],
        value_min=30.0,
        value_max=200.0,
    ),
    MeasurementDef(
        name="LV End-Systolic Volume Index",
        abbreviation="LVESVi",
        unit="mL/m2",
        patterns=[
            rf"(?i)LVESVi{_SEP}{_NUM}\s*(?:mL\/m2|ml\/m2|mL\/m\u00b2)?",
            rf"(?i)LVESV\s+index{_SEP}{_NUM}\s*(?:mL\/m2|ml\/m2|mL\/m\u00b2)?",
            rf"(?i)LV\s+ESV\s+index{_SEP}{_NUM}\s*(?:mL\/m2|ml\/m2|mL\/m\u00b2)?",
        ],
        value_min=10.0,
        value_max=120.0,
    ),
    # --- LV Mass ---
    MeasurementDef(
        name="LV Mass",
        abbreviation="LVMass",
        unit="g",
        patterns=[
            rf"(?i)LV\s+mass{_SEP}{_NUM}\s*(?:g|grams?)?",
            rf"(?i)left\s+ventricular\s+mass{_SEP}{_NUM}\s*(?:g|grams?)?",
        ],
        value_min=50.0,
        value_max=400.0,
    ),
    MeasurementDef(
        name="LV Mass Index",
        abbreviation="LVMi",
        unit="g/m2",
        patterns=[
            rf"(?i)LV\s+mass\s+index{_SEP}{_NUM}\s*(?:g\/m2|g\/m\u00b2)?",
            rf"(?i)LVMi{_SEP}{_NUM}\s*(?:g\/m2|g\/m\u00b2)?",
        ],
        value_min=25.0,
        value_max=200.0,
    ),
    # --- RV Function & Volumes ---
    MeasurementDef(
        name="RV Ejection Fraction",
        abbreviation="RVEF",
        unit="%",
        patterns=[
            rf"(?i)RVEF{_SEP}{_NUM}\s*%?",
            rf"(?i)RV\s+ejection\s+fraction{_SEP}{_NUM}\s*%?",
        ],
        value_min=10.0,
        value_max=80.0,
    ),
    MeasurementDef(
        name="RV End-Diastolic Volume",
        abbreviation="RVEDV",
        unit="mL",
        patterns=[
            rf"(?i)RVEDV{_SEP}{_NUM}\s*(?:mL|ml)?",
            rf"(?i)RV\s+end[- ]?diastolic\s+volume{_SEP}{_NUM}\s*(?:mL|ml)?",
        ],
        value_min=50.0,
        value_max=400.0,
    ),
    MeasurementDef(
        name="RV End-Systolic Volume",
        abbreviation="RVESV",
        unit="mL",
        patterns=[
            rf"(?i)RVESV{_SEP}{_NUM}\s*(?:mL|ml)?",
            rf"(?i)RV\s+end[- ]?systolic\s+volume{_SEP}{_NUM}\s*(?:mL|ml)?",
        ],
        value_min=10.0,
        value_max=200.0,
    ),
    # --- Tissue Characterization ---
    MeasurementDef(
        name="Native T1",
        abbreviation="NativeT1",
        unit="ms",
        patterns=[
            rf"(?i)native\s+T1{_SEP}{_NUM}\s*(?:ms|msec)?",
            rf"(?i)T1\s+value{_SEP}{_NUM}\s*(?:ms|msec)?",
            rf"(?i)T1\s+mapping{_SEP}{_NUM}\s*(?:ms|msec)?",
        ],
        value_min=800.0,
        value_max=1400.0,
    ),
    MeasurementDef(
        name="T2 Value",
        abbreviation="T2",
        unit="ms",
        patterns=[
            rf"(?i)T2\s+value{_SEP}{_NUM}\s*(?:ms|msec)?",
            rf"(?i)T2\s+mapping{_SEP}{_NUM}\s*(?:ms|msec)?",
            rf"(?i)T2\s+time{_SEP}{_NUM}\s*(?:ms|msec)?",
        ],
        value_min=30.0,
        value_max=80.0,
    ),
    MeasurementDef(
        name="Extracellular Volume",
        abbreviation="ECV",
        unit="%",
        patterns=[
            rf"(?i)ECV{_SEP}{_NUM}\s*%?",
            rf"(?i)extracellular\s+volume{_SEP}{_NUM}\s*%?",
        ],
        value_min=15.0,
        value_max=60.0,
    ),
    MeasurementDef(
        name="Scar Burden",
        abbreviation="ScarBurden",
        unit="%",
        patterns=[
            rf"(?i)scar\s+burden{_SEP}{_NUM}\s*%?",
            rf"(?i)(?:%\s*)?scar{_SEP}{_NUM}\s*%?",
            rf"(?i)LGE\s*.*?{_NUM}\s*%",
            rf"(?i)%\s*LGE{_SEP}{_NUM}\s*%?",
            rf"(?i)%\s*scar{_SEP}{_NUM}\s*%?",
        ],
        value_min=0.0,
        value_max=100.0,
    ),
    # --- Left Atrium ---
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
