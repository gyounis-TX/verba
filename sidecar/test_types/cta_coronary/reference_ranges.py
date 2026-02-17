"""
SCCT 2022 CTA Coronary reference ranges and severity classification.

Source: Defined per SCCT 2022 Guidelines for Coronary CTA and
        CAD-RADS 2.0 classification system.
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
    source: str = "SCCT 2022 / CAD-RADS 2.0"


REFERENCE_RANGES: dict[str, RangeThresholds] = {
    # --- Coronary Artery Calcium Score (Agatston) ---
    # 0 = no calcium (normal), 1-10 minimal, 11-100 mild,
    # 101-400 moderate, >400 severe
    "CAC_score": RangeThresholds(
        normal_min=0.0,
        normal_max=0.0,
        mild_min=1.0,
        mild_max=100.0,
        moderate_min=101.0,
        moderate_max=400.0,
        severe_high=400.0,
        unit="AU",
        source="CAD-RADS 2.0 / Agatston Classification",
    ),
    # --- CAC Percentile ---
    # Context-dependent (age/sex adjusted); no fixed normal range
    "CAC_percentile": RangeThresholds(
        normal_min=0.0,
        normal_max=100.0,
        unit="%",
        source="Age/sex adjusted; context-dependent (MESA database)",
    ),
    # --- Left Main Stenosis ---
    # Normal 0%, mild 1-24%, moderate 25-49%, severe 50-69%, critical >=70%
    "LM_stenosis": RangeThresholds(
        normal_min=0.0,
        normal_max=0.0,
        mild_min=1.0,
        mild_max=24.0,
        moderate_min=25.0,
        moderate_max=49.0,
        severe_high=50.0,
        unit="%",
        source="CAD-RADS 2.0 (left main: significant >= 50%)",
    ),
    # --- LAD Stenosis ---
    # Normal 0%, minimal 1-24%, mild 25-49%, moderate 50-69%,
    # severe 70-99%, occluded 100%
    "LAD_stenosis": RangeThresholds(
        normal_min=0.0,
        normal_max=0.0,
        mild_min=1.0,
        mild_max=49.0,
        moderate_min=50.0,
        moderate_max=69.0,
        severe_high=70.0,
        unit="%",
        source="CAD-RADS 2.0",
    ),
    # --- LCx Stenosis ---
    "LCx_stenosis": RangeThresholds(
        normal_min=0.0,
        normal_max=0.0,
        mild_min=1.0,
        mild_max=49.0,
        moderate_min=50.0,
        moderate_max=69.0,
        severe_high=70.0,
        unit="%",
        source="CAD-RADS 2.0",
    ),
    # --- RCA Stenosis ---
    "RCA_stenosis": RangeThresholds(
        normal_min=0.0,
        normal_max=0.0,
        mild_min=1.0,
        mild_max=49.0,
        moderate_min=50.0,
        moderate_max=69.0,
        severe_high=70.0,
        unit="%",
        source="CAD-RADS 2.0",
    ),
    # --- CT-FFR ---
    # Normal > 0.80, ischemic <= 0.80
    "CT_FFR": RangeThresholds(
        normal_min=0.81,
        normal_max=1.0,
        mild_min=0.76,
        mild_max=0.80,
        moderate_min=0.66,
        moderate_max=0.75,
        severe_low=0.65,
        unit="ratio",
        source="CT-FFR reference (ischemic <= 0.80)",
    ),
    # --- LVEF (from gated CT) ---
    # Normal >= 52% (male) / >= 54% (female). Using 52%.
    # Mildly abnormal: 41-51%, Moderately: 30-40%, Severely: <30%
    "LVEF": RangeThresholds(
        normal_min=52.0,
        mild_min=41.0,
        moderate_min=30.0,
        severe_low=30.0,
        unit="%",
        source="ASE 2015 Guidelines (applied to gated CT)",
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

    Gender parameter is accepted for API compatibility but CTA coronary
    measurements are not sex-stratified (except LVEF which uses the
    union range here).
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
