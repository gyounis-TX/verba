"""Extract medical-to-plain-language term preferences from doctor edits.

Compares original generated text with the doctor's edited version to
identify systematic vocabulary choices (e.g., "ejection fraction" → "pumping
strength", or keeping "mitral regurgitation" as-is).
"""

from __future__ import annotations

import difflib
import re
from typing import Any


# Common medical abbreviations and their full terms for matching
_KNOWN_MEDICAL_TERMS: dict[str, list[str]] = {
    "ejection fraction": ["ef", "lvef"],
    "mitral regurgitation": ["mr"],
    "tricuspid regurgitation": ["tr"],
    "aortic stenosis": ["as", "avs"],
    "aortic regurgitation": ["ar", "ai"],
    "left ventricle": ["lv"],
    "right ventricle": ["rv"],
    "left atrium": ["la"],
    "right atrium": ["ra"],
    "interventricular septum": ["ivs", "ivsd"],
    "posterior wall": ["pw", "lvpw"],
    "pulmonary artery": ["pa", "pasp"],
    "diastolic function": [],
    "systolic function": [],
    "pericardial effusion": [],
    "wall motion": [],
    "regional wall motion": ["rwma"],
    "e/a ratio": ["e/a"],
    "e/e' ratio": ["e/e'", "e/e prime"],
    "stroke volume": ["sv"],
    "cardiac output": ["co"],
    "end-diastolic": ["edd", "lved", "lvedd"],
    "end-systolic": ["esd", "lves", "lvesd"],
    "hemoglobin": ["hgb", "hb"],
    "hematocrit": ["hct"],
    "white blood cell": ["wbc"],
    "platelet": ["plt"],
    "creatinine": ["cr", "scr"],
    "blood urea nitrogen": ["bun"],
    "glomerular filtration rate": ["gfr", "egfr"],
    "thyroid stimulating hormone": ["tsh"],
    "cholesterol": ["tc"],
    "triglycerides": ["tg"],
    "low density lipoprotein": ["ldl"],
    "high density lipoprotein": ["hdl"],
    "glycated hemoglobin": ["hba1c", "a1c"],
    "myocardial blood flow": ["mbf"],
    "coronary flow reserve": ["cfr"],
    "summed stress score": ["sss"],
    "summed rest score": ["srs"],
    "summed difference score": ["sds"],
    "transient ischemic dilation": ["tid"],
}


def extract_term_preferences(
    original: str,
    edited: str,
    measurements: list[dict[str, Any]] | None = None,
) -> list[dict[str, str | bool]]:
    """Compare original and edited text to find term substitutions.

    Returns a list of dicts:
        [{"medical_term": "...", "preferred_phrasing": "...", "keep_technical": bool}]
    """
    if not original or not edited:
        return []

    results: list[dict[str, str | bool]] = []
    seen_terms: set[str] = set()

    original_lower = original.lower()
    edited_lower = edited.lower()

    # Strategy 1: Check known medical terms
    for term, abbreviations in _KNOWN_MEDICAL_TERMS.items():
        term_lower = term.lower()
        all_forms = [term_lower] + [a.lower() for a in abbreviations]

        for form in all_forms:
            # Use word boundary check to avoid partial matches
            if form not in original_lower or term_lower in seen_terms:
                continue
            # Verify it's a real word boundary (not a substring of a longer word)
            idx = original_lower.find(form)
            if idx > 0 and original_lower[idx - 1].isalpha():
                continue
            end = idx + len(form)
            if end < len(original_lower) and original_lower[end].isalpha():
                continue

            if form in edited_lower:
                # Term kept — mark as keep_technical
                seen_terms.add(term_lower)
                results.append({
                    "medical_term": term,
                    "preferred_phrasing": term,
                    "keep_technical": True,
                })
            else:
                # Term was replaced — find what it was replaced with
                replacement = _find_replacement(original, edited, form)
                if replacement and replacement.lower() != form:
                    seen_terms.add(term_lower)
                    results.append({
                        "medical_term": term,
                        "preferred_phrasing": replacement,
                        "keep_technical": False,
                    })
            break  # Only process first matching form

    # Strategy 2: Check measurement abbreviations
    if measurements:
        for m in measurements:
            abbrev = m.get("abbreviation", "")
            name = m.get("name", "")
            if not abbrev:
                continue

            abbrev_lower = abbrev.lower()
            name_lower = name.lower() if name else ""

            if name_lower and name_lower not in seen_terms:
                if name_lower in original_lower and name_lower not in edited_lower:
                    replacement = _find_replacement(original, edited, name_lower)
                    if replacement and replacement.lower() != name_lower:
                        seen_terms.add(name_lower)
                        results.append({
                            "medical_term": name,
                            "preferred_phrasing": replacement,
                            "keep_technical": False,
                        })
                elif abbrev_lower in original_lower and abbrev_lower not in edited_lower:
                    replacement = _find_replacement(original, edited, abbrev_lower)
                    if replacement and replacement.lower() != abbrev_lower:
                        seen_terms.add(name_lower or abbrev_lower)
                        results.append({
                            "medical_term": name or abbrev,
                            "preferred_phrasing": replacement,
                            "keep_technical": False,
                        })

    return results


def _find_replacement(original: str, edited: str, term: str) -> str | None:
    """Find what replaced a term in the edited text.

    Strategy: Find the term position in original, extract surrounding context
    (before/after), then locate that same context in the edited text and
    extract what's between the before/after anchors.
    """
    term_lower = term.lower()
    orig_lower = original.lower()
    pos = orig_lower.find(term_lower)
    if pos == -1:
        return None

    # Extract context anchors (words before and after the term)
    before_text = original[:pos].rstrip()
    after_text = original[pos + len(term):].lstrip()

    # Get last ~20 chars before as anchor
    before_anchor = before_text[-20:].lower() if before_text else ""
    # Get first ~20 chars after as anchor
    after_anchor = after_text[:20].lower() if after_text else ""

    edited_lower = edited.lower()

    # Find before_anchor in edited text
    before_pos = -1
    if before_anchor:
        before_pos = edited_lower.find(before_anchor)

    # Find after_anchor in edited text
    after_pos = -1
    if after_anchor:
        search_start = (before_pos + len(before_anchor)) if before_pos >= 0 else 0
        after_pos = edited_lower.find(after_anchor, search_start)

    # Extract replacement from between anchors
    if before_pos >= 0 and after_pos >= 0:
        start = before_pos + len(before_anchor)
        replacement = edited[start:after_pos].strip()
        if 2 <= len(replacement) <= 100:
            return replacement

    # Fallback: use word-level diff
    orig_words = original.split()
    edit_words = edited.split()
    matcher = difflib.SequenceMatcher(None, orig_words, edit_words)

    term_words = term.lower().split()
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "replace":
            replaced_words = [w.lower() for w in orig_words[i1:i2]]
            # Check if any of the term words are in the replaced segment
            if any(tw in replaced_words for tw in term_words):
                replacement = " ".join(edit_words[j1:j2])
                if 2 <= len(replacement) <= 100:
                    return replacement

    return None
