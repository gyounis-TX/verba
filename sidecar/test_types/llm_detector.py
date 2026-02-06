"""
LLM-based test type detection fallback.

Uses a cheap LLM call to classify a medical report when keyword-based
detection returns low confidence.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from llm.client import LLMClient

logger = logging.getLogger(__name__)


def _build_system_prompt(registry_types: list[dict]) -> str:
    """Build classifier prompt from currently registered types.

    Groups types by category for readability and omits keyword listings
    to keep the prompt compact as the type count grows.
    """
    lines = [
        "You are a medical report classifier. Given the text of a medical "
        "report, identify which type of test it represents.",
        "",
        "Available test types (grouped by category):",
    ]

    # Group by category
    from collections import defaultdict
    groups: dict[str, list[dict]] = defaultdict(list)
    for t in registry_types:
        groups[t.get("category", "other")].append(t)

    # Pretty labels for category headers
    category_labels = {
        "cardiac": "Cardiac",
        "vascular": "Vascular",
        "lab": "Laboratory",
        "imaging_ct": "CT Imaging",
        "imaging_mri": "MRI",
        "imaging_ultrasound": "Ultrasound",
        "imaging_xray": "X-Ray / Radiography",
        "pulmonary": "Pulmonary",
        "neurophysiology": "Neurophysiology",
        "endoscopy": "Endoscopy",
        "pathology": "Pathology",
        "other": "Other",
    }

    idx = 1
    for cat, cat_types in groups.items():
        label = category_labels.get(cat, cat.replace("_", " ").title())
        lines.append(f"\n[{label}]")
        for t in cat_types:
            lines.append(f"  {idx}. {t['test_type_id']} — {t['display_name']}")
            idx += 1

    lines.append("")
    lines.append(
        "If the report is a body-part-specific variant of a modality "
        "(e.g., MRI Lumbar Spine), map to the modality-level type (e.g., mri). "
        "Prefer specific types when they exist (e.g., use ct_chest for a chest CT, "
        "not ct_scan; use chest_xray for a chest X-ray, not xray)."
    )
    lines.append("")
    lines.append(
        'Respond with a JSON object only — no markdown, no explanation:\n'
        '{"test_type_id": "<id>", "display_name": "<name>", '
        '"confidence": <0.0-1.0>, "reasoning": "<one sentence>"}'
    )
    lines.append(
        "If the report does not match any listed type, use the CLOSEST "
        "match or create a descriptive snake_case ID."
    )
    return "\n".join(lines)


async def llm_detect_test_type(
    client: LLMClient,
    report_text: str,
    user_hint: Optional[str] = None,
    registry_types: list[dict] | None = None,
) -> tuple[Optional[str], float, Optional[str]]:
    """Classify a medical report using an LLM.

    Returns (test_type_id, confidence, display_name) or (None, 0.0, None)
    on any failure.
    """
    if registry_types is None:
        registry_types = []

    system_prompt = _build_system_prompt(registry_types)

    # Truncate to keep cost low
    truncated = report_text[:2000]

    user_prompt = f"Report text:\n\n{truncated}"
    if user_hint:
        user_prompt += f'\n\nThe user describes this report as: "{user_hint}"'

    try:
        response = await client.call(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=200,
            temperature=0.0,
        )

        raw = response.text_content.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()

        parsed = json.loads(raw)
        type_id = parsed.get("test_type_id")
        confidence = float(parsed.get("confidence", 0.0))
        display_name = parsed.get("display_name")

        logger.info(
            "LLM detection: type=%s confidence=%.2f display=%s reasoning=%s",
            type_id,
            confidence,
            display_name,
            parsed.get("reasoning", ""),
        )
        return (type_id, confidence, display_name)

    except Exception:
        logger.exception("LLM test type detection failed")
        return (None, 0.0, None)
