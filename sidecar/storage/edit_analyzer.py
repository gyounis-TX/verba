"""Word-level edit analysis for learning physician style corrections.

Uses difflib.SequenceMatcher to find word-level diffs between original
LLM output and physician-edited versions. Tracks:
- Deletions: phrases consistently removed
- Additions: phrases consistently added
- Replacements: A→B swaps

Only tracks patterns appearing 2+ times. Excludes clinical terms to
focus on style/phrasing preferences.
"""

from __future__ import annotations

import difflib
import json
import re
from collections import Counter
from typing import Any

# Clinical terms to exclude from style analysis (these are content, not style)
_CLINICAL_TERMS = {
    "normal", "abnormal", "elevated", "decreased", "mild", "moderate", "severe",
    "critical", "borderline", "within", "range", "stable", "unchanged",
    "improved", "worsened", "significant", "insignificant",
}

# Minimum phrase length in words to track
_MIN_PHRASE_WORDS = 2
_MAX_PHRASE_WORDS = 8


def _tokenize(text: str) -> list[str]:
    """Split text into words, preserving punctuation as separate tokens."""
    return re.findall(r"[\w']+|[.,!?;:—\-]", text.lower())


def _is_clinical(phrase: str) -> bool:
    """Check if a phrase is primarily clinical terminology."""
    words = set(phrase.lower().split())
    clinical_overlap = words & _CLINICAL_TERMS
    return len(clinical_overlap) > len(words) * 0.5


def _extract_ngrams(tokens: list[str], min_n: int = 2, max_n: int = 5) -> list[str]:
    """Extract n-grams from a token list."""
    ngrams = []
    for n in range(min_n, min(max_n + 1, len(tokens) + 1)):
        for i in range(len(tokens) - n + 1):
            phrase = " ".join(tokens[i:i + n])
            if not _is_clinical(phrase):
                ngrams.append(phrase)
    return ngrams


def _analyze_single_edit(original: str, edited: str) -> dict[str, Any]:
    """Analyze a single original→edited pair for word-level changes.

    Returns dict with:
    - deleted_phrases: list of phrases removed
    - added_phrases: list of phrases added
    - replacements: list of (old, new) tuples
    """
    orig_tokens = _tokenize(original)
    edit_tokens = _tokenize(edited)

    matcher = difflib.SequenceMatcher(None, orig_tokens, edit_tokens)

    deleted_phrases: list[str] = []
    added_phrases: list[str] = []
    replacements: list[tuple[str, str]] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue

        old_chunk = " ".join(orig_tokens[i1:i2])
        new_chunk = " ".join(edit_tokens[j1:j2])

        # Skip very short changes (single punctuation, etc.)
        old_words = i2 - i1
        new_words = j2 - j1

        if tag == "delete" and old_words >= _MIN_PHRASE_WORDS and old_words <= _MAX_PHRASE_WORDS:
            if not _is_clinical(old_chunk):
                deleted_phrases.append(old_chunk)

        elif tag == "insert" and new_words >= _MIN_PHRASE_WORDS and new_words <= _MAX_PHRASE_WORDS:
            if not _is_clinical(new_chunk):
                added_phrases.append(new_chunk)

        elif tag == "replace":
            if (old_words >= _MIN_PHRASE_WORDS and new_words >= _MIN_PHRASE_WORDS
                    and old_words <= _MAX_PHRASE_WORDS and new_words <= _MAX_PHRASE_WORDS):
                if not _is_clinical(old_chunk) and not _is_clinical(new_chunk):
                    replacements.append((old_chunk, new_chunk))

    return {
        "deleted_phrases": deleted_phrases,
        "added_phrases": added_phrases,
        "replacements": replacements,
    }


def _fetch_edit_pairs_sync(db: Any, test_type: str, limit: int = 20) -> list[tuple[str, str]]:
    """Fetch original/edited pairs from SQLite database."""
    conn = db._get_conn()
    try:
        rows = conn.execute(
            """SELECT full_response, edited_text FROM history
               WHERE test_type = ? AND edited_text IS NOT NULL
               ORDER BY updated_at DESC LIMIT ?""",
            (test_type, limit),
        ).fetchall()
        pairs = []
        for row in rows:
            try:
                if not row["edited_text"]:
                    continue
                full_response = json.loads(row["full_response"])
                original = full_response.get("explanation", {}).get("overall_summary", "")
                if original:
                    pairs.append((original, row["edited_text"]))
            except (json.JSONDecodeError, TypeError, KeyError):
                continue
        return pairs
    finally:
        conn.close()


async def _fetch_edit_pairs_pg(db: Any, test_type: str, user_id: str | None, limit: int = 20) -> list[tuple[str, str]]:
    """Fetch original/edited pairs from PostgreSQL database."""
    from storage.pg_database import _get_pool
    pool = await _get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT full_response, edited_text FROM history
               WHERE user_id = $1 AND test_type = $2 AND edited_text IS NOT NULL
               ORDER BY updated_at DESC LIMIT $3""",
            user_id, test_type, limit,
        )
    pairs = []
    for row in rows:
        try:
            if not row["edited_text"]:
                continue
            fr_raw = row["full_response"]
            full_response = json.loads(fr_raw) if isinstance(fr_raw, str) else fr_raw
            original = full_response.get("explanation", {}).get("overall_summary", "")
            if original:
                pairs.append((original, row["edited_text"]))
        except (json.JSONDecodeError, TypeError, KeyError):
            continue
    return pairs


def _compute_corrections(pairs: list[tuple[str, str]]) -> dict[str, Any]:
    """Compute aggregate corrections from multiple edit pairs.

    Only returns patterns that appear 2+ times across different edits.
    """
    if not pairs:
        return {"banned": [], "preferred": [], "replacements": []}

    all_deleted: Counter[str] = Counter()
    all_added: Counter[str] = Counter()
    all_replacements: Counter[tuple[str, str]] = Counter()

    for original, edited in pairs:
        result = _analyze_single_edit(original, edited)
        all_deleted.update(result["deleted_phrases"])
        all_added.update(result["added_phrases"])
        all_replacements.update(
            (old, new) for old, new in result["replacements"]
        )

    # Only keep patterns with 2+ occurrences
    banned = [phrase for phrase, count in all_deleted.most_common(15) if count >= 2]
    preferred = [phrase for phrase, count in all_added.most_common(15) if count >= 2]
    replacements = [
        (old, new) for (old, new), count in all_replacements.most_common(15)
        if count >= 2
    ]

    return {
        "banned": banned,
        "preferred": preferred,
        "replacements": replacements,
    }


def get_edit_corrections(
    db: Any, test_type: str, user_id: str | None = None, is_pg: bool = False,
) -> Any:
    """Get edit corrections for a test type.

    Returns a dict (sync) or coroutine (async for PG).
    """
    if is_pg:
        return _get_edit_corrections_pg(db, test_type, user_id)
    else:
        pairs = _fetch_edit_pairs_sync(db, test_type)
        return _compute_corrections(pairs)


async def _get_edit_corrections_pg(
    db: Any, test_type: str, user_id: str | None,
) -> dict[str, Any]:
    pairs = await _fetch_edit_pairs_pg(db, test_type, user_id)
    return _compute_corrections(pairs)


def get_vocabulary_preferences(
    db: Any, test_type: str, user_id: str | None = None, is_pg: bool = False,
) -> Any:
    """Extract vocabulary preferences from edit patterns.

    Returns {preferred: [...], avoided: [...]} mapping word choices.
    """
    if is_pg:
        return _get_vocab_prefs_pg(db, test_type, user_id)
    else:
        pairs = _fetch_edit_pairs_sync(db, test_type)
        return _compute_vocab_preferences(pairs)


async def _get_vocab_prefs_pg(
    db: Any, test_type: str, user_id: str | None,
) -> dict[str, list[str]]:
    pairs = await _fetch_edit_pairs_pg(db, test_type, user_id)
    return _compute_vocab_preferences(pairs)


def _compute_vocab_preferences(pairs: list[tuple[str, str]]) -> dict[str, list[str]]:
    """Compute word-choice preferences from edit pairs.

    Looks for individual word swaps in replacements to learn vocabulary preferences.
    E.g., "labs" → "bloodwork", "robust" → "strong".
    """
    if not pairs:
        return {"preferred": [], "avoided": []}

    word_swaps: Counter[tuple[str, str]] = Counter()

    for original, edited in pairs:
        result = _analyze_single_edit(original, edited)
        for old_phrase, new_phrase in result["replacements"]:
            old_words = old_phrase.split()
            new_words = new_phrase.split()
            # Only track single-word swaps for vocabulary
            if len(old_words) == 1 and len(new_words) == 1:
                if not _is_clinical(old_words[0]) and not _is_clinical(new_words[0]):
                    word_swaps[(old_words[0], new_words[0])] += 1

    # Collect preferences from 2+ occurrences
    preferred = []
    avoided = []
    for (old_word, new_word), count in word_swaps.most_common(20):
        if count >= 2:
            preferred.append(new_word)
            avoided.append(old_word)

    return {"preferred": preferred[:10], "avoided": avoided[:10]}
