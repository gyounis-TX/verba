from __future__ import annotations

import logging
import re
from typing import Optional

from api.models import ExtractionResult
from .base import BaseTestType

logger = logging.getLogger(__name__)

_HEADER_PATTERNS = [
    re.compile(r"(?i)(?:report|procedure|study|exam(?:ination)?|test)\s*(?:type)?[:\-]\s*(.+)", re.MULTILINE),
    re.compile(r"(?i)^(?:IMPRESSION|INDICATION|FINDINGS)\s+(?:FOR|OF)\s+(.+)", re.MULTILINE),
]


class TestTypeRegistry:
    """Registry for medical test type handlers."""

    def __init__(self):
        self._handlers: dict[str, BaseTestType] = {}
        # Maps subtype IDs to their parent family handler
        self._subtype_parents: dict[str, BaseTestType] = {}
        # Handler IDs that are family parents (hidden from list_types)
        self._hidden_ids: set[str] = set()

    def register(self, handler: BaseTestType) -> None:
        type_id = handler.test_type_id
        if type_id in self._handlers:
            logger.warning(f"Overwriting existing handler for '{type_id}'")
        self._handlers[type_id] = handler
        logger.info(f"Registered test type handler: {type_id}")

    def register_subtype(self, subtype_id: str, parent_handler: BaseTestType) -> None:
        """Map a subtype ID to its parent family handler."""
        self._subtype_parents[subtype_id] = parent_handler
        # Hide the parent from type listings (replaced by subtypes)
        self._hidden_ids.add(parent_handler.test_type_id)

    def detect_from_header(self, extraction_result: ExtractionResult) -> tuple[Optional[str], float]:
        """Pre-pass: scan first 500 chars for explicit report type labels."""
        header_text = extraction_result.full_text[:500]
        for pattern in _HEADER_PATTERNS:
            m = pattern.search(header_text)
            if m:
                label = m.group(1).strip().rstrip(".")
                resolved_id, handler = self.resolve(label)
                if resolved_id is not None:
                    return (resolved_id, 0.85)
        return (None, 0.0)

    def detect(
        self, extraction_result: ExtractionResult
    ) -> tuple[Optional[str], float]:
        """Auto-detect test type. Returns (type_id, confidence) or (None, 0.0)."""
        # Pre-pass: explicit header labels
        header_id, header_conf = self.detect_from_header(extraction_result)
        if header_id is not None:
            return (header_id, header_conf)

        scores: list[tuple[str, float, BaseTestType]] = []
        for type_id, handler in self._handlers.items():
            try:
                confidence = handler.detect(extraction_result)
                if confidence > 0.0:
                    scores.append((type_id, confidence, handler))
            except Exception as e:
                logger.error(f"Detection failed for '{type_id}': {e}")

        if not scores:
            return (None, 0.0)

        scores.sort(key=lambda x: x[1], reverse=True)
        best_id, best_confidence, best_handler = scores[0]

        # Disambiguation: prefer specialized over generic when close
        if len(scores) >= 2:
            _, second_conf, second_handler = scores[1]
            if best_confidence - second_conf <= 0.15:
                from test_types.generic import GenericTestType
                if isinstance(best_handler, GenericTestType) and not isinstance(second_handler, GenericTestType):
                    best_id, best_confidence, best_handler = scores[1]

        # Allow family-style handlers to resolve to a specific subtype
        subtype = best_handler.resolve_subtype(extraction_result)
        if subtype is not None:
            best_id = subtype[0]

        return (best_id, best_confidence)

    def detect_multi(
        self, extraction_result: ExtractionResult, threshold: float = 0.3,
    ) -> list[tuple[str, float]]:
        """Detect all test types above *threshold*.

        Returns list of (type_id, confidence) sorted descending by confidence.
        The first entry is the primary type.
        """
        results: list[tuple[str, float]] = []

        # Pre-pass: explicit header labels
        header_id, header_conf = self.detect_from_header(extraction_result)
        if header_id is not None:
            results.append((header_id, header_conf))

        for type_id, handler in self._handlers.items():
            try:
                confidence = handler.detect(extraction_result)
                if confidence >= threshold:
                    # Resolve subtypes
                    resolved_id = type_id
                    subtype = handler.resolve_subtype(extraction_result)
                    if subtype is not None:
                        resolved_id = subtype[0]
                    results.append((resolved_id, confidence))
            except Exception as e:
                logger.error(f"Multi-detection failed for '{type_id}': {e}")

        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def get(self, type_id: str) -> Optional[BaseTestType]:
        # Prefer specialized family handler for subtype IDs
        parent = self._subtype_parents.get(type_id)
        if parent is not None:
            return parent
        return self._handlers.get(type_id)

    def resolve(self, type_id_or_name: str) -> tuple[Optional[str], Optional[BaseTestType]]:
        """Resolve a type ID or free-text name to a handler.

        1. Exact ID match (existing behavior)
        2. Subtype parent match (family handlers)
        3. Keyword match against registered handlers
        Returns (resolved_id, handler) or (None, None).
        """
        # Subtype parent match — prefer the specialized family handler
        parent = self._subtype_parents.get(type_id_or_name)
        if parent is not None:
            return (type_id_or_name, parent)

        # Exact match
        handler = self._handlers.get(type_id_or_name)
        if handler is not None:
            return (type_id_or_name, handler)

        # Keyword match: check if the user string matches any handler's keywords
        query = type_id_or_name.lower()
        best_handler = None
        best_id: Optional[str] = None
        best_score = 0
        for tid, h in self._handlers.items():
            for kw in h.keywords:
                if kw.lower() in query or query in kw.lower():
                    score = len(kw)  # longer keyword match = more specific
                    if score > best_score:
                        best_score = score
                        best_handler = h
                        best_id = tid

        return (best_id, best_handler) if best_handler else (None, None)

    def list_types(self) -> list[dict]:
        return [
            handler.get_metadata()
            for tid, handler in self._handlers.items()
            if tid not in self._hidden_ids
        ]
