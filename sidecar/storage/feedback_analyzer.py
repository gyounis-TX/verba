"""Feedback analyzer: categorize quality rating notes into prompt adjustments.

When physicians rate outputs <= 3/5 and provide notes, this module categorizes
the notes by keyword and generates specific prompt adjustments.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

# Feedback categories with keyword patterns and prompt adjustments
_FEEDBACK_CATEGORIES: dict[str, dict[str, Any]] = {
    "LENGTH_TOO_LONG": {
        "patterns": [
            r"\b(too long|too wordy|too verbose|too detailed|shorter|more concise|brevity|trim|reduce)\b",
        ],
        "adjustment": "Be more concise. The physician finds recent outputs too long. Reduce length by 20-30%.",
    },
    "LENGTH_TOO_SHORT": {
        "patterns": [
            r"\b(too short|too brief|more detail|not enough|elaborate|expand|more info)\b",
        ],
        "adjustment": "Provide more detail. The physician finds recent outputs too brief. Expand explanations.",
    },
    "TONE_TOO_ALARMING": {
        "patterns": [
            r"\b(too alarming|too scary|too worrying|tone down|softer|less scary|frightening|alarming)\b",
        ],
        "adjustment": "Soften the tone. Avoid language that may cause unnecessary anxiety. Use reassuring framing where clinically appropriate.",
    },
    "TONE_TOO_CASUAL": {
        "patterns": [
            r"\b(too casual|more professional|more formal|unprofessional|informal)\b",
        ],
        "adjustment": "Use a more professional tone. Avoid overly casual language.",
    },
    "TONE_TOO_CLINICAL": {
        "patterns": [
            r"\b(too clinical|too technical|too medical|jargon|simpler|plain language|easier to understand)\b",
        ],
        "adjustment": "Use simpler language. Avoid medical jargon and explain concepts in plain terms.",
    },
    "MISSED_FINDING": {
        "patterns": [
            r"\b(missed|missing|didn't mention|forgot|overlooked|left out|omitted|incomplete)\b",
        ],
        "adjustment": "Be more thorough. Check that all clinically relevant findings from the report are addressed.",
    },
    "WRONG_INTERPRETATION": {
        "patterns": [
            r"\b(wrong|incorrect|inaccurate|error|mistake|misinterpreted|not right)\b",
        ],
        "adjustment": "Double-check clinical interpretations carefully against the provided reference ranges and measurement data.",
    },
    "STRUCTURE_ISSUE": {
        "patterns": [
            r"\b(structure|organization|organize|layout|format|formatting|flow|order)\b",
        ],
        "adjustment": "Improve the organizational structure. Group related findings together and use clear transitions.",
    },
}

# Minimum occurrences of a category before adding the adjustment
_MIN_CATEGORY_COUNT = 2


def _categorize_note(note: str) -> list[str]:
    """Categorize a single feedback note into one or more categories."""
    categories = []
    note_lower = note.lower()
    for cat_name, cat_info in _FEEDBACK_CATEGORIES.items():
        for pattern in cat_info["patterns"]:
            if re.search(pattern, note_lower, re.IGNORECASE):
                categories.append(cat_name)
                break
    return categories


def _compute_adjustments(feedback_rows: list[dict[str, Any]]) -> list[str]:
    """Compute prompt adjustments from feedback rows.

    Only includes adjustments for categories that appear 2+ times.
    """
    if not feedback_rows:
        return []

    category_counts: Counter[str] = Counter()
    for row in feedback_rows:
        note = row.get("quality_note", "")
        if note:
            categories = _categorize_note(note)
            category_counts.update(categories)

    adjustments = []
    for cat_name, count in category_counts.most_common():
        if count >= _MIN_CATEGORY_COUNT:
            adjustment = _FEEDBACK_CATEGORIES[cat_name]["adjustment"]
            adjustments.append(adjustment)

    return adjustments


def get_feedback_adjustments(
    db: Any, test_type: str, user_id: str | None = None, is_pg: bool = False,
) -> Any:
    """Get feedback-based prompt adjustments for a test type.

    Returns a list of adjustment strings (sync) or coroutine (async for PG).
    """
    if is_pg:
        return _get_feedback_adjustments_pg(db, test_type, user_id)
    else:
        return _get_feedback_adjustments_sync(db, test_type)


def _get_feedback_adjustments_sync(db: Any, test_type: str) -> list[str]:
    feedback_rows = db.get_recent_feedback(test_type, limit=10)
    return _compute_adjustments(feedback_rows)


async def _get_feedback_adjustments_pg(
    db: Any, test_type: str, user_id: str | None,
) -> list[str]:
    feedback_rows = await db.get_recent_feedback(test_type, limit=10, user_id=user_id)
    return _compute_adjustments(feedback_rows)
