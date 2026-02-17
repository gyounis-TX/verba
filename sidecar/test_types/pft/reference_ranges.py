"""
PFT reference ranges and severity classification.

Source: ATS/ERS 2022 Spirometry Standards; GOLD 2023 for obstructive severity.

PFT interpretation relies primarily on % predicted values, since normal
absolute values depend on age, height, sex, and race.  Absolute value
measurements (FEV1, FVC, etc.) are classified as UNDETERMINED.
"""

from __future__ import annotations

from dataclasses import dataclass
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
    source: str = "ATS/ERS 2022 / GOLD 2023"


REFERENCE_RANGES: dict[str, RangeThresholds] = {
    # --- Spirometry: % Predicted ---
    # FEV1 % predicted: Normal >= 80%; GOLD severity for obstructive patterns:
    #   Mild: 70-79%, Moderate: 50-69%, Severe: 35-49%, Very Severe: <35%
    "FEV1_pct": RangeThresholds(
        normal_min=80.0,
        mild_min=70.0,
        moderate_min=50.0,
        severe_low=35.0,
        unit="%",
    ),
    # FVC % predicted: Normal >= 80%
    #   Mild: 70-79%, Moderate: 50-69%, Severe: <50%
    "FVC_pct": RangeThresholds(
        normal_min=80.0,
        mild_min=70.0,
        moderate_min=50.0,
        severe_low=50.0,
        unit="%",
    ),
    # FEV1/FVC ratio: Normal >= 70% (fixed ratio; LLN also used but 70% is
    # the commonly applied threshold). Below 70% = obstruction.
    "FEV1_FVC": RangeThresholds(
        normal_min=70.0,
        mild_min=60.0,
        moderate_min=50.0,
        severe_low=50.0,
        unit="%",
    ),
    # --- Diffusing Capacity: % Predicted ---
    # DLCO % predicted: Normal >= 80%
    #   Mild: 60-79%, Moderate: 40-59%, Severe: <40%
    "DLCO_pct": RangeThresholds(
        normal_min=80.0,
        mild_min=60.0,
        moderate_min=40.0,
        severe_low=40.0,
        unit="%",
    ),
    # --- Lung Volumes: % Predicted ---
    # TLC % predicted: Normal 80-120%
    #   Low <80% = restriction, High >120% = hyperinflation
    "TLC_pct": RangeThresholds(
        normal_min=80.0,
        normal_max=120.0,
        mild_min=70.0,
        mild_max=130.0,
        moderate_min=60.0,
        moderate_max=140.0,
        severe_low=60.0,
        severe_high=140.0,
        unit="%",
    ),
    # RV % predicted: Normal 80-120%
    #   Elevated >120% = air trapping
    "RV_pct": RangeThresholds(
        normal_min=80.0,
        normal_max=120.0,
        mild_max=140.0,
        moderate_max=170.0,
        severe_high=170.0,
        unit="%",
    ),
    # --- Flow Rates: % Predicted ---
    # FEF25-75 % predicted: Normal >= 65%
    #   Reduced suggests small airway disease
    "FEF25_75_pct": RangeThresholds(
        normal_min=65.0,
        mild_min=50.0,
        moderate_min=35.0,
        severe_low=35.0,
        unit="%",
    ),
    # --- Absolute values ---
    # Normal ranges for absolute FEV1, FVC, TLC, etc. depend on
    # age/height/sex/race, so they are classified as UNDETERMINED.
    # We still store them so the UI can display them.
    "FEV1": RangeThresholds(unit="L", source="Patient-specific (age/height/sex)"),
    "FVC": RangeThresholds(unit="L", source="Patient-specific (age/height/sex)"),
    "DLCO": RangeThresholds(unit="mL/min/mmHg", source="Patient-specific (age/height/sex)"),
    "TLC": RangeThresholds(unit="L", source="Patient-specific (age/height/sex)"),
    "RV": RangeThresholds(unit="L", source="Patient-specific (age/height/sex)"),
    "FRC": RangeThresholds(unit="L", source="Patient-specific (age/height/sex)"),
    "PEF": RangeThresholds(unit="L/s", source="Patient-specific (age/height/sex)"),
    "FEF25_75": RangeThresholds(unit="L/s", source="Patient-specific (age/height/sex)"),
    "FEV1_post": RangeThresholds(unit="L", source="Patient-specific (age/height/sex)"),
    "FVC_post": RangeThresholds(unit="L", source="Patient-specific (age/height/sex)"),
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
    """Classify a measurement value against PFT reference ranges.

    PFT absolute values (FEV1, FVC, etc.) depend on patient demographics
    and are classified as UNDETERMINED.  % predicted values use standard
    thresholds from ATS/ERS and GOLD guidelines.
    """
    rr = REFERENCE_RANGES.get(abbreviation)

    if rr is None:
        return ClassificationResult(
            status=SeverityStatus.UNDETERMINED,
            direction=AbnormalityDirection.NORMAL,
            reference_range_str="No reference range available",
        )

    # Absolute values without defined normal ranges -> UNDETERMINED
    if rr.normal_min is None and rr.normal_max is None:
        return ClassificationResult(
            status=SeverityStatus.UNDETERMINED,
            direction=AbnormalityDirection.NORMAL,
            reference_range_str=f"Patient-specific ({rr.unit})",
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
