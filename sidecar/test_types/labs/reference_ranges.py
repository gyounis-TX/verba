"""
Standard adult clinical laboratory reference ranges and severity classification.

Source: Standard adult clinical reference ranges commonly used in US laboratories.

These represent general adult ranges. Individual lab reference ranges may vary
slightly based on methodology and population.
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
    source: str = "Standard adult clinical reference ranges"


# Sex-stratified reference ranges for key analytes
# Used when gender is provided; otherwise falls back to union ranges
SEX_STRATIFIED_RANGES: dict[str, dict[str, RangeThresholds]] = {
    # Hemoglobin: Male 13.5-17.5, Female 12.0-16.0 g/dL
    "HGB": {
        "male": RangeThresholds(
            normal_min=13.5,
            normal_max=17.5,
            mild_min=12.0,
            mild_max=18.5,
            moderate_min=10.0,
            moderate_max=20.0,
            severe_low=8.0,
            severe_high=22.0,
            unit="g/dL",
        ),
        "female": RangeThresholds(
            normal_min=12.0,
            normal_max=16.0,
            mild_min=10.0,
            mild_max=17.0,
            moderate_min=8.0,
            moderate_max=18.0,
            severe_low=7.0,
            severe_high=20.0,
            unit="g/dL",
        ),
    },
    # Hematocrit: Male 38.3-48.6%, Female 35.5-44.9%
    "HCT": {
        "male": RangeThresholds(
            normal_min=38.3,
            normal_max=48.6,
            mild_min=35.0,
            mild_max=52.0,
            moderate_min=30.0,
            moderate_max=56.0,
            severe_low=25.0,
            severe_high=60.0,
            unit="%",
        ),
        "female": RangeThresholds(
            normal_min=35.5,
            normal_max=44.9,
            mild_min=32.0,
            mild_max=48.0,
            moderate_min=28.0,
            moderate_max=52.0,
            severe_low=22.0,
            severe_high=58.0,
            unit="%",
        ),
    },
    # RBC: Male 4.5-5.5, Female 4.0-5.0 M/uL
    "RBC": {
        "male": RangeThresholds(
            normal_min=4.5,
            normal_max=5.5,
            mild_min=4.0,
            mild_max=6.0,
            moderate_min=3.5,
            moderate_max=6.5,
            severe_low=3.0,
            severe_high=7.0,
            unit="M/uL",
        ),
        "female": RangeThresholds(
            normal_min=4.0,
            normal_max=5.0,
            mild_min=3.5,
            mild_max=5.5,
            moderate_min=3.0,
            moderate_max=6.0,
            severe_low=2.5,
            severe_high=6.5,
            unit="M/uL",
        ),
    },
    # Creatinine: Male 0.7-1.3, Female 0.6-1.1 mg/dL
    "CREAT": {
        "male": RangeThresholds(
            normal_min=0.7,
            normal_max=1.3,
            mild_min=0.6,
            mild_max=1.6,
            moderate_min=0.5,
            moderate_max=2.5,
            severe_low=0.4,
            severe_high=5.0,
            unit="mg/dL",
        ),
        "female": RangeThresholds(
            normal_min=0.6,
            normal_max=1.1,
            mild_min=0.5,
            mild_max=1.4,
            moderate_min=0.4,
            moderate_max=2.2,
            severe_low=0.3,
            severe_high=4.5,
            unit="mg/dL",
        ),
    },
    # Ferritin: Male 12-300, Female 12-150 ng/mL
    "FERR": {
        "male": RangeThresholds(
            normal_min=12.0,
            normal_max=300.0,
            mild_min=8.0,
            mild_max=400.0,
            moderate_min=4.0,
            moderate_max=600.0,
            severe_low=2.0,
            severe_high=1000.0,
            unit="ng/mL",
        ),
        "female": RangeThresholds(
            normal_min=12.0,
            normal_max=150.0,
            mild_min=8.0,
            mild_max=200.0,
            moderate_min=4.0,
            moderate_max=350.0,
            severe_low=2.0,
            severe_high=600.0,
            unit="ng/mL",
        ),
    },
    # HDL: Male >= 40, Female >= 50 mg/dL
    "HDL": {
        "male": RangeThresholds(
            normal_min=40.0,
            mild_min=35.0,
            moderate_min=25.0,
            severe_low=20.0,
            unit="mg/dL",
        ),
        "female": RangeThresholds(
            normal_min=50.0,
            mild_min=40.0,
            moderate_min=30.0,
            severe_low=20.0,
            unit="mg/dL",
        ),
    },
}


REFERENCE_RANGES: dict[str, RangeThresholds] = {
    # ===== Comprehensive Metabolic Panel (CMP) =====

    # Glucose: normal 70-99 mg/dL (fasting)
    "GLU": RangeThresholds(
        normal_min=70.0,
        normal_max=99.0,
        mild_min=65.0,
        mild_max=125.0,
        moderate_min=55.0,
        moderate_max=200.0,
        severe_low=40.0,
        severe_high=400.0,
        unit="mg/dL",
    ),
    # BUN: normal 7-20 mg/dL
    "BUN": RangeThresholds(
        normal_min=7.0,
        normal_max=20.0,
        mild_min=5.0,
        mild_max=25.0,
        moderate_min=3.0,
        moderate_max=40.0,
        severe_low=2.0,
        severe_high=60.0,
        unit="mg/dL",
    ),
    # Creatinine: normal 0.6-1.2 mg/dL
    "CREAT": RangeThresholds(
        normal_min=0.6,
        normal_max=1.2,
        mild_min=0.5,
        mild_max=1.5,
        moderate_min=0.4,
        moderate_max=2.5,
        severe_low=0.3,
        severe_high=5.0,
        unit="mg/dL",
    ),
    # eGFR: normal >= 60 mL/min/1.73m2
    "EGFR": RangeThresholds(
        normal_min=60.0,
        mild_min=45.0,
        moderate_min=30.0,
        severe_low=15.0,
        unit="mL/min/1.73m2",
    ),
    # Sodium: normal 136-145 mEq/L
    "NA": RangeThresholds(
        normal_min=136.0,
        normal_max=145.0,
        mild_min=133.0,
        mild_max=148.0,
        moderate_min=128.0,
        moderate_max=155.0,
        severe_low=120.0,
        severe_high=160.0,
        unit="mEq/L",
    ),
    # Potassium: normal 3.5-5.0 mEq/L
    "K": RangeThresholds(
        normal_min=3.5,
        normal_max=5.0,
        mild_min=3.2,
        mild_max=5.3,
        moderate_min=2.8,
        moderate_max=5.8,
        severe_low=2.5,
        severe_high=6.5,
        unit="mEq/L",
    ),
    # Chloride: normal 98-106 mEq/L
    "CL": RangeThresholds(
        normal_min=98.0,
        normal_max=106.0,
        mild_min=95.0,
        mild_max=110.0,
        moderate_min=90.0,
        moderate_max=115.0,
        severe_low=85.0,
        severe_high=120.0,
        unit="mEq/L",
    ),
    # CO2/Bicarbonate: normal 23-29 mEq/L
    "CO2": RangeThresholds(
        normal_min=23.0,
        normal_max=29.0,
        mild_min=20.0,
        mild_max=32.0,
        moderate_min=16.0,
        moderate_max=36.0,
        severe_low=12.0,
        severe_high=40.0,
        unit="mEq/L",
    ),
    # Calcium: normal 8.5-10.5 mg/dL
    "CA": RangeThresholds(
        normal_min=8.5,
        normal_max=10.5,
        mild_min=8.0,
        mild_max=11.0,
        moderate_min=7.0,
        moderate_max=12.0,
        severe_low=6.0,
        severe_high=14.0,
        unit="mg/dL",
    ),
    # Total Protein: normal 6.0-8.3 g/dL
    "TP": RangeThresholds(
        normal_min=6.0,
        normal_max=8.3,
        mild_min=5.5,
        mild_max=9.0,
        moderate_min=4.5,
        moderate_max=10.0,
        severe_low=3.5,
        severe_high=12.0,
        unit="g/dL",
    ),
    # Albumin: normal 3.5-5.5 g/dL
    "ALB": RangeThresholds(
        normal_min=3.5,
        normal_max=5.5,
        mild_min=3.0,
        mild_max=5.8,
        moderate_min=2.5,
        moderate_max=6.0,
        severe_low=1.5,
        severe_high=6.5,
        unit="g/dL",
    ),
    # Total Bilirubin: normal 0.1-1.2 mg/dL
    "TBILI": RangeThresholds(
        normal_min=0.1,
        normal_max=1.2,
        mild_max=2.0,
        moderate_max=5.0,
        severe_high=10.0,
        unit="mg/dL",
    ),
    # AST: normal 10-40 U/L
    "AST": RangeThresholds(
        normal_min=10.0,
        normal_max=40.0,
        mild_max=80.0,
        moderate_max=200.0,
        severe_high=500.0,
        unit="U/L",
    ),
    # ALT: normal 7-56 U/L
    "ALT": RangeThresholds(
        normal_min=7.0,
        normal_max=56.0,
        mild_max=100.0,
        moderate_max=300.0,
        severe_high=500.0,
        unit="U/L",
    ),
    # Alkaline Phosphatase: normal 44-147 U/L
    "ALP": RangeThresholds(
        normal_min=44.0,
        normal_max=147.0,
        mild_max=200.0,
        moderate_max=400.0,
        severe_high=600.0,
        unit="U/L",
    ),

    # ===== Complete Blood Count (CBC) =====

    # WBC: normal 4.5-11.0 K/uL
    "WBC": RangeThresholds(
        normal_min=4.5,
        normal_max=11.0,
        mild_min=3.5,
        mild_max=15.0,
        moderate_min=2.0,
        moderate_max=20.0,
        severe_low=1.0,
        severe_high=30.0,
        unit="K/uL",
    ),
    # RBC: normal 4.0-5.5 M/uL (union of male/female)
    "RBC": RangeThresholds(
        normal_min=4.0,
        normal_max=5.5,
        mild_min=3.5,
        mild_max=6.0,
        moderate_min=3.0,
        moderate_max=6.5,
        severe_low=2.0,
        severe_high=7.5,
        unit="M/uL",
    ),
    # Hemoglobin: normal 12.0-17.5 g/dL (union of male/female)
    "HGB": RangeThresholds(
        normal_min=12.0,
        normal_max=17.5,
        mild_min=10.0,
        mild_max=18.5,
        moderate_min=8.0,
        moderate_max=20.0,
        severe_low=7.0,
        severe_high=22.0,
        unit="g/dL",
    ),
    # Hematocrit: normal 36-50% (union of male/female)
    "HCT": RangeThresholds(
        normal_min=36.0,
        normal_max=50.0,
        mild_min=32.0,
        mild_max=54.0,
        moderate_min=25.0,
        moderate_max=58.0,
        severe_low=20.0,
        severe_high=65.0,
        unit="%",
    ),
    # MCV: normal 80-100 fL
    "MCV": RangeThresholds(
        normal_min=80.0,
        normal_max=100.0,
        mild_min=75.0,
        mild_max=105.0,
        moderate_min=65.0,
        moderate_max=110.0,
        severe_low=55.0,
        severe_high=120.0,
        unit="fL",
    ),
    # MCH: normal 27-33 pg
    "MCH": RangeThresholds(
        normal_min=27.0,
        normal_max=33.0,
        mild_min=24.0,
        mild_max=36.0,
        moderate_min=20.0,
        moderate_max=40.0,
        severe_low=16.0,
        severe_high=45.0,
        unit="pg",
    ),
    # MCHC: normal 32-36 g/dL
    "MCHC": RangeThresholds(
        normal_min=32.0,
        normal_max=36.0,
        mild_min=30.0,
        mild_max=37.5,
        moderate_min=28.0,
        moderate_max=39.0,
        severe_low=25.0,
        severe_high=42.0,
        unit="g/dL",
    ),
    # RDW: normal 11.5-14.5%
    "RDW": RangeThresholds(
        normal_min=11.5,
        normal_max=14.5,
        mild_max=16.0,
        moderate_max=20.0,
        severe_high=25.0,
        unit="%",
    ),
    # Platelet Count: normal 150-400 K/uL
    "PLT": RangeThresholds(
        normal_min=150.0,
        normal_max=400.0,
        mild_min=100.0,
        mild_max=450.0,
        moderate_min=50.0,
        moderate_max=600.0,
        severe_low=20.0,
        severe_high=1000.0,
        unit="K/uL",
    ),
    # MPV: normal 7.5-11.5 fL
    "MPV": RangeThresholds(
        normal_min=7.5,
        normal_max=11.5,
        mild_min=6.5,
        mild_max=13.0,
        moderate_min=5.0,
        moderate_max=15.0,
        severe_low=4.0,
        severe_high=18.0,
        unit="fL",
    ),

    # ===== Lipid Panel =====

    # Total Cholesterol: desirable <200 mg/dL
    "CHOL": RangeThresholds(
        normal_max=200.0,
        mild_max=239.0,
        moderate_max=280.0,
        severe_high=300.0,
        unit="mg/dL",
    ),
    # HDL: normal >=40 (male) / >=50 (female), using 40 as lower bound
    "HDL": RangeThresholds(
        normal_min=40.0,
        mild_min=35.0,
        moderate_min=25.0,
        severe_low=20.0,
        unit="mg/dL",
    ),
    # LDL: optimal <100 mg/dL
    "LDL": RangeThresholds(
        normal_max=100.0,
        mild_max=130.0,
        moderate_max=160.0,
        severe_high=190.0,
        unit="mg/dL",
    ),
    # Triglycerides: normal <150 mg/dL
    "TRIG": RangeThresholds(
        normal_max=150.0,
        mild_max=199.0,
        moderate_max=499.0,
        severe_high=500.0,
        unit="mg/dL",
    ),
    # VLDL: normal 5-40 mg/dL
    "VLDL": RangeThresholds(
        normal_min=5.0,
        normal_max=40.0,
        mild_max=50.0,
        moderate_max=65.0,
        severe_high=80.0,
        unit="mg/dL",
    ),

    # ===== Thyroid Panel =====

    # TSH: normal 0.4-4.0 uIU/mL
    "TSH": RangeThresholds(
        normal_min=0.4,
        normal_max=4.0,
        mild_min=0.2,
        mild_max=5.5,
        moderate_min=0.1,
        moderate_max=10.0,
        severe_low=0.01,
        severe_high=20.0,
        unit="uIU/mL",
    ),
    # Free T4: normal 0.8-1.8 ng/dL
    "FT4": RangeThresholds(
        normal_min=0.8,
        normal_max=1.8,
        mild_min=0.6,
        mild_max=2.2,
        moderate_min=0.4,
        moderate_max=3.0,
        severe_low=0.2,
        severe_high=5.0,
        unit="ng/dL",
    ),
    # Free T3: normal 2.3-4.2 pg/mL
    "FT3": RangeThresholds(
        normal_min=2.3,
        normal_max=4.2,
        mild_min=2.0,
        mild_max=5.0,
        moderate_min=1.5,
        moderate_max=7.0,
        severe_low=1.0,
        severe_high=10.0,
        unit="pg/mL",
    ),
    # Total T4: normal 5.0-12.0 ug/dL
    "TT4": RangeThresholds(
        normal_min=5.0,
        normal_max=12.0,
        mild_min=4.0,
        mild_max=14.0,
        moderate_min=2.5,
        moderate_max=18.0,
        severe_low=1.0,
        severe_high=25.0,
        unit="ug/dL",
    ),

    # ===== Iron Studies =====

    # Iron: normal 60-170 ug/dL
    "FE": RangeThresholds(
        normal_min=60.0,
        normal_max=170.0,
        mild_min=40.0,
        mild_max=200.0,
        moderate_min=25.0,
        moderate_max=250.0,
        severe_low=10.0,
        severe_high=350.0,
        unit="ug/dL",
    ),
    # TIBC: normal 250-370 ug/dL
    "TIBC": RangeThresholds(
        normal_min=250.0,
        normal_max=370.0,
        mild_min=220.0,
        mild_max=420.0,
        moderate_min=180.0,
        moderate_max=500.0,
        severe_low=100.0,
        severe_high=600.0,
        unit="ug/dL",
    ),
    # Ferritin: normal 12-300 ng/mL (union of male/female)
    "FERR": RangeThresholds(
        normal_min=12.0,
        normal_max=300.0,
        mild_min=8.0,
        mild_max=400.0,
        moderate_min=4.0,
        moderate_max=600.0,
        severe_low=2.0,
        severe_high=1000.0,
        unit="ng/mL",
    ),
    # Transferrin Saturation: normal 20-50%
    "TSAT": RangeThresholds(
        normal_min=20.0,
        normal_max=50.0,
        mild_min=15.0,
        mild_max=55.0,
        moderate_min=10.0,
        moderate_max=70.0,
        severe_low=5.0,
        severe_high=90.0,
        unit="%",
    ),

    # ===== HbA1c =====

    # HbA1c: normal <=5.6%, prediabetes 5.7-6.4%, diabetes >=6.5%
    "A1C": RangeThresholds(
        normal_max=5.6,
        mild_max=6.4,
        moderate_max=8.0,
        severe_high=10.0,
        unit="%",
    ),

    # ===== Urinalysis (Numeric) =====

    # pH: normal 4.5-8.0
    "UA_PH": RangeThresholds(
        normal_min=4.5,
        normal_max=8.0,
        mild_min=4.0,
        mild_max=8.5,
        moderate_min=3.5,
        moderate_max=9.0,
        severe_low=3.0,
        severe_high=9.5,
        unit="",
    ),
    # Specific Gravity: normal 1.005-1.030
    "UA_SG": RangeThresholds(
        normal_min=1.005,
        normal_max=1.030,
        mild_min=1.001,
        mild_max=1.035,
        moderate_min=1.000,
        moderate_max=1.040,
        severe_low=1.000,
        severe_high=1.050,
        unit="",
    ),
    # Urine Protein: normal 0-14 mg/dL (negative/trace)
    "UA_PROT": RangeThresholds(
        normal_max=14.0,
        mild_max=30.0,
        moderate_max=100.0,
        severe_high=300.0,
        unit="mg/dL",
    ),
    # Urine Glucose: normal 0-15 mg/dL (negative)
    "UA_GLU": RangeThresholds(
        normal_max=15.0,
        mild_max=50.0,
        moderate_max=250.0,
        severe_high=1000.0,
        unit="mg/dL",
    ),
    # Urine WBC: normal 0-5 /HPF
    "UA_WBC": RangeThresholds(
        normal_max=5.0,
        mild_max=10.0,
        moderate_max=25.0,
        severe_high=50.0,
        unit="/HPF",
    ),
    # Urine RBC: normal 0-3 /HPF
    "UA_RBC": RangeThresholds(
        normal_max=3.0,
        mild_max=10.0,
        moderate_max=25.0,
        severe_high=50.0,
        unit="/HPF",
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
    """Classify a measurement value against standard clinical reference ranges.

    If gender is provided and a sex-stratified range exists for this analyte,
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
