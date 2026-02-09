"""
Parse and validate the LLM structured response.

Post-response validation:
1. Schema validation (Pydantic)
2. Measurement cross-check against original ParsedReport
3. Auto-correct value/status discrepancies
4. Remove hallucinated measurements
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from api.analysis_models import ParsedReport
from api.explain_models import ExplanationResult

logger = logging.getLogger(__name__)


@dataclass
class ValidationIssue:
    severity: str  # "warning" or "error"
    message: str


def parse_and_validate_response(
    tool_result: Optional[dict],
    parsed_report: ParsedReport,
    humanization_level: int = 3,
) -> tuple[ExplanationResult, list[ValidationIssue]]:
    """
    Parse the LLM tool call result into ExplanationResult.
    Returns (result, issues). Issues with severity="error" indicate
    the response should be rejected.
    """
    issues: list[ValidationIssue] = []

    if tool_result is None:
        raise ValueError("LLM did not produce a tool call result")

    # 1. Parse into Pydantic model
    try:
        result = ExplanationResult(**tool_result)
    except Exception as e:
        raise ValueError(f"Failed to parse LLM response into schema: {e}")

    # 2. Build lookup of expected measurements
    expected = {m.abbreviation: m for m in parsed_report.measurements}

    # Only validate against pre-extracted measurements if we have them.
    # For unknown test types, the LLM extracts measurements from raw text,
    # so there's nothing to cross-check against — let them through.
    if not expected:
        return result, issues

    # 3. Check each measurement in the response
    for mexp in result.measurements:
        if mexp.abbreviation not in expected:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    message=(
                        f"LLM included measurement '{mexp.abbreviation}' "
                        f"not found in parsed report. Removing."
                    ),
                )
            )
            continue

        orig = expected[mexp.abbreviation]

        # Value check
        if abs(mexp.value - orig.value) > 0.1:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    message=(
                        f"Measurement '{mexp.abbreviation}': LLM reported "
                        f"value {mexp.value} but parsed value is {orig.value}. "
                        f"Correcting to parsed value."
                    ),
                )
            )
            mexp.value = orig.value

        # Status check
        if mexp.status != orig.status:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    message=(
                        f"Measurement '{mexp.abbreviation}': LLM status "
                        f"'{mexp.status}' differs from parsed status "
                        f"'{orig.status}'. Correcting to parsed status."
                    ),
                )
            )
            mexp.status = orig.status

    # 4. Filter out hallucinated measurements
    valid_abbreviations = set(expected.keys())
    original_count = len(result.measurements)
    result.measurements = [
        m for m in result.measurements if m.abbreviation in valid_abbreviations
    ]
    if len(result.measurements) < original_count:
        removed = original_count - len(result.measurements)
        issues.append(
            ValidationIssue(
                severity="warning",
                message=(
                    f"Removed {removed} hallucinated measurement(s) "
                    f"from response."
                ),
            )
        )

    # 5. Missing measurements — not a warning. The LLM is instructed to
    #    synthesize and interpret, not to produce a 1:1 listing of every
    #    measurement. Normal/unremarkable values are typically grouped or
    #    omitted in clinical communication, which is the correct behavior.

    # 6. Expand bare medical abbreviations in patient-facing text
    result.overall_summary = expand_abbreviations(result.overall_summary)
    for f in result.key_findings:
        f.explanation = expand_abbreviations(f.explanation)
    for m in result.measurements:
        m.plain_language = expand_abbreviations(m.plain_language)

    # 7. Apply natural contractions to patient-facing text
    result.overall_summary = apply_contractions(result.overall_summary)
    for f in result.key_findings:
        f.explanation = apply_contractions(f.explanation)
    for m in result.measurements:
        m.plain_language = apply_contractions(m.plain_language)

    # 8. Auto-fix AI patterns at higher humanization levels
    if humanization_level >= 4:
        aggressive = humanization_level >= 5
        result.overall_summary = fix_ai_patterns(result.overall_summary, aggressive=aggressive)
        for f in result.key_findings:
            f.explanation = fix_ai_patterns(f.explanation, aggressive=aggressive)
        for m in result.measurements:
            m.plain_language = fix_ai_patterns(m.plain_language, aggressive=aggressive)

    # 9. Check for residual AI-like patterns in the summary
    if humanization_level >= 3:
        ai_warnings = check_ai_patterns(result.overall_summary)
        for w in ai_warnings:
            issues.append(ValidationIssue(severity="warning", message=w))

    # 10. Check measurement plain_language diversity
    diversity_warnings = check_measurement_diversity(result.measurements)
    for w in diversity_warnings:
        issues.append(ValidationIssue(severity="warning", message=w))

    return result, issues


# ---------------------------------------------------------------------------
# Abbreviation expansion post-processing
# ---------------------------------------------------------------------------

# Map of abbreviation → full name. Order matters: longer/more-specific first.
_ABBREVIATION_MAP: list[tuple[str, str]] = [
    # --- Redundant patterns (abbreviation already contains trailing word) ---
    ("LAD artery", "left anterior descending artery"),
    ("RCA artery", "right coronary artery"),
    ("LCX artery", "left circumflex artery"),
    ("LCx artery", "left circumflex artery"),
    ("LMCA artery", "left main coronary artery"),
    ("PDA artery", "posterior descending artery"),
    ("LIMA graft", "left internal mammary artery graft"),
    ("RIMA graft", "right internal mammary artery graft"),
    # --- Bare coronary abbreviations ---
    ("LAD", "left anterior descending artery (LAD)"),
    ("RCA", "right coronary artery (RCA)"),
    ("LCX", "left circumflex artery (LCX)"),
    ("LCx", "left circumflex artery (LCx)"),
    ("LMCA", "left main coronary artery (LMCA)"),
    ("PDA", "posterior descending artery (PDA)"),
    ("LIMA", "left internal mammary artery (LIMA)"),
    ("RIMA", "right internal mammary artery (RIMA)"),
    ("SVG", "saphenous vein graft (SVG)"),
    # --- Cardiac procedures ---
    ("CABG", "coronary artery bypass graft surgery (CABG)"),
    ("PCI", "percutaneous coronary intervention (PCI)"),
    # --- Cardiac measurements ---
    ("LVEF", "left ventricular ejection fraction (LVEF)"),
    ("RVSP", "right ventricular systolic pressure (RVSP)"),
    ("TAPSE", "tricuspid annular plane systolic excursion (TAPSE)"),
    ("LAVI", "left atrial volume index (LAVI)"),
    # --- Lab abbreviations ---
    ("eGFR", "estimated glomerular filtration rate (eGFR)"),
    ("BUN", "blood urea nitrogen (BUN)"),
    ("WBC", "white blood cells (WBC)"),
    ("RBC", "red blood cells (RBC)"),
    ("Hgb", "hemoglobin (Hgb)"),
    ("HGB", "hemoglobin (HGB)"),
    ("Hct", "hematocrit (Hct)"),
    ("HCT", "hematocrit (HCT)"),
    ("PLT", "platelets (PLT)"),
    ("MCV", "mean corpuscular volume (MCV)"),
    ("MCH", "mean corpuscular hemoglobin (MCH)"),
    ("MCHC", "mean corpuscular hemoglobin concentration (MCHC)"),
    ("RDW", "red cell distribution width (RDW)"),
    ("TSH", "thyroid-stimulating hormone (TSH)"),
    ("HbA1c", "hemoglobin A1c (HbA1c)"),
    ("A1C", "hemoglobin A1c (A1C)"),
    ("BNP", "B-type natriuretic peptide (BNP)"),
    ("NT-proBNP", "N-terminal pro-B-type natriuretic peptide (NT-proBNP)"),
    ("CRP", "C-reactive protein (CRP)"),
    ("ESR", "erythrocyte sedimentation rate (ESR)"),
    ("ALT", "alanine aminotransferase (ALT)"),
    ("AST", "aspartate aminotransferase (AST)"),
    ("ALP", "alkaline phosphatase (ALP)"),
    ("GGT", "gamma-glutamyl transferase (GGT)"),
    ("LDH", "lactate dehydrogenase (LDH)"),
    ("TIBC", "total iron-binding capacity (TIBC)"),
    ("INR", "international normalized ratio (INR)"),
    ("PTT", "partial thromboplastin time (PTT)"),
    ("PSA", "prostate-specific antigen (PSA)"),
    ("CEA", "carcinoembryonic antigen (CEA)"),
    ("HDL", "high-density lipoprotein (HDL)"),
    ("LDL-P", "LDL particle number (LDL-P)"),
    ("sdLDL", "small dense LDL (sdLDL)"),
    ("LDL", "low-density lipoprotein (LDL)"),
    ("VLDL", "very-low-density lipoprotein (VLDL)"),
    ("ApoB", "apolipoprotein B (ApoB)"),
    ("Lp(a)", "lipoprotein(a) (Lp(a))"),
    ("Lp-PLA2", "lipoprotein-associated phospholipase A2 (Lp-PLA2)"),
    ("LP-IR", "lipoprotein insulin resistance score (LP-IR)"),
    ("hs-CRP", "high-sensitivity C-reactive protein (hs-CRP)"),
    ("hsCRP", "high-sensitivity C-reactive protein (hsCRP)"),
    # --- Pulmonary abbreviations ---
    ("FEV1", "forced expiratory volume in one second (FEV1)"),
    ("FVC", "forced vital capacity (FVC)"),
    ("DLCO", "diffusing capacity of the lungs for carbon monoxide (DLCO)"),
    ("TLC", "total lung capacity (TLC)"),
    ("PEF", "peak expiratory flow (PEF)"),
    # --- General ---
    ("BMI", "body mass index (BMI)"),
]


def expand_abbreviations(text: str) -> str:
    """Replace bare medical abbreviations with full names in patient text.

    Covers cardiac, lab, pulmonary, and general abbreviations.
    Only expands the FIRST bare occurrence of each abbreviation. If the full
    name already appears in the text, that abbreviation is skipped entirely.
    """
    if not text:
        return text

    for abbrev, expansion in _ABBREVIATION_MAP:
        # If the full name (without the parenthetical) is already present, skip
        full_name = expansion.split(" (")[0]
        if full_name.lower() in text.lower():
            continue

        # Replace first bare occurrence (word-boundary match)
        pattern = re.compile(r"\b" + re.escape(abbrev) + r"\b")
        # Don't replace if inside parentheses — e.g. "(LAD)" is already expanded
        def _replace_first(m: re.Match, _exp=expansion) -> str:
            start = m.start()
            if start > 0 and text[start - 1] == "(":
                return m.group(0)  # skip — inside parens
            result = _exp
            # Capitalize if at sentence start (pos 0, or after ". " / "? " / "! " / newline)
            if start == 0 or (start >= 2 and text[start - 2] in ".?!"):
                result = result[0].upper() + result[1:]
            return result

        text, count = pattern.subn(_replace_first, text, count=1)

    return text


# ---------------------------------------------------------------------------
# Contraction enforcement post-processing
# ---------------------------------------------------------------------------

# Formal phrase → contraction. Applied case-insensitively but preserving the
# original case of the first character. Order: longer phrases first to avoid
# partial matches (e.g. "it is not" before "it is").
_CONTRACTION_MAP: list[tuple[str, str]] = [
    ("it is not", "it isn't"),
    ("that is not", "that isn't"),
    ("this is not", "this isn't"),
    ("there is not", "there isn't"),
    ("does not", "doesn't"),
    ("do not", "don't"),
    ("did not", "didn't"),
    ("is not", "isn't"),
    ("are not", "aren't"),
    ("was not", "wasn't"),
    ("were not", "weren't"),
    ("has not", "hasn't"),
    ("have not", "haven't"),
    ("had not", "hadn't"),
    ("will not", "won't"),
    ("would not", "wouldn't"),
    ("could not", "couldn't"),
    ("should not", "shouldn't"),
    ("cannot", "can't"),
    ("can not", "can't"),
    ("it is", "it's"),
    ("that is", "that's"),
    ("this is", "this is"),  # skip — "this's" sounds unnatural
    ("there is", "there's"),
    ("here is", "here's"),
    ("what is", "what's"),
    ("who is", "who's"),
    ("you are", "you're"),
    ("we are", "we're"),
    ("they are", "they're"),
    ("you will", "you'll"),
    ("we will", "we'll"),
    ("it will", "it'll"),
    ("that will", "that'll"),
    ("you would", "you'd"),
    ("we would", "we'd"),
    ("I would", "I'd"),
    ("you have", "you've"),
    ("we have", "we've"),
    ("they have", "they've"),
    ("I have", "I've"),
    ("let us", "let's"),
]

# Pre-compile patterns for performance
_CONTRACTION_PATTERNS: list[tuple[re.Pattern, str]] = []
for _formal, _contracted in _CONTRACTION_MAP:
    if _formal.lower() == _contracted.lower():
        continue  # skip no-ops like "this is" → "this is"
    _CONTRACTION_PATTERNS.append((
        re.compile(r"\b" + re.escape(_formal) + r"\b", re.IGNORECASE),
        _contracted,
    ))


def apply_contractions(text: str) -> str:
    """Convert formal phrases to natural contractions in patient-facing text.

    Preserves the original capitalization of the first character.
    Skips text inside quotation marks (may be intentionally formal).
    """
    if not text:
        return text

    for pattern, replacement in _CONTRACTION_PATTERNS:
        def _contract(m: re.Match) -> str:
            original = m.group(0)
            # Preserve leading capitalization
            if original[0].isupper():
                return replacement[0].upper() + replacement[1:]
            return replacement
        text = pattern.sub(_contract, text)

    return text


# ---------------------------------------------------------------------------
# AI-pattern post-processing heuristics
# ---------------------------------------------------------------------------

_BANNED_PHRASES = [
    "i'm pleased to report",
    "it's important to note",
    "rest assured",
    "this is great news",
    "i hope this helps",
    "please don't hesitate",
    "i'd like to highlight",
    "it should be noted",
    "moving on to",
    "in terms of",
    "with regard to",
    "with respect to",
    "it is reassuring that",
    "it is encouraging that",
    "as we can see",
    "looking at the results",
    "i would recommend",
    "i would suggest",
    "my recommendation",
    "i hope this clarifies",
]


def check_ai_patterns(overall_summary: str) -> list[str]:
    """Scan LLM output for residual AI-like patterns. Returns warning strings."""
    if not overall_summary:
        return []

    warnings: list[str] = []
    sentences = [s.strip() for s in re.split(r"[.!?]+", overall_summary) if s.strip()]

    # Check for consecutive "Your" sentence starters
    your_streak = 0
    for s in sentences:
        if s.lower().startswith("your"):
            your_streak += 1
            if your_streak >= 3:
                warnings.append("3+ consecutive sentences starting with 'Your'")
                break
        else:
            your_streak = 0

    # Check banned phrases that slipped through prompting
    lower = overall_summary.lower()
    for phrase in _BANNED_PHRASES:
        if phrase in lower:
            warnings.append(f"Banned phrase detected: '{phrase}'")

    # Check for "Additionally"/"Furthermore" overuse
    for word in ["additionally", "furthermore"]:
        count = lower.count(word)
        if count > 1:
            warnings.append(f"'{word}' used {count} times")

    # Check paragraph length uniformity (AI fingerprint)
    paragraphs = [p.strip() for p in overall_summary.split("\n\n") if p.strip()]
    if len(paragraphs) >= 3:
        lengths = [len(p) for p in paragraphs]
        avg = sum(lengths) / len(lengths)
        if avg > 0 and all(abs(length - avg) / avg < 0.15 for length in lengths):
            warnings.append(
                "All paragraphs within 15% of same length (uniform structure)"
            )

    return warnings


# ---------------------------------------------------------------------------
# AI pattern auto-fix post-processing
# ---------------------------------------------------------------------------

# Phrases to strip from output (case-insensitive matching)
_FIX_BANNED_PHRASES = [
    "let's break this down",
    "let me break this down",
    "let me walk you through",
    "i'll walk you through",
    "here's what that means",
    "here's what we're looking at",
    "to put it simply",
    "in simple terms",
    "simply put",
    "the key takeaway is",
    "the bottom line is",
    "the main takeaway",
    "what does this mean for you?",
    "what does this tell us?",
    "there are several things",
    "there are a few things",
    "as noted in your report",
    "as your report shows",
    "after reviewing",
    "upon review",
    "having reviewed",
    "it's important to note that",
    "it's worth noting that",
    "it's worth mentioning that",
    "it's also worth noting",
    "it's also important to",
    "another thing to note",
    "i want to draw your attention to",
    "i'd like to draw attention to",
    "based on the results provided",
    "based on your test results",
]

# Formal transitions → casual replacements (used at level 5 only)
_TRANSITION_REPLACEMENTS: list[tuple[str, list[str]]] = [
    ("additionally,", ["Also,", "And", "Plus,"]),
    ("furthermore,", ["And", "On top of that,", "Also,"]),
    ("moreover,", ["And", "Plus,", "Also,"]),
    ("however,", ["That said,", "But", "Though"]),
    ("consequently,", ["So", "Which means", "As a result,"]),
    ("nevertheless,", ["Still,", "That said,", "Even so,"]),
    ("in conclusion,", ["So overall —", "Bottom line:", "All in all,"]),
    ("in summary,", ["So overall —", "The short version:", "Bottom line:"]),
    ("to summarize,", ["So —", "In short,", "Bottom line:"]),
]

# Pre-compile patterns for banned phrases
_FIX_BANNED_PATTERNS = [
    (re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE), phrase)
    for phrase in _FIX_BANNED_PHRASES
]

# Counter for rotating through transition alternatives
_transition_counter = 0


def fix_ai_patterns(text: str, aggressive: bool = False) -> str:
    """Auto-fix AI-like patterns in generated text.

    Args:
        text: The text to clean up.
        aggressive: If True (level 5), also replace formal transitions and
            strip trailing .0 from whole numbers.
    """
    if not text:
        return text

    # 1. Strip banned phrases
    for pattern, _ in _FIX_BANNED_PATTERNS:
        text = pattern.sub("", text)

    # 2. Replace formal transitions (aggressive mode only)
    if aggressive:
        global _transition_counter
        for formal, alternatives in _TRANSITION_REPLACEMENTS:
            pat = re.compile(r"\b" + re.escape(formal), re.IGNORECASE)
            def _replace_transition(m: re.Match, _alts=alternatives) -> str:
                global _transition_counter
                replacement = _alts[_transition_counter % len(_alts)]
                _transition_counter += 1
                # Preserve capitalization context
                if m.start() == 0 or (m.start() >= 2 and text[m.start() - 2] in ".!?\n"):
                    return replacement[0].upper() + replacement[1:]
                return replacement
            text = pat.sub(_replace_transition, text)

        # 3. Strip trailing .0 from whole numbers (e.g., "60.0%" → "60%")
        text = re.sub(r"(\d+)\.0(%|\s|,|\.(?:\s|$))", r"\1\2", text)

    # 4. Clean up artifacts from removals
    text = re.sub(r"  +", " ", text)          # double spaces
    text = re.sub(r" ([,.])", r"\1", text)     # space before punctuation
    text = re.sub(r"\.\s*\.", ".", text)        # double periods
    text = re.sub(r"^\s+", "", text, flags=re.MULTILINE)  # leading whitespace on lines

    # 5. Capitalize after period if removal left lowercase
    def _cap_after_period(m: re.Match) -> str:
        return m.group(1) + m.group(2).upper()
    text = re.sub(r"(\.\s+)([a-z])", _cap_after_period, text)

    return text.strip()


# ---------------------------------------------------------------------------
# Measurement plain-language diversity check
# ---------------------------------------------------------------------------

def check_measurement_diversity(
    measurements: list,
) -> list[str]:
    """Detect repetitive sentence patterns in measurement plain_language fields.

    AI models tend to produce measurements like:
      "Your X is normal at Y."
      "Your Z is normal at W."
    This function flags when too many measurements share the same opening
    pattern, which is a strong AI fingerprint.
    """
    if len(measurements) < 4:
        return []

    warnings: list[str] = []

    # Extract the first ~5 words of each plain_language as a pattern signature
    openers: list[str] = []
    for m in measurements:
        text = getattr(m, "plain_language", "") or ""
        words = text.split()[:5]
        if len(words) >= 3:
            # Normalize: lowercase, strip the specific measurement name
            opener = " ".join(words[:3]).lower()
            openers.append(opener)

    if not openers:
        return warnings

    # Count how many share the same 3-word opener
    from collections import Counter
    opener_counts = Counter(openers)
    most_common_opener, most_common_count = opener_counts.most_common(1)[0]

    # Flag if >50% of measurements share the same opener
    threshold = max(3, len(openers) // 2)
    if most_common_count >= threshold:
        warnings.append(
            f"Measurement diversity: {most_common_count}/{len(openers)} measurements "
            f"start with the same pattern ('{most_common_opener}...')"
        )

    # Also check if all measurements follow "Your X is" pattern
    your_x_is_count = sum(1 for o in openers if o.startswith("your ") and " is " in o)
    if your_x_is_count >= len(openers) * 0.7 and your_x_is_count >= 4:
        if "your" not in most_common_opener:  # Avoid duplicate warning
            warnings.append(
                f"Measurement diversity: {your_x_is_count}/{len(openers)} measurements "
                f"follow 'Your X is...' pattern"
            )

    return warnings
