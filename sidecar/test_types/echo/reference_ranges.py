"""
ASE 2015 echocardiography reference ranges and severity classification.

Source: Lang RM, et al. "Recommendations for Cardiac Chamber Quantification
        by Echocardiography in Adults." JASE 2015;28:1-39.

Where sex-specific ranges exist, the more inclusive (union) range is used.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from api.analysis_models import AbnormalityDirection, SeverityStatus


@dataclass
class ClassificationResult:
    status: SeverityStatus
    direction: AbnormalityDirection
    reference_range_str: str


@dataclass
class RangeThresholds:
    normal_min: Optional[float] = None
    normal_max: Optional[float] = None
    mild_min: Optional[float] = None
    mild_max: Optional[float] = None
    moderate_min: Optional[float] = None
    moderate_max: Optional[float] = None
    severe_low: Optional[float] = None
    severe_high: Optional[float] = None
    unit: str = ""
    source: str = "ASE 2015 Guidelines"


# Sex-stratified reference ranges for key echo measurements
# Based on ASE 2015 Guidelines
SEX_STRATIFIED_RANGES: dict[str, dict[str, RangeThresholds]] = {
    # LVEF: Male >= 52%, Female >= 54%
    "LVEF": {
        "male": RangeThresholds(
            normal_min=52.0,
            mild_min=41.0,
            moderate_min=30.0,
            severe_low=30.0,
            unit="%",
        ),
        "female": RangeThresholds(
            normal_min=54.0,
            mild_min=41.0,
            moderate_min=30.0,
            severe_low=30.0,
            unit="%",
        ),
    },
    # LVIDd: Male 4.2-5.8, Female 3.8-5.2 cm
    "LVIDd": {
        "male": RangeThresholds(
            normal_min=4.2,
            normal_max=5.8,
            mild_max=6.1,
            moderate_max=6.8,
            severe_high=6.8,
            mild_min=3.9,
            moderate_min=3.5,
            severe_low=3.5,
            unit="cm",
        ),
        "female": RangeThresholds(
            normal_min=3.8,
            normal_max=5.2,
            mild_max=5.6,
            moderate_max=6.2,
            severe_high=6.2,
            mild_min=3.5,
            moderate_min=3.2,
            severe_low=3.2,
            unit="cm",
        ),
    },
    # LVIDs: Male 2.5-4.0, Female 2.2-3.5 cm
    "LVIDs": {
        "male": RangeThresholds(
            normal_min=2.5,
            normal_max=4.0,
            mild_max=4.4,
            moderate_max=5.0,
            severe_high=5.0,
            unit="cm",
        ),
        "female": RangeThresholds(
            normal_min=2.2,
            normal_max=3.5,
            mild_max=3.9,
            moderate_max=4.5,
            severe_high=4.5,
            unit="cm",
        ),
    },
    # LA diameter: Male 3.0-4.0, Female 2.7-3.8 cm
    "LA": {
        "male": RangeThresholds(
            normal_min=3.0,
            normal_max=4.0,
            mild_max=4.6,
            moderate_max=5.0,
            severe_high=5.0,
            unit="cm",
        ),
        "female": RangeThresholds(
            normal_min=2.7,
            normal_max=3.8,
            mild_max=4.2,
            moderate_max=4.6,
            severe_high=4.6,
            unit="cm",
        ),
    },
    # Aortic Root: Male 2.9-4.0, Female 2.5-3.5 cm
    "AoRoot": {
        "male": RangeThresholds(
            normal_min=2.9,
            normal_max=4.0,
            mild_max=4.3,
            moderate_max=4.7,
            severe_high=4.7,
            unit="cm",
        ),
        "female": RangeThresholds(
            normal_min=2.5,
            normal_max=3.5,
            mild_max=3.9,
            moderate_max=4.3,
            severe_high=4.3,
            unit="cm",
        ),
    },
}


REFERENCE_RANGES: dict[str, RangeThresholds] = {
    # --- LVEF ---
    # Normal >= 52% (male) / >= 54% (female). Using 52%.
    # Mildly abnormal: 41-51%, Moderately: 30-40%, Severely: <30%
    "LVEF": RangeThresholds(
        normal_min=52.0,
        mild_min=41.0,
        moderate_min=30.0,
        severe_low=30.0,
        unit="%",
    ),
    # --- LV Dimensions ---
    # LVIDd: Male 4.2-5.8, Female 3.8-5.2 -> union 3.8-5.8
    "LVIDd": RangeThresholds(
        normal_min=3.8,
        normal_max=5.8,
        mild_max=6.1,
        moderate_max=6.8,
        severe_high=6.8,
        mild_min=3.5,
        moderate_min=3.2,
        severe_low=3.2,
        unit="cm",
    ),
    # LVIDs: Male 2.5-4.0, Female 2.2-3.5 -> union 2.2-4.0
    "LVIDs": RangeThresholds(
        normal_min=2.2,
        normal_max=4.0,
        mild_max=4.3,
        moderate_max=5.0,
        severe_high=5.0,
        unit="cm",
    ),
    # IVSd: Normal 0.6-1.0
    "IVSd": RangeThresholds(
        normal_min=0.6,
        normal_max=1.0,
        mild_max=1.3,
        moderate_max=1.6,
        severe_high=1.7,
        unit="cm",
    ),
    # LVPWd: Normal 0.6-1.0
    "LVPWd": RangeThresholds(
        normal_min=0.6,
        normal_max=1.0,
        mild_max=1.3,
        moderate_max=1.6,
        severe_high=1.7,
        unit="cm",
    ),
    # --- Fractional Shortening ---
    "FS": RangeThresholds(
        normal_min=25.0,
        normal_max=43.0,
        mild_min=20.0,
        moderate_min=15.0,
        severe_low=15.0,
        unit="%",
    ),
    # --- Left Atrium ---
    # LA diameter: Male 3.0-4.0, Female 2.7-3.8 -> union 2.7-4.0
    "LA": RangeThresholds(
        normal_min=2.7,
        normal_max=4.0,
        mild_max=4.6,
        moderate_max=5.0,
        severe_high=5.0,
        unit="cm",
    ),
    # LA Volume Index: Normal < 34 mL/m2
    "LAVI": RangeThresholds(
        normal_max=34.0,
        mild_max=41.0,
        moderate_max=48.0,
        severe_high=48.0,
        unit="mL/m2",
    ),
    # --- Right Side ---
    # RV basal diameter: Normal 2.5-4.1
    "RVD": RangeThresholds(
        normal_min=2.5,
        normal_max=4.1,
        mild_max=4.5,
        moderate_max=5.0,
        severe_high=5.0,
        unit="cm",
    ),
    # RA area: Normal < 18 cm2
    "RAA": RangeThresholds(
        normal_max=18.0,
        mild_max=22.0,
        moderate_max=26.0,
        severe_high=26.0,
        unit="cm2",
    ),
    # --- Aortic Root ---
    # Male 2.9-4.0, Female 2.5-3.5 -> union 2.5-4.0
    "AoRoot": RangeThresholds(
        normal_min=2.5,
        normal_max=4.0,
        mild_max=4.3,
        moderate_max=4.7,
        severe_high=4.7,
        unit="cm",
    ),
    # --- Valvular ---
    # Aortic valve area: Normal > 2.0
    "AVA": RangeThresholds(
        normal_min=2.0,
        mild_min=1.5,
        moderate_min=1.0,
        severe_low=1.0,
        unit="cm2",
    ),
    # E/A ratio: Normal 0.8-2.0 (simplified, age-dependent)
    "E/A": RangeThresholds(
        normal_min=0.8,
        normal_max=2.0,
        unit="",
    ),
    # E/e' ratio: Normal < 8, indeterminate 8-14, elevated > 14
    "E/e'": RangeThresholds(
        normal_max=8.0,
        mild_max=14.0,
        severe_high=14.0,
        unit="",
    ),
    # TR velocity: Normal < 2.8 m/s
    "TRV": RangeThresholds(
        normal_max=2.8,
        mild_max=2.9,
        moderate_max=3.4,
        severe_high=3.5,
        unit="m/s",
    ),
    # --- Hemodynamics ---
    # RVSP: Normal < 35 mmHg
    "RVSP": RangeThresholds(
        normal_max=35.0,
        mild_max=45.0,
        moderate_max=60.0,
        severe_high=60.0,
        unit="mmHg",
    ),
    # --- Diastolic Function ---
    "DT": RangeThresholds(
        normal_min=160.0,
        normal_max=220.0,
        unit="ms",
    ),
    "IVRT": RangeThresholds(
        normal_min=50.0,
        normal_max=100.0,
        unit="ms",
    ),
    # e' septal: Normal >= 7 cm/s
    "e'_septal": RangeThresholds(
        normal_min=7.0,
        unit="cm/s",
    ),
    # e' lateral: Normal >= 10 cm/s
    "e'_lateral": RangeThresholds(
        normal_min=10.0,
        unit="cm/s",
    ),
    # TAPSE: Normal >= 1.7 cm
    "TAPSE": RangeThresholds(
        normal_min=1.7,
        unit="cm",
    ),
}


def _format_reference_range(rr: RangeThresholds) -> str:
    """Format reference range as a human-readable string."""
    unit = f" {rr.unit}" if rr.unit else ""
    if rr.normal_min is not None and rr.normal_max is not None:
        return f"{rr.normal_min}-{rr.normal_max}{unit}"
    elif rr.normal_min is not None:
        return f">= {rr.normal_min}{unit}"
    elif rr.normal_max is not None:
        return f"<= {rr.normal_max}{unit}"
    return "N/A"


def classify_measurement(
    abbreviation: str, value: float, gender: Optional[str] = None
) -> ClassificationResult:
    """Classify a measurement value against ASE reference ranges.

    If gender is provided and a sex-stratified range exists for this measurement,
    uses the sex-specific range; otherwise falls back to the union range.
    """
    rr: Optional[RangeThresholds] = None

    # Try sex-stratified range first if gender is provided
    if gender is not None:
        gender_key = gender.lower()
        if gender_key in ("f", "female"):
            gender_key = "female"
        elif gender_key in ("m", "male"):
            gender_key = "male"

        stratified = SEX_STRATIFIED_RANGES.get(abbreviation)
        if stratified is not None:
            rr = stratified.get(gender_key)

    # Fall back to union range
    if rr is None:
        rr = REFERENCE_RANGES.get(abbreviation)

    if rr is None:
        return ClassificationResult(
            status=SeverityStatus.UNDETERMINED,
            direction=AbnormalityDirection.NORMAL,
            reference_range_str="No reference range available",
        )

    ref_str = _format_reference_range(rr)

    # Check above normal
    if rr.normal_max is not None and value > rr.normal_max:
        direction = AbnormalityDirection.ABOVE_NORMAL
        status = _classify_above(value, rr)
        return ClassificationResult(
            status=status, direction=direction, reference_range_str=ref_str
        )

    # Check below normal
    if rr.normal_min is not None and value < rr.normal_min:
        direction = AbnormalityDirection.BELOW_NORMAL
        status = _classify_below(value, rr)
        return ClassificationResult(
            status=status, direction=direction, reference_range_str=ref_str
        )

    return ClassificationResult(
        status=SeverityStatus.NORMAL,
        direction=AbnormalityDirection.NORMAL,
        reference_range_str=ref_str,
    )


def _classify_above(value: float, rr: RangeThresholds) -> SeverityStatus:
    """Classify a value that is above the normal range."""
    if rr.severe_high is not None and value >= rr.severe_high:
        return SeverityStatus.SEVERELY_ABNORMAL
    if rr.moderate_max is not None and value > rr.moderate_max:
        return SeverityStatus.SEVERELY_ABNORMAL
    if rr.mild_max is not None and value > rr.mild_max:
        return SeverityStatus.MODERATELY_ABNORMAL
    return SeverityStatus.MILDLY_ABNORMAL


def _classify_below(value: float, rr: RangeThresholds) -> SeverityStatus:
    """Classify a value that is below the normal range."""
    if rr.severe_low is not None and value <= rr.severe_low:
        return SeverityStatus.SEVERELY_ABNORMAL
    if rr.moderate_min is not None and value < rr.moderate_min:
        return SeverityStatus.SEVERELY_ABNORMAL
    if rr.mild_min is not None and value < rr.mild_min:
        return SeverityStatus.MODERATELY_ABNORMAL
    return SeverityStatus.MILDLY_ABNORMAL
