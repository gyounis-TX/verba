"""Extract physician name from medical report text."""

from __future__ import annotations

import re

# Labels that indicate the patient's referring/ordering physician.
# Ordered by priority — "Referred by" / "Ordering" are the strongest signals.
_REFERRING_LABELS = (
    r"Referred\s+by",
    r"Referring\s+Physician",
    r"Referring\s+Provider",
    r"Referring\s+Doctor",
    r"Ordering\s+Physician",
    r"Ordering\s+Provider",
    r"Ordering\s+Doctor",
    r"Ordered\s+by",
    r"Requesting\s+Physician",
    r"Requesting\s+Provider",
    r"Primary\s+Care\s+Physician",
    r"Primary\s+Care\s+Provider",
    r"PCP",
)

_SECONDARY_LABELS = (
    r"Attending\s+Physician",
    r"Attending\s+Provider",
    r"Clinician",
    r"Practice\s+Provider",
    r"Provider",
)

# Same-line pattern: label and name on one line.
# [^\S\n] = whitespace excluding newline, so the capture stays on one line.
_SAMELINE_RE = re.compile(
    r"(?:{labels})"
    r"[^\S\n]*[:\-]?[^\S\n]*"
    r"(?:Dr\.?[^\S\n]*)?"
    r"([A-Za-z][A-Za-z \t.\-']+)",
    re.IGNORECASE,
)

# Next-line pattern: label on one line, name on the very next non-blank line.
_NEXTLINE_RE = re.compile(
    r"(?:{labels})"
    r"[^\S\n]*[:\-]?[^\S\n]*\n[^\S\n]*"
    r"(?:Dr\.?[^\S\n]*)?"
    r"([A-Za-z][A-Za-z \t.\-']+)",
    re.IGNORECASE,
)

_SUFFIX_PATTERN = re.compile(
    r"\b(?:MD|DO|NP|PA|Ph\.?D|FACC|FACS|Jr|Sr|II|III|IV)\b\.?",
    re.IGNORECASE,
)

# Boundary words that signal the end of the physician name section.
# If any of these appear in the captured text, truncate before them.
_BOUNDARY_PATTERN = re.compile(
    r"\b(?:age|dob|date|patient|sex|gender|mrn|acct|account|location|dept"
    r"|phone|fax|tel|address|npi|specialty|clinic|hospital|department"
    r"|indication|reason|history|findings)\b",
    re.IGNORECASE,
)


def _build_pattern(template: re.Pattern[str], labels: tuple[str, ...]) -> re.Pattern[str]:
    """Compile *template* with the given label alternatives."""
    joined = "|".join(labels)
    return re.compile(template.pattern.format(labels=joined), template.flags)


def _clean_match(raw_name: str) -> str | None:
    """Validate and clean a captured name, returning 'Dr. LastName' or None."""
    raw_name = raw_name.strip()

    # Truncate at boundary words (e.g. "Younis age 45" → "Younis")
    boundary = _BOUNDARY_PATTERN.search(raw_name)
    if boundary:
        raw_name = raw_name[: boundary.start()].strip()

    # Remove suffixes like MD, DO, NP, PA
    cleaned = _SUFFIX_PATTERN.sub("", raw_name).strip()
    # Remove trailing commas/periods/spaces left after suffix removal
    cleaned = re.sub(r"[,.\s]+$", "", cleaned).strip()

    if not cleaned:
        return None

    # Split into tokens to get the last name
    tokens = cleaned.split()
    last_name = tokens[-1].strip(".,")

    if not last_name:
        return None

    # Capitalize properly (handle all-lower or all-upper input, including hyphens)
    last_name = "-".join(part.capitalize() for part in last_name.split("-"))

    return f"Dr. {last_name}"


def _try_patterns(text: str, labels: tuple[str, ...]) -> str | None:
    """Try same-line then next-line patterns for the given labels."""
    for template in (_SAMELINE_RE, _NEXTLINE_RE):
        pattern = _build_pattern(template, labels)
        for match in pattern.finditer(text):
            result = _clean_match(match.group(1))
            if result:
                return result
    return None


def extract_physician_name(text: str | None) -> str | None:
    """Extract the ordering/referring physician name from report text.

    Returns 'Dr. LastName' or None.  Prioritises ordering/referring labels
    and deliberately ignores interpreting/reading physician labels to avoid
    confusing the person who read the study with the one who ordered it.
    """
    if not text:
        return None

    # First try referring/ordering labels (highest priority)
    result = _try_patterns(text, _REFERRING_LABELS)
    if result:
        return result

    # Fall back to secondary labels (attending, clinician, provider)
    # but NOT interpreting/reading physicians — those are the ones who
    # read the study, not who ordered it.
    return _try_patterns(text, _SECONDARY_LABELS)
