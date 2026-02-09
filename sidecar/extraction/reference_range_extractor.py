"""Extract lab-printed reference ranges from report text.

Lab reports often print their own reference ranges next to values in various formats:
- Parenthetical: "TSH 2.5 (0.4-4.0)"
- Labeled: "Ref: 0.4-4.0"
- Flags: "H" or "L" after values
- Bracketed: "[0.4 - 4.0]"

This module extracts these lab-printed ranges so they can be compared with
the app's built-in clinically calibrated ranges.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LabReferenceRange:
    """A reference range as printed in the lab report."""
    abbreviation: str
    lab_ref_min: float | None = None
    lab_ref_max: float | None = None
    lab_flag: str | None = None  # "H", "L", "HH", "LL", "A", etc.


# Patterns for extracting reference ranges
# Format: "value (min-max)" or "value (min - max)"
_PAREN_RANGE = re.compile(
    r"(\d+\.?\d*)\s*"                 # value
    r"\(\s*(\d+\.?\d*)\s*[-–]\s*"      # ( min -
    r"(\d+\.?\d*)\s*\)",               # max )
)

# Format: "Ref: min-max" or "Reference Range: min-max" or "Normal: min-max"
_REF_LABEL_RANGE = re.compile(
    r"(?:Ref(?:erence)?(?:\s*Range)?|Normal|Range)\s*[:=]\s*"
    r"(\d+\.?\d*)\s*[-–]\s*(\d+\.?\d*)",
    re.IGNORECASE,
)

# Format: "[min - max]" or "[min-max]"
_BRACKET_RANGE = re.compile(
    r"\[\s*(\d+\.?\d*)\s*[-–]\s*(\d+\.?\d*)\s*\]",
)

# Format: "< max" or "> min" or "<= max"
_COMPARISON_RANGE = re.compile(
    r"(?:Ref(?:erence)?(?:\s*Range)?|Normal|Range)\s*[:=]\s*"
    r"([<>]=?)\s*(\d+\.?\d*)",
    re.IGNORECASE,
)

# Flag patterns: "H", "L", "HH", "LL", "A" (abnormal) after a value
_FLAG_PATTERN = re.compile(
    r"(\d+\.?\d*)\s+([HL]{1,2}|A)\s*(?:\s|$|\|)",
    re.IGNORECASE,
)

# Common lab abbreviation patterns near values
_LAB_LINE = re.compile(
    r"(?:^|\n)\s*"
    r"([A-Za-z][A-Za-z0-9 /\-]{1,30}?)"   # test name
    r"\s+(\d+\.?\d*)"                       # value
    r"\s*(\S*?)"                            # unit (optional)
    r"\s+(?:(?:H|L|HH|LL|A)\s+)?"          # flag (optional)
    r"(\d+\.?\d*)\s*[-–]\s*(\d+\.?\d*)",    # reference range min-max
    re.MULTILINE,
)


def extract_reference_ranges(text: str) -> list[LabReferenceRange]:
    """Extract all lab-printed reference ranges from report text.

    Returns a list of LabReferenceRange objects with whatever information
    could be extracted (min, max, flag).
    """
    results: list[LabReferenceRange] = []
    seen_names: set[str] = set()

    # Pattern 1: Structured lab lines with name, value, range
    for match in _LAB_LINE.finditer(text):
        name = match.group(1).strip()
        ref_min = _safe_float(match.group(4))
        ref_max = _safe_float(match.group(5))
        if name and ref_min is not None and ref_max is not None:
            abbr = _normalize_name(name)
            if abbr not in seen_names:
                seen_names.add(abbr)
                results.append(LabReferenceRange(
                    abbreviation=abbr,
                    lab_ref_min=ref_min,
                    lab_ref_max=ref_max,
                ))

    # Pattern 2: Flags (H/L) next to values
    for match in _FLAG_PATTERN.finditer(text):
        flag = match.group(2).upper()
        # We can't easily associate these with specific test names
        # without more context, so we skip standalone flags

    return results


def extract_flags_from_text(text: str) -> dict[str, str]:
    """Extract H/L flags associated with test values.

    Returns a dict mapping approximate test name to flag.
    This is a best-effort extraction.
    """
    flags: dict[str, str] = {}

    # Look for patterns like "TSH 2.5 H" or "WBC 12.3 HH"
    flag_pattern = re.compile(
        r"([A-Za-z][A-Za-z0-9 /\-]{1,20}?)"   # test name
        r"\s+(\d+\.?\d*)"                       # value
        r"\s*\S*?"                              # unit (optional)
        r"\s+([HL]{1,2}|A)\b",                  # flag
        re.IGNORECASE | re.MULTILINE,
    )
    for match in flag_pattern.finditer(text):
        name = _normalize_name(match.group(1).strip())
        flag = match.group(3).upper()
        if name:
            flags[name] = flag

    return flags


def merge_reference_ranges(
    lab_ranges: list[LabReferenceRange],
    builtin_ranges: dict[str, dict],
    measurements: list[Any],
) -> str:
    """Build a prompt section comparing lab-printed and built-in ranges.

    When they disagree, instructs the LLM to acknowledge both.
    Uses the built-in range as authoritative for severity classification.
    """
    if not lab_ranges:
        return ""

    lines = [
        "\n## Lab-Printed Reference Ranges",
        "The lab report includes its own reference ranges for some values. "
        "These may differ slightly from the clinically calibrated ranges used "
        "for severity classification. When they disagree, mention both:\n",
    ]

    for lr in lab_ranges:
        builtin = builtin_ranges.get(lr.abbreviation)
        if builtin:
            bi_min = builtin.get("normal_min")
            bi_max = builtin.get("normal_max")
            unit = builtin.get("unit", "")

            lab_range_str = _format_range(lr.lab_ref_min, lr.lab_ref_max, unit)
            builtin_range_str = _format_range(bi_min, bi_max, unit)

            # Check for disagreement
            if _ranges_differ(lr.lab_ref_min, lr.lab_ref_max, bi_min, bi_max):
                lines.append(
                    f"- {lr.abbreviation}: Lab range {lab_range_str} vs "
                    f"clinical range {builtin_range_str} (use clinical range for severity)"
                )
            else:
                lines.append(
                    f"- {lr.abbreviation}: Lab range {lab_range_str} (consistent with clinical range)"
                )
        else:
            lab_range_str = _format_range(lr.lab_ref_min, lr.lab_ref_max, "")
            lines.append(
                f"- {lr.abbreviation}: Lab range {lab_range_str}"
            )

    return "\n".join(lines)


def _safe_float(s: str | None) -> float | None:
    if s is None:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _normalize_name(name: str) -> str:
    """Normalize a test name to a standard abbreviation."""
    # Remove common prefixes/suffixes
    name = name.strip().upper()
    # Map common full names to abbreviations
    _MAPPINGS = {
        "WHITE BLOOD CELL": "WBC",
        "RED BLOOD CELL": "RBC",
        "HEMOGLOBIN": "HGB",
        "HEMATOCRIT": "HCT",
        "PLATELET": "PLT",
        "PLATELETS": "PLT",
        "THYROID STIMULATING HORMONE": "TSH",
        "BLOOD UREA NITROGEN": "BUN",
        "CREATININE": "CREAT",
        "GLUCOSE": "GLU",
        "SODIUM": "NA",
        "POTASSIUM": "K",
        "CHLORIDE": "CL",
        "CARBON DIOXIDE": "CO2",
        "CALCIUM": "CA",
        "TOTAL PROTEIN": "TP",
        "ALBUMIN": "ALB",
        "TOTAL BILIRUBIN": "TBILI",
        "ALKALINE PHOSPHATASE": "ALP",
        "ALT": "ALT",
        "AST": "AST",
        "TOTAL CHOLESTEROL": "TC",
        "TRIGLYCERIDES": "TG",
        "HDL CHOLESTEROL": "HDL",
        "LDL CHOLESTEROL": "LDL",
    }
    for full, abbr in _MAPPINGS.items():
        if name.startswith(full):
            return abbr
    return name


def _format_range(
    min_val: float | None, max_val: float | None, unit: str,
) -> str:
    if min_val is not None and max_val is not None:
        return f"{min_val}-{max_val} {unit}".strip()
    elif min_val is not None:
        return f">= {min_val} {unit}".strip()
    elif max_val is not None:
        return f"<= {max_val} {unit}".strip()
    return "unknown"


def _ranges_differ(
    lab_min: float | None, lab_max: float | None,
    bi_min: float | None, bi_max: float | None,
    tolerance: float = 0.1,
) -> bool:
    """Check if two ranges differ beyond a small tolerance."""
    if lab_min is not None and bi_min is not None:
        if abs(lab_min - bi_min) / max(abs(bi_min), 0.001) > tolerance:
            return True
    if lab_max is not None and bi_max is not None:
        if abs(lab_max - bi_max) / max(abs(bi_max), 0.001) > tolerance:
            return True
    return False
