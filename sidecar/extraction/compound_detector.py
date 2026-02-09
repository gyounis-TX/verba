"""Compound report detection and splitting.

Identifies multi-test PDFs (e.g. echo + labs in one document) by detecting
repeated patient header blocks and divergent type signals across pages,
then splits the extraction result into separate segments for independent
processing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

from api.models import ExtractionResult, InputMode, PageExtractionResult

if TYPE_CHECKING:
    from test_types.registry import TestTypeRegistry

# ---------------------------------------------------------------------------
# Pattern for patient header blocks (Patient Name / MRN / DOB)
# ---------------------------------------------------------------------------
_PATIENT_HEADER_RE = re.compile(
    r"(?:Patient\s*(?:Name)?|MRN|Medical\s+Record)\s*[:\-]\s*\S",
    re.IGNORECASE,
)

# Known report-type header keywords that indicate a new report section
_REPORT_TYPE_HEADERS = [
    "ECHOCARDIOGRAM",
    "ELECTROCARDIOGRAM",
    "EKG",
    "ECG",
    "LABORATORY",
    "LAB RESULTS",
    "STRESS TEST",
    "NUCLEAR STRESS",
    "CARDIAC CATHETERIZATION",
    "CATHETERIZATION REPORT",
    "HOLTER MONITOR",
    "PULMONARY FUNCTION",
    "CHEST X-RAY",
    "CT SCAN",
    "MRI",
    "ULTRASOUND",
    "DOPPLER",
    "PATHOLOGY",
    "OPERATIVE REPORT",
]

_REPORT_HEADER_RE = re.compile(
    r"(?m)^\s*(?:" + "|".join(re.escape(h) for h in _REPORT_TYPE_HEADERS) + r")\s*(?:REPORT|STUDY|RESULTS?)?\s*$",
    re.IGNORECASE,
)


@dataclass
class SplitSegment:
    """One segment of a compound report."""
    start_page: int
    end_page: int
    text: str
    pages: list[PageExtractionResult] = field(default_factory=list)
    tables: list = field(default_factory=list)
    detected_type: Optional[str] = None
    confidence: float = 0.0


@dataclass
class CompoundDetectionResult:
    is_compound: bool
    segments: list[SplitSegment] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


def _find_patient_header_offsets(text: str) -> list[int]:
    """Find character offsets where patient header blocks appear."""
    return [m.start() for m in _PATIENT_HEADER_RE.finditer(text)]


def _find_report_header_pages(pages: list[PageExtractionResult]) -> list[int]:
    """Return page numbers where a new report-type header appears in first 200 chars."""
    result: list[int] = []
    for page in pages:
        snippet = page.text[:200] if page.text else ""
        if _REPORT_HEADER_RE.search(snippet):
            result.append(page.page_number)
    return result


def detect_compound_report(
    extraction_result: ExtractionResult,
    registry: Optional["TestTypeRegistry"] = None,
) -> CompoundDetectionResult:
    """Detect whether an extraction result contains multiple concatenated reports.

    Heuristic signals:
    1. Repeated patient header blocks (Patient Name/MRN appearing 2+ times)
    2. New report type headers on subsequent pages
    3. Multiple strong type detections from different categories

    Decision: compound if (page splits AND type divergence) OR (2+ patient header blocks).
    """
    reasons: list[str] = []

    # --- Page-based detection (multi-page PDFs) ---
    if len(extraction_result.pages) >= 2:
        header_pages = _find_report_header_pages(extraction_result.pages)
        # Remove page 1 — the first report header is expected
        subsequent_headers = [p for p in header_pages if p > 1]

        if subsequent_headers:
            reasons.append(
                f"Report-type headers found on pages: {subsequent_headers}"
            )

    # --- Patient header repetition (works for both PDF and text) ---
    header_offsets = _find_patient_header_offsets(extraction_result.full_text)
    if len(header_offsets) >= 2:
        # Check they're sufficiently far apart (not just adjacent fields)
        spaced = [
            header_offsets[i]
            for i in range(1, len(header_offsets))
            if header_offsets[i] - header_offsets[i - 1] > 500
        ]
        if spaced:
            reasons.append(
                f"Patient header blocks found at {len(spaced) + 1} distinct locations"
            )

    # --- Type divergence via registry ---
    if registry is not None:
        multi = registry.detect_multi(extraction_result, threshold=0.3)
        strong = [(tid, c) for tid, c in multi if c >= 0.35]
        if len(strong) >= 2:
            # Check they're from different categories
            seen_categories: set[str] = set()
            divergent = False
            for tid, _ in strong:
                handler = registry.get(tid)
                if handler:
                    cat = getattr(handler, '_category', '') or handler.category
                    if cat in seen_categories and cat != "other":
                        continue
                    if seen_categories and cat not in seen_categories:
                        divergent = True
                    seen_categories.add(cat)
            if divergent:
                types_str = ", ".join(f"{tid}({c:.2f})" for tid, c in strong[:4])
                reasons.append(f"Multiple divergent type detections: {types_str}")

    if not reasons:
        return CompoundDetectionResult(is_compound=False)

    # --- Build segments ---
    segments = _split_into_segments(extraction_result, registry)

    if len(segments) < 2:
        return CompoundDetectionResult(is_compound=False, reasons=reasons)

    return CompoundDetectionResult(
        is_compound=True,
        segments=segments,
        reasons=reasons,
    )


def _split_into_segments(
    extraction_result: ExtractionResult,
    registry: Optional["TestTypeRegistry"] = None,
) -> list[SplitSegment]:
    """Split an extraction result into segments at detected boundaries."""
    pages = extraction_result.pages

    if len(pages) >= 2:
        return _split_by_pages(extraction_result, registry)
    else:
        return _split_by_text(extraction_result, registry)


def _split_by_pages(
    extraction_result: ExtractionResult,
    registry: Optional["TestTypeRegistry"] = None,
) -> list[SplitSegment]:
    """Split multi-page PDF by page boundaries where new reports begin."""
    pages = sorted(extraction_result.pages, key=lambda p: p.page_number)

    # Find split points: pages where a new report-type header appears
    split_pages: list[int] = []
    for page in pages[1:]:  # skip first page
        snippet = page.text[:200] if page.text else ""
        if _REPORT_HEADER_RE.search(snippet):
            split_pages.append(page.page_number)

    # Also split on repeated patient headers
    for page in pages[1:]:
        if page.page_number not in split_pages:
            if page.text and _PATIENT_HEADER_RE.search(page.text[:300]):
                split_pages.append(page.page_number)

    split_pages = sorted(set(split_pages))

    if not split_pages:
        return []

    # Build page ranges
    all_page_nums = [p.page_number for p in pages]
    boundaries = [all_page_nums[0]] + split_pages + [all_page_nums[-1] + 1]

    segments: list[SplitSegment] = []
    page_map = {p.page_number: p for p in pages}

    for i in range(len(boundaries) - 1):
        start = boundaries[i]
        end = boundaries[i + 1]
        seg_pages = [page_map[pn] for pn in range(start, end) if pn in page_map]
        if not seg_pages:
            continue

        seg_text = "\n\n".join(p.text for p in seg_pages if p.text)
        seg_tables = [
            t for t in extraction_result.tables
            if start <= t.page_number < end
        ]

        seg = SplitSegment(
            start_page=start,
            end_page=end - 1,
            text=seg_text,
            pages=seg_pages,
            tables=seg_tables,
        )

        # Detect type for this segment
        if registry and seg_text.strip():
            mini_er = ExtractionResult(
                input_mode=extraction_result.input_mode,
                full_text=seg_text,
                pages=seg_pages,
                tables=seg_tables,
                total_pages=len(seg_pages),
                total_chars=len(seg_text),
            )
            tid, conf = registry.detect(mini_er)
            seg.detected_type = tid
            seg.confidence = conf

        segments.append(seg)

    return segments


def _split_by_text(
    extraction_result: ExtractionResult,
    registry: Optional["TestTypeRegistry"] = None,
) -> list[SplitSegment]:
    """Split single-page/text-paste by repeated patient header offsets."""
    text = extraction_result.full_text
    offsets = _find_patient_header_offsets(text)

    # Filter to offsets that are sufficiently spaced
    boundaries = [0]
    for off in offsets:
        if off - boundaries[-1] > 500:
            boundaries.append(off)

    if len(boundaries) < 2:
        return []

    boundaries.append(len(text))

    segments: list[SplitSegment] = []
    for i in range(len(boundaries) - 1):
        seg_text = text[boundaries[i]:boundaries[i + 1]].strip()
        if not seg_text:
            continue

        seg = SplitSegment(
            start_page=1,
            end_page=1,
            text=seg_text,
            char_count=len(seg_text),
        )

        if registry:
            mini_er = ExtractionResult(
                input_mode=InputMode.TEXT,
                full_text=seg_text,
                pages=[PageExtractionResult(
                    page_number=1,
                    text=seg_text,
                    extraction_method="split",
                    confidence=1.0,
                    char_count=len(seg_text),
                )],
                tables=[],
                total_pages=1,
                total_chars=len(seg_text),
            )
            tid, conf = registry.detect(mini_er)
            seg.detected_type = tid
            seg.confidence = conf

        segments.append(seg)

    return segments


def split_extraction_result(
    extraction_result: ExtractionResult,
    segments: list[SplitSegment],
) -> list[ExtractionResult]:
    """Convert SplitSegments into separate ExtractionResult objects."""
    results: list[ExtractionResult] = []
    for seg in segments:
        er = ExtractionResult(
            input_mode=extraction_result.input_mode,
            full_text=seg.text,
            pages=seg.pages,
            tables=seg.tables,
            total_pages=len(seg.pages) if seg.pages else 1,
            total_chars=len(seg.text),
            filename=extraction_result.filename,
            emr_source=extraction_result.emr_source,
            emr_source_confidence=extraction_result.emr_source_confidence,
        )
        results.append(er)
    return results
