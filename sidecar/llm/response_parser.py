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

    return result, issues
