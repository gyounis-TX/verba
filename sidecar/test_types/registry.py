from __future__ import annotations

import logging
from typing import Optional

from api.models import ExtractionResult
from .base import BaseTestType

logger = logging.getLogger(__name__)


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

    def detect(
        self, extraction_result: ExtractionResult
    ) -> tuple[Optional[str], float]:
        """Auto-detect test type. Returns (type_id, confidence) or (None, 0.0)."""
        best_id: Optional[str] = None
        best_confidence: float = 0.0
        best_handler: Optional[BaseTestType] = None

        for type_id, handler in self._handlers.items():
            try:
                confidence = handler.detect(extraction_result)
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_id = type_id
                    best_handler = handler
            except Exception as e:
                logger.error(f"Detection failed for '{type_id}': {e}")

        # Allow family-style handlers to resolve to a specific subtype
        if best_handler is not None:
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
