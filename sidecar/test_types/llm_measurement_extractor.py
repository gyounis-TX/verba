"""LLM-assisted measurement extraction for generic test types.

When a GenericTestType has no specialized measurement_extractor, this module
uses the LLM (via structured tool calling) to extract numeric measurements
from the report text. Called as async post-processing in routes.py, NOT in
the sync ``parse()`` path.
"""

from __future__ import annotations

import logging
from typing import Optional

from api.analysis_models import (
    AbnormalityDirection,
    ParsedMeasurement,
    SeverityStatus,
)
from llm.client import LLMClient

logger = logging.getLogger(__name__)

# Tool schema for structured extraction
_TOOL_NAME = "extract_measurements"
_TOOL_SCHEMA = {
    "type": "object",
    "properties": {
        "measurements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Full measurement name (e.g. 'Ejection Fraction')",
                    },
                    "abbreviation": {
                        "type": "string",
                        "description": "Standard abbreviation (e.g. 'LVEF')",
                    },
                    "value": {
                        "type": "number",
                        "description": "Numeric value",
                    },
                    "unit": {
                        "type": "string",
                        "description": "Unit of measurement (e.g. '%', 'cm', 'mg/dL')",
                    },
                    "reference_range": {
                        "type": "string",
                        "description": "Normal reference range if stated (e.g. '55-70%')",
                    },
                    "is_abnormal": {
                        "type": "boolean",
                        "description": "Whether this value is flagged as abnormal in the report",
                    },
                },
                "required": ["name", "abbreviation", "value", "unit"],
            },
            "description": "List of numeric measurements extracted from the report",
        },
    },
    "required": ["measurements"],
}

_MAX_MEASUREMENTS = 20


def _build_system_prompt(test_type_display: str, specialty: str) -> str:
    return (
        f"You are a medical data extraction tool specializing in {specialty}. "
        f"Given a {test_type_display} report, extract numeric measurements. "
        "Only extract explicitly stated numeric values — do not infer or calculate. "
        "Skip patient demographics (age, weight, height, BMI) unless clinically relevant. "
        f"Limit to the {_MAX_MEASUREMENTS} most clinically significant measurements. "
        "For each measurement provide: name, standard abbreviation, numeric value, "
        "unit, reference range (if stated), and whether it is abnormal."
    )


def _build_measurement_excerpt(
    full_text: str, sections_text: str | None = None
) -> str:
    """Build the text excerpt to send to the LLM.

    Prefers FINDINGS/RESULTS/MEASUREMENTS sections if available.
    """
    if sections_text and len(sections_text.strip()) > 100:
        # Use sections text, cap at 4000 chars
        return sections_text[:4000]
    # Fall back to first 3000 chars of full text
    return full_text[:3000]


def _to_parsed_measurement(item: dict) -> Optional[ParsedMeasurement]:
    """Convert a single LLM extraction dict to a ParsedMeasurement."""
    try:
        name = item.get("name", "").strip()
        abbr = item.get("abbreviation", "").strip()
        value = item.get("value")
        unit = item.get("unit", "").strip()

        if not name or value is None:
            return None

        # Ensure value is numeric
        value = float(value)

        # Default abbreviation to first letters of name
        if not abbr:
            abbr = "".join(w[0].upper() for w in name.split() if w)

        # Map is_abnormal to severity/direction
        is_abnormal = item.get("is_abnormal", False)
        ref_range = item.get("reference_range")

        if is_abnormal:
            status = SeverityStatus.MILDLY_ABNORMAL
            direction = AbnormalityDirection.ABOVE_NORMAL
        elif ref_range:
            status = SeverityStatus.NORMAL
            direction = AbnormalityDirection.NORMAL
        else:
            status = SeverityStatus.UNDETERMINED
            direction = AbnormalityDirection.NORMAL

        return ParsedMeasurement(
            name=name,
            abbreviation=abbr,
            value=value,
            unit=unit,
            status=status,
            direction=direction,
            reference_range=ref_range or None,
            raw_text=f"{name}: {value} {unit}",
        )
    except (TypeError, ValueError) as e:
        logger.debug(f"Skipping invalid measurement item: {e}")
        return None


async def llm_extract_measurements(
    client: LLMClient,
    full_text: str,
    sections_text: str | None,
    test_type_display: str,
    specialty: str = "general",
) -> list[ParsedMeasurement]:
    """Use the LLM to extract measurements from report text.

    Returns a list of ParsedMeasurement objects (empty on any failure).
    Deduplicates by abbreviation, hard-capped at 20 measurements.
    """
    try:
        system_prompt = _build_system_prompt(test_type_display, specialty)
        excerpt = _build_measurement_excerpt(full_text, sections_text)

        user_prompt = (
            f"Extract all numeric measurements from this {test_type_display} report:\n\n"
            f"{excerpt}"
        )

        response = await client.call_with_tool(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            tool_name=_TOOL_NAME,
            tool_schema=_TOOL_SCHEMA,
            max_tokens=2048,
            temperature=0.1,
        )

        if not response.tool_call_result:
            logger.debug("LLM measurement extraction: no tool call result")
            return []

        raw_measurements = response.tool_call_result.get("measurements", [])
        if not isinstance(raw_measurements, list):
            return []

        # Convert and deduplicate
        seen_abbrs: set[str] = set()
        results: list[ParsedMeasurement] = []

        for item in raw_measurements:
            if not isinstance(item, dict):
                continue
            parsed = _to_parsed_measurement(item)
            if parsed is None:
                continue

            abbr_key = parsed.abbreviation.lower()
            if abbr_key in seen_abbrs:
                continue
            seen_abbrs.add(abbr_key)
            results.append(parsed)

            if len(results) >= _MAX_MEASUREMENTS:
                break

        logger.info(
            f"LLM extracted {len(results)} measurements for {test_type_display}"
        )
        return results

    except Exception:
        logger.exception("LLM measurement extraction failed")
        return []
