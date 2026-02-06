"""
Prompt construction for medical report explanation.

Builds a system prompt (role, rules, anti-hallucination constraints)
and a user prompt (parsed report data, reference ranges, glossary).

The LLM acts AS the physician in the specified specialty, producing
patient-facing communications that require no editing before sending.
"""

from __future__ import annotations

import re
from enum import Enum

from api.analysis_models import ParsedReport


def _extract_indication_from_report(report_text: str) -> str | None:
    """Extract indication/reason for study from report header.

    Many medical reports include an 'Indication:' or 'Reason for study:'
    line near the top. This function extracts that text so it can be used
    as clinical context when none is explicitly provided.
    """
    patterns = [
        r"Indication[s]?:\s*(.+?)(?:\n|$)",
        r"Reason for (?:study|exam|test|examination):\s*(.+?)(?:\n|$)",
        r"Clinical indication[s]?:\s*(.+?)(?:\n|$)",
        r"Reason for referral:\s*(.+?)(?:\n|$)",
        r"Clinical history:\s*(.+?)(?:\n|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, report_text, re.IGNORECASE)
        if match:
            indication = match.group(1).strip()
            # Skip if it's just "None" or empty
            if indication.lower() not in ("none", "n/a", "not provided", ""):
                return indication
    return None


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
   d. Only comment on valvular stenosis or regurgitation if the report
      specifically names and grades it (e.g. "trace mitral regurgitation",
      "mild aortic regurgitation"). A blanket exclusion such as "no
      significant valvular regurgitation" or "no significant stenosis" means
      nothing was found — do NOT interpret it as trace or mild disease.

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
9. When prior values are provided, briefly note the trend. Don't
   over-interpret small fluctuations within normal range.
10. DATES — When comparing dates (e.g. current exam vs. prior study),
   always consider the FULL date including the YEAR. "1/31/2025" to
   "01/12/2026" is approximately one year apart, NOT two weeks.
   Calculate the actual elapsed time using years, months, and days.
   State the time interval accurately (e.g. "approximately one year
   ago", "about 11 months prior").

"""

_CLINICAL_DOMAIN_KNOWLEDGE_CARDIAC = """\
## Clinical Domain Knowledge — Cardiac

Apply these cardiac-specific interpretation rules:

- HYPERTROPHIC CARDIOMYOPATHY (HCM): A supra-normal or hyperdynamic ejection
  fraction (e.g. LVEF > 65-70%) is NOT reassuring in HCM. It may reflect
  hypercontractility from a thickened, stiff ventricle. Do NOT describe it as
  "strong" or "better than normal." Instead, note the EF value neutrally and
  explain that in the context of HCM, an elevated EF can be part of the
  disease pattern rather than a sign of good health.

- DIASTOLIC FUNCTION GRADING: When E/A ratio, E/e', and TR velocity are
  provided, synthesize them into a diastolic function assessment:
  - Grade I (impaired relaxation): E/A < 0.8, low e', normal LA
  - Grade II (pseudonormal): E/A 0.8-2.0, elevated E/e' > 14, enlarged LA
  - Grade III (restrictive): E/A > 2.0, E/e' > 14, dilated LA
  Explain what the grade means clinically, not just the individual numbers.

- LV WALL THICKNESS: IVSd or LVPWd > 1.1 cm suggests left ventricular
  hypertrophy (LVH). When both are elevated, note concentric hypertrophy.
  If only one wall is thick, note asymmetric hypertrophy.

- VALVULAR SEVERITY: When aortic valve area (AVA) is present, classify
  stenosis: mild (> 1.5 cm2), moderate (1.0-1.5 cm2), severe (< 1.0 cm2).
  Pair with peak velocity and mean gradient for concordance assessment.

- PULMONARY HYPERTENSION: RVSP > 35 mmHg suggests elevated pulmonary
  pressures. Pair with RV size and TR velocity for a complete picture.

"""

_CLINICAL_DOMAIN_KNOWLEDGE_LABS = """\
## Clinical Domain Knowledge — Laboratory Medicine

Apply these lab pattern interpretation rules:

- IRON DEFICIENCY PATTERN: When low Iron (FE) + low Ferritin (FERR) + high TIBC
  appear together, this constellation suggests iron deficiency. Do not interpret
  each value in isolation — synthesize them into a single clinical statement
  about iron stores.

- THYROID PATTERNS:
  - High TSH + low FT4 = primary hypothyroidism pattern
  - Low TSH + high FT4 = hyperthyroidism pattern
  - High TSH + normal FT4 = subclinical hypothyroidism
  - Low TSH + normal FT4 = subclinical hyperthyroidism
  Describe the pattern holistically, not as isolated lab values.

- CKD STAGING (based on eGFR):
  - Stage 1: eGFR >= 90 (normal function, but other kidney markers abnormal)
  - Stage 2: eGFR 60-89 (mildly decreased)
  - Stage 3a: eGFR 45-59 (mild-to-moderate)
  - Stage 3b: eGFR 30-44 (moderate-to-severe)
  - Stage 4: eGFR 15-29 (severe)
  - Stage 5: eGFR < 15 (kidney failure)
  When eGFR is abnormal, pair it with Creatinine and BUN for a kidney function
  narrative rather than listing each separately.

- DIABETES / GLUCOSE METABOLISM:
  - A1C 5.7-6.4% = prediabetic range
  - A1C >= 6.5% = diabetic range
  - A1C > 8% = poorly controlled diabetes
  When both Glucose and A1C are present, synthesize them together. A1C reflects
  3-month average; fasting glucose reflects acute status.

- LIVER PANEL: When multiple liver enzymes (AST, ALT, ALP, Bilirubin) are
  abnormal, describe the hepatic pattern rather than listing each value.
  AST/ALT ratio > 2 may suggest alcoholic liver disease.

- ANEMIA CLASSIFICATION: Use MCV to classify anemia type:
  - Low MCV (< 80) = microcytic (iron deficiency, thalassemia)
  - Normal MCV (80-100) = normocytic (chronic disease, acute blood loss)
  - High MCV (> 100) = macrocytic (B12/folate deficiency)
  Group RBC, HGB, HCT, and MCV together when interpreting.

- LIPID RISK: Synthesize total cholesterol, LDL, HDL, and triglycerides
  together. High LDL + low HDL is a more concerning pattern than either alone.
  Triglycerides > 500 is a separate risk for pancreatitis.

"""

_CLINICAL_DOMAIN_KNOWLEDGE_IMAGING = """\
## Clinical Domain Knowledge — Imaging

Apply these imaging-specific interpretation rules:

- ANATOMICAL ORGANIZATION: Group findings by anatomical region rather than
  listing them in report order. For chest CT: lungs first, then mediastinum,
  then bones/soft tissue. For abdominal imaging: solid organs, then hollow
  viscera, then vasculature, then musculoskeletal.

- INCIDENTAL FINDINGS: Common incidentalomas (simple renal cysts, small
  hepatic cysts, small pulmonary nodules < 6mm in low-risk patients) should
  be mentioned but contextualized as typically benign and common.

- LUNG NODULE RISK STRATIFICATION: Fleischner criteria context:
  - < 6mm in low-risk patient: typically no follow-up needed
  - 6-8mm: may warrant short-interval follow-up
  - > 8mm or growing: more concerning, warrants attention
  Do NOT specify exact follow-up schedules — that is the physician's decision.

- LESION SIZE CONTEXT: Always provide size context when discussing lesions.
  A 3mm lesion is very different from a 3cm lesion. Use analogies appropriate
  to the literacy level (e.g., "about the size of a grain of rice" vs.
  "approximately 3 millimeters").

"""

_CLINICAL_DOMAIN_KNOWLEDGE_EKG = """\
## Clinical Domain Knowledge — EKG/ECG

Apply this interpretation structure for EKG/ECG reports:

1. RHYTHM — Sinus rhythm vs. arrhythmia. If atrial fibrillation, note it
   prominently. If sinus rhythm, confirm it is normal.
2. RATE — Bradycardia (< 60), normal (60-100), tachycardia (> 100).
   Context: trained athletes may normally be bradycardic.
3. INTERVALS — PR interval (normal 0.12-0.20s), QRS duration (normal < 0.12s),
   QTc interval (normal < 440ms male, < 460ms female). Prolonged QTc is
   clinically significant.
4. AXIS — Normal, left axis deviation, right axis deviation. Brief context
   on what deviation may suggest.
5. ST/T WAVE CHANGES — ST elevation, ST depression, T-wave inversions.
   These are often the most clinically important findings.

"""

_CLINICAL_DOMAIN_KNOWLEDGE_PFT = """\
## Clinical Domain Knowledge — Pulmonary Function Tests

Apply this interpretation structure:

- OBSTRUCTIVE PATTERN: FEV1/FVC ratio < 0.70 (or below lower limit of normal).
  Classify severity by FEV1 % predicted: mild (>= 70%), moderate (50-69%),
  severe (35-49%), very severe (< 35%). Common in COPD, asthma.

- RESTRICTIVE PATTERN: FVC reduced with normal or elevated FEV1/FVC ratio.
  Confirm with total lung capacity (TLC) if available. Common in
  interstitial lung disease, chest wall disorders.

- MIXED PATTERN: Both obstructive and restrictive features present.
  FEV1/FVC ratio reduced AND FVC reduced disproportionately.

- DLCO: Reduced DLCO suggests impaired gas exchange (emphysema, interstitial
  disease, pulmonary vascular disease). Normal DLCO with obstruction suggests
  asthma over emphysema.

- BRONCHODILATOR RESPONSE: Significant response (>= 12% AND >= 200mL
  improvement in FEV1) suggests reversible obstruction (asthma pattern).

"""

# Default domain knowledge for backwards compatibility
_CLINICAL_DOMAIN_KNOWLEDGE = _CLINICAL_DOMAIN_KNOWLEDGE_CARDIAC


def _select_domain_knowledge(prompt_context: dict) -> str:
    """Select appropriate domain knowledge block based on test type/category."""
    test_type = prompt_context.get("test_type", "")
    category = prompt_context.get("category", "")
    interpretation_rules = prompt_context.get("interpretation_rules", "")

    # Select based on test type first, then category
    if test_type in ("lab_results", "blood_lab_results"):
        domain = _CLINICAL_DOMAIN_KNOWLEDGE_LABS
    elif test_type in ("ekg", "ecg"):
        domain = _CLINICAL_DOMAIN_KNOWLEDGE_EKG
    elif test_type == "pft":
        domain = _CLINICAL_DOMAIN_KNOWLEDGE_PFT
    elif category == "lab":
        domain = _CLINICAL_DOMAIN_KNOWLEDGE_LABS
    elif category in ("imaging_ct", "imaging_mri", "imaging_xray", "imaging_ultrasound"):
        domain = _CLINICAL_DOMAIN_KNOWLEDGE_IMAGING
    elif category in ("cardiac", "vascular"):
        domain = _CLINICAL_DOMAIN_KNOWLEDGE_CARDIAC
    elif category == "neurophysiology":
        domain = _CLINICAL_DOMAIN_KNOWLEDGE_EKG  # Similar structure for EEG/EMG
    elif category == "pulmonary":
        domain = _CLINICAL_DOMAIN_KNOWLEDGE_PFT
    else:
        domain = _CLINICAL_DOMAIN_KNOWLEDGE_CARDIAC  # Default

    # Append any handler-provided interpretation rules
    if interpretation_rules:
        domain = domain + f"\n{interpretation_rules}\n"

    return domain

_CLINICAL_CONTEXT_RULE = """\
## Clinical Context Integration

When clinical context is provided — either explicitly by the user OR
extracted from report sections such as INDICATION, REASON FOR TEST,
CLINICAL HISTORY, or CONCLUSION:
- You MUST connect at least one finding to the clinical context.
- Tie findings directly to the clinical context by explaining how the
  results relate to the patient's symptoms or reason for testing.
- Use phrasing like "Given that this test was ordered for [reason]..."
  or "These findings help explain your [symptom]..."
- Synthesize indication and conclusion data with the structured
  measurements to provide a clinically coherent interpretation.
- This applies to BOTH long-form and short comment outputs.
- If no clinical context was provided or extracted, skip this requirement.

"""

_INTERPRETATION_QUALITY_RULE = """\
## Interpretation Quality — Never Restate Without Meaning

CRITICAL: Never simply restate measurements without interpretation.
The patient can already see the numbers on their report. Your job is to
explain what those numbers MEAN for THEM.

BAD: "The left atrium measures 4.3 cm."
GOOD: "The left atrium is mildly enlarged at 4.3 cm (normal <4.0 cm), which
can occur with high blood pressure or heart valve issues."

BAD: "Your hemoglobin is 10.2 g/dL."
GOOD: "Your hemoglobin is mildly low at 10.2 (normal 12-16 for women), which
explains why you may feel more tired than usual."

Every measurement mentioned must include:
- What the value means (normal, abnormal, borderline)
- Clinical significance in plain language
- Relevance to the patient's context if provided

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
        sms_summary: bool = False,
        sms_summary_char_limit: int = 300,
    ) -> str:
        """Build the system prompt with role, rules, and constraints."""
        specialty = prompt_context.get("specialty", "general medicine")

        if sms_summary:
            target = int(sms_summary_char_limit * 0.9)
            hard_limit = sms_summary_char_limit
            return (
                f"You are a clinical communicator writing an ultra-condensed "
                f"SMS-length summary of lab/test results for a patient. "
                f"Write as the physician or care team for a {specialty} practice.\n\n"
                f"## Rules\n"
                f"- 2-3 sentences MAX. Plain text only — no markdown, no bullets, "
                f"no headers, no emojis.\n"
                f"- Target {target} characters; NEVER exceed {hard_limit} characters.\n"
                f"- Lead with the most important finding. Mention key abnormalities.\n"
                f"- Use simple, patient-friendly language.\n"
                f"- NEVER suggest treatments, future testing, or hypothetical actions.\n"
                f"- ONLY use data from the report. Never invent findings.\n"
                f"- Use the provided status (normal, mildly_abnormal, etc.) — "
                f"do NOT reclassify.\n"
                f"- Do NOT mention the patient by name.\n"
                f"- Call the explain_report tool with your response.\n"
            )

        demographics_section = ""
        if patient_age is not None or patient_gender is not None:
            parts: list[str] = []
            guidance_parts: list[str] = []

            if patient_age is not None:
                parts.append(f"Age: {patient_age}")
                if patient_age >= 80:
                    guidance_parts.append(
                        "Very elderly patient (80+): Expect some age-related changes. "
                        "Mild LVH, diastolic dysfunction grade I, and mild valve "
                        "calcification are common. Focus on clinically actionable findings. "
                        "eGFR decline is expected; creatinine-based estimates may "
                        "underestimate true function due to reduced muscle mass."
                    )
                elif patient_age >= 65:
                    guidance_parts.append(
                        "Geriatric patient (65+): Mildly abnormal values may be more "
                        "clinically significant. Pay particular attention to renal function, "
                        "electrolytes, cardiac findings, and fall risk indicators. "
                        "Diastolic dysfunction grade I is common at this age."
                    )
                elif patient_age >= 40:
                    guidance_parts.append(
                        "Middle-aged adult: Cardiovascular risk factors become more relevant. "
                        "Lipid panel, A1C, and blood pressure context are important. "
                        "Mention if findings warrant lifestyle discussion."
                    )
                elif patient_age < 18:
                    guidance_parts.append(
                        "Pediatric patient: Adult reference ranges may not apply. "
                        "Note that some values differ significantly in children. "
                        "Heart rate and blood pressure norms are age-dependent."
                    )
                elif patient_age < 40:
                    guidance_parts.append(
                        "Young adult: Abnormal findings are less expected and may warrant "
                        "closer attention. Consider family history implications."
                    )

            if patient_gender is not None:
                parts.append(f"Sex: {patient_gender}")
                gender_lower = patient_gender.lower()
                if gender_lower in ("female", "f"):
                    guidance_parts.append(
                        "Female patient: Use female-specific reference ranges — "
                        "hemoglobin (12.0-16.0), hematocrit (35.5-44.9%), creatinine "
                        "(0.6-1.1), ferritin (12-150), LVEF (≥54%), LVIDd (3.8-5.2 cm). "
                        "Ferritin < 30 may indicate iron deficiency even if within range. "
                        "HDL target ≥ 50. QTc prolongation threshold: > 460 ms."
                    )
                elif gender_lower in ("male", "m"):
                    guidance_parts.append(
                        "Male patient: Use male-specific reference ranges — "
                        "hemoglobin (13.5-17.5), hematocrit (38.3-48.6%), creatinine "
                        "(0.7-1.3), ferritin (12-300), LVEF (≥52%), LVIDd (4.2-5.8 cm). "
                        "HDL target ≥ 40. QTc prolongation threshold: > 450 ms."
                    )

            # Combined age+sex guidance
            if patient_age is not None and patient_gender is not None:
                gender_lower = patient_gender.lower() if patient_gender else ""
                if gender_lower in ("female", "f") and patient_age >= 50:
                    guidance_parts.append(
                        "Post-menopausal female: Cardiovascular risk approaches male levels. "
                        "Bone density may be relevant if DEXA. Thyroid screening is common."
                    )
                elif gender_lower in ("male", "m") and patient_age >= 50:
                    guidance_parts.append(
                        "Male 50+: Prostate markers (if present) need age context. "
                        "Cardiovascular risk assessment is particularly important."
                    )

            guidance_text = "\n".join(f"- {g}" for g in guidance_parts) if guidance_parts else (
                "Use age-appropriate reference ranges and clinical context "
                "when interpreting results."
            )
            demographics_section = (
                f"## Patient Demographics\n"
                f"{', '.join(parts)}.\n\n"
                f"**Interpretation guidance based on demographics:**\n"
                f"{guidance_text}\n\n"
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
        test_type_hint = prompt_context.get("test_type_hint", "")

        tone_section = f"## Template Tone\n{tone}\n\n" if tone else ""
        test_type_hint_section = (
            f"## Report Type\n"
            f"The user describes this report as: \"{test_type_hint}\". "
            f"Use this as context when interpreting the report. "
            f"Extract and explain relevant measurements, findings, and "
            f"conclusions based on this report type.\n\n"
        ) if test_type_hint else ""

        tone_pref = _TONE_DESCRIPTIONS.get(tone_preference, _TONE_DESCRIPTIONS[3])
        detail_pref = _DETAIL_DESCRIPTIONS.get(detail_preference, _DETAIL_DESCRIPTIONS[3])

        style_section = (
            f"## Explanation Style\n{explanation_style}\n\n" if explanation_style else ""
        )

        return (
            f"{_PHYSICIAN_IDENTITY.format(specialty=specialty)}"
            f"{demographics_section}"
            f"{test_type_hint_section}"
            f"{_CLINICAL_VOICE_RULE.format(specialty=specialty)}"
            f"{_NO_RECOMMENDATIONS_RULE}"
            f"{_CLINICAL_CONTEXT_RULE}"
            f"{_INTERPRETATION_QUALITY_RULE}"
            f"{_select_domain_knowledge(prompt_context)}"
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
        prior_results: list[dict] | None = None,
        recent_edits: list[dict] | None = None,
        patient_age: int | None = None,
        patient_gender: str | None = None,
    ) -> str:
        """Build the user prompt with report data, ranges, and glossary.

        When *short_comment* is True the raw report text is omitted (the
        structured parsed data is sufficient) and the glossary is trimmed to
        keep total token count well under typical rate limits.

        Args:
            prior_results: Optional list of prior test results for trend comparison.
                Each dict has 'date' (ISO date str) and 'measurements' (list of
                {abbreviation, value, unit, status}).
            recent_edits: Optional list of structural metadata from recent doctor edits.
                Each dict has 'length_change_pct', 'paragraph_change', 'shorter', 'longer'.
        """
        sections: list[str] = []

        # 1. Report text (scrubbed) — normally skipped because the structured
        #    parsed data is sufficient. However, for unknown test types (no
        #    handler), the parsed report is empty, so include the raw text so
        #    the LLM can interpret the report directly.
        has_structured_data = bool(
            parsed_report.measurements or parsed_report.sections or parsed_report.findings
        )
        if not has_structured_data and scrubbed_text:
            sections.append("## Full Report Text (PHI Scrubbed)")
            sections.append(scrubbed_text)

        # 1b. Clinical context (if provided, or extracted from report indication)
        effective_context = clinical_context
        if not effective_context and scrubbed_text:
            # Try to extract indication from the report itself
            indication = _extract_indication_from_report(scrubbed_text)
            if indication:
                effective_context = f"Indication for test: {indication}"

        if effective_context:
            sections.append("\n## Clinical Context")
            sections.append(f"{effective_context}")
            sections.append(
                "\n**Instructions for using clinical context:**\n"
                "- This may be a full office note containing HPI, PMH, and medications — extract all relevant information\n"
                "- Identify the chief complaint or reason for this test\n"
                "- Prioritize findings relevant to the clinical question\n"
                "- Specifically address whether results support, argue against, or are inconclusive for the suspected condition\n"
                "- Note findings particularly relevant to the patient's history or medications\n"
                "- If medications affect interpretation (e.g., beta blockers → controlled heart rate, diuretics → electrolytes), mention this"
            )

        # 1c. Patient demographics (for interpretation context)
        if patient_age is not None or patient_gender is not None:
            demo_parts: list[str] = []
            if patient_age is not None:
                demo_parts.append(f"Age: {patient_age}")
            if patient_gender is not None:
                demo_parts.append(f"Sex: {patient_gender}")
            sections.append("\n## Patient Demographics")
            sections.append(", ".join(demo_parts))
            sections.append(
                "Use these demographics to apply appropriate reference ranges and "
                "tailor the interpretation to this patient's age and sex."
            )

        # 1d. Next steps to include (if provided)
        if next_steps and any(s != "No comment" for s in next_steps):
            sections.append("\n## Specific Next Steps to Include")
            sections.append(
                "Include ONLY these exact next steps as stated. Do not expand, "
                "embellish, or add additional recommendations:"
            )
            for step in next_steps:
                if step != "No comment":
                    sections.append(f"- {step}")

        # 1e. Template instructions (if provided)
        if template_instructions:
            sections.append("\n## Structure Instructions")
            sections.append(template_instructions)
        if closing_text:
            sections.append("\n## Closing Text")
            sections.append(
                f"End the overall_summary with the following closing text:\n{closing_text}"
            )

        # 1f. Preferred output style from liked/copied examples
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

        # 1g. Teaching points (personalized instructions)
        if teaching_points:
            sections.append("\n## Teaching Points")
            sections.append(
                "The physician has provided the following personalized instructions.\n"
                "These reflect their clinical style and preferences. Follow them closely\n"
                "so the output matches how this physician communicates:"
            )
            for tp in teaching_points:
                source = tp.get("source", "own")
                if source == "own":
                    sections.append(f"- {tp['text']}")
                else:
                    sections.append(f"- [From {source}] {tp['text']}")

        # 1h. Doctor editing patterns (learned from recent edits)
        if recent_edits and not short_comment:
            # Analyze patterns in the edits
            shorter_count = sum(1 for e in recent_edits if e.get("shorter"))
            longer_count = sum(1 for e in recent_edits if e.get("longer"))
            avg_length_change = sum(e.get("length_change_pct", 0) for e in recent_edits) / len(recent_edits)
            avg_para_change = sum(e.get("paragraph_change", 0) for e in recent_edits) / len(recent_edits)

            guidance: list[str] = []
            if shorter_count > longer_count and avg_length_change < -10:
                guidance.append(
                    f"The physician tends to shorten output by ~{abs(int(avg_length_change))}%. "
                    f"Be more concise than the default output."
                )
            elif longer_count > shorter_count and avg_length_change > 10:
                guidance.append(
                    f"The physician tends to expand output by ~{int(avg_length_change)}%. "
                    f"Provide more detail than the default output."
                )

            if avg_para_change < -0.5:
                guidance.append(
                    "The physician prefers fewer paragraphs. Combine related points."
                )
            elif avg_para_change > 0.5:
                guidance.append(
                    "The physician prefers more paragraphs for separation. "
                    "Break up content into shorter paragraphs."
                )

            if guidance:
                sections.append("\n## Doctor Editing Patterns")
                sections.append(
                    "Based on the physician's recent edits, adjust the output style:"
                )
                for g in guidance:
                    sections.append(f"- {g}")

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

                prior_info = ""
                if m.prior_values:
                    prior_parts = [
                        f"{pv.time_label}: {pv.value} {m.unit}"
                        for pv in m.prior_values
                    ]
                    prior_info = " | " + " | ".join(prior_parts)

                sections.append(
                    f"- {m.name} ({m.abbreviation}): {m.value} {m.unit} "
                    f"[status: {m.status.value}]{prior_info}{ref_info}"
                )
        else:
            sections.append(
                "No measurements were pre-extracted by the parser. "
                "You MUST identify and interpret all clinically relevant "
                "measurements, values, and findings directly from the report text above. "
                "Extract key values (e.g., percentages, dimensions, velocities, pressures, "
                "lab values) and explain what they mean for the patient."
            )

        # 2b. Prior results for trend comparison (if available)
        if prior_results and not short_comment:
            sections.append("\n## Prior Results (for trend comparison)")
            sections.append(
                "When a current measurement has a corresponding prior value, "
                "briefly note the trend (stable, improved, worsened). "
                "Do not over-interpret small fluctuations within normal range."
            )
            for prior in prior_results:
                date = prior.get("date", "Unknown date")
                measurements = prior.get("measurements", [])
                if measurements:
                    sections.append(f"\n### {date}")
                    for m in measurements[:10]:  # Limit to avoid token bloat
                        abbrev = m.get("abbreviation", "")
                        value = m.get("value", "")
                        unit = m.get("unit", "")
                        status = m.get("status", "")
                        sections.append(f"- {abbrev}: {value} {unit} [{status}]")

        # 3. Findings
        if parsed_report.findings:
            sections.append("\n## Report Findings/Conclusions")
            for f in parsed_report.findings:
                sections.append(f"- {f}")

        # 4. Sections — include clinical context sections (indication, reason,
        #    findings, conclusions) to give the LLM richer context for interpretation
        if parsed_report.sections:
            for s in parsed_report.sections:
                name_lower = s.name.lower()
                if any(kw in name_lower for kw in (
                    "finding", "conclusion", "impression",
                    "indication", "reason", "clinical history",
                    "history", "referral",
                )):
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
