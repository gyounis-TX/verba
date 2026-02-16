"""
Regex-based PHI scrubber.

Removes common PHI patterns from medical report text before LLM API calls.
Only modifies the copy sent to the API -- never the original text stored locally.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ScrubResult:
    scrubbed_text: str
    phi_found: list[str]
    redaction_count: int


_PHI_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    # Catch-all: redact everything after "patient name:" (or similar labels)
    # regardless of name format. Must come before structured name patterns.
    (
        "patient_name",
        re.compile(
            r"(?i)(?:patient\s+name|patient|pt\.?\s*name|pt\.?|name)\s*[:=]\s*[^\n]+"
        ),
        "[PATIENT NAME REDACTED]",
    ),
    # Patient name: "Patient: John Doe", "Name: Jane Smith", "Pt: John Doe"
    # Also handles "Patient Name:", "Pt Name:", "Pt.:", variations with commas
    # (Last, First), and optional suffixes/middle initials.
    (
        "patient_name",
        re.compile(
            r"(?i)(?:patient|patient\s+name|pt\.?\s*name|pt\.?|name)\s*[:=]\s*"
            r"(?:"
            # Last, First Middle? format
            r"[A-Z][a-z]+(?:\-[A-Z][a-z]+)?\s*,\s*[A-Z][a-z]+(?:\s+[A-Z]\.?)?"
            r"|"
            # First Middle? Last format
            r"[A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+(?:\-[A-Z][a-z]+)?"
            r")"
            r"(?:\s+(?:Jr|Sr|II|III|IV)\.?)?"
        ),
        "[PATIENT NAME REDACTED]",
    ),
    # Patient name on labeled lines with broader labels seen in reports:
    # "PATIENT:", "CLIENT:", "SUBJECT:", "Examinee:"
    (
        "patient_name",
        re.compile(
            r"(?i)(?:client|subject|examinee|individual)\s*[:=]\s*"
            r"(?:"
            r"[A-Z][a-z]+(?:\-[A-Z][a-z]+)?\s*,\s*[A-Z][a-z]+(?:\s+[A-Z]\.?)?"
            r"|"
            r"[A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+(?:\-[A-Z][a-z]+)?"
            r")"
            r"(?:\s+(?:Jr|Sr|II|III|IV)\.?)?"
        ),
        "[PATIENT NAME REDACTED]",
    ),
    # Date of birth — labeled: "DOB: 01/15/1980", "Date of Birth: January 15, 1980"
    # Also handles "D.O.B.", "Birth Date", "Birthdate", "Born: ..."
    (
        "dob",
        re.compile(
            r"(?i)(?:DOB|D\.O\.B\.|date\s+of\s+birth|birth\s*date|born)\s*[:=]\s*"
            r"(?:\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}|"
            r"[A-Z][a-z]+\s+\d{1,2},?\s+\d{4}|"
            r"\d{4}[/\-]\d{1,2}[/\-]\d{1,2})"
        ),
        "[DOB REDACTED]",
    ),
    # MRN / Medical Record Number — many label variants
    (
        "mrn",
        re.compile(
            r"(?i)(?:MRN|M\.R\.N\.|medical\s+record\s*(?:number|#|no\.?)"
            r"|med\s*rec\s*(?:number|#|no\.?)"
            r"|record\s*(?:number|#|no\.?))"
            r"\s*[:=#]\s*"
            r"[A-Z0-9\-]{4,20}"
        ),
        "[MRN REDACTED]",
    ),
    # MRN: bare parenthesized format common in EHR headers/footers
    # e.g. "Anderson, Joseph N ( 030868921)" or "(MRN 030868921)"
    (
        "mrn",
        re.compile(
            r"\(\s*(?:MRN\s*)?([0-9]{6,20})\s*\)"
        ),
        "[MRN REDACTED]",
    ),
    # SSN: "123-45-6789" or labeled "SSN: 123-45-6789"
    (
        "ssn",
        re.compile(
            r"(?i)(?:SSN|social\s+security(?:\s+(?:number|#|no\.?))?)\s*[:=]?\s*"
            r"\d{3}-\d{2}-\d{4}"
        ),
        "[SSN REDACTED]",
    ),
    # SSN: bare pattern without label
    (
        "ssn",
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "[SSN REDACTED]",
    ),
    # Phone: "(555) 123-4567", "555-123-4567", "555.123.4567"
    # Also handles labeled: "Phone: ...", "Tel: ...", "Fax: ..."
    (
        "phone",
        re.compile(
            r"(?i)(?:(?:phone|telephone|tel|fax|cell|mobile|contact)\s*"
            r"(?:number|#|no\.?)?\s*[:=]\s*)?"
            r"(?<!\d)(?:\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}(?!\d)"
        ),
        "[PHONE REDACTED]",
    ),
    # Email address
    (
        "email",
        re.compile(
            r"(?i)(?:e-?mail\s*[:=]\s*)?[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
        ),
        "[EMAIL REDACTED]",
    ),
    # Address: street number + name + suffix (with optional apt/suite/unit)
    (
        "address",
        re.compile(
            r"\b\d{1,5}\s+(?:[A-Za-z][a-z]+\s+){1,4}"
            r"(?:St(?:reet)?|Ave(?:nue)?|Blvd|Boulevard|Dr(?:ive)?|Ln|Lane|"
            r"Rd|Road|Way|Ct|Court|Pl(?:ace)?|Cir(?:cle)?|Pkwy|Parkway|"
            r"Ter(?:race)?|Trl|Trail|Hwy|Highway)"
            r"\.?"
            r"(?:\s*,?\s*(?:Apt|Suite|Ste|Unit|#)\s*\.?\s*[A-Za-z0-9\-]+)?"
            r"\b"
        ),
        "[ADDRESS REDACTED]",
    ),
    # Labeled address: "Address: ..." — catch full line after label
    (
        "address",
        re.compile(
            r"(?i)(?:address|addr|mailing\s+address|home\s+address|"
            r"street\s+address)\s*[:=]\s*[^\n]+"
        ),
        "[ADDRESS REDACTED]",
    ),
    # City, State ZIP — "Springfield, IL 62704" or "New York, NY 10001-1234"
    (
        "address",
        re.compile(
            r"(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*,\s*"
            r"[A-Z]{2}\s+\d{5}(?:-\d{4})?"
        ),
        "[ADDRESS REDACTED]",
    ),
    # Standalone ZIP code labeled: "Zip: 62704"
    (
        "zip_code",
        re.compile(
            r"(?i)(?:zip\s*(?:code)?|postal\s*code)\s*[:=]\s*\d{5}(?:-\d{4})?"
        ),
        "[ZIP REDACTED]",
    ),
    # Insurance / Policy / Group numbers (before account pattern to match first)
    # NOTE: "plan" requires a qualifier (number/#/ID) to avoid matching
    # clinical "Plan:" section headers common in progress notes.
    (
        "insurance",
        re.compile(
            r"(?i)(?:insurance|policy|group|member|subscriber)\s*"
            r"(?:number|#|no\.?|ID)?\s*[:=]\s*"
            r"[A-Z0-9\-]{4,20}"
        ),
        "[INSURANCE REDACTED]",
    ),
    (
        "insurance",
        re.compile(
            r"(?i)plan\s+(?:number|#|no\.?|ID)\s*[:=]\s*"
            r"[A-Z0-9\-]{4,20}"
        ),
        "[INSURANCE REDACTED]",
    ),
    # Account/ID number: "Account #: 123456789", "Visit #: ...", "Encounter: ..."
    (
        "account_number",
        re.compile(
            r"(?i)(?:account|acct|visit|encounter|case)\s*"
            r"(?:number|#|no\.?|ID)?\s*[:=]\s*"
            r"[A-Z0-9\-]{4,20}"
        ),
        "[ACCOUNT REDACTED]",
    ),
    # Physician names: "Ordering Physician: Dr. John Smith"
    (
        "physician_name",
        re.compile(
            r"(?i)(?:Referred\s+by|Referring\s+Physician|Ordering\s+Physician"
            r"|Ordered\s+by|Referring\s+Provider|Attending\s+Physician"
            r"|Requesting\s+Physician|Primary\s+Care\s+Physician|Clinician"
            r"|Interpreting\s+Physician|Interpreted\s+by|Read\s+by"
            r"|Electronically\s+Signed\s+by|Signed\s+by|Dictated\s+by"
            r"|Verified\s+by|Approved\s+by|Reported\s+by|Finalized\s+by"
            r"|Supervising\s+Physician|Sonographer|Technologist"
            r"|Practice\s+Provider|Provider)"
            r"\s*[:\-]?\s*"
            r"(?:Dr\.?\s*)?"
            r"[A-Za-z][A-Za-z\s.\-']+?"
            r"(?=\s*(?:\n|$|(?:,\s*(?:MD|DO|NP|PA|Ph\.?D|FACC|FACS|FASE|FHRS"
            r"|RPVI|RN|RDCS|RDMS|RT|MBA|MPH|MS|BSN|ARNP|CNP|CRNP|DNP))|"
            r"(?:\s+(?:MD|DO|NP|PA|Ph\.?D|FACC|FACS|FASE|FHRS"
            r"|RPVI|RN|RDCS|RDMS|RT|MBA|MPH|MS|BSN|ARNP|CNP|CRNP|DNP))"
            r"|\s+on\s+\d))"
        ),
        "[PHYSICIAN REDACTED]",
    ),
]


def _build_provider_patterns(names: list[str]) -> list[re.Pattern]:
    """Build whole-word regex patterns for practice provider names.

    For each name, matches the bare name and optional "Dr."/"Dr" prefix.
    Also captures a preceding first name or credentials suffix so that
    "Matthew Bruce" or "Bruce, MD" is fully redacted when "Bruce" is
    in the provider list.

    E.g. provider "Dr. Bruce" → matches "Matthew Bruce", "Dr. Bruce",
    "Bruce, MD", "George A. Bruce, MD, FACC", etc.
    """
    _CREDENTIALS = r"(?:\s*,?\s*(?:MD|DO|NP|PA|Ph\.?D|FACC|FACS|FSCAI|FACP|RN|BSN|MSN|DNP)\.?)*"
    patterns = []
    for name in names:
        bare = re.sub(r"(?i)^dr\.?\s*", "", name).strip()
        if not bare:
            continue
        parts = bare.split()
        if len(parts) >= 2:
            # Full name provided (e.g. "Matthew Bruce") — match as-is plus
            # reversed "Last, First" format, with optional middle initials
            first_escaped = re.escape(parts[0])
            last_escaped = re.escape(parts[-1])
            _MIDDLE = r"(?:\s+[A-Z]\.?)*"
            # "Matthew [A.] Bruce" or "Dr. Matthew [A.] Bruce" + credentials
            patterns.append(re.compile(
                rf"(?i)\b(?:Dr\.?\s*)?{first_escaped}{_MIDDLE}\s+{last_escaped}{_CREDENTIALS}\b"
            ))
            # "Bruce, Matthew [A.]" + credentials
            patterns.append(re.compile(
                rf"(?i)\b{last_escaped}\s*,\s*{first_escaped}{_MIDDLE}{_CREDENTIALS}\b"
            ))
        else:
            # Single name (last name only, e.g. "Bruce") — also capture
            # a preceding first name + optional middle initial
            escaped = re.escape(bare)
            patterns.append(re.compile(
                rf"(?i)\b(?:Dr\.?\s*)?"
                rf"(?:[A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+)?"
                rf"{escaped}"
                rf"{_CREDENTIALS}\b"
            ))
    return patterns


# ---------------------------------------------------------------------------
# Patient-name extraction for second-pass scrubbing
# ---------------------------------------------------------------------------

# Patterns that capture the patient name from labeled occurrences.
_NAME_EXTRACT_PATTERNS: list[re.Pattern] = [
    # "Patient: Last, First M." or "Patient Name: Last, First"
    re.compile(
        r"(?i)(?:patient|patient\s+name|pt\.?\s*name|pt\.?|name)\s*[:=]\s*"
        r"(?P<name>[A-Za-z][A-Za-z'\-]+\s*,\s*[A-Za-z][A-Za-z'\- .]+)"
    ),
    # "Patient: First Last" or "Patient Name: First M. Last"
    re.compile(
        r"(?i)(?:patient|patient\s+name|pt\.?\s*name|pt\.?|name)\s*[:=]\s*"
        r"(?P<name>[A-Za-z][A-Za-z'\-]+(?:\s+[A-Za-z]\.?)?\s+[A-Za-z][A-Za-z'\-]+)"
    ),
    # EHR header pattern: "Last, First M. (MRN ..." or "Last, First M. ( 030..."
    re.compile(
        r"(?P<name>[A-Z][A-Za-z'\-]+\s*,\s*[A-Z][A-Za-z'\- .]+?)"
        r"\s*\(\s*(?:MRN\s*)?[A-Z0-9]{4,20}\s*\)"
    ),
]


def _extract_patient_names(text: str) -> list[str]:
    """Extract patient name variants from labeled or structured occurrences.

    Returns a list of name parts to scrub (full name, last name, first name)
    with duplicates removed. Only returns parts >= 3 chars to avoid
    over-matching short strings like "Mr" or "Jr".
    """
    raw_name: str | None = None
    for pat in _NAME_EXTRACT_PATTERNS:
        m = pat.search(text)
        if m:
            raw_name = m.group("name").strip()
            break

    if not raw_name:
        return []

    # Normalise whitespace
    raw_name = re.sub(r"\s+", " ", raw_name).strip()

    # Build variant list: full name + individual parts
    variants: list[str] = [raw_name]

    # Handle "Last, First Middle" format
    if "," in raw_name:
        parts = [p.strip() for p in raw_name.split(",", 1)]
        last = parts[0]
        first_parts = parts[1].split() if len(parts) > 1 else []
        first = first_parts[0] if first_parts else ""
        # Add "First Last" variant
        if first and last:
            variants.append(f"{first} {last}")
            # Add "First M. Last" if middle initial present
            if len(first_parts) > 1:
                variants.append(f"{first} {' '.join(first_parts[1:])} {last}")
            # Add standalone last and first name (for "Mr. Anderson", "Joseph")
            variants.append(last)
            variants.append(first)
    else:
        # "First Last" format — add "Last, First" variant
        name_parts = raw_name.split()
        if len(name_parts) >= 2:
            first = name_parts[0]
            last = name_parts[-1]
            variants.append(f"{last}, {first}")
            if len(name_parts) > 2:
                middle = " ".join(name_parts[1:-1])
                variants.append(f"{last}, {first} {middle}")
            # Add standalone last and first name
            variants.append(last)
            variants.append(first)

    # Deduplicate, filter short strings, order longest first
    seen: set[str] = set()
    unique: list[str] = []
    for v in variants:
        v_lower = v.strip().lower()
        if len(v.strip()) >= 3 and v_lower not in seen:
            seen.add(v_lower)
            unique.append(v.strip())
    unique.sort(key=len, reverse=True)
    return unique


def scrub_phi(text: str, provider_names: list[str] | None = None) -> ScrubResult:
    """Remove PHI patterns from text. Returns scrubbed copy."""
    scrubbed = text
    categories_found: set[str] = set()
    total_redactions = 0

    # --- Pass 0: extract patient name from labeled/structured occurrences
    # BEFORE any redaction so the original labels are intact for extraction.
    patient_name_variants = _extract_patient_names(text)

    # --- Pass 1: standard pattern-based scrubbing
    for category, pattern, replacement in _PHI_PATTERNS:
        matches = pattern.findall(scrubbed)
        if matches:
            categories_found.add(category)
            total_redactions += len(matches)
            scrubbed = pattern.sub(replacement, scrubbed)

    # --- Pass 2: scrub bare patient name occurrences
    # Uses the name extracted in Pass 0 to catch unlabeled repetitions
    # (EHR headers, footers, inline references like "Anderson, Joseph N").
    if patient_name_variants:
        for variant in patient_name_variants:
            escaped = re.escape(variant)
            # Allow optional middle initial or suffix after the name
            pat = re.compile(
                rf"(?i)\b{escaped}(?:\s+[A-Z]\.?)?(?:\s+(?:Jr|Sr|II|III|IV)\.?)?\b"
            )
            matches = pat.findall(scrubbed)
            if matches:
                categories_found.add("patient_name")
                total_redactions += len(matches)
                scrubbed = pat.sub("[PATIENT NAME REDACTED]", scrubbed)

    # --- Pass 3: scrub practice provider names (bare names without labels)
    if provider_names:
        for pat in _build_provider_patterns(provider_names):
            matches = pat.findall(scrubbed)
            if matches:
                categories_found.add("physician_name")
                total_redactions += len(matches)
                scrubbed = pat.sub("[PHYSICIAN REDACTED]", scrubbed)

    return ScrubResult(
        scrubbed_text=scrubbed,
        phi_found=sorted(categories_found),
        redaction_count=total_redactions,
    )


def compute_patient_fingerprint(text: str) -> str:
    """Compute a deterministic hash of patient identity hints from raw text.

    Extracts patient name, DOB, and MRN patterns, normalises them, and
    returns a SHA-256 hex digest.  Two reports belonging to the same patient
    will produce the same fingerprint.  The actual PHI values are never
    stored — only the hash.

    Returns an empty string if no patient identifiers are found.
    """
    import hashlib

    tokens: list[str] = []

    # Patient name (from label patterns)
    name_pat = re.compile(
        r"(?i)(?:patient(?:\s*name)?|name)\s*[:\-]\s*"
        r"([A-Za-z][A-Za-z\s.\-']{2,40}?)(?=\s*(?:\n|$|,|\s{2}))",
    )
    m = name_pat.search(text)
    if m:
        tokens.append("name:" + re.sub(r"\s+", " ", m.group(1).strip().upper()))

    # DOB
    dob_pat = re.compile(
        r"(?i)(?:DOB|Date\s+of\s+Birth|Birth\s*Date)\s*[:\-]\s*"
        r"(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})",
    )
    m = dob_pat.search(text)
    if m:
        tokens.append("dob:" + m.group(1).strip())

    # MRN / account
    mrn_pat = re.compile(
        r"(?i)(?:MRN|Medical\s+Record|Account|Accession)\s*(?:#|No\.?|Number)?\s*[:\-]?\s*"
        r"([A-Z0-9]{4,20})",
    )
    m = mrn_pat.search(text)
    if m:
        tokens.append("mrn:" + m.group(1).strip().upper())

    if not tokens:
        return ""

    combined = "|".join(sorted(tokens))
    return hashlib.sha256(combined.encode()).hexdigest()
