"""
TEE reference ranges and severity classification.

Sources:
  - ASE/SCA 2013 TEE Guidelines
  - ASE 2015 Chamber Quantification Guidelines (shared cardiac measurements)
  - ASE 2017 Valvular Regurgitation Guidelines
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
    source: str = "ASE/SCA 2013 TEE Guidelines"


# Sex-stratified reference ranges for key measurements
# Based on ASE 2015 Guidelines (shared with echo)
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
    # --- LAA ---
    # LAA Emptying Velocity: Normal >= 40 cm/s
    # Low <40 suggests thromboembolic risk, very low <20 high risk
    "LAA_vel": RangeThresholds(
        normal_min=40.0,
        mild_min=20.0,
        severe_low=20.0,
        unit="cm/s",
        source="ASE/SCA 2013 TEE Guidelines",
    ),
    # --- Left Atrium ---
    # LA Area: Normal <= 20 cm2
    "LA_area": RangeThresholds(
        normal_max=20.0,
        mild_max=25.0,
        moderate_max=30.0,
        severe_high=30.0,
        unit="cm2",
    ),
    # LA Volume Index: Normal < 34 mL/m2
    "LAVI": RangeThresholds(
        normal_max=34.0,
        mild_max=41.0,
        moderate_max=48.0,
        severe_high=48.0,
        unit="mL/m2",
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
    # Mitral valve area: Normal >= 4.0 cm2
    # Mild stenosis 1.5-4.0, Moderate 1.0-1.5, Severe <1.0
    "MV_area": RangeThresholds(
        normal_min=4.0,
        mild_min=1.5,
        moderate_min=1.0,
        severe_low=1.0,
        unit="cm2",
    ),
    # Mean AV Gradient: Normal < 20 mmHg
    # Mild 20-39, Moderate 40-59, Severe >= 60 (native valve)
    "AV_gradient_mean": RangeThresholds(
        normal_max=20.0,
        mild_max=39.0,
        moderate_max=59.0,
        severe_high=60.0,
        unit="mmHg",
    ),
    # Peak AV Gradient: Normal < 36 mmHg
    "AV_gradient_peak": RangeThresholds(
        normal_max=36.0,
        mild_max=50.0,
        moderate_max=80.0,
        severe_high=80.0,
        unit="mmHg",
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
    # Ascending Aorta: Normal 2.0-3.7 cm
    # Dilated >3.7, Aneurysmal >4.5
    "Ascending_Ao": RangeThresholds(
        normal_min=2.0,
        normal_max=3.7,
        mild_max=4.0,
        moderate_max=4.5,
        severe_high=4.5,
        unit="cm",
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
    """Classify a measurement value against reference ranges.

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
