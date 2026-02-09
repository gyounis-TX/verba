"""EMR/PACS source fingerprinting.

Detects whether extracted text originated from known EMR/PACS systems
(Vidistar, Epic, Cerner, Meditech) based on characteristic patterns
in text content and PDF metadata.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class EMRSource(str, Enum):
    VIDISTAR = "vidistar"
    EPIC = "epic"
    CERNER = "cerner"
    MEDITECH = "meditech"
    UNKNOWN = "unknown"


@dataclass
class EMRFingerprint:
    source: EMRSource
    confidence: float
    matched_patterns: list[str] = field(default_factory=list)
    input_mode: str = "text"  # "pdf" or "text"


# ---------------------------------------------------------------------------
# Pattern definitions: (compiled_regex | literal_str, weight, label)
# ---------------------------------------------------------------------------

_VIDISTAR_PATTERNS: list[tuple[re.Pattern | str, float, str]] = [
    ("vidistar", 0.9, "vidistar_text"),
    (re.compile(r"printed\s+from\s+(?:pacs|vidi)", re.IGNORECASE), 0.8, "vidistar_footer"),
    (re.compile(r"(?m)^study\s+date\s*[:\-].*\n\s*study\s+type\s*[:\-]", re.IGNORECASE), 0.6, "vidistar_header_format"),
    (re.compile(r"LVIDd\s*:\s*\d+\.?\d*\s*cm", re.IGNORECASE), 0.5, "vidistar_echo_format"),
]

_EPIC_PATTERNS: list[tuple[re.Pattern | str, float, str]] = [
    (re.compile(r"(?:Lab|Result)\s+Status\s*:\s*Final", re.IGNORECASE), 0.7, "epic_status_final"),
    (re.compile(r"Resulted\s*:\s*\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}", re.IGNORECASE), 0.6, "epic_resulted_ts"),
    (re.compile(r"Component\s*\|\s*Value\s*\|\s*Units\s*\|\s*Range", re.IGNORECASE), 0.7, "epic_table_header"),
    (re.compile(r"MD\s*,\s*NPI\s*:\s*\d{10}", re.IGNORECASE), 0.5, "epic_npi"),
    (re.compile(r"(?:Ordered\s+By|Authorizing\s+Provider)\s*:", re.IGNORECASE), 0.4, "epic_provider_label"),
]

_CERNER_PATTERNS: list[tuple[re.Pattern | str, float, str]] = [
    (re.compile(r"Status\s*:\s*Auth\s*\(Verified\)", re.IGNORECASE), 0.8, "cerner_auth_verified"),
    (re.compile(r"Verified\s+By\s*:", re.IGNORECASE), 0.6, "cerner_verified_by"),
    (re.compile(r"Performed\s+By\s*:", re.IGNORECASE), 0.5, "cerner_performed_by"),
    (re.compile(r"Chart\s+(?:reviewed|signed)", re.IGNORECASE), 0.3, "cerner_chart_signed"),
]

_MEDITECH_PATTERNS: list[tuple[re.Pattern | str, float, str]] = [
    (re.compile(r"MEDITECH", re.IGNORECASE), 0.9, "meditech_text"),
    (re.compile(r"Dict(?:ated)?\s+By\s*:.*Transcribed\s+By\s*:", re.IGNORECASE | re.DOTALL), 0.5, "meditech_dict_trans"),
]

_ALL_SOURCES: list[tuple[EMRSource, list]] = [
    (EMRSource.VIDISTAR, _VIDISTAR_PATTERNS),
    (EMRSource.EPIC, _EPIC_PATTERNS),
    (EMRSource.CERNER, _CERNER_PATTERNS),
    (EMRSource.MEDITECH, _MEDITECH_PATTERNS),
]


def _match_patterns(
    text: str, patterns: list[tuple[re.Pattern | str, float, str]]
) -> tuple[float, list[str]]:
    """Score text against a pattern set. Returns (best_score, matched_labels)."""
    best = 0.0
    matched: list[str] = []
    for pat, weight, label in patterns:
        if isinstance(pat, str):
            if pat.lower() in text.lower():
                matched.append(label)
                best = max(best, weight)
        else:
            if pat.search(text):
                matched.append(label)
                best = max(best, weight)
    return best, matched


def detect_emr_source(
    text: str,
    pdf_metadata: Optional[dict] = None,
    input_mode: str = "text",
) -> EMRFingerprint:
    """Detect the EMR/PACS source of extracted report text.

    Args:
        text: The extracted report text.
        pdf_metadata: Optional dict from PyMuPDF ``doc.metadata`` (keys like
            ``producer``, ``creator``). Checked first for high-confidence matches.
        input_mode: ``"pdf"`` or ``"text"``.

    Returns:
        An EMRFingerprint with the detected source and confidence.
    """
    best_source = EMRSource.UNKNOWN
    best_confidence = 0.0
    best_matched: list[str] = []

    # PDF metadata check (highest-confidence signal)
    if pdf_metadata:
        meta_str = " ".join(
            str(v) for v in pdf_metadata.values() if v
        ).lower()
        if "vidistar" in meta_str or "vidi" in meta_str:
            return EMRFingerprint(
                source=EMRSource.VIDISTAR,
                confidence=0.95,
                matched_patterns=["pdf_metadata_vidistar"],
                input_mode=input_mode,
            )
        if "epic" in meta_str:
            return EMRFingerprint(
                source=EMRSource.EPIC,
                confidence=0.9,
                matched_patterns=["pdf_metadata_epic"],
                input_mode=input_mode,
            )
        if "cerner" in meta_str:
            return EMRFingerprint(
                source=EMRSource.CERNER,
                confidence=0.9,
                matched_patterns=["pdf_metadata_cerner"],
                input_mode=input_mode,
            )
        if "meditech" in meta_str:
            return EMRFingerprint(
                source=EMRSource.MEDITECH,
                confidence=0.9,
                matched_patterns=["pdf_metadata_meditech"],
                input_mode=input_mode,
            )

    # Text pattern scanning — first 2000 chars
    snippet = text[:2000]

    for source, patterns in _ALL_SOURCES:
        score, matched = _match_patterns(snippet, patterns)
        if score > best_confidence:
            best_confidence = score
            best_source = source
            best_matched = matched

    return EMRFingerprint(
        source=best_source,
        confidence=round(best_confidence, 3),
        matched_patterns=best_matched,
        input_mode=input_mode,
    )
