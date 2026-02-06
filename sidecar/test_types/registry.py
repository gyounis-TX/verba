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

    def register(self, handler: BaseTestType) -> None:
        type_id = handler.test_type_id
        if type_id in self._handlers:
            logger.warning(f"Overwriting existing handler for '{type_id}'")
        self._handlers[type_id] = handler
        logger.info(f"Registered test type handler: {type_id}")

    def detect(
        self, extraction_result: ExtractionResult
    ) -> tuple[Optional[str], float]:
        """Auto-detect test type. Returns (type_id, confidence) or (None, 0.0)."""
        best_id: Optional[str] = None
        best_confidence: float = 0.0

        for type_id, handler in self._handlers.items():
            try:
                confidence = handler.detect(extraction_result)
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_id = type_id
            except Exception as e:
                logger.error(f"Detection failed for '{type_id}': {e}")

        return (best_id, best_confidence)

    def get(self, type_id: str) -> Optional[BaseTestType]:
        return self._handlers.get(type_id)

    def resolve(self, type_id_or_name: str) -> tuple[Optional[str], Optional[BaseTestType]]:
        """Resolve a type ID or free-text name to a handler.

        1. Exact ID match (existing behavior)
        2. Keyword match against registered handlers
        Returns (resolved_id, handler) or (None, None).
        """
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
        return [handler.get_metadata() for handler in self._handlers.values()]
