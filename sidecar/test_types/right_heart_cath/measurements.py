"""
Regex-based measurement extraction for right heart catheterization reports.

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
    # --- Right Atrial Pressures ---
    MeasurementDef(
        name="RA Mean Pressure",
        abbreviation="RA_mean",
        unit="mmHg",
        patterns=[
            rf"(?i)RA\s+mean{_SEP}{_NUM}\s*(?:mmHg)?",
            rf"(?i)right\s+atri(?:um|al).*?mean{_SEP}{_NUM}\s*(?:mmHg)?",
            rf"(?i)RA\s+pressure.*?mean{_SEP}{_NUM}\s*(?:mmHg)?",
            rf"(?i)mean\s+RA{_SEP}{_NUM}\s*(?:mmHg)?",
        ],
        value_min=0.0,
        value_max=30.0,
    ),
    MeasurementDef(
        name="RA A Wave",
        abbreviation="RA_a",
        unit="mmHg",
        patterns=[
            rf"(?i)RA\s+a\s+wave{_SEP}{_NUM}\s*(?:mmHg)?",
            rf"(?i)RA.*?a\s*={_SEP}{_NUM}\s*(?:mmHg)?",
            rf"(?i)a\s+wave{_SEP}{_NUM}\s*(?:mmHg)?",
        ],
        value_min=0.0,
        value_max=25.0,
    ),
    MeasurementDef(
        name="RA V Wave",
        abbreviation="RA_v",
        unit="mmHg",
        patterns=[
            rf"(?i)RA\s+v\s+wave{_SEP}{_NUM}\s*(?:mmHg)?",
            rf"(?i)RA.*?v\s*={_SEP}{_NUM}\s*(?:mmHg)?",
        ],
        value_min=0.0,
        value_max=25.0,
    ),
    # --- Pulmonary Artery Pressures ---
    MeasurementDef(
        name="PA Systolic",
        abbreviation="PA_sys",
        unit="mmHg",
        patterns=[
            rf"(?i)PA\s+systolic{_SEP}{_NUM}\s*(?:mmHg)?",
            rf"(?i)pulmonary\s+artery\s+systolic{_SEP}{_NUM}\s*(?:mmHg)?",
            rf"(?i)PA\s+sys{_SEP}{_NUM}\s*(?:mmHg)?",
            rf"(?i)PASP{_SEP}{_NUM}\s*(?:mmHg)?",
        ],
        value_min=10.0,
        value_max=120.0,
    ),
    MeasurementDef(
        name="PA Diastolic",
        abbreviation="PA_dia",
        unit="mmHg",
        patterns=[
            rf"(?i)PA\s+diastolic{_SEP}{_NUM}\s*(?:mmHg)?",
            rf"(?i)pulmonary\s+artery\s+diastolic{_SEP}{_NUM}\s*(?:mmHg)?",
            rf"(?i)PA\s+dia{_SEP}{_NUM}\s*(?:mmHg)?",
            rf"(?i)PADP{_SEP}{_NUM}\s*(?:mmHg)?",
        ],
        value_min=2.0,
        value_max=50.0,
    ),
    MeasurementDef(
        name="PA Mean",
        abbreviation="PA_mean",
        unit="mmHg",
        patterns=[
            rf"(?i)PA\s+mean{_SEP}{_NUM}\s*(?:mmHg)?",
            rf"(?i)mean\s+PA{_SEP}{_NUM}\s*(?:mmHg)?",
            rf"(?i)mPAP{_SEP}{_NUM}\s*(?:mmHg)?",
            rf"(?i)mean\s+pulmonary\s+artery{_SEP}{_NUM}\s*(?:mmHg)?",
        ],
        value_min=5.0,
        value_max=80.0,
    ),
    # --- Wedge Pressure ---
    MeasurementDef(
        name="Pulmonary Capillary Wedge Pressure",
        abbreviation="PCWP",
        unit="mmHg",
        patterns=[
            rf"(?i)PCWP{_SEP}{_NUM}\s*(?:mmHg)?",
            rf"(?i)wedge{_SEP}{_NUM}\s*(?:mmHg)?",
            rf"(?i)pulmonary\s+capillary\s+wedge{_SEP}{_NUM}\s*(?:mmHg)?",
            rf"(?i)PAWP{_SEP}{_NUM}\s*(?:mmHg)?",
        ],
        value_min=0.0,
        value_max=40.0,
    ),
    # --- Cardiac Output / Index ---
    MeasurementDef(
        name="Cardiac Output",
        abbreviation="CO",
        unit="L/min",
        patterns=[
            rf"(?i)cardiac\s+output{_SEP}{_NUM}\s*(?:L\/min|l\/min)?",
            rf"(?i)CO{_SEP}{_NUM}\s*(?:L\/min|l\/min)?",
            rf"(?i)CO.*?L\/min{_SEP}{_NUM}",
        ],
        value_min=1.0,
        value_max=12.0,
    ),
    MeasurementDef(
        name="Cardiac Index",
        abbreviation="CI",
        unit="L/min/m2",
        patterns=[
            rf"(?i)cardiac\s+index{_SEP}{_NUM}\s*(?:L\/min\/m2|l\/min\/m\u00b2)?",
            rf"(?i)CI{_SEP}{_NUM}\s*(?:L\/min\/m2|l\/min\/m\u00b2)?",
            rf"(?i)CI.*?L\/min{_SEP}{_NUM}",
        ],
        value_min=0.5,
        value_max=6.0,
    ),
    # --- Vascular Resistance ---
    MeasurementDef(
        name="Pulmonary Vascular Resistance",
        abbreviation="PVR",
        unit="Wood units",
        patterns=[
            rf"(?i)PVR{_SEP}{_NUM}\s*(?:Wood\s+units?|WU)?",
            rf"(?i)pulmonary\s+vascular\s+resistance{_SEP}{_NUM}\s*(?:Wood\s+units?|WU)?",
        ],
        value_min=0.0,
        value_max=15.0,
    ),
    MeasurementDef(
        name="Systemic Vascular Resistance",
        abbreviation="SVR",
        unit="dynes",
        patterns=[
            rf"(?i)SVR{_SEP}{_NUM}\s*(?:dynes|dyn)?",
            rf"(?i)systemic\s+vascular\s+resistance{_SEP}{_NUM}\s*(?:dynes|dyn)?",
        ],
        value_min=400.0,
        value_max=3000.0,
    ),
    # --- Gradients ---
    MeasurementDef(
        name="Transpulmonary Gradient",
        abbreviation="TPG",
        unit="mmHg",
        patterns=[
            rf"(?i)TPG{_SEP}{_NUM}\s*(?:mmHg)?",
            rf"(?i)transpulmonary\s+gradient{_SEP}{_NUM}\s*(?:mmHg)?",
        ],
        value_min=0.0,
        value_max=30.0,
    ),
    MeasurementDef(
        name="Diastolic Pressure Gradient",
        abbreviation="DPG",
        unit="mmHg",
        patterns=[
            rf"(?i)DPG{_SEP}{_NUM}\s*(?:mmHg)?",
            rf"(?i)diastolic\s+pressure\s+gradient{_SEP}{_NUM}\s*(?:mmHg)?",
        ],
        value_min=-5.0,
        value_max=20.0,
    ),
    # --- Oxygen Saturations ---
    MeasurementDef(
        name="Mixed Venous O2 Saturation",
        abbreviation="MVO2",
        unit="%",
        patterns=[
            rf"(?i)mixed\s+venous{_SEP}{_NUM}\s*%?",
            rf"(?i)MvO2{_SEP}{_NUM}\s*%?",
            rf"(?i)SvO2{_SEP}{_NUM}\s*%?",
            rf"(?i)PA\s+sat{_SEP}{_NUM}\s*%?",
            rf"(?i)PA\s+O2{_SEP}{_NUM}\s*%?",
        ],
        value_min=40.0,
        value_max=85.0,
    ),
    # --- Fick ---
    MeasurementDef(
        name="Fick Cardiac Output",
        abbreviation="Fick_CO",
        unit="L/min",
        patterns=[
            rf"(?i)Fick.*?cardiac\s+output{_SEP}{_NUM}\s*(?:L\/min|l\/min)?",
            rf"(?i)Fick\s+CO{_SEP}{_NUM}\s*(?:L\/min|l\/min)?",
        ],
        value_min=1.0,
        value_max=12.0,
    ),
]


def extract_measurements(
    full_text: str,
    pages: list[PageExtractionResult],
) -> list[RawMeasurement]:
    """Extract all recognized measurements from the report text."""
    results: list[RawMeasurement] = []
    seen: set[str] = set()

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
