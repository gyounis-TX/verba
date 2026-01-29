"""
Prompt construction for medical report explanation.

Builds a system prompt (role, rules, anti-hallucination constraints)
and a user prompt (parsed report data, reference ranges, glossary).
"""

from __future__ import annotations

from enum import Enum

from api.analysis_models import ParsedReport


class LiteracyLevel(str, Enum):
    GRADE_4 = "grade_4"
    GRADE_6 = "grade_6"
    GRADE_8 = "grade_8"
    CLINICAL = "clinical"


_LITERACY_DESCRIPTIONS: dict[LiteracyLevel, str] = {
    LiteracyLevel.GRADE_4: (
        "Write at a 4th-grade reading level. Use very simple words and short "
        "sentences. Avoid all medical jargon. Use analogies a child could "
        "understand."
    ),
    LiteracyLevel.GRADE_6: (
        "Write at a 6th-grade reading level. Use simple, clear language. "
        "Briefly define medical terms when you must use them. Keep sentences "
        "short."
    ),
    LiteracyLevel.GRADE_8: (
        "Write at an 8th-grade reading level. Use clear language, briefly "
        "defining technical terms. Moderate sentence complexity is acceptable."
    ),
    LiteracyLevel.CLINICAL: (
        "Write at a clinical level suitable for a healthcare professional. "
        "Use standard medical terminology. Be precise and concise."
    ),
}


class PromptEngine:
    """Constructs system and user prompts for report explanation."""

    def build_system_prompt(
        self,
        literacy_level: LiteracyLevel,
        prompt_context: dict,
    ) -> str:
        """Build the system prompt with role, rules, and constraints."""
        literacy_desc = _LITERACY_DESCRIPTIONS[literacy_level]
        specialty = prompt_context.get("specialty", "general medicine")
        guidelines = prompt_context.get("guidelines", "standard clinical guidelines")
        explanation_style = prompt_context.get("explanation_style", "")
        tone = prompt_context.get("tone", "")

        tone_section = f"## Tone\n{tone}\n\n" if tone else ""

        return (
            f"You are a medical report explanation assistant specializing "
            f"in {specialty}.\n"
            f"Your task is to explain a medical report to a patient in "
            f"plain language.\n\n"
            f"## Literacy Level\n{literacy_desc}\n\n"
            f"## Clinical Guidelines\n"
            f"Base your interpretations on: {guidelines}\n\n"
            f"## Explanation Style\n{explanation_style}\n\n"
            f"{tone_section}"
            f"## Critical Rules\n"
            f"1. ONLY use data that appears in the report provided. "
            f"NEVER invent, guess, or assume measurements, findings, or "
            f"diagnoses that are not explicitly stated.\n"
            f"2. For each measurement, the app has already classified it "
            f"against reference ranges. You MUST use the status provided "
            f"(normal, mildly_abnormal, etc.) -- do NOT re-classify.\n"
            f"3. When explaining a measurement, always mention the patient's "
            f"value, the normal range, and what the status means.\n"
            f"4. If a measurement has status \"undetermined\", say the value "
            f"was noted but cannot be classified without more context.\n"
            f"5. The disclaimer MUST state: this is an AI-generated "
            f"explanation, not medical advice; always discuss results with "
            f"your healthcare provider; the AI may make errors.\n"
            f"6. Do NOT mention the patient by name or include any personally "
            f"identifying information.\n"
            f"7. Call the explain_report tool with your response. Do not "
            f"produce any output outside of this tool call."
        )

    def build_user_prompt(
        self,
        parsed_report: ParsedReport,
        reference_ranges: dict,
        glossary: dict[str, str],
        scrubbed_text: str,
        clinical_context: str | None = None,
        template_instructions: str | None = None,
        closing_text: str | None = None,
    ) -> str:
        """Build the user prompt with report data, ranges, and glossary."""
        sections: list[str] = []

        # 1. Report text (scrubbed)
        sections.append("## Report Text (PHI Removed)")
        sections.append(scrubbed_text)

        # 1b. Clinical context (if provided)
        if clinical_context:
            sections.append("\n## Clinical Context")
            sections.append(
                f"The clinical reason for this test: {clinical_context}\n"
                f"Prioritize findings relevant to this clinical context in your explanation."
            )

        # 1c. Template instructions (if provided)
        if template_instructions:
            sections.append("\n## Structure Instructions")
            sections.append(template_instructions)
        if closing_text:
            sections.append("\n## Closing Text")
            sections.append(
                f"End the overall_summary with the following closing text:\n{closing_text}"
            )

        # 2. Parsed measurements with reference ranges
        sections.append("\n## Parsed Measurements")
        if parsed_report.measurements:
            for m in parsed_report.measurements:
                ref_info = ""
                if m.abbreviation in reference_ranges:
                    rr = reference_ranges[m.abbreviation]
                    parts: list[str] = []
                    if rr.get("normal_min") is not None:
                        parts.append(f"min={rr['normal_min']}")
                    if rr.get("normal_max") is not None:
                        parts.append(f"max={rr['normal_max']}")
                    if parts:
                        ref_info = (
                            f" | Normal range: {', '.join(parts)} "
                            f"{rr.get('unit', '')}"
                        )

                sections.append(
                    f"- {m.name} ({m.abbreviation}): {m.value} {m.unit} "
                    f"[status: {m.status.value}]{ref_info}"
                )
        else:
            sections.append("No structured measurements were extracted.")

        # 3. Findings
        if parsed_report.findings:
            sections.append("\n## Report Findings/Conclusions")
            for f in parsed_report.findings:
                sections.append(f"- {f}")

        # 4. Sections
        if parsed_report.sections:
            sections.append("\n## Report Sections")
            for s in parsed_report.sections:
                sections.append(f"### {s.name}")
                sections.append(s.content)

        # 5. Glossary
        sections.append(
            "\n## Glossary (use these definitions when explaining terms)"
        )
        for term, definition in glossary.items():
            sections.append(f"- **{term}**: {definition}")

        # 6. Instructions
        sections.append(
            "\n## Instructions\n"
            "Using ONLY the data above, generate a structured explanation by "
            "calling the explain_report tool. Include all measurements listed "
            "above. Do not add measurements or findings not present in the data."
        )

        return "\n".join(sections)
