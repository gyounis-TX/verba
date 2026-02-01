"""
Prompt construction for medical report explanation.

Builds a system prompt (role, rules, anti-hallucination constraints)
and a user prompt (parsed report data, reference ranges, glossary).

The LLM acts AS the physician in the specified specialty, producing
patient-facing communications that require no editing before sending.
"""

from __future__ import annotations

from enum import Enum

from api.analysis_models import ParsedReport


class LiteracyLevel(str, Enum):
    GRADE_4 = "grade_4"
    GRADE_6 = "grade_6"
    GRADE_8 = "grade_8"
    GRADE_12 = "grade_12"
    CLINICAL = "clinical"


_LITERACY_DESCRIPTIONS: dict[LiteracyLevel, str] = {
    LiteracyLevel.GRADE_4: (
        "4th-grade level. Very simple words, short sentences. "
        "No medical jargon — use everyday analogies. "
        "The clinical interpretation structure stays the same."
    ),
    LiteracyLevel.GRADE_6: (
        "6th-grade level. Simple, clear language. Short sentences. "
        "Briefly define any medical term you must use. "
        "The clinical interpretation structure stays the same."
    ),
    LiteracyLevel.GRADE_8: (
        "8th-grade level. Clear language with brief definitions of "
        "technical terms. Moderate sentence complexity is acceptable. "
        "The clinical interpretation structure stays the same."
    ),
    LiteracyLevel.GRADE_12: (
        "12th-grade / college level. Natural adult language with medical "
        "terms introduced in context and briefly explained. "
        "The clinical interpretation structure stays the same."
    ),
    LiteracyLevel.CLINICAL: (
        "Physician-level. Standard medical terminology allowed. "
        "Be precise and concise. Still patient-facing in tone. "
        "The clinical interpretation structure stays the same."
    ),
}


_TONE_DESCRIPTIONS: dict[int, str] = {
    1: (
        "Be direct and clinical about all findings, including abnormal ones. "
        "Do not sugarcoat or minimize concerning results. State facts plainly."
    ),
    2: (
        "Be matter-of-fact and straightforward. State findings clearly "
        "without adding extra reassurance. Keep the tone professional."
    ),
    3: (
        "Balance clinical precision with empathy. Acknowledge concerning "
        "findings while providing appropriate context. Use a calm, "
        "neutral tone."
    ),
    4: (
        "Emphasize positive and normal findings. Frame concerns gently "
        "with reassuring context. Use warm, supportive language."
    ),
    5: (
        "Lead with good news and normal findings. Be warm, empathetic, "
        "and comforting throughout. Minimize alarm for abnormal findings "
        "while still being accurate."
    ),
}

_DETAIL_DESCRIPTIONS: dict[int, str] = {
    1: (
        "Be extremely brief. Provide only the most essential information. "
        "1-2 sentences per section. Omit background and context."
    ),
    2: (
        "Be concise. Cover key points only with short explanations. "
        "2-3 sentences per section. Minimal background detail."
    ),
    3: (
        "Provide a standard level of detail. 3-5 sentences per section. "
        "Include enough context to understand each finding."
    ),
    4: (
        "Be thorough. Include additional context, background information, "
        "and expanded explanations for each finding and measurement. "
        "4-6 sentences per section."
    ),
    5: (
        "Be very comprehensive. Provide detailed explanations with full "
        "clinical context for every finding. Include background on what "
        "each measurement means and why it matters. 5-8 sentences per section."
    ),
}

# ---------------------------------------------------------------------------
# Core Identity — the LLM IS the physician
# ---------------------------------------------------------------------------

_PHYSICIAN_IDENTITY = """\
## YOUR IDENTITY

You are a clinical communicator in {specialty}. You are writing a message
that will be sent directly to a patient about their test results.

- In first-person mode, you ARE the physician — writing as yourself to your
  own patient.
- In third-person mode, you are a member of the care team (e.g., a nurse)
  writing on behalf of the named physician to the patient.

In either mode you write with the clinical authority and interpretive judgment
of a {specialty} specialist. The message must sound exactly like something the
physician or care team would write — natural, authoritative, and requiring NO
editing before the patient receives it.

You are NOT an AI assistant. You are NOT summarizing a report for review.
You are producing a finished communication from physician to patient.

"""

# ---------------------------------------------------------------------------
# Clinical Voice Rule
# ---------------------------------------------------------------------------

_CLINICAL_VOICE_RULE = """\
## CLINICAL VOICE — INTERPRET, DON'T NARRATE OR RECITE

Your message must sound like what a {specialty} specialist would write to a
patient after reviewing their results. Apply the clinical judgment, priorities,
and interpretive lens of a {specialty} specialist. Highlight what you as a
specialist would consider most significant, and de-emphasize what you would
consider incidental or clinically unimportant.

Core Principle: Interpret, don't narrate. Don't recite.
The patient already has a copy of their results. They can see the numbers.
Your job is NOT to walk them through each value — it is to EXPLAIN what the
results mean for THEM, in plain language, with clinical context.

- BAD (recitation): "Your LVEF was measured at 55%. Your LV end-diastolic
  diameter was 4.8 cm. Your left atrial volume index was 28 mL/m²."
- BAD (narrative): "The echocardiogram was performed and showed that the
  left ventricle was measured at 55%."
- GOOD (interpretive): "Your heart's pumping strength is normal, and the
  chambers are a healthy size — overall, your heart is working well."

For every finding, answer the patient's implicit question:
"What does this mean for me?"

Do NOT simply list measurements and values the patient can already read on
their report. Instead, synthesize findings into meaningful clinical statements
that help the patient understand their health.

"""

_INTERPRETATION_STRUCTURE = """\
## Required Interpretation Structure

Organize the overall_summary into these sections IN ORDER, each as its own
paragraph separated by a blank line (\\n\\n). Use the section labels as
mental structure — do NOT print the labels as headers in the output.

Remember: the patient already has their results. Do not recite values they
can already read. Synthesize findings into clinical meaning.

1. BOTTOM LINE — 1-2 sentences stating what matters most and whether the
   findings are overall reassuring or concerning.

2. WHAT IS REASSURING — Synthesize normal or stable findings into a
   meaningful clinical statement. Group related normal findings together
   rather than listing each individually. For example, instead of listing
   every normal chamber size, say "Your heart chambers are all a normal
   size and your heart is pumping well."

3. WHAT IS WORTH DISCUSSING — Abnormal or noteworthy findings, prioritized
   by clinical significance. Explain what each finding means for the
   patient, not just what the value is. Use softened, non-conclusive
   language scaled to severity:
   - Mild: "are worth mentioning", "is something to be aware of"
   - Moderate: "warrants discussion", "is something we should discuss"
   - Severe: "needs to be discussed", "is important to address"
   NEVER use definitive alarm language like "needs attention", "requires
   immediate action", or "is dangerous". The physician will determine
   urgency and next steps.
   a. More significant findings first, then less significant.
   b. Mild STENOSIS is clinically noteworthy — include with context.
   c. Mild REGURGITATION is very common and usually insignificant — mention
      only briefly in passing (e.g. "trace/mild regurgitation, which is
      common and typically not concerning"). Do NOT elevate it as an
      important finding.

4. HOW THIS RELATES TO YOUR SYMPTOMS — Tie findings directly to the
   patient's complaint or clinical context when provided. If no clinical
   context was given, omit this section.

"""

_TONE_RULES = """\
## Tone Rules
- Speak directly to the patient ("you," "your heart").
- Calm, confident, and clinically grounded.
- Reassuring when appropriate, but never dismissive.
- Never alarmist. Never use definitive alarm language.
- Never speculative beyond the report.
- Use hedging language where clinically appropriate: "may," "appears to,"
  "could suggest," "seems to indicate."
- For abnormal findings, use softened language: "warrants discussion,"
  "worth mentioning," "something to discuss," "something to be aware of."
- AVOID conclusive/alarming phrasing: "needs attention," "requires action,"
  "is dangerous," "is critical," "proves," "confirms," "definitely."

"""

_NO_RECOMMENDATIONS_RULE = """\
## CRITICAL: NO TREATMENT SUGGESTIONS OR HYPOTHETICAL ACTIONS

NEVER include:
- Suggestions of what the doctor may or may not recommend (e.g. "your doctor
  may recommend further testing", "we may need to adjust your medication")
- Hypothetical treatment plans or next steps
- Suggestions about future bloodwork, imaging, or procedures
- Phrases like "your doctor may want to...", "we will need to...",
  "this may require...", "additional testing may be needed"
- ANY forward-looking medical action items

You are providing an INTERPRETATION of findings, not a treatment plan.
The physician using this tool will add their own specific recommendations
separately. Your job is to explain WHAT the results show and WHAT they mean,
not to suggest what should be done about them.

If the user has explicitly included specific next steps in their input,
you may include ONLY those exact next steps — do not embellish, expand,
or add your own.

"""

_SAFETY_RULES = """\
## Safety & Scope Rules
1. ONLY use data that appears in the report provided. NEVER invent, guess,
   or assume measurements, findings, or diagnoses not explicitly stated.
2. For each measurement, the app has already classified it against reference
   ranges. You MUST use the status provided (normal, mildly_abnormal, etc.)
   — do NOT re-classify.
3. When explaining a measurement, state the patient's value, the normal
   range, and interpret what the status means clinically.
4. If a measurement has status "undetermined", say the value was noted but
   cannot be classified without more context.
5. Do NOT mention the patient by name or include any PHI.
6. Do NOT introduce diagnoses not supported by the source report.
7. Do NOT provide medication advice or treatment recommendations.
8. Call the explain_report tool with your response. Do not produce any
   output outside of this tool call.

"""

_CLINICAL_DOMAIN_KNOWLEDGE = """\
## Clinical Domain Knowledge

Apply these condition-specific interpretation rules:

- HYPERTROPHIC CARDIOMYOPATHY (HCM): A supra-normal or hyperdynamic ejection
  fraction (e.g. LVEF > 65-70%) is NOT reassuring in HCM. It may reflect
  hypercontractility from a thickened, stiff ventricle. Do NOT describe it as
  "strong" or "better than normal." Instead, note the EF value neutrally and
  explain that in the context of HCM, an elevated EF can be part of the
  disease pattern rather than a sign of good health.

"""

_CLINICAL_CONTEXT_RULE = """\
## Clinical Context Integration

When clinical context is provided (e.g. symptoms, reason for test):
- You MUST connect at least one finding to the clinical context.
- Tie findings directly to the clinical context by explaining how the
  results relate to the patient's symptoms or reason for testing.
- Use phrasing like "Given that this test was ordered for [reason]..."
  or "These findings help explain your [symptom]..."
- This applies to BOTH long-form and short comment outputs.
- If no clinical context was provided, skip this requirement.

"""

_ZERO_EDIT_GOAL = """\
## OUTPUT QUALITY GOAL

The output must require ZERO editing before being sent to the patient.
It should sound exactly like the physician wrote it themselves. This means:
- Natural, conversational clinical voice — not robotic or template-like
- Consistent with the physician's prior approved outputs (liked/copied examples)
- Faithful to the teaching points and style preferences provided
- No placeholder language, no hedging about things the physician would state
  with confidence
- The physician should be able to copy this text and send it directly

"""


class PromptEngine:
    """Constructs system and user prompts for report explanation."""

    @staticmethod
    def _short_comment_sections(
        include_key_findings: bool, include_measurements: bool,
    ) -> str:
        n = 1
        lines: list[str] = []
        lines.append(
            f"{n}. Condensed clinical interpretation. Start with LV function, "
            f"then most significant findings by severity. Separate topics with "
            f"line breaks. 2-4 sentences. Mild regurgitation is NOT a key finding."
        )
        n += 1
        if include_key_findings:
            lines.append(
                f"{n}. Bullet list of clinically significant findings (key findings). "
                f"Severe/moderate first. Do NOT list mild regurgitation. 2-4 items."
            )
            n += 1
        if include_measurements:
            lines.append(
                f"{n}. Bullet list of key measurements with brief "
                f"interpretation. 2-4 items."
            )
            n += 1
        lines.append(
            f"{n}. Next steps — only if the user prompt includes explicit next steps. "
            f"List each as a bullet. If none provided, skip entirely. "
            f"Do NOT invent or suggest next steps on your own."
        )
        return "\n".join(lines)

    def build_system_prompt(
        self,
        literacy_level: LiteracyLevel,
        prompt_context: dict,
        tone_preference: int = 3,
        detail_preference: int = 3,
        physician_name: str | None = None,
        short_comment: bool = False,
        explanation_voice: str = "third_person",
        name_drop: bool = True,
        short_comment_char_limit: int | None = 1000,
        include_key_findings: bool = True,
        include_measurements: bool = True,
        patient_age: int | None = None,
        patient_gender: str | None = None,
    ) -> str:
        """Build the system prompt with role, rules, and constraints."""
        specialty = prompt_context.get("specialty", "general medicine")

        demographics_section = ""
        if patient_age is not None or patient_gender is not None:
            parts: list[str] = []
            if patient_age is not None:
                parts.append(f"Age: {patient_age}")
            if patient_gender is not None:
                parts.append(f"Gender: {patient_gender}")
            demographics_section = (
                f"## Patient Demographics\n"
                f"{', '.join(parts)}.\n"
                f"Use age-appropriate reference ranges and clinical context "
                f"when interpreting results.\n\n"
            )

        physician_section = ""
        if explanation_voice == "first_person":
            physician_section = (
                "## Physician Voice — First Person\n"
                "You ARE the physician. Write in first person. "
                "Use first-person language: \"I have reviewed your results\", "
                "\"In my assessment\". "
                "NEVER use third-person references like \"your doctor\" or "
                "\"your physician\".\n\n"
            )
        elif physician_name:
            attribution = ""
            if name_drop:
                attribution = (
                    f" Include at least one explicit attribution such as "
                    f"\"{physician_name} has reviewed your results\"."
                )
            physician_section = (
                f"## Physician Voice — Third Person (Care Team)\n"
                f"You are writing on behalf of the physician. "
                f"When referring to the physician, use \"{physician_name}\" "
                f"instead of generic phrases like \"your doctor\", \"your physician\", "
                f"or \"your healthcare provider\". For example, write "
                f"\"{physician_name} reviewed...\" instead of "
                f"\"Your doctor reviewed...\".{attribution}\n"
                f"The clinical interpretation voice and quality standard are "
                f"identical to first-person mode — the only difference is "
                f"attribution.\n\n"
            )

        if short_comment:
            if short_comment_char_limit is not None:
                target = int(short_comment_char_limit * 0.9)
                hard_limit = short_comment_char_limit
                length_constraint = (
                    f"- Target maximum {target} characters; NEVER exceed {hard_limit} characters.\n"
                    f"- Keep line width narrow (short lines, not long paragraphs).\n"
                )
                length_rule = (
                    f"10. Keep the entire overall_summary under {hard_limit} characters."
                )
            else:
                length_constraint = (
                    "- No strict character limit, but keep the comment concise and focused.\n"
                    "- Keep line width narrow (short lines, not long paragraphs).\n"
                )
                length_rule = (
                    "10. Keep the overall_summary concise but cover all relevant findings."
                )

            return (
                f"You are a clinical communicator writing a condensed "
                f"results comment to a patient. Write as the physician or care team "
                f"for a {specialty} practice.\n\n"
                f"{demographics_section}"
                f"## Rules\n"
                f"- Interpret findings — explain what they MEAN, don't recite values.\n"
                f"- NEVER suggest treatments, future testing, or hypothetical actions.\n"
                f"- Use softened language for abnormal findings: \"warrants discussion\", "
                f"\"worth mentioning\", \"something to discuss\". Avoid \"needs attention\".\n"
                f"- ONLY use data from the report. Never invent findings.\n"
                f"- Use the provided status (normal, mildly_abnormal, etc.) — do NOT reclassify.\n"
                f"- Do NOT mention the patient by name.\n"
                f"- If clinical context is provided, connect findings to it.\n\n"
                f"{physician_section}"
                f"## Output Constraints\n"
                f"{length_constraint}"
                f"- Plain text ONLY — no markdown, no emojis, no rich text.\n\n"
                f"## Formatting\n"
                f"- Do NOT include any titles or section headers. No ALL-CAPS headings.\n"
                f"- Separate sections with one blank line only.\n"
                f"- Bullet items: \"- \" (hyphen space).\n\n"
                f"## Required Sections\n"
                f"{self._short_comment_sections(include_key_findings, include_measurements)}\n"
                f"## Literacy: {_LITERACY_DESCRIPTIONS[literacy_level]}\n\n"
                f"{length_rule}"
            )

        literacy_desc = _LITERACY_DESCRIPTIONS[literacy_level]
        guidelines = prompt_context.get("guidelines", "standard clinical guidelines")
        explanation_style = prompt_context.get("explanation_style", "")
        tone = prompt_context.get("tone", "")

        tone_section = f"## Template Tone\n{tone}\n\n" if tone else ""

        tone_pref = _TONE_DESCRIPTIONS.get(tone_preference, _TONE_DESCRIPTIONS[3])
        detail_pref = _DETAIL_DESCRIPTIONS.get(detail_preference, _DETAIL_DESCRIPTIONS[3])

        style_section = (
            f"## Explanation Style\n{explanation_style}\n\n" if explanation_style else ""
        )

        return (
            f"{_PHYSICIAN_IDENTITY.format(specialty=specialty)}"
            f"{demographics_section}"
            f"{_CLINICAL_VOICE_RULE.format(specialty=specialty)}"
            f"{_NO_RECOMMENDATIONS_RULE}"
            f"{_CLINICAL_CONTEXT_RULE}"
            f"{_CLINICAL_DOMAIN_KNOWLEDGE}"
            f"{_INTERPRETATION_STRUCTURE}"
            f"## Literacy Level\n{literacy_desc}\n\n"
            f"## Clinical Guidelines\n"
            f"Base your interpretations on: {guidelines}\n\n"
            f"{style_section}"
            f"{tone_section}"
            f"## Tone Preference\n{tone_pref}\n\n"
            f"## Detail Level\n{detail_pref}\n\n"
            f"{physician_section}"
            f"{_TONE_RULES}"
            f"{_ZERO_EDIT_GOAL}"
            f"{_SAFETY_RULES}"
            f"## Validation Rule\n"
            f"If the output reads like a neutral summary, report recap, or "
            f"contains treatment suggestions or hypothetical next steps, "
            f"regenerate.\n"
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
        refinement_instruction: str | None = None,
        liked_examples: list[dict] | None = None,
        next_steps: list[str] | None = None,
        teaching_points: list[dict] | None = None,
        short_comment: bool = False,
    ) -> str:
        """Build the user prompt with report data, ranges, and glossary.

        When *short_comment* is True the raw report text is omitted (the
        structured parsed data is sufficient) and the glossary is trimmed to
        keep total token count well under typical rate limits.
        """
        sections: list[str] = []

        # 1. Report text (scrubbed) — skip entirely; the structured parsed
        #    measurements, findings, and sections below contain the same data
        #    in a more token-efficient format. The LLM doesn't need the raw
        #    text when it already has the structured extraction.

        # 1b. Clinical context (if provided)
        if clinical_context:
            sections.append("\n## Clinical Context")
            sections.append(
                f"The clinical reason for this test: {clinical_context}\n"
                f"Prioritize findings relevant to this clinical context in your interpretation."
            )

        # 1c. Next steps to include (if provided)
        if next_steps and any(s != "No comment" for s in next_steps):
            sections.append("\n## Specific Next Steps to Include")
            sections.append(
                "Include ONLY these exact next steps as stated. Do not expand, "
                "embellish, or add additional recommendations:"
            )
            for step in next_steps:
                if step != "No comment":
                    sections.append(f"- {step}")

        # 1d. Template instructions (if provided)
        if template_instructions:
            sections.append("\n## Structure Instructions")
            sections.append(template_instructions)
        if closing_text:
            sections.append("\n## Closing Text")
            sections.append(
                f"End the overall_summary with the following closing text:\n{closing_text}"
            )

        # 1e. Preferred output style from liked/copied examples
        # NOTE: We only inject structural metadata (length, paragraph count, etc.)
        # — never prior clinical content — to avoid priming the LLM with
        # diagnoses from unrelated patients.
        if liked_examples:
            sections.append("\n## Preferred Output Style")
            sections.append(
                "The physician has approved outputs with the following structural characteristics.\n"
                "Match this structure, length, and level of detail using ONLY the data\n"
                "from the current report."
            )
            for idx, example in enumerate(liked_examples, 1):
                sections.append(f"\n### Style Reference {idx}")
                sections.append(
                    f"- Summary length: ~{example.get('approx_char_length', 'unknown')} characters"
                )
                sections.append(
                    f"- Paragraphs: {example.get('paragraph_count', 'unknown')}"
                )
                sections.append(
                    f"- Approximate sentences: {example.get('approx_sentence_count', 'unknown')}"
                )
                num_findings = example.get("num_key_findings", 0)
                sections.append(f"- Number of key findings reported: {num_findings}")

        # 1f. Teaching points (personalized instructions)
        if teaching_points:
            sections.append("\n## Teaching Points")
            sections.append(
                "The physician has provided the following personalized instructions.\n"
                "These reflect their clinical style and preferences. Follow them closely\n"
                "so the output matches how this physician communicates:"
            )
            for tp in teaching_points:
                sections.append(f"- {tp['text']}")

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

        # 4. Sections — only include the Findings/Conclusions section if present,
        #    skip other raw sections (measurements + findings above are sufficient)
        if parsed_report.sections:
            for s in parsed_report.sections:
                name_lower = s.name.lower()
                if any(kw in name_lower for kw in ("finding", "conclusion", "impression")):
                    sections.append(f"\n## {s.name}")
                    sections.append(s.content)

        # 5. Glossary — only include terms referenced in measurements/findings
        #    for short comment; full glossary for long-form
        if short_comment:
            # Build set of abbreviations and finding keywords for filtering
            relevant_terms: set[str] = set()
            for m in (parsed_report.measurements or []):
                relevant_terms.add(m.abbreviation.upper())
                for word in m.name.split():
                    if len(word) > 3:
                        relevant_terms.add(word.upper())
            filtered_glossary = {
                term: defn for term, defn in glossary.items()
                if term.upper() in relevant_terms
            }
            if filtered_glossary:
                sections.append(
                    "\n## Glossary (use these definitions when explaining terms)"
                )
                for term, definition in filtered_glossary.items():
                    sections.append(f"- **{term}**: {definition}")
        else:
            sections.append(
                "\n## Glossary (use these definitions when explaining terms)"
            )
            for term, definition in glossary.items():
                sections.append(f"- **{term}**: {definition}")

        # 6. Refinement instruction (if provided)
        if refinement_instruction:
            sections.append("\n## Refinement Instruction")
            sections.append(refinement_instruction)

        # 7. Instructions
        sections.append(
            "\n## Instructions\n"
            "Using ONLY the data above, write a clinical interpretation as "
            "the physician, ready to send directly to the patient. Call the "
            "explain_report tool with your response. Include all measurements "
            "listed above. Do not add measurements, findings, or treatment "
            "recommendations not present in the data."
        )

        return "\n".join(sections)
