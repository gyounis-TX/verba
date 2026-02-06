"""Extract patient demographics (age, gender) from medical report text."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Demographics:
    age: Optional[int] = None
    gender: Optional[str] = None


# Age patterns
_AGE_PATTERNS = [
    # "Age: 45" or "Age 45" or "Age/Sex: 45/M"
    re.compile(r"(?i)\bage\s*(?:/\s*sex)?\s*[:=]?\s*(\d{1,3})\b"),
    # "45 yo" or "45 y/o" or "45 y.o."
    re.compile(r"\b(\d{1,3})\s*(?:yo|y\.?o\.?|y/o)\b", re.IGNORECASE),
    # "45 year old" or "45-year-old" or "45 years old"
    re.compile(r"\b(\d{1,3})\s*[-]?\s*year[s]?\s*[-]?\s*old\b", re.IGNORECASE),
    # Patient header: "Patient: John Doe, 45M" or "45 M" or "45/M"
    re.compile(r"\b(\d{1,3})\s*[/]?\s*[MF]\b", re.IGNORECASE),
]

# DOB pattern to calculate age
_DOB_PATTERN = re.compile(
    r"(?i)(?:DOB|date\s+of\s+birth|birth\s*date)\s*[:=]\s*"
    r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})"
)

# Gender patterns
_GENDER_PATTERNS = [
    # "Sex: M" or "Sex: F" or "Gender: Male"
    re.compile(
        r"(?i)(?:sex|gender)\s*[:=]\s*(male|female|m|f)\b"
    ),
    # "45 yo male" or "45 y/o female"
    re.compile(
        r"(?i)\b\d{1,3}\s*(?:yo|y\.?o\.?|y/o|year[s]?\s*[-]?\s*old)\s+"
        r"(male|female|man|woman|m|f)\b"
    ),
    # "45M" or "45 M" or "45/M" or "45/F" (common report header format)
    re.compile(r"\b\d{1,3}\s*[/]?\s*(M|F)\b"),
    # "Age/Sex: 45/M" pattern
    re.compile(r"(?i)age\s*/\s*sex\s*[:=]?\s*\d{1,3}\s*[/]?\s*(M|F)\b"),
]

_GENDER_MAP = {
    "m": "Male",
    "male": "Male",
    "man": "Male",
    "f": "Female",
    "female": "Female",
    "woman": "Female",
}


def _calculate_age_from_dob(month: int, day: int, year: int) -> Optional[int]:
    """Calculate age from DOB components."""
    if year < 100:
        year += 1900 if year > 30 else 2000
    try:
        dob = datetime(year, month, day)
        today = datetime.now()
        age = today.year - dob.year
        if (today.month, today.day) < (dob.month, dob.day):
            age -= 1
        if 0 <= age <= 120:
            return age
    except (ValueError, OverflowError):
        pass
    return None


def extract_demographics(text: str) -> Demographics:
    """Extract age and gender from medical report text."""
    if not text:
        return Demographics()

    result = Demographics()

    # Extract age
    for pattern in _AGE_PATTERNS:
        match = pattern.search(text)
        if match:
            age = int(match.group(1))
            if 0 <= age <= 120:
                result.age = age
                break

    # Try DOB if no age found
    if result.age is None:
        dob_match = _DOB_PATTERN.search(text)
        if dob_match:
            month = int(dob_match.group(1))
            day = int(dob_match.group(2))
            year = int(dob_match.group(3))
            result.age = _calculate_age_from_dob(month, day, year)

    # Extract gender
    for pattern in _GENDER_PATTERNS:
        match = pattern.search(text)
        if match:
            raw = match.group(1).lower()
            result.gender = _GENDER_MAP.get(raw)
            if result.gender:
                break

    return result
