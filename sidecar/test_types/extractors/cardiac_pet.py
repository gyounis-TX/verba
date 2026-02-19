"""
Measurement extraction, reference ranges, and glossary for Cardiac PET / PET-CT reports.

Extracts myocardial blood flow (MBF), coronary flow reserve (CFR), and related metrics.
"""

from __future__ import annotations

import re
from typing import Optional

from api.analysis_models import ParsedMeasurement


_NUM = r"(\d+\.?\d*)"
_SEP = r"[\s:=]+\s*"


def extract_cardiac_pet_measurements(
    full_text: str,
    gender: Optional[str] = None,
) -> list[ParsedMeasurement]:
    """Extract PET-specific measurements from report text."""
    results: list[ParsedMeasurement] = []
    seen: set[str] = set()

    for mdef in _PET_MEASUREMENTS:
        if mdef["abbr"] in seen:
            continue
        for pattern in mdef["patterns"]:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match:
                try:
                    value = float(match.group(1))
                except (ValueError, IndexError):
                    continue
                if not (mdef["min"] <= value <= mdef["max"]):
                    continue
                # Classify against reference ranges
                abbr = mdef["abbr"]
                ref = CARDIAC_PET_REFERENCE_RANGES.get(abbr, {})
                normal_range = ref.get("normal")
                if normal_range and len(normal_range) == 2:
                    lo, hi = normal_range
                    if lo <= value <= hi:
                        status = "normal"
                        direction = "normal"
                    elif value < lo:
                        status = "abnormal"
                        direction = "low"
                    else:
                        status = "abnormal"
                        direction = "high"
                    ref_str = f"{lo}–{hi} {mdef['unit']}".strip()
                else:
                    status = "normal"
                    direction = "normal"
                    ref_str = ""
                results.append(
                    ParsedMeasurement(
                        name=mdef["name"],
                        abbreviation=abbr,
                        value=value,
                        unit=mdef["unit"],
                        status=status,
                        direction=direction,
                        reference_range=ref_str,
                        raw_text=match.group(0),
                    )
                )
                seen.add(mdef["abbr"])
                break

    return results


_PET_MEASUREMENTS: list[dict] = [
    # --- Global MBF at Rest ---
    {
        "name": "Global MBF (Rest)",
        "abbr": "MBF_Rest",
        "unit": "mL/min/g",
        "min": 0.1,
        "max": 5.0,
        "patterns": [
            rf"(?:global|overall)\s+(?:rest(?:ing)?)\s+(?:MBF|myocardial\s+blood\s+flow){_SEP}{_NUM}",
            rf"(?:rest(?:ing)?)\s+(?:global\s+)?(?:MBF|myocardial\s+blood\s+flow){_SEP}{_NUM}",
            rf"MBF\s+rest{_SEP}{_NUM}",
        ],
    },
    # --- Global MBF at Stress ---
    {
        "name": "Global MBF (Stress)",
        "abbr": "MBF_Stress",
        "unit": "mL/min/g",
        "min": 0.1,
        "max": 8.0,
        "patterns": [
            rf"(?:global|overall)\s+(?:stress)\s+(?:MBF|myocardial\s+blood\s+flow){_SEP}{_NUM}",
            rf"(?:stress)\s+(?:global\s+)?(?:MBF|myocardial\s+blood\s+flow){_SEP}{_NUM}",
            rf"MBF\s+stress{_SEP}{_NUM}",
        ],
    },
    # --- Global CFR ---
    {
        "name": "Global CFR",
        "abbr": "CFR_Global",
        "unit": "",
        "min": 0.5,
        "max": 6.0,
        "patterns": [
            rf"(?:global|overall)\s+(?:CFR|coronary\s+flow\s+(?:reserve|capacity)){_SEP}{_NUM}",
            rf"(?:CFR|coronary\s+flow\s+(?:reserve|capacity)){_SEP}{_NUM}",
        ],
    },
    # --- LAD CFR ---
    {
        "name": "LAD CFR",
        "abbr": "CFR_LAD",
        "unit": "",
        "min": 0.5,
        "max": 6.0,
        "patterns": [
            rf"LAD\s+(?:territory\s+)?(?:CFR|coronary\s+flow\s+(?:reserve|capacity)){_SEP}{_NUM}",
            rf"(?:left\s+anterior\s+descending)\s+(?:CFR|flow\s+reserve){_SEP}{_NUM}",
        ],
    },
    # --- LCx CFR ---
    {
        "name": "LCx CFR",
        "abbr": "CFR_LCx",
        "unit": "",
        "min": 0.5,
        "max": 6.0,
        "patterns": [
            rf"(?:LCx|LCX|circumflex)\s+(?:territory\s+)?(?:CFR|coronary\s+flow\s+(?:reserve|capacity)){_SEP}{_NUM}",
        ],
    },
    # --- RCA CFR ---
    {
        "name": "RCA CFR",
        "abbr": "CFR_RCA",
        "unit": "",
        "min": 0.5,
        "max": 6.0,
        "patterns": [
            rf"(?:RCA|right\s+coronary)\s+(?:territory\s+)?(?:CFR|coronary\s+flow\s+(?:reserve|capacity)){_SEP}{_NUM}",
        ],
    },
    # --- LVEF ---
    {
        "name": "LVEF",
        "abbr": "LVEF",
        "unit": "%",
        "min": 5.0,
        "max": 85.0,
        "patterns": [
            rf"(?:LVEF|LV\s+ejection\s+fraction|ejection\s+fraction){_SEP}{_NUM}\s*%?",
            rf"{_NUM}\s*%\s*(?:LVEF|ejection\s+fraction)",
        ],
    },
    # --- Summed Stress Score ---
    {
        "name": "Summed Stress Score",
        "abbr": "SSS",
        "unit": "",
        "min": 0.0,
        "max": 80.0,
        "patterns": [
            rf"(?:summed\s+stress\s+score|SSS){_SEP}{_NUM}",
        ],
    },
    # --- Summed Rest Score ---
    {
        "name": "Summed Rest Score",
        "abbr": "SRS",
        "unit": "",
        "min": 0.0,
        "max": 80.0,
        "patterns": [
            rf"(?:summed\s+rest\s+score|SRS){_SEP}{_NUM}",
        ],
    },
    # --- Summed Difference Score ---
    {
        "name": "Summed Difference Score",
        "abbr": "SDS",
        "unit": "",
        "min": 0.0,
        "max": 80.0,
        "patterns": [
            rf"(?:summed\s+difference\s+score|SDS){_SEP}{_NUM}",
        ],
    },
    # --- Transient Ischemic Dilation ---
    {
        "name": "TID Ratio",
        "abbr": "TID",
        "unit": "",
        "min": 0.5,
        "max": 2.5,
        "patterns": [
            rf"(?:TID|transient\s+ischemic\s+dilation)\s+(?:ratio)?{_SEP}{_NUM}",
        ],
    },
]


CARDIAC_PET_REFERENCE_RANGES: dict = {
    "MBF_Rest": {"normal": [0.6, 1.2], "unit": "mL/min/g"},
    "MBF_Stress": {"normal": [2.0, 4.0], "unit": "mL/min/g"},
    "CFR_Global": {"normal": [2.0, 5.0], "unit": ""},
    "CFR_LAD": {"normal": [2.0, 5.0], "unit": ""},
    "CFR_LCx": {"normal": [2.0, 5.0], "unit": ""},
    "CFR_RCA": {"normal": [2.0, 5.0], "unit": ""},
    "LVEF": {"normal": [55, 75], "unit": "%"},
    "SSS": {"normal": [0, 3], "unit": ""},
    "SRS": {"normal": [0, 3], "unit": ""},
    "SDS": {"normal": [0, 1], "unit": ""},
    "TID": {"normal": [0.9, 1.2], "unit": ""},
}


CARDIAC_PET_GLOSSARY: dict[str, str] = {
    "MBF": "Myocardial blood flow — the amount of blood flowing through the heart muscle, measured in mL/min/g. Higher values during stress indicate better blood supply.",
    "Myocardial Blood Flow": "The volume of blood delivered to the heart muscle per minute per gram of tissue. Measured at rest and during stress to assess coronary artery function.",
    "CFR": "Coronary flow reserve — the ratio of stress blood flow to resting blood flow. A CFR above 2.0 is generally normal. Below 2.0 suggests impaired blood supply, which may indicate coronary artery disease.",
    "Coronary Flow Reserve": "The heart's ability to increase blood flow during stress compared to rest. A normal heart can increase flow 2-4 times above resting levels.",
    "Coronary Flow Capacity": "A composite metric combining stress myocardial blood flow (MBF) and coronary flow reserve (CFR) to classify coronary vasomotor function. Categorized as normal, mildly reduced, moderately reduced, or severely reduced. Provides stronger prognostic value than CFR alone.",
    "CFC": "Coronary flow capacity — a composite classification integrating stress MBF and CFR to assess overall coronary vasomotor function. Not the same as CFR alone.",
    "Rb-82": "Rubidium-82, a radioactive tracer used in cardiac PET imaging. It is injected intravenously and taken up by the heart muscle in proportion to blood flow.",
    "Rubidium": "A radioactive tracer (Rb-82) used in PET scans to create images of blood flow to the heart muscle.",
    "N-13 Ammonia": "An alternative PET tracer used to measure myocardial blood flow, with a longer half-life than rubidium.",
    "PET": "Positron emission tomography — an advanced imaging technique that measures blood flow to the heart muscle with high accuracy.",
    "PET/CT": "A combined scan using PET (for blood flow) and CT (for anatomy). The CT component may also provide a coronary calcium score.",
    "Perfusion Defect": "An area of the heart that receives less blood than normal, suggesting a narrowed or blocked coronary artery.",
    "Reversible Defect": "A perfusion defect seen during stress but not at rest, indicating an area with reduced blood flow during exertion (ischemia) that still has living heart muscle.",
    "Fixed Defect": "A perfusion defect seen both at rest and during stress, which may indicate scarring from a prior heart attack.",
    "Ischemia": "Reduced blood flow to the heart muscle, often caused by narrowed coronary arteries. PET can detect ischemia by showing decreased blood flow during stress.",
    "SSS": "Summed stress score — a number summarizing perfusion abnormalities during stress. Higher scores indicate more widespread reduced blood flow. A score of 0-3 is normal.",
    "SRS": "Summed rest score — a number summarizing perfusion abnormalities at rest. Higher scores suggest scarring or prior heart damage.",
    "SDS": "Summed difference score — the difference between stress and rest scores. Higher values indicate more ischemia (reversible blood flow problems).",
    "TID": "Transient ischemic dilation — when the heart chamber appears larger during stress than at rest. A TID ratio above 1.2 may suggest widespread coronary artery disease.",
    "LVEF": "Left ventricular ejection fraction — the percentage of blood pumped out of the heart with each beat. Normal is 55-70%.",
    "Pharmacologic Stress": "Using a medication (like regadenoson or adenosine) instead of exercise to simulate stress on the heart during the test.",
    "Regadenoson": "A medication used to dilate coronary arteries during a pharmacologic stress test. Brand name Lexiscan.",
    "Adenosine": "A medication that dilates coronary arteries, used as an alternative to exercise during stress testing.",
    "Dipyridamole": "A medication (Persantine) used to stress the heart by dilating coronary arteries during PET imaging.",
    "LAD": "Left anterior descending artery — supplies blood to the front and part of the side of the heart.",
    "LCx": "Left circumflex artery — supplies blood to the side and back of the heart.",
    "RCA": "Right coronary artery — supplies blood to the bottom of the heart and often the back.",
    "Polar Map": "A bull's-eye diagram showing blood flow to all regions of the heart in a single image.",
    "Attenuation Correction": "A technique using CT to correct for tissue density differences that could affect the accuracy of PET images.",
}
