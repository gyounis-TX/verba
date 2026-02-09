"""Analyze liked/copied outputs to discover severity-conditional communication patterns.

E.g., "when results are normal, always add 'Please continue your current medications.'"
Patterns are structural/communication phrases — never clinical content.
"""

from __future__ import annotations

import json
import re
from typing import Any


# Patterns that indicate structural communication choices (not clinical content)
_REASSURANCE_PATTERNS = re.compile(
    r"(?:reassur|encouraging|good news|no changes|continue (?:your|the) current|"
    r"everything (?:looks|appears) (?:normal|good|healthy|stable)|"
    r"no (?:significant |concerning )?(?:changes|abnormalities|issues)|"
    r"results are (?:normal|within normal|reassuring))",
    re.IGNORECASE,
)

_FOLLOWUP_PATTERNS = re.compile(
    r"(?:we (?:will|should) (?:recheck|follow.?up|monitor|repeat)|"
    r"recommend (?:follow.?up|repeating|rechecking)|"
    r"in \d+ (?:months?|weeks?|years?)|"
    r"schedule (?:a|an) (?:follow.?up|repeat)|"
    r"worth (?:monitoring|watching|keeping an eye))",
    re.IGNORECASE,
)

_ESCALATION_PATTERNS = re.compile(
    r"(?:warrants? (?:further|additional|urgent)|"
    r"I (?:would |strongly )?recommend|"
    r"important (?:that|to)|"
    r"please (?:contact|call|reach out|schedule)|"
    r"(?:should|need to) (?:be seen|discuss|address))",
    re.IGNORECASE,
)


def _classify_phrase(phrase: str) -> str:
    """Classify a phrase as reassurance, follow_up, escalation, or general."""
    if _REASSURANCE_PATTERNS.search(phrase):
        return "reassurance"
    if _FOLLOWUP_PATTERNS.search(phrase):
        return "follow_up"
    if _ESCALATION_PATTERNS.search(phrase):
        return "escalation"
    return "general"


def _is_clinical_content(phrase: str) -> bool:
    """Return True if the phrase contains specific clinical findings/diagnoses.

    We want to learn communication patterns, not reproduce clinical content.
    """
    clinical_indicators = re.compile(
        r"\b(?:\d+\s*(?:mm|cm|ml|mg|%|bpm|mmHg)|"
        r"ejection fraction|stenosis|regurgitation|"
        r"ischemia|infarct|thrombus|embolism|"
        r"hemoglobin|creatinine|glucose|cholesterol|"
        r"TSH|T3|T4|INR|BNP|troponin)\b",
        re.IGNORECASE,
    )
    return bool(clinical_indicators.search(phrase))


def _extract_sentences(text: str) -> list[str]:
    """Split text into sentences, filtering out very short/long ones."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    return [
        s.strip() for s in sentences
        if 15 <= len(s.strip()) <= 200
    ]


async def analyze_and_store_patterns(
    db: Any,
    test_type: str,
    user_id: str | None = None,
    is_pg: bool = False,
) -> None:
    """Fetch recent liked/copied outputs and extract severity-conditional patterns.

    Groups outputs by severity band, finds phrases that appear in >= 3 outputs
    of one band, and stores them as conditional rules.
    """
    from storage.database import _severity_band

    # Fetch recent liked/copied outputs with severity_score
    if is_pg:
        from storage.pg_database import get_pg_db, _get_pool
        pool = await _get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT full_response, edited_text, severity_score
                   FROM history
                   WHERE user_id = $1 AND test_type = $2 AND (liked = true OR copied = true)
                   ORDER BY updated_at DESC LIMIT 20""",
                user_id, test_type,
            )
        rows = [dict(r) for r in rows]
    else:
        import sqlite3
        from storage.database import get_db
        conn = db._get_conn() if hasattr(db, '_get_conn') else get_db()._get_conn()
        try:
            raw_rows = conn.execute(
                """SELECT full_response, edited_text, severity_score
                   FROM history
                   WHERE test_type = ? AND (liked = 1 OR copied = 1)
                   ORDER BY updated_at DESC LIMIT 20""",
                (test_type,),
            ).fetchall()
            rows = [dict(r) for r in raw_rows]
        finally:
            conn.close()

    # Group sentences by severity band
    band_sentences: dict[str, list[str]] = {
        "normal": [], "mild": [], "moderate": [], "severe": [],
    }

    for row in rows:
        sev_score = row.get("severity_score")
        band = _severity_band(sev_score)

        # Prefer edited_text (doctor's actual words)
        text = row.get("edited_text")
        if not text:
            fr_raw = row.get("full_response", "{}")
            try:
                fr = json.loads(fr_raw) if isinstance(fr_raw, str) else fr_raw
                text = fr.get("explanation", {}).get("overall_summary", "")
            except (json.JSONDecodeError, TypeError):
                continue

        if not text:
            continue

        sentences = _extract_sentences(text)
        band_sentences[band].extend(sentences)

    # Find phrases appearing in >= 3 outputs of one band but rarely in others
    all_bands = list(band_sentences.keys())

    for band in all_bands:
        sentences = band_sentences[band]
        if len(sentences) < 3:
            continue

        # Count sentence occurrences (normalized)
        phrase_counts: dict[str, int] = {}
        for s in sentences:
            normalized = s.lower().strip()
            # Truncate for fuzzy matching
            key = normalized[:80]
            phrase_counts[key] = phrase_counts.get(key, 0) + 1

        # Find phrases with count >= 3
        other_sentences_set = set()
        for other_band in all_bands:
            if other_band != band:
                for s in band_sentences[other_band]:
                    other_sentences_set.add(s.lower().strip()[:80])

        for phrase_key, count in phrase_counts.items():
            if count < 3:
                continue
            # Skip if phrase also appears frequently in other bands
            if phrase_key in other_sentences_set:
                continue
            # Skip clinical content
            if _is_clinical_content(phrase_key):
                continue

            # Find original-case version
            original_phrase = phrase_key
            for s in sentences:
                if s.lower().strip()[:80] == phrase_key:
                    original_phrase = s
                    break

            pattern_type = _classify_phrase(original_phrase)

            # Store the rule
            if is_pg:
                pool = await _get_pool()
                async with pool.acquire() as conn:
                    await conn.execute(
                        """INSERT INTO conditional_rules
                           (user_id, test_type, severity_band, phrase, pattern_type, count, updated_at)
                           VALUES ($1, $2, $3, $4, $5, 1, NOW())
                           ON CONFLICT(user_id, test_type, severity_band, phrase) DO UPDATE SET
                           count = conditional_rules.count + 1,
                           pattern_type = $5, updated_at = NOW()""",
                        user_id, test_type, band, original_phrase, pattern_type,
                    )
            else:
                db.upsert_conditional_rule(test_type, band, original_phrase, pattern_type)
