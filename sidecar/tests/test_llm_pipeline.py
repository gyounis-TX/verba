"""Tests for the LLM pipeline: prompt engine and response parser."""

import pytest

from api.analysis_models import (
    AbnormalityDirection,
    ParsedMeasurement,
    ParsedReport,
    SeverityStatus,
)
from api.explain_models import ExplanationResult
from llm.prompt_engine import LiteracyLevel, PromptEngine
from llm.response_parser import parse_and_validate_response


def _make_parsed_report() -> ParsedReport:
    """Create a minimal parsed report for testing."""
    return ParsedReport(
        test_type="echocardiogram",
        test_type_display="Echocardiogram",
        detection_confidence=0.9,
        measurements=[
            ParsedMeasurement(
                name="Left Ventricular Ejection Fraction",
                abbreviation="LVEF",
                value=57.5,
                unit="%",
                status=SeverityStatus.NORMAL,
                direction=AbnormalityDirection.NORMAL,
                reference_range=">= 52.0 %",
                raw_text="LVEF: 55-60%",
            ),
            ParsedMeasurement(
                name="Left Ventricular Internal Diameter diastole",
                abbreviation="LVIDd",
                value=4.8,
                unit="cm",
                status=SeverityStatus.NORMAL,
                direction=AbnormalityDirection.NORMAL,
                reference_range="3.8-5.8 cm",
                raw_text="LVIDd: 4.8 cm",
            ),
        ],
        findings=["Normal LV systolic function."],
    )


MOCK_PROMPT_CONTEXT = {
    "specialty": "cardiology",
    "test_type": "echocardiogram",
    "guidelines": "ASE 2015 Guidelines",
    "explanation_style": "Explain clearly.",
}

MOCK_REFERENCE_RANGES = {
    "LVEF": {"normal_min": 52.0, "normal_max": None, "unit": "%"},
    "LVIDd": {"normal_min": 3.8, "normal_max": 5.8, "unit": "cm"},
}

MOCK_GLOSSARY = {
    "Ejection Fraction": "How well the heart pumps blood.",
    "LVIDd": "The width of the left pumping chamber at rest.",
}


class TestPromptEngine:
    def test_system_prompt_contains_specialty(self):
        engine = PromptEngine()
        prompt = engine.build_system_prompt(
            LiteracyLevel.GRADE_6, MOCK_PROMPT_CONTEXT
        )
        assert "cardiology" in prompt

    def test_system_prompt_contains_literacy_instructions(self):
        engine = PromptEngine()
        prompt = engine.build_system_prompt(
            LiteracyLevel.GRADE_4, MOCK_PROMPT_CONTEXT
        )
        assert "4th-grade" in prompt

    def test_system_prompt_grade_12_literacy(self):
        engine = PromptEngine()
        prompt = engine.build_system_prompt(
            LiteracyLevel.GRADE_12, MOCK_PROMPT_CONTEXT
        )
        assert "12th-grade" in prompt
        assert "adult language" in prompt

    def test_system_prompt_contains_anti_hallucination_rules(self):
        engine = PromptEngine()
        prompt = engine.build_system_prompt(
            LiteracyLevel.GRADE_6, MOCK_PROMPT_CONTEXT
        )
        assert "ONLY use data" in prompt
        assert "NEVER invent" in prompt
        assert "explain_report" in prompt

    def test_user_prompt_contains_measurements(self):
        engine = PromptEngine()
        report = _make_parsed_report()
        prompt = engine.build_user_prompt(
            report, MOCK_REFERENCE_RANGES, MOCK_GLOSSARY, "scrubbed text"
        )
        assert "LVEF" in prompt
        assert "LVIDd" in prompt
        assert "57.5" in prompt

    def test_user_prompt_contains_glossary(self):
        engine = PromptEngine()
        report = _make_parsed_report()
        prompt = engine.build_user_prompt(
            report, MOCK_REFERENCE_RANGES, MOCK_GLOSSARY, "scrubbed text"
        )
        assert "Ejection Fraction" in prompt
        assert "How well the heart pumps blood" in prompt

    def test_user_prompt_omits_raw_scrubbed_text(self):
        """Raw scrubbed text is no longer included — structured data is used instead."""
        engine = PromptEngine()
        report = _make_parsed_report()
        prompt = engine.build_user_prompt(
            report, MOCK_REFERENCE_RANGES, MOCK_GLOSSARY, "my scrubbed text"
        )
        assert "my scrubbed text" not in prompt
        # But structured measurements should still be present
        assert "LVEF" in prompt

    def test_clinical_literacy_level(self):
        engine = PromptEngine()
        prompt = engine.build_system_prompt(
            LiteracyLevel.CLINICAL, MOCK_PROMPT_CONTEXT
        )
        assert "Physician-level" in prompt
        assert "medical terminology" in prompt

    def test_user_prompt_contains_clinical_context(self):
        engine = PromptEngine()
        report = _make_parsed_report()
        prompt = engine.build_user_prompt(
            report,
            MOCK_REFERENCE_RANGES,
            MOCK_GLOSSARY,
            "scrubbed text",
            clinical_context="Chest pain and dyspnea",
        )
        assert "Clinical Context" in prompt
        assert "Chest pain and dyspnea" in prompt
        assert "Prioritize findings" in prompt

    def test_user_prompt_without_clinical_context(self):
        engine = PromptEngine()
        report = _make_parsed_report()
        prompt = engine.build_user_prompt(
            report,
            MOCK_REFERENCE_RANGES,
            MOCK_GLOSSARY,
            "scrubbed text",
            clinical_context=None,
        )
        assert "Clinical Context" not in prompt

    def test_user_prompt_contains_template_instructions(self):
        engine = PromptEngine()
        report = _make_parsed_report()
        prompt = engine.build_user_prompt(
            report,
            MOCK_REFERENCE_RANGES,
            MOCK_GLOSSARY,
            "scrubbed text",
            template_instructions="Start with a brief overview.",
        )
        assert "Structure Instructions" in prompt
        assert "Start with a brief overview." in prompt

    def test_user_prompt_contains_closing_text(self):
        engine = PromptEngine()
        report = _make_parsed_report()
        prompt = engine.build_user_prompt(
            report,
            MOCK_REFERENCE_RANGES,
            MOCK_GLOSSARY,
            "scrubbed text",
            closing_text="Discuss with your doctor.",
        )
        assert "Closing Text" in prompt
        assert "Discuss with your doctor." in prompt

    def test_user_prompt_without_template_params(self):
        engine = PromptEngine()
        report = _make_parsed_report()
        prompt = engine.build_user_prompt(
            report,
            MOCK_REFERENCE_RANGES,
            MOCK_GLOSSARY,
            "scrubbed text",
        )
        assert "Structure Instructions" not in prompt
        assert "Closing Text" not in prompt

    def test_system_prompt_contains_tone(self):
        engine = PromptEngine()
        context = {**MOCK_PROMPT_CONTEXT, "tone": "Warm and reassuring"}
        prompt = engine.build_system_prompt(LiteracyLevel.GRADE_6, context)
        assert "Warm and reassuring" in prompt
        assert "## Tone" in prompt

    def test_system_prompt_omits_tone_when_empty(self):
        engine = PromptEngine()
        prompt = engine.build_system_prompt(
            LiteracyLevel.GRADE_6, MOCK_PROMPT_CONTEXT
        )
        # The template-provided "## Tone\n" section should be absent,
        # but the always-present "## Tone and Language Style" is expected.
        assert "## Tone\n" not in prompt

    def test_system_prompt_contains_hedging_instructions(self):
        engine = PromptEngine()
        prompt = engine.build_system_prompt(
            LiteracyLevel.GRADE_6, MOCK_PROMPT_CONTEXT
        )
        assert "## Tone Rules" in prompt
        assert "hedging" in prompt.lower()
        assert "appears to" in prompt
        assert "may" in prompt

    def test_user_prompt_contains_refinement_instruction(self):
        engine = PromptEngine()
        report = _make_parsed_report()
        prompt = engine.build_user_prompt(
            report,
            MOCK_REFERENCE_RANGES,
            MOCK_GLOSSARY,
            "scrubbed text",
            refinement_instruction="Make it shorter and simpler.",
        )
        assert "## Refinement Instruction" in prompt
        assert "Make it shorter and simpler." in prompt

    def test_user_prompt_without_refinement_instruction(self):
        engine = PromptEngine()
        report = _make_parsed_report()
        prompt = engine.build_user_prompt(
            report,
            MOCK_REFERENCE_RANGES,
            MOCK_GLOSSARY,
            "scrubbed text",
            refinement_instruction=None,
        )
        assert "Refinement Instruction" not in prompt

    def test_user_prompt_contains_liked_examples(self):
        engine = PromptEngine()
        report = _make_parsed_report()
        liked_examples = [
            {
                "paragraph_count": 2,
                "approx_sentence_count": 5,
                "approx_char_length": 320,
                "num_key_findings": 1,
                "finding_severities": ["normal"],
            },
        ]
        prompt = engine.build_user_prompt(
            report,
            MOCK_REFERENCE_RANGES,
            MOCK_GLOSSARY,
            "scrubbed text",
            liked_examples=liked_examples,
        )
        assert "## Preferred Output Style" in prompt
        assert "Style Reference 1" in prompt
        assert "320 characters" in prompt
        assert "Paragraphs: 2" in prompt
        # Must NOT contain any clinical content from prior analyses
        assert "Your heart looks great" not in prompt

    def test_user_prompt_without_liked_examples(self):
        engine = PromptEngine()
        report = _make_parsed_report()
        prompt = engine.build_user_prompt(
            report,
            MOCK_REFERENCE_RANGES,
            MOCK_GLOSSARY,
            "scrubbed text",
            liked_examples=None,
        )
        assert "Preferred Output Style" not in prompt

    def test_user_prompt_empty_liked_examples(self):
        engine = PromptEngine()
        report = _make_parsed_report()
        prompt = engine.build_user_prompt(
            report,
            MOCK_REFERENCE_RANGES,
            MOCK_GLOSSARY,
            "scrubbed text",
            liked_examples=[],
        )
        assert "Preferred Output Style" not in prompt

    def test_system_prompt_tone_preference_1(self):
        engine = PromptEngine()
        prompt = engine.build_system_prompt(
            LiteracyLevel.GRADE_6, MOCK_PROMPT_CONTEXT, tone_preference=1
        )
        assert "direct and clinical" in prompt

    def test_system_prompt_tone_preference_5(self):
        engine = PromptEngine()
        prompt = engine.build_system_prompt(
            LiteracyLevel.GRADE_6, MOCK_PROMPT_CONTEXT, tone_preference=5
        )
        assert "warm, empathetic" in prompt

    def test_system_prompt_detail_preference_1(self):
        engine = PromptEngine()
        prompt = engine.build_system_prompt(
            LiteracyLevel.GRADE_6, MOCK_PROMPT_CONTEXT, detail_preference=1
        )
        assert "extremely brief" in prompt.lower()

    def test_system_prompt_detail_preference_5(self):
        engine = PromptEngine()
        prompt = engine.build_system_prompt(
            LiteracyLevel.GRADE_6, MOCK_PROMPT_CONTEXT, detail_preference=5
        )
        assert "comprehensive" in prompt.lower()

    def test_system_prompt_default_preferences(self):
        engine = PromptEngine()
        prompt = engine.build_system_prompt(
            LiteracyLevel.GRADE_6, MOCK_PROMPT_CONTEXT
        )
        assert "## Tone Preference" in prompt
        assert "## Detail Level" in prompt
        # Default tone=3: "Balance clinical precision"
        assert "Balance clinical precision" in prompt
        # Default detail=3: "standard level of detail"
        assert "standard level of detail" in prompt

    def test_system_prompt_contains_physician_name(self):
        engine = PromptEngine()
        prompt = engine.build_system_prompt(
            LiteracyLevel.GRADE_6, MOCK_PROMPT_CONTEXT, physician_name="Dr. Smith"
        )
        assert "Physician Voice" in prompt
        assert "Dr. Smith" in prompt
        assert "your doctor" in prompt.lower()

    def test_system_prompt_no_physician_section_when_none(self):
        engine = PromptEngine()
        prompt = engine.build_system_prompt(
            LiteracyLevel.GRADE_6, MOCK_PROMPT_CONTEXT, physician_name=None
        )
        assert "Physician Voice" not in prompt

    def test_system_prompt_no_physician_section_when_empty(self):
        engine = PromptEngine()
        prompt = engine.build_system_prompt(
            LiteracyLevel.GRADE_6, MOCK_PROMPT_CONTEXT, physician_name=""
        )
        assert "Physician Voice" not in prompt

    def test_system_prompt_no_disclaimer_rule(self):
        engine = PromptEngine()
        prompt = engine.build_system_prompt(
            LiteracyLevel.GRADE_6, MOCK_PROMPT_CONTEXT
        )
        assert "disclaimer MUST state" not in prompt

    def test_response_without_questions_and_disclaimer(self):
        """Backward compat: response parser accepts output without questions/disclaimer."""
        report = _make_parsed_report()
        tool_result = {
            "overall_summary": "Your heart appears to be functioning normally.",
            "measurements": [
                {
                    "abbreviation": "LVEF",
                    "value": 57.5,
                    "unit": "%",
                    "status": "normal",
                    "plain_language": "Your heart pumps normally.",
                },
                {
                    "abbreviation": "LVIDd",
                    "value": 4.8,
                    "unit": "cm",
                    "status": "normal",
                    "plain_language": "Heart chamber size is normal.",
                },
            ],
            "key_findings": [
                {
                    "finding": "Normal heart function",
                    "severity": "normal",
                    "explanation": "Everything looks good.",
                }
            ],
        }

        result, issues = parse_and_validate_response(tool_result, report)
        assert isinstance(result, ExplanationResult)
        assert result.questions_for_doctor == []
        assert result.disclaimer == ""


class TestResponseParser:
    def test_valid_response_parses(self):
        report = _make_parsed_report()
        tool_result = {
            "overall_summary": "Your heart function is normal.",
            "measurements": [
                {
                    "abbreviation": "LVEF",
                    "value": 57.5,
                    "unit": "%",
                    "status": "normal",
                    "plain_language": "Your heart pumps normally.",
                },
                {
                    "abbreviation": "LVIDd",
                    "value": 4.8,
                    "unit": "cm",
                    "status": "normal",
                    "plain_language": "Heart chamber size is normal.",
                },
            ],
            "key_findings": [
                {
                    "finding": "Normal heart function",
                    "severity": "normal",
                    "explanation": "Everything looks good.",
                }
            ],
            "questions_for_doctor": ["Any lifestyle changes?"],
            "disclaimer": "This is AI-generated, not medical advice.",
        }

        result, issues = parse_and_validate_response(tool_result, report)
        assert isinstance(result, ExplanationResult)
        assert len(result.measurements) == 2
        assert result.overall_summary == "Your heart function is normal."
        # No warnings for a valid response
        warnings = [i for i in issues if i.severity == "warning"]
        # May have 0 warnings if everything matches
        assert len(warnings) == 0

    def test_hallucinated_measurement_removed(self):
        report = _make_parsed_report()
        tool_result = {
            "overall_summary": "Summary.",
            "measurements": [
                {
                    "abbreviation": "LVEF",
                    "value": 57.5,
                    "unit": "%",
                    "status": "normal",
                    "plain_language": "Normal.",
                },
                {
                    "abbreviation": "FAKE_MEASURE",
                    "value": 99.0,
                    "unit": "?",
                    "status": "normal",
                    "plain_language": "This is fake.",
                },
            ],
            "key_findings": [],
            "questions_for_doctor": [],
            "disclaimer": "Disclaimer.",
        }

        result, issues = parse_and_validate_response(tool_result, report)
        abbrs = [m.abbreviation for m in result.measurements]
        assert "FAKE_MEASURE" not in abbrs
        assert "LVEF" in abbrs
        warning_messages = [i.message for i in issues]
        assert any("hallucinated" in m.lower() for m in warning_messages)

    def test_value_mismatch_corrected(self):
        report = _make_parsed_report()
        tool_result = {
            "overall_summary": "Summary.",
            "measurements": [
                {
                    "abbreviation": "LVEF",
                    "value": 60.0,  # Wrong: should be 57.5
                    "unit": "%",
                    "status": "normal",
                    "plain_language": "Normal.",
                },
            ],
            "key_findings": [],
            "questions_for_doctor": [],
            "disclaimer": "Disclaimer.",
        }

        result, issues = parse_and_validate_response(tool_result, report)
        lvef = next(m for m in result.measurements if m.abbreviation == "LVEF")
        assert lvef.value == 57.5  # Corrected to parsed value
        warning_messages = [i.message for i in issues]
        assert any("Correcting to parsed value" in m for m in warning_messages)

    def test_status_mismatch_corrected(self):
        report = _make_parsed_report()
        tool_result = {
            "overall_summary": "Summary.",
            "measurements": [
                {
                    "abbreviation": "LVEF",
                    "value": 57.5,
                    "unit": "%",
                    "status": "mildly_abnormal",  # Wrong: should be normal
                    "plain_language": "Slightly low.",
                },
            ],
            "key_findings": [],
            "questions_for_doctor": [],
            "disclaimer": "Disclaimer.",
        }

        result, issues = parse_and_validate_response(tool_result, report)
        lvef = next(m for m in result.measurements if m.abbreviation == "LVEF")
        assert lvef.status == SeverityStatus.NORMAL
        warning_messages = [i.message for i in issues]
        assert any("Correcting to parsed status" in m for m in warning_messages)

    def test_none_tool_result_raises(self):
        report = _make_parsed_report()
        with pytest.raises(ValueError, match="did not produce"):
            parse_and_validate_response(None, report)

    def test_missing_measurements_not_warned(self):
        """Missing measurements are acceptable — the LLM synthesizes, not catalogs."""
        report = _make_parsed_report()
        tool_result = {
            "overall_summary": "Summary.",
            "measurements": [
                {
                    "abbreviation": "LVEF",
                    "value": 57.5,
                    "unit": "%",
                    "status": "normal",
                    "plain_language": "Normal.",
                },
                # LVIDd is missing — that's fine
            ],
            "key_findings": [],
            "questions_for_doctor": [],
            "disclaimer": "Disclaimer.",
        }

        result, issues = parse_and_validate_response(tool_result, report)
        warning_messages = [i.message for i in issues]
        assert not any("not explained" in m for m in warning_messages)
