"""
SCMR 2020 cardiac MRI reference ranges and severity classification.

Source: Kawel-Boehm N, et al. "Reference ranges ('normal values') for
        cardiovascular magnetic resonance (CMR) in adults and children:
        2020 update." J Cardiovasc Magn Reson 2020;22:87.

Where sex-specific ranges exist, the more inclusive (union) range is used
for the default REFERENCE_RANGES dict.
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
    source: str = "SCMR 2020 Guidelines"


# Sex-stratified reference ranges for key CMR measurements
# Based on SCMR 2020 Guidelines
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
    # LVEDV: Male 77-195 mL, Female 62-150 mL
    "LVEDV": {
        "male": RangeThresholds(
            normal_min=77.0,
            normal_max=195.0,
            mild_max=215.0,
            moderate_max=250.0,
            severe_high=250.0,
            mild_min=65.0,
            moderate_min=55.0,
            severe_low=55.0,
            unit="mL",
        ),
        "female": RangeThresholds(
            normal_min=62.0,
            normal_max=150.0,
            mild_max=170.0,
            moderate_max=200.0,
            severe_high=200.0,
            mild_min=50.0,
            moderate_min=42.0,
            severe_low=42.0,
            unit="mL",
        ),
    },
    # LVESV: Male 22-75 mL, Female 17-56 mL
    "LVESV": {
        "male": RangeThresholds(
            normal_min=22.0,
            normal_max=75.0,
            mild_max=95.0,
            moderate_max=120.0,
            severe_high=120.0,
            mild_min=15.0,
            moderate_min=10.0,
            severe_low=10.0,
            unit="mL",
        ),
        "female": RangeThresholds(
            normal_min=17.0,
            normal_max=56.0,
            mild_max=70.0,
            moderate_max=90.0,
            severe_high=90.0,
            mild_min=12.0,
            moderate_min=8.0,
            severe_low=8.0,
            unit="mL",
        ),
    },
    # LVEDVi: Male 54-93 mL/m2, Female 46-81 mL/m2
    "LVEDVi": {
        "male": RangeThresholds(
            normal_min=54.0,
            normal_max=93.0,
            mild_max=107.0,
            moderate_max=125.0,
            severe_high=125.0,
            mild_min=46.0,
            moderate_min=38.0,
            severe_low=38.0,
            unit="mL/m2",
        ),
        "female": RangeThresholds(
            normal_min=46.0,
            normal_max=81.0,
            mild_max=93.0,
            moderate_max=110.0,
            severe_high=110.0,
            mild_min=38.0,
            moderate_min=32.0,
            severe_low=32.0,
            unit="mL/m2",
        ),
    },
    # LVESVi: Male 17-36 mL/m2, Female 14-30 mL/m2
    "LVESVi": {
        "male": RangeThresholds(
            normal_min=17.0,
            normal_max=36.0,
            mild_max=45.0,
            moderate_max=58.0,
            severe_high=58.0,
            mild_min=12.0,
            moderate_min=8.0,
            severe_low=8.0,
            unit="mL/m2",
        ),
        "female": RangeThresholds(
            normal_min=14.0,
            normal_max=30.0,
            mild_max=38.0,
            moderate_max=50.0,
            severe_high=50.0,
            mild_min=10.0,
            moderate_min=6.0,
            severe_low=6.0,
            unit="mL/m2",
        ),
    },
    # LV Mass: Male 85-195 g, Female 60-145 g
    "LVMass": {
        "male": RangeThresholds(
            normal_min=85.0,
            normal_max=195.0,
            mild_max=220.0,
            moderate_max=260.0,
            severe_high=260.0,
            mild_min=70.0,
            moderate_min=55.0,
            severe_low=55.0,
            unit="g",
        ),
        "female": RangeThresholds(
            normal_min=60.0,
            normal_max=145.0,
            mild_max=170.0,
            moderate_max=200.0,
            severe_high=200.0,
            mild_min=48.0,
            moderate_min=38.0,
            severe_low=38.0,
            unit="g",
        ),
    },
    # LV Mass Index: Male 49-85 g/m2, Female 37-67 g/m2
    "LVMi": {
        "male": RangeThresholds(
            normal_min=49.0,
            normal_max=85.0,
            mild_max=100.0,
            moderate_max=120.0,
            severe_high=120.0,
            mild_min=40.0,
            moderate_min=32.0,
            severe_low=32.0,
            unit="g/m2",
        ),
        "female": RangeThresholds(
            normal_min=37.0,
            normal_max=67.0,
            mild_max=80.0,
            moderate_max=95.0,
            severe_high=95.0,
            mild_min=30.0,
            moderate_min=24.0,
            severe_low=24.0,
            unit="g/m2",
        ),
    },
    # RVEDV: Male 88-227 mL, Female 63-168 mL
    "RVEDV": {
        "male": RangeThresholds(
            normal_min=88.0,
            normal_max=227.0,
            mild_max=255.0,
            moderate_max=295.0,
            severe_high=295.0,
            mild_min=72.0,
            moderate_min=58.0,
            severe_low=58.0,
            unit="mL",
        ),
        "female": RangeThresholds(
            normal_min=63.0,
            normal_max=168.0,
            mild_max=195.0,
            moderate_max=230.0,
            severe_high=230.0,
            mild_min=50.0,
            moderate_min=40.0,
            severe_low=40.0,
            unit="mL",
        ),
    },
    # RVESV: Male 23-103 mL, Female 15-72 mL
    "RVESV": {
        "male": RangeThresholds(
            normal_min=23.0,
            normal_max=103.0,
            mild_max=125.0,
            moderate_max=155.0,
            severe_high=155.0,
            mild_min=15.0,
            moderate_min=10.0,
            severe_low=10.0,
            unit="mL",
        ),
        "female": RangeThresholds(
            normal_min=15.0,
            normal_max=72.0,
            mild_max=90.0,
            moderate_max=115.0,
            severe_high=115.0,
            mild_min=10.0,
            moderate_min=6.0,
            severe_low=6.0,
            unit="mL",
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
    # --- LV Volumes ---
    # LVEDV: Male 77-195, Female 62-150 -> union 62-195 mL
    "LVEDV": RangeThresholds(
        normal_min=62.0,
        normal_max=195.0,
        mild_max=215.0,
        moderate_max=250.0,
        severe_high=250.0,
        mild_min=50.0,
        moderate_min=42.0,
        severe_low=42.0,
        unit="mL",
    ),
    # LVESV: Male 22-75, Female 17-56 -> union 17-75 mL
    "LVESV": RangeThresholds(
        normal_min=17.0,
        normal_max=75.0,
        mild_max=95.0,
        moderate_max=120.0,
        severe_high=120.0,
        mild_min=12.0,
        moderate_min=8.0,
        severe_low=8.0,
        unit="mL",
    ),
    # --- LV Indexed Volumes ---
    # LVEDVi: Male 54-93, Female 46-81 -> union 46-93 mL/m2
    "LVEDVi": RangeThresholds(
        normal_min=46.0,
        normal_max=93.0,
        mild_max=107.0,
        moderate_max=125.0,
        severe_high=125.0,
        mild_min=38.0,
        moderate_min=32.0,
        severe_low=32.0,
        unit="mL/m2",
    ),
    # LVESVi: Male 17-36, Female 14-30 -> union 14-36 mL/m2
    "LVESVi": RangeThresholds(
        normal_min=14.0,
        normal_max=36.0,
        mild_max=45.0,
        moderate_max=58.0,
        severe_high=58.0,
        mild_min=10.0,
        moderate_min=6.0,
        severe_low=6.0,
        unit="mL/m2",
    ),
    # --- LV Mass ---
    # LV Mass: Male 85-195, Female 60-145 -> union 60-195 g
    "LVMass": RangeThresholds(
        normal_min=60.0,
        normal_max=195.0,
        mild_max=220.0,
        moderate_max=260.0,
        severe_high=260.0,
        mild_min=48.0,
        moderate_min=38.0,
        severe_low=38.0,
        unit="g",
    ),
    # LV Mass Index: Male 49-85, Female 37-67 -> union 37-85 g/m2
    "LVMi": RangeThresholds(
        normal_min=37.0,
        normal_max=85.0,
        mild_max=100.0,
        moderate_max=120.0,
        severe_high=120.0,
        mild_min=30.0,
        moderate_min=24.0,
        severe_low=24.0,
        unit="g/m2",
    ),
    # --- RV Function ---
    # RVEF: Normal >= 45%, Mild 40-44, Moderate 30-39, Severe <30
    "RVEF": RangeThresholds(
        normal_min=45.0,
        mild_min=40.0,
        moderate_min=30.0,
        severe_low=30.0,
        unit="%",
    ),
    # --- RV Volumes ---
    # RVEDV: Male 88-227, Female 63-168 -> union 63-227 mL
    "RVEDV": RangeThresholds(
        normal_min=63.0,
        normal_max=227.0,
        mild_max=255.0,
        moderate_max=295.0,
        severe_high=295.0,
        mild_min=50.0,
        moderate_min=40.0,
        severe_low=40.0,
        unit="mL",
    ),
    # RVESV: Male 23-103, Female 15-72 -> union 15-103 mL
    "RVESV": RangeThresholds(
        normal_min=15.0,
        normal_max=103.0,
        mild_max=125.0,
        moderate_max=155.0,
        severe_high=155.0,
        mild_min=10.0,
        moderate_min=6.0,
        severe_low=6.0,
        unit="mL",
    ),
    # --- Tissue Characterization ---
    # Native T1: Normal 950-1050 ms at 1.5T (elevated > 1050 suggests fibrosis/edema)
    "NativeT1": RangeThresholds(
        normal_min=950.0,
        normal_max=1050.0,
        mild_max=1100.0,
        moderate_max=1150.0,
        severe_high=1150.0,
        mild_min=900.0,
        moderate_min=850.0,
        severe_low=850.0,
        unit="ms",
    ),
    # T2: Normal 40-55 ms at 1.5T (elevated > 55 suggests edema)
    "T2": RangeThresholds(
        normal_min=40.0,
        normal_max=55.0,
        mild_max=60.0,
        moderate_max=70.0,
        severe_high=70.0,
        mild_min=35.0,
        moderate_min=30.0,
        severe_low=30.0,
        unit="ms",
    ),
    # ECV: Normal 22-28% (elevated > 28% suggests diffuse fibrosis)
    "ECV": RangeThresholds(
        normal_min=22.0,
        normal_max=28.0,
        mild_max=32.0,
        moderate_max=38.0,
        severe_high=38.0,
        mild_min=18.0,
        moderate_min=15.0,
        severe_low=15.0,
        unit="%",
    ),
    # Scar Burden: Normal 0% (any > 0 is abnormal; >15% severely abnormal)
    "ScarBurden": RangeThresholds(
        normal_max=0.0,
        mild_max=5.0,
        moderate_max=15.0,
        severe_high=15.0,
        unit="%",
    ),
    # --- Left Atrium ---
    # LA Volume Index: Normal < 34 mL/m2 (same as echo)
    "LAVI": RangeThresholds(
        normal_max=34.0,
        mild_max=41.0,
        moderate_max=48.0,
        severe_high=48.0,
        unit="mL/m2",
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
    """Classify a measurement value against SCMR reference ranges.

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
