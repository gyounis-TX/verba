"""
ESC/ERS 2022 right heart catheterization reference ranges and severity classification.

Source: Humbert M, et al. "2022 ESC/ERS Guidelines for the diagnosis and
        treatment of pulmonary hypertension." Eur Heart J 2022;43:3618-3731.
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
    source: str = "ESC/ERS 2022 Pulmonary Hypertension Guidelines"


REFERENCE_RANGES: dict[str, RangeThresholds] = {
    # --- RA Pressure ---
    # Normal 0-5 mmHg; mild 6-10, moderate 11-15, severe >15
    "RA_mean": RangeThresholds(
        normal_min=0.0,
        normal_max=5.0,
        mild_max=10.0,
        moderate_max=15.0,
        severe_high=15.0,
        unit="mmHg",
    ),
    # --- PA Pressures ---
    # PA systolic: Normal 15-30 mmHg; mild 31-40, moderate 41-55, severe >55
    "PA_sys": RangeThresholds(
        normal_min=15.0,
        normal_max=30.0,
        mild_max=40.0,
        moderate_max=55.0,
        severe_high=55.0,
        unit="mmHg",
    ),
    # PA diastolic: Normal 4-12 mmHg; elevated >12
    "PA_dia": RangeThresholds(
        normal_min=4.0,
        normal_max=12.0,
        unit="mmHg",
    ),
    # PA mean: Normal <= 20 mmHg; mild 21-24 (borderline), moderate 25-34, severe >=35
    "PA_mean": RangeThresholds(
        normal_max=20.0,
        mild_max=24.0,
        moderate_max=34.0,
        severe_high=35.0,
        unit="mmHg",
    ),
    # --- Wedge Pressure ---
    # PCWP: Normal <= 12 mmHg; mild 13-15, moderate 16-20, severe >20
    "PCWP": RangeThresholds(
        normal_max=12.0,
        mild_max=15.0,
        moderate_max=20.0,
        severe_high=20.0,
        unit="mmHg",
    ),
    # --- Cardiac Output ---
    # CO: Normal 4.0-8.0 L/min; low <4.0
    "CO": RangeThresholds(
        normal_min=4.0,
        normal_max=8.0,
        unit="L/min",
    ),
    # CI: Normal >= 2.5 L/min/m2; mild 2.0-2.4, moderate 1.5-1.9, severe <1.5
    "CI": RangeThresholds(
        normal_min=2.5,
        mild_min=2.0,
        moderate_min=1.5,
        severe_low=1.5,
        unit="L/min/m2",
    ),
    # --- Vascular Resistance ---
    # PVR: Normal < 2 Wood units; mild 2-3, moderate 3-5, severe >5
    "PVR": RangeThresholds(
        normal_max=2.0,
        mild_max=3.0,
        moderate_max=5.0,
        severe_high=5.0,
        unit="Wood units",
    ),
    # SVR: Normal 800-1200 dynes (wider clinical range 400-1600)
    "SVR": RangeThresholds(
        normal_min=800.0,
        normal_max=1200.0,
        unit="dynes",
    ),
    # --- Gradients ---
    # TPG: Normal <= 12 mmHg; elevated >12 suggests pre-capillary component
    "TPG": RangeThresholds(
        normal_max=12.0,
        unit="mmHg",
    ),
    # DPG: Normal <= 7 mmHg
    "DPG": RangeThresholds(
        normal_max=7.0,
        unit="mmHg",
    ),
    # --- Oxygen Saturation ---
    # MVO2: Normal 65-75%; low <60%
    "MVO2": RangeThresholds(
        normal_min=65.0,
        normal_max=75.0,
        mild_min=60.0,
        severe_low=60.0,
        unit="%",
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
    """Classify a measurement value against ESC/ERS reference ranges.

    Gender parameter is accepted for interface compatibility but RHC
    reference ranges are not sex-stratified.
    """
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
