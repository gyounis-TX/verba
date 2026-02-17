"""
Regex-based measurement extraction for pulmonary function test reports.

Uses a data-driven approach: each measurement is defined with multiple
regex patterns, sanity bounds, and metadata. Patterns use named capture
groups (?P<value>...) for the numeric value.

NOTE: PFT reports commonly show both absolute values and % predicted.
Both are extracted when possible using separate measurement definitions.
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
    # --- Spirometry: Absolute Values ---
    MeasurementDef(
        name="Forced Expiratory Volume in 1 Second",
        abbreviation="FEV1",
        unit="L",
        patterns=[
            rf"(?i)(?:FEV1|FEV-1|FEV\s+1){_SEP}{_NUM}\s*(?:L|liters?|litres?)(?!\s*[/%])",
            rf"(?i)(?:FEV1|FEV-1|FEV\s+1)\s+(?:is\s+|of\s+)?{_NUM}\s*(?:L|liters?|litres?)(?!\s*[/%])",
        ],
        value_min=0.3,
        value_max=7.0,
    ),
    MeasurementDef(
        name="FEV1 % Predicted",
        abbreviation="FEV1_pct",
        unit="%",
        patterns=[
            rf"(?i)(?:FEV1|FEV-1|FEV\s+1)\s*%\s*pred(?:icted)?{_SEP}{_NUM}\s*%?",
            rf"(?i)(?:FEV1|FEV-1|FEV\s+1)\s+predicted\s*%?{_SEP}{_NUM}\s*%?",
            rf"(?i)(?:FEV1|FEV-1|FEV\s+1)\s*%\s*pred{_SEP}{_NUM}\s*%?",
            rf"(?i)(?:FEV1|FEV-1|FEV\s+1).*?{_NUM}\s*%\s*(?:of\s+)?pred(?:icted)?",
        ],
        value_min=10.0,
        value_max=150.0,
    ),
    MeasurementDef(
        name="Forced Vital Capacity",
        abbreviation="FVC",
        unit="L",
        patterns=[
            rf"(?i)FVC{_SEP}{_NUM}\s*(?:L|liters?|litres?)(?!\s*[/%])",
            rf"(?i)FVC\s+(?:is\s+|of\s+)?{_NUM}\s*(?:L|liters?|litres?)(?!\s*[/%])",
        ],
        value_min=0.5,
        value_max=8.0,
    ),
    MeasurementDef(
        name="FVC % Predicted",
        abbreviation="FVC_pct",
        unit="%",
        patterns=[
            rf"(?i)FVC\s*%\s*pred(?:icted)?{_SEP}{_NUM}\s*%?",
            rf"(?i)FVC\s+predicted\s*%?{_SEP}{_NUM}\s*%?",
            rf"(?i)FVC.*?{_NUM}\s*%\s*(?:of\s+)?pred(?:icted)?",
        ],
        value_min=10.0,
        value_max=150.0,
    ),
    MeasurementDef(
        name="FEV1/FVC Ratio",
        abbreviation="FEV1_FVC",
        unit="%",
        patterns=[
            rf"(?i)(?:FEV1/FVC|FEV1:FVC)\s*(?:ratio)?{_SEP}{_NUM}\s*%?",
            rf"(?i)(?:FEV1/FVC|FEV1:FVC)\s+(?:is\s+|of\s+)?{_NUM}\s*%?",
        ],
        value_min=20.0,
        value_max=100.0,
    ),
    # --- Diffusing Capacity ---
    MeasurementDef(
        name="Diffusing Capacity",
        abbreviation="DLCO",
        unit="mL/min/mmHg",
        patterns=[
            rf"(?i)(?:DLCO|diffusing\s+capacity|diffusion\s+capacity|gas\s+transfer){_SEP}{_NUM}\s*(?:mL/min/mmHg|ml/min/mmhg)?",
            rf"(?i)(?:DLCO|diffusing\s+capacity)\s+(?:is\s+|of\s+)?{_NUM}\s*(?:mL/min/mmHg)?",
        ],
        value_min=5.0,
        value_max=50.0,
    ),
    MeasurementDef(
        name="DLCO % Predicted",
        abbreviation="DLCO_pct",
        unit="%",
        patterns=[
            rf"(?i)DLCO\s*%\s*pred(?:icted)?{_SEP}{_NUM}\s*%?",
            rf"(?i)DLCO.*?{_NUM}\s*%\s*(?:of\s+)?pred(?:icted)?",
        ],
        value_min=10.0,
        value_max=150.0,
    ),
    # --- Lung Volumes ---
    MeasurementDef(
        name="Total Lung Capacity",
        abbreviation="TLC",
        unit="L",
        patterns=[
            rf"(?i)(?:TLC|total\s+lung\s+capacity){_SEP}{_NUM}\s*(?:L|liters?|litres?)(?!\s*[/%])",
        ],
        value_min=1.0,
        value_max=10.0,
    ),
    MeasurementDef(
        name="TLC % Predicted",
        abbreviation="TLC_pct",
        unit="%",
        patterns=[
            rf"(?i)TLC\s*%\s*pred(?:icted)?{_SEP}{_NUM}\s*%?",
            rf"(?i)(?:TLC|total\s+lung\s+capacity).*?{_NUM}\s*%\s*(?:of\s+)?pred(?:icted)?",
        ],
        value_min=30.0,
        value_max=150.0,
    ),
    MeasurementDef(
        name="Residual Volume",
        abbreviation="RV",
        unit="L",
        patterns=[
            rf"(?i)residual\s+volume{_SEP}{_NUM}\s*(?:L|liters?|litres?)(?!\s*[/%])",
            rf"(?i)(?<![A-Za-z])RV{_SEP}{_NUM}\s*(?:L|liters?|litres?)(?!\s*[/%])",
        ],
        value_min=0.5,
        value_max=6.0,
    ),
    MeasurementDef(
        name="RV % Predicted",
        abbreviation="RV_pct",
        unit="%",
        patterns=[
            rf"(?i)RV\s*%\s*pred(?:icted)?{_SEP}{_NUM}\s*%?",
            rf"(?i)residual\s+volume\s*%?\s*pred(?:icted)?{_SEP}{_NUM}\s*%?",
            rf"(?i)residual\s+volume.*?{_NUM}\s*%\s*(?:of\s+)?pred(?:icted)?",
        ],
        value_min=30.0,
        value_max=250.0,
    ),
    MeasurementDef(
        name="Functional Residual Capacity",
        abbreviation="FRC",
        unit="L",
        patterns=[
            rf"(?i)(?:FRC|functional\s+residual(?:\s+capacity)?){_SEP}{_NUM}\s*(?:L|liters?|litres?)(?!\s*[/%])",
        ],
        value_min=1.0,
        value_max=7.0,
    ),
    # --- Flow Rates ---
    MeasurementDef(
        name="Peak Expiratory Flow",
        abbreviation="PEF",
        unit="L/s",
        patterns=[
            rf"(?i)(?:PEF|peak\s*(?:expiratory)?\s*flow){_SEP}{_NUM}\s*(?:L/s|L/sec|l/s)?",
        ],
        value_min=1.0,
        value_max=15.0,
    ),
    MeasurementDef(
        name="Mid-Expiratory Flow",
        abbreviation="FEF25_75",
        unit="L/s",
        patterns=[
            rf"(?i)(?:FEF25-75|FEF\s*25-75|FEF25[-\u201375]+){_SEP}{_NUM}\s*(?:L/s|L/sec|l/s)?",
            rf"(?i)mid[- ]?expiratory\s+flow{_SEP}{_NUM}\s*(?:L/s|L/sec|l/s)?",
        ],
        value_min=0.3,
        value_max=8.0,
    ),
    MeasurementDef(
        name="FEF25-75 % Predicted",
        abbreviation="FEF25_75_pct",
        unit="%",
        patterns=[
            rf"(?i)(?:FEF25-75|FEF\s*25-75)\s*%\s*pred(?:icted)?{_SEP}{_NUM}\s*%?",
            rf"(?i)(?:FEF25-75|FEF\s*25-75).*?{_NUM}\s*%\s*(?:of\s+)?pred(?:icted)?",
        ],
        value_min=10.0,
        value_max=150.0,
    ),
    # --- Post-Bronchodilator Values ---
    MeasurementDef(
        name="Post-BD FEV1",
        abbreviation="FEV1_post",
        unit="L",
        patterns=[
            rf"(?i)post[- ]?(?:bronchodilator|BD)\s+(?:FEV1|FEV-1|FEV\s+1){_SEP}{_NUM}\s*(?:L|liters?|litres?)?",
            rf"(?i)post[- ]?(?:bronchodilator|BD).*?(?:FEV1|FEV-1){_SEP}{_NUM}\s*(?:L|liters?|litres?)?",
        ],
        value_min=0.3,
        value_max=7.0,
    ),
    MeasurementDef(
        name="Post-BD FVC",
        abbreviation="FVC_post",
        unit="L",
        patterns=[
            rf"(?i)post[- ]?(?:bronchodilator|BD)\s+FVC{_SEP}{_NUM}\s*(?:L|liters?|litres?)?",
            rf"(?i)post[- ]?(?:bronchodilator|BD).*?FVC{_SEP}{_NUM}\s*(?:L|liters?|litres?)?",
        ],
        value_min=0.5,
        value_max=8.0,
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

                # Handle FEV1/FVC ratio that may be expressed as a decimal (0.2-1.0)
                # Convert to percentage for consistency
                if mdef.abbreviation == "FEV1_FVC" and value < 1.0:
                    value = round(value * 100, 1)

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
