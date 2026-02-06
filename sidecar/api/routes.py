import os
import tempfile

from fastapi import APIRouter, Body, File, HTTPException, Query, Request, Response, UploadFile

from api.analysis_models import DetectTypeRequest, DetectTypeResponse, ParsedReport, ParseRequest
from api.explain_models import (
    AppSettings,
    ExplainRequest,
    ExplainResponse,
    SettingsUpdate,
)
from api.template_models import (
    TemplateCreateRequest,
    TemplateListResponse,
    TemplateResponse,
    TemplateUpdateRequest,
)
from api.history_models import (
    ConsentStatusResponse,
    HistoryCreateRequest,
    HistoryDeleteResponse,
    HistoryDetailResponse,
    HistoryLikeRequest,
    HistoryLikeResponse,
    HistoryListItem,
    HistoryListResponse,
)
from api.letter_models import (
    LetterDeleteResponse,
    LetterGenerateRequest,
    LetterLikeRequest,
    LetterListResponse,
    LetterResponse,
    LetterUpdateRequest,
)
from api.models import DetectionResult, ExtractionResult
from api import settings_store
from storage.database import get_db
from extraction import ExtractionPipeline, extract_physician_name
from extraction.demographics import extract_demographics
from extraction.detector import PDFDetector
from llm.client import LLMClient, LLMProvider
from llm.prompt_engine import LiteracyLevel, PromptEngine
from llm.response_parser import parse_and_validate_response
from llm.retry import LLMRetryError, with_retry
from llm.schemas import EXPLANATION_TOOL_NAME, EXPLANATION_TOOL_SCHEMA
from phi.scrubber import scrub_phi
from test_types import registry

router = APIRouter()

pipeline = ExtractionPipeline()


@router.get("/health")
async def health_check():
    try:
        get_db()
        return {"status": "ok"}
    except Exception:
        return {"status": "starting"}


@router.post("/extract/pdf", response_model=ExtractionResult)
async def extract_pdf(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    if file.content_type and file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid content type: {file.content_type}. Expected application/pdf.",
        )

    tmp_path = None
    try:
        content = await file.read()
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        if not content[:4] == b"%PDF":
            raise HTTPException(
                status_code=400,
                detail="File does not appear to be a valid PDF.",
            )

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        result = pipeline.extract_from_pdf(tmp_path)
        result.filename = file.filename
        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Failed to extract text from PDF: {str(e)}",
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.post("/extract/file", response_model=ExtractionResult)
async def extract_file(file: UploadFile = File(...)):
    """Accept PDF, image (jpg/jpeg/png), or text (.txt) files."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    ext = os.path.splitext(file.filename.lower())[1]
    supported = {".pdf", ".jpg", ".jpeg", ".png", ".txt"}
    if ext not in supported:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {ext}. Accepted: {', '.join(sorted(supported))}",
        )

    tmp_path = None
    try:
        content = await file.read()
        if len(content) == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        if ext == ".pdf":
            if not content[:4] == b"%PDF":
                raise HTTPException(
                    status_code=400,
                    detail="File does not appear to be a valid PDF.",
                )
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            result = pipeline.extract_from_pdf(tmp_path)
            result.filename = file.filename
            return result

        elif ext in (".jpg", ".jpeg", ".png"):
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            result = pipeline.extract_from_image(tmp_path)
            result.filename = file.filename
            return result

        else:  # .txt
            text = content.decode("utf-8", errors="replace")
            result = pipeline.extract_from_text(text)
            result.filename = file.filename
            return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Failed to extract text from file: {str(e)}",
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.post("/extract/text", response_model=ExtractionResult)
async def extract_text(body: dict = Body(...)):
    text = body.get("text", "")
    if not text or not text.strip():
        raise HTTPException(
            status_code=400,
            detail="Text content is required and cannot be empty.",
        )
    return pipeline.extract_from_text(text)


@router.post("/detect", response_model=DetectionResult)
async def detect_pdf_type(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    tmp_path = None
    try:
        content = await file.read()
        if not content[:4] == b"%PDF":
            raise HTTPException(
                status_code=400,
                detail="File does not appear to be a valid PDF.",
            )

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        detector = PDFDetector(tmp_path)
        return detector.detect()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Failed to detect PDF type: {str(e)}",
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.post("/extraction/scrub-preview")
async def scrub_preview(body: dict = Body(...)):
    """Return PHI-scrubbed text for preview purposes."""
    full_text = body.get("full_text", "")
    clinical_context = body.get("clinical_context", "")
    if not full_text:
        raise HTTPException(status_code=400, detail="full_text is required.")

    scrub_result = scrub_phi(full_text)
    scrubbed_clinical = scrub_phi(clinical_context).scrubbed_text if clinical_context else ""

    return {
        "scrubbed_text": scrub_result.scrubbed_text,
        "scrubbed_clinical_context": scrubbed_clinical,
        "phi_found": scrub_result.phi_found,
        "redaction_count": scrub_result.redaction_count,
    }


@router.post("/analyze/detect-type", response_model=DetectTypeResponse)
async def detect_test_type(body: DetectTypeRequest = Body(...)):
    """Auto-detect the medical test type from extraction results.

    Uses a three-tier strategy:
    1. Keyword detection (fast, free) — accept if confidence >= 0.4
    2. LLM fallback — if keywords are low confidence
    3. Return best result with detection_method indicating outcome
    """
    import logging
    _logger = logging.getLogger(__name__)

    try:
        extraction_result = ExtractionResult.model_validate(body.extraction_result)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid extraction result: {str(e)}",
        )

    available = registry.list_types()

    # Tier 1: Keyword detection
    type_id, confidence = registry.detect(extraction_result)

    if confidence >= 0.4 and type_id is not None:
        return DetectTypeResponse(
            test_type=type_id,
            confidence=round(confidence, 3),
            available_types=available,
            detection_method="keyword",
            llm_attempted=False,
        )

    # Tier 2: LLM fallback
    llm_attempted = False
    try:
        settings = settings_store.get_settings()
        provider_str = settings.llm_provider.value
        api_key = settings_store.get_api_key_for_provider(provider_str)

        if api_key:
            from test_types.llm_detector import llm_detect_test_type

            llm_attempted = True
            provider_enum = LLMProvider(provider_str)
            client = LLMClient(provider=provider_enum, api_key=api_key)
            llm_type_id, llm_confidence, llm_display = await llm_detect_test_type(
                client, extraction_result.full_text, body.user_hint,
                registry_types=available,
            )

            if llm_type_id is not None and llm_confidence >= 0.5:
                return DetectTypeResponse(
                    test_type=llm_type_id,
                    confidence=round(llm_confidence, 3),
                    available_types=available,
                    detection_method="llm",
                    llm_attempted=True,
                )
    except Exception:
        _logger.exception("LLM fallback failed during detect-type")

    # Tier 3: Return best keyword result with "none" method (frontend shows dropdown)
    return DetectTypeResponse(
        test_type=type_id,
        confidence=round(confidence, 3),
        available_types=available,
        detection_method="none",
        llm_attempted=llm_attempted,
    )


@router.post("/analyze/classify-input")
async def classify_input(body: dict = Body(...)):
    """Classify whether input text is a medical report or a question/request."""
    import re as _re

    text = body.get("text", "").strip()
    if not text:
        return {"classification": "question", "confidence": 0.5}

    # Heuristic tier — fast, no API call
    text_lower = text.lower()
    lines = text.strip().split("\n")

    # Strong report signals
    report_signals = 0
    if len(text) > 500:
        report_signals += 2
    if len(lines) > 10:
        report_signals += 1
    # Medical report headers
    report_headers = [
        "findings:", "impression:", "conclusion:", "indication:",
        "technique:", "comparison:", "history:", "procedure:",
        "clinical information:", "report:", "examination:",
        "echocardiogram", "stress test", "nuclear", "catheterization",
        "electrocardiogram", "holter", "mri", "ct scan",
    ]
    for header in report_headers:
        if header in text_lower:
            report_signals += 2
    # Measurement patterns (e.g., "3.5 cm", "120/80", "55%")
    if _re.search(r'\d+\.?\d*\s*(?:cm|mm|mg|ml|%|mmHg|bpm)', text):
        report_signals += 2

    # Strong question signals
    question_signals = 0
    if text.endswith("?"):
        question_signals += 3
    question_starters = [
        "explain", "help me", "how do i", "what does", "what is",
        "can you", "please", "write", "draft", "tell the patient",
        "why is", "why are", "what should", "how should",
    ]
    for starter in question_starters:
        if text_lower.startswith(starter):
            question_signals += 3
    if len(text) < 200 and len(lines) <= 3:
        question_signals += 1

    if report_signals > question_signals:
        return {"classification": "report", "confidence": 0.9}
    elif question_signals > report_signals:
        return {"classification": "question", "confidence": 0.9}

    # Ambiguous — use LLM for tiebreak (optional, if API key available)
    try:
        settings = settings_store.get_settings()
        api_key = settings_store.get_api_key_for_provider(settings.llm_provider.value)
        if api_key:
            client = LLMClient(
                provider=LLMProvider(settings.llm_provider.value),
                api_key=api_key,
            )
            resp = await client.call(
                system_prompt="Classify the following text as either 'report' (a medical test report) or 'question' (a question or request for help). Reply with exactly one word: report or question.",
                user_prompt=text[:1000],
            )
            word = resp.text_content.strip().lower()
            if word in ("report", "question"):
                return {"classification": word, "confidence": 0.7}
    except Exception:
        pass

    # Default: if short text, assume question; if long, assume report
    if len(text) < 300:
        return {"classification": "question", "confidence": 0.5}
    return {"classification": "report", "confidence": 0.5}


@router.post("/analyze/parse", response_model=ParsedReport)
async def parse_report(request: ParseRequest = Body(...)):
    """Parse extraction results into structured medical report."""
    try:
        extraction_result = ExtractionResult.model_validate(request.extraction_result)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid extraction result: {str(e)}",
        )

    test_type = request.test_type
    if not test_type:
        type_id, confidence = registry.detect(extraction_result)
        if type_id is None or confidence < 0.2:
            raise HTTPException(
                status_code=422,
                detail="Could not determine the test type. Please specify test_type.",
            )
        test_type = type_id

    handler = registry.get(test_type)
    if handler is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown test type: {test_type}. "
            f"Available: {[t['test_type_id'] for t in registry.list_types()]}",
        )

    try:
        return handler.parse(extraction_result)
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Failed to parse report: {str(e)}",
        )


@router.post("/analyze/explain", response_model=ExplainResponse)
async def explain_report(request: ExplainRequest = Body(...)):
    """Full analysis pipeline: detect type -> parse -> PHI scrub -> LLM explain."""

    # 1. Parse extraction result
    try:
        extraction_result = ExtractionResult.model_validate(request.extraction_result)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid extraction result: {str(e)}",
        )

    # 2. Detect test type
    test_type = request.test_type
    detection_confidence = 0.0
    if not test_type:
        type_id, confidence = registry.detect(extraction_result)
        if type_id is None or confidence < 0.2:
            raise HTTPException(
                status_code=422,
                detail="Could not determine the test type. Please specify test_type.",
            )
        test_type = type_id
        detection_confidence = confidence

    resolved_id, handler = registry.resolve(test_type)
    if handler is not None:
        test_type = resolved_id  # Use canonical ID

    # 2b. Extract demographics early so they can be used in parsing
    demographics = extract_demographics(extraction_result.full_text)
    patient_age = request.patient_age if request.patient_age is not None else demographics.age
    patient_gender = request.patient_gender if request.patient_gender is not None else demographics.gender

    # 3. Parse report (or build a generic one for unknown types)
    if handler is not None:
        try:
            parsed_report = handler.parse(extraction_result, gender=patient_gender, age=patient_age)
        except Exception as e:
            raise HTTPException(
                status_code=422,
                detail=f"Failed to parse report: {str(e)}",
            )
    else:
        # Unknown / user-specified test type — build a minimal parsed report
        # and let the LLM interpret the raw text directly.
        parsed_report = ParsedReport(
            test_type=test_type,
            test_type_display=test_type.replace("_", " ").title(),
            detection_confidence=detection_confidence,
        )

    # 4. Resolve API key
    settings = settings_store.get_settings()
    provider_str = request.provider.value if request.provider else settings.llm_provider.value
    api_key = request.api_key or settings_store.get_api_key_for_provider(
        provider_str
    )
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail=(
                f"No API key configured for provider '{provider_str}'. "
                f"Set it in Settings or pass api_key in the request."
            ),
        )

    # 5. PHI scrub
    scrub_result = scrub_phi(extraction_result.full_text)

    # 5a. PHI scrub clinical context if provided
    scrubbed_clinical_context = (
        scrub_phi(request.clinical_context).scrubbed_text
        if request.clinical_context
        else None
    )

    # Note: demographics (patient_age, patient_gender) already extracted above in step 2b

    # 5b. Always extract physician name from report text (for the UI)
    extracted_physician = extract_physician_name(extraction_result.full_text)

    # Resolve which physician name to use in the LLM prompt
    if request.physician_name_override is not None:
        active_physician = request.physician_name_override or None
    else:
        source = settings.physician_name_source.value
        if source == "auto_extract":
            active_physician = extracted_physician
        elif source == "custom":
            active_physician = settings.custom_physician_name
        else:
            active_physician = None

    # 5c. Resolve voice & name_drop — request override takes priority
    voice = request.explanation_voice.value if request.explanation_voice is not None else settings.explanation_voice.value
    name_drop = request.name_drop if request.name_drop is not None else settings.name_drop

    # 6. Build prompts
    literacy_level = LiteracyLevel(request.literacy_level.value)
    prompt_engine = PromptEngine()
    prompt_context = handler.get_prompt_context(extraction_result) if handler else {}
    if not handler:
        # For unknown test types, tell the LLM what the user thinks it is
        prompt_context["test_type_hint"] = test_type
    if settings.specialty and "specialty" not in prompt_context:
        prompt_context["specialty"] = settings.specialty
    tone_pref = request.tone_preference if request.tone_preference is not None else settings.tone_preference
    detail_pref = request.detail_preference if request.detail_preference is not None else settings.detail_preference
    inc_findings = request.include_key_findings if request.include_key_findings is not None else settings.include_key_findings
    inc_measurements = request.include_measurements if request.include_measurements is not None else settings.include_measurements
    is_sms = bool(request.sms_summary)
    system_prompt = prompt_engine.build_system_prompt(
        literacy_level=literacy_level,
        prompt_context=prompt_context,
        tone_preference=tone_pref,
        detail_preference=detail_pref,
        physician_name=active_physician,
        short_comment=bool(request.short_comment),
        explanation_voice=voice,
        name_drop=name_drop,
        short_comment_char_limit=settings.short_comment_char_limit,
        include_key_findings=inc_findings,
        include_measurements=inc_measurements,
        patient_age=patient_age,
        patient_gender=patient_gender,
        sms_summary=is_sms,
        sms_summary_char_limit=settings.sms_summary_char_limit,
    )
    # 6b. Load template if specified
    template_tone = None
    template_instructions = None
    template_closing = None
    if request.template_id is not None:
        db = get_db()
        tpl = db.get_template(request.template_id)
        if tpl:
            template_tone = tpl.get("tone")
            template_instructions = tpl.get("structure_instructions")
            template_closing = tpl.get("closing_text")
            if template_tone:
                prompt_context["tone"] = template_tone
    elif request.shared_template_sync_id:
        db = get_db()
        tpl = db.get_shared_template_by_sync_id(request.shared_template_sync_id)
        if tpl:
            template_tone = tpl.get("tone")
            template_instructions = tpl.get("structure_instructions")
            template_closing = tpl.get("closing_text")
            if template_tone:
                prompt_context["tone"] = template_tone

    # 6c. Fetch liked examples for style guidance
    liked_examples = get_db().get_liked_examples(
        limit=2, test_type=test_type,
        tone_preference=tone_pref, detail_preference=detail_pref,
    )

    # 6d. Fetch teaching points (global + type-specific, including shared)
    teaching_points = get_db().list_all_teaching_points_for_prompt(test_type=test_type)

    # 6e. Fetch prior results for longitudinal trend comparison
    prior_results = get_db().get_prior_measurements(test_type=test_type, limit=3)

    # 6f. Fetch recent doctor edits for style learning
    recent_edits = get_db().get_recent_edits(test_type=test_type, limit=3)

    user_prompt = prompt_engine.build_user_prompt(
        parsed_report=parsed_report,
        reference_ranges=handler.get_reference_ranges() if handler else {},
        glossary=handler.get_glossary() if handler else {},
        scrubbed_text=scrub_result.scrubbed_text,
        clinical_context=scrubbed_clinical_context,
        template_instructions=template_instructions,
        closing_text=template_closing,
        refinement_instruction=request.refinement_instruction,
        liked_examples=liked_examples,
        next_steps=request.next_steps,
        teaching_points=teaching_points,
        short_comment=bool(request.short_comment) or is_sms,
        prior_results=prior_results,
        recent_edits=recent_edits,
        patient_age=patient_age,
        patient_gender=patient_gender,
    )

    # Log prompt sizes for debugging token issues
    import logging
    _logger = logging.getLogger(__name__)
    _logger.warning(
        "Prompt sizes — system: %d chars, user: %d chars, short_comment: %s, sms: %s",
        len(system_prompt), len(user_prompt), bool(request.short_comment), is_sms,
    )

    # 7. Call LLM with retry
    llm_provider = LLMProvider(provider_str)
    model_override = (
        settings.claude_model
        if provider_str == "claude"
        else settings.openai_model
    )
    if request.deep_analysis and provider_str == "claude":
        from llm.client import CLAUDE_DEEP_MODEL
        model_override = CLAUDE_DEEP_MODEL
    client = LLMClient(
        provider=llm_provider,
        api_key=api_key,
        model=model_override,
    )

    # SMS/short comments need far fewer output tokens
    if request.deep_analysis:
        max_tokens = 8192
    elif is_sms:
        max_tokens = 512
    elif request.short_comment:
        max_tokens = 1024
    else:
        max_tokens = 4096

    try:
        llm_response = await with_retry(
            client.call_with_tool,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            tool_name=EXPLANATION_TOOL_NAME,
            tool_schema=EXPLANATION_TOOL_SCHEMA,
            max_tokens=max_tokens,
            max_attempts=2,
        )
    except LLMRetryError as e:
        raise HTTPException(
            status_code=502,
            detail=f"LLM API call failed after retries: {e.last_error}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"LLM API call failed: {e}",
        )

    # 8. Parse and validate response
    try:
        explanation, issues = parse_and_validate_response(
            tool_result=llm_response.tool_call_result,
            parsed_report=parsed_report,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=502,
            detail=f"LLM response validation failed: {e}",
        )

    return ExplainResponse(
        explanation=explanation,
        parsed_report=parsed_report,
        validation_warnings=[issue.message for issue in issues],
        phi_categories_found=scrub_result.phi_found,
        physician_name=extracted_physician,
        model_used=llm_response.model,
        input_tokens=llm_response.input_tokens,
        output_tokens=llm_response.output_tokens,
    )


@router.get("/glossary/{test_type}")
async def get_glossary(test_type: str):
    """Return glossary of medical terms for a given test type."""
    resolved_id, handler = registry.resolve(test_type)
    if handler is None:
        return {"test_type": test_type, "glossary": {}}
    return {"test_type": resolved_id, "glossary": handler.get_glossary()}


@router.post("/export/pdf")
async def export_pdf(request: Request):
    """Generate a PDF report from an ExplainResponse."""
    try:
        from report_gen import render_pdf
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="PDF export is not available: weasyprint is not installed.",
        )

    body = await request.json()

    try:
        pdf_bytes = render_pdf(body)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"PDF generation failed: {e}",
        )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="explify-report.pdf"'},
    )


def _mask_api_key(key: str | None) -> str | None:
    """Mask an API key for display, keeping first 8 and last 4 chars."""
    if not key:
        return key
    if len(key) < 16:
        return "***"
    return key[:8] + "..." + key[-4:]


@router.get("/settings", response_model=AppSettings)
async def get_settings():
    """Return current application settings with masked API keys."""
    settings = settings_store.get_settings()
    settings.claude_api_key = _mask_api_key(settings.claude_api_key)
    settings.openai_api_key = _mask_api_key(settings.openai_api_key)
    return settings


@router.patch("/settings", response_model=AppSettings)
async def update_settings(update: SettingsUpdate = Body(...)):
    """Update application settings (partial update)."""
    updated = settings_store.update_settings(update)
    updated.claude_api_key = _mask_api_key(updated.claude_api_key)
    updated.openai_api_key = _mask_api_key(updated.openai_api_key)
    return updated


# --- Template Endpoints ---


@router.get("/templates", response_model=TemplateListResponse)
async def list_templates():
    """Return all templates."""
    db = get_db()
    items, total = db.list_templates()
    return TemplateListResponse(
        items=[TemplateResponse(**item) for item in items],
        total=total,
    )


@router.post("/templates", response_model=TemplateResponse, status_code=201)
async def create_template(request: TemplateCreateRequest = Body(...)):
    """Create a new template."""
    db = get_db()
    record = db.create_template(
        name=request.name,
        test_type=request.test_type,
        tone=request.tone,
        structure_instructions=request.structure_instructions,
        closing_text=request.closing_text,
    )
    return TemplateResponse(**record)


@router.post("/templates/shared/sync")
async def sync_shared_templates(body: dict = Body(...)):
    """Full-replace local shared templates cache."""
    rows = body.get("rows", [])
    if not isinstance(rows, list):
        raise HTTPException(status_code=400, detail="rows must be a list.")
    db = get_db()
    count = db.replace_shared_templates(rows)
    return {"replaced": count}


@router.get("/templates/shared")
async def list_shared_templates():
    """Return cached shared templates."""
    db = get_db()
    return db.list_shared_templates()


@router.patch("/templates/{template_id}", response_model=TemplateResponse)
async def update_template(template_id: int, request: TemplateUpdateRequest = Body(...)):
    """Update an existing template."""
    db = get_db()
    update_data = request.model_dump(exclude_unset=True)
    record = db.update_template(template_id, **update_data)
    if not record:
        raise HTTPException(status_code=404, detail="Template not found.")
    return TemplateResponse(**record)


@router.delete("/templates/{template_id}")
async def delete_template(template_id: int):
    """Delete a template."""
    db = get_db()
    deleted = db.delete_template(template_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Template not found.")
    return {"deleted": True, "id": template_id}


# --- History Endpoints ---


@router.get("/history", response_model=HistoryListResponse)
async def list_history(
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    liked_only: bool = Query(False),
):
    """Return paginated history list, newest first."""
    db = get_db()
    items, total = db.list_history(
        offset=offset, limit=limit, search=search, liked_only=liked_only,
    )
    for item in items:
        item["liked"] = bool(item.get("liked", 0))
    return HistoryListResponse(
        items=[HistoryListItem(**item) for item in items],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/history/{history_id}", response_model=HistoryDetailResponse)
async def get_history_detail(history_id: int):
    """Return single history record with full_response."""
    db = get_db()
    record = db.get_history(history_id)
    if not record:
        raise HTTPException(status_code=404, detail="History record not found.")
    record["liked"] = bool(record.get("liked", 0))
    return HistoryDetailResponse(**record)


@router.post("/history", response_model=HistoryDetailResponse, status_code=201)
async def create_history(request: HistoryCreateRequest = Body(...)):
    """Save a new analysis history record."""
    db = get_db()
    record = db.save_history(
        test_type=request.test_type,
        test_type_display=request.test_type_display,
        summary=request.summary,
        full_response=request.full_response,
        filename=request.filename,
        tone_preference=request.tone_preference,
        detail_preference=request.detail_preference,
    )
    record["liked"] = bool(record.get("liked", 0))
    return HistoryDetailResponse(**record)


@router.delete("/history/{history_id}", response_model=HistoryDeleteResponse)
async def delete_history(history_id: int):
    """Hard-delete a history record."""
    db = get_db()
    deleted = db.delete_history(history_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="History record not found.")
    return HistoryDeleteResponse(deleted=True, id=history_id)


@router.patch("/history/{history_id}/like", response_model=HistoryLikeResponse)
async def toggle_history_liked(
    history_id: int,
    request: HistoryLikeRequest = Body(...),
):
    """Toggle the liked status of a history record."""
    db = get_db()
    updated = db.update_history_liked(history_id, request.liked)
    if not updated:
        raise HTTPException(status_code=404, detail="History record not found.")
    return HistoryLikeResponse(id=history_id, liked=request.liked)


@router.put("/history/{history_id}/copied")
async def mark_history_copied(history_id: int):
    """Mark a history record as copied (lightweight positive signal)."""
    db = get_db()
    updated = db.mark_copied(history_id)
    if not updated:
        raise HTTPException(status_code=404, detail="History record not found.")
    return {"id": history_id, "copied": True}


class EditedTextRequest(BaseModel):
    edited_text: str


@router.patch("/history/{history_id}/edited_text")
async def save_edited_text(history_id: int, request: EditedTextRequest = Body(...)):
    """Save the doctor's edited version of the explanation text."""
    db = get_db()
    updated = db.save_edited_text(history_id, request.edited_text)
    if not updated:
        raise HTTPException(status_code=404, detail="History record not found.")
    return {"id": history_id, "edited_text_saved": True}


# --- Consent Endpoints ---


@router.get("/settings/raw-key/{provider}")
async def get_raw_key(provider: str):
    """Return the unmasked API key for a provider. Safe because sidecar is local-only."""
    key = settings_store.get_api_key_for_provider(provider)
    if not key:
        raise HTTPException(status_code=404, detail=f"No key configured for {provider}")
    return {"provider": provider, "key": key}


@router.get("/consent", response_model=ConsentStatusResponse)
async def get_consent():
    """Check whether the user has given privacy consent."""
    db = get_db()
    value = db.get_setting("privacy_consent_given")
    return ConsentStatusResponse(consent_given=value == "true")


@router.post("/consent", response_model=ConsentStatusResponse)
async def grant_consent():
    """Record that the user has given privacy consent."""
    db = get_db()
    db.set_setting("privacy_consent_given", "true")
    return ConsentStatusResponse(consent_given=True)


# --- Onboarding Endpoints ---


@router.get("/onboarding")
async def get_onboarding():
    """Check whether the user has completed onboarding."""
    db = get_db()
    value = db.get_setting("onboarding_completed")
    return {"onboarding_completed": value == "true"}


@router.post("/onboarding")
async def complete_onboarding():
    """Record that the user has completed onboarding."""
    db = get_db()
    db.set_setting("onboarding_completed", "true")
    return {"onboarding_completed": True}


# --- Letter Endpoints ---


# --- Teaching Points Endpoints ---


@router.get("/teaching-points")
async def list_teaching_points(test_type: str | None = Query(None)):
    """Return teaching points (global + test-type-specific)."""
    db = get_db()
    points = db.list_teaching_points(test_type=test_type)
    return points


@router.post("/teaching-points", status_code=201)
async def create_teaching_point(body: dict = Body(...)):
    """Create a new teaching point."""
    text = body.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Teaching point text is required.")
    test_type = body.get("test_type")
    db = get_db()
    return db.create_teaching_point(text=text, test_type=test_type)


@router.post("/teaching-points/shared/sync")
async def sync_shared_teaching_points(body: dict = Body(...)):
    """Full-replace local shared teaching points cache."""
    rows = body.get("rows", [])
    if not isinstance(rows, list):
        raise HTTPException(status_code=400, detail="rows must be a list.")
    db = get_db()
    count = db.replace_shared_teaching_points(rows)
    # Remove any shared content that was incorrectly merged into the user's
    # own teaching_points table during earlier syncs.
    purged = db.purge_shared_duplicates_from_own()
    return {"replaced": count, "purged_duplicates": purged}


@router.get("/teaching-points/shared")
async def list_shared_teaching_points(test_type: str | None = Query(None)):
    """Return cached shared teaching points."""
    db = get_db()
    return db.list_shared_teaching_points(test_type=test_type)


@router.delete("/teaching-points/{point_id}")
async def delete_teaching_point(point_id: int):
    """Delete a teaching point."""
    db = get_db()
    deleted = db.delete_teaching_point(point_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Teaching point not found.")
    return {"deleted": True, "id": point_id}


@router.put("/teaching-points/{point_id}")
async def update_teaching_point(point_id: int, body: dict = Body(...)):
    """Update a teaching point's text and/or test_type."""
    db = get_db()
    updated = db.update_teaching_point(
        point_id,
        text=body.get("text"),
        test_type=body.get("test_type", "UNSET"),
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Teaching point not found.")
    return updated


@router.post("/letters/generate", response_model=LetterResponse, status_code=201)
async def generate_letter(request: LetterGenerateRequest = Body(...)):
    """Generate a patient-facing letter/explanation from free-text input."""
    settings = settings_store.get_settings()
    provider_str = settings.llm_provider.value
    api_key = settings_store.get_api_key_for_provider(provider_str)
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail=f"No API key configured for provider '{provider_str}'. Set it in Settings.",
        )

    specialty = settings.specialty or "general medicine"

    # Resolve physician voice settings
    voice = settings.explanation_voice.value
    name_drop = settings.name_drop
    source = settings.physician_name_source.value
    if source == "custom":
        physician_name = settings.custom_physician_name
    else:
        physician_name = None

    physician_section = ""
    if voice == "first_person":
        physician_section = (
            "\n## Physician Voice — First Person\n"
            "You ARE the physician. Write in first person. "
            'Use first-person language: "I have reviewed your results", '
            '"In my assessment". '
            'NEVER use third-person references like "your doctor" or '
            '"your physician".\n'
        )
    elif physician_name:
        attribution = ""
        if name_drop:
            attribution = (
                f" Include at least one explicit attribution such as "
                f'"{physician_name} has reviewed your results".'
            )
        physician_section = (
            f"\n## Physician Voice — Third Person (Care Team)\n"
            f"You are writing on behalf of the physician. "
            f'When referring to the physician, use "{physician_name}" '
            f'instead of generic phrases like "your doctor" or "your physician".{attribution}\n'
        )

    # Fetch teaching points (including shared) and liked examples for style guidance
    db = get_db()
    teaching_points = db.list_all_teaching_points_for_prompt(test_type=None)
    liked_examples = db.get_liked_examples(
        limit=2, test_type=None,
        tone_preference=settings.tone_preference,
        detail_preference=settings.detail_preference,
    )

    teaching_section = ""
    if teaching_points:
        teaching_section = (
            "\n## Teaching Points\n"
            "The physician has provided the following personalized instructions.\n"
            "These reflect their clinical style and preferences. Follow them closely\n"
            "so the output matches how this physician communicates:\n"
        )
        for tp in teaching_points:
            source = tp.get("source", "own")
            if source == "own":
                teaching_section += f"- {tp['text']}\n"
            else:
                teaching_section += f"- [From {source}] {tp['text']}\n"

    style_section = ""
    if liked_examples:
        style_section = (
            "\n## Preferred Output Style\n"
            "The physician has approved outputs with the following structural characteristics.\n"
            "Match this structure, length, and level of detail.\n"
        )
        for idx, example in enumerate(liked_examples, 1):
            style_section += (
                f"\n### Style Reference {idx}\n"
                f"- Summary length: ~{example.get('approx_char_length', 'unknown')} characters\n"
                f"- Paragraphs: {example.get('paragraph_count', 'unknown')}\n"
                f"- Approximate sentences: {example.get('approx_sentence_count', 'unknown')}\n"
            )

    from llm.prompt_engine import _TONE_DESCRIPTIONS, _DETAIL_DESCRIPTIONS
    tone_desc = _TONE_DESCRIPTIONS.get(settings.tone_preference, _TONE_DESCRIPTIONS[3])
    detail_desc = _DETAIL_DESCRIPTIONS.get(settings.detail_preference, _DETAIL_DESCRIPTIONS[3])

    system_prompt = (
        f"You are writing as a physician or member of the care team at a "
        f"{specialty} practice, composing a message to a patient. The message "
        f"must sound exactly like the clinician wrote it themselves and require "
        f"no editing before sending.\n\n"
        f"## Rules\n"
        f"1. Write in plain, compassionate language appropriate for patients.\n"
        f"2. Do NOT include any patient-identifying information.\n"
        f"3. Interpret findings — explain WHAT results mean for the patient. "
        f"The patient already has their results; do NOT simply recite values "
        f"they can already read. Synthesize findings into meaningful clinical "
        f"statements that help the patient understand their health.\n"
        f"4. NEVER suggest treatments, future testing, or hypothetical actions. "
        f"Do NOT write phrases like 'your doctor may recommend' or 'we may need to'. "
        f"The physician will add their own specific recommendations separately.\n"
        f"5. Be thorough but concise.\n"
        f"6. Structure the response clearly with paragraphs or sections as appropriate.\n"
        f"7. Return ONLY the letter/explanation text. No preamble or meta-commentary.\n"
        f"{physician_section}"
        f"\n## Tone Preference\n{tone_desc}\n"
        f"\n## Detail Level\n{detail_desc}\n"
        f"{teaching_section}"
        f"{style_section}"
    )

    llm_provider = LLMProvider(provider_str)
    model_override = (
        settings.claude_model if provider_str == "claude" else settings.openai_model
    )
    client = LLMClient(
        provider=llm_provider,
        api_key=api_key,
        model=model_override,
    )

    try:
        llm_response = await client.call(
            system_prompt=system_prompt,
            user_prompt=request.prompt,
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"LLM API call failed: {e}",
        )

    content = llm_response.text_content

    db = get_db()
    letter_id = db.save_letter(
        prompt=request.prompt,
        content=content,
        letter_type=request.letter_type,
        model_used=getattr(llm_response, "model", None),
        input_tokens=getattr(llm_response, "input_tokens", None),
        output_tokens=getattr(llm_response, "output_tokens", None),
    )
    record = db.get_letter(letter_id)
    return LetterResponse(**record)  # type: ignore[arg-type]


@router.get("/letters", response_model=LetterListResponse)
async def list_letters(
    offset: int = 0,
    limit: int = 50,
    search: str | None = None,
    liked_only: bool = False,
):
    """Return generated letters with pagination, newest first."""
    db = get_db()
    items, total = db.list_letters(
        offset=offset,
        limit=limit,
        search=search,
        liked_only=liked_only,
    )
    return LetterListResponse(
        items=[LetterResponse(**item) for item in items],
        total=total,
    )


@router.get("/letters/{letter_id}", response_model=LetterResponse)
async def get_letter(letter_id: int):
    """Return a single letter."""
    db = get_db()
    record = db.get_letter(letter_id)
    if not record:
        raise HTTPException(status_code=404, detail="Letter not found.")
    return LetterResponse(**record)


@router.delete("/letters/{letter_id}", response_model=LetterDeleteResponse)
async def delete_letter(letter_id: int):
    """Delete a letter."""
    db = get_db()
    deleted = db.delete_letter(letter_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Letter not found.")
    return LetterDeleteResponse(deleted=True, id=letter_id)


@router.put("/letters/{letter_id}", response_model=LetterResponse)
async def update_letter(letter_id: int, request: LetterUpdateRequest = Body(...)):
    """Update a letter's content."""
    db = get_db()
    record = db.update_letter(letter_id, request.content)
    if not record:
        raise HTTPException(status_code=404, detail="Letter not found.")
    return LetterResponse(**record)


@router.put("/letters/{letter_id}/like")
async def toggle_letter_liked(letter_id: int, request: LetterLikeRequest = Body(...)):
    """Toggle the liked status of a letter."""
    db = get_db()
    updated = db.toggle_letter_liked(letter_id, request.liked)
    if not updated:
        raise HTTPException(status_code=404, detail="Letter not found.")
    return {"id": letter_id, "liked": request.liked}


# --- Sync Endpoints ---


@router.get("/sync/export/{table}")
async def sync_export_all(table: str):
    """Return all local rows for a table (for sync push)."""
    db = get_db()
    rows = db.export_table(table)
    return rows


@router.get("/sync/export/{table}/{record_id}")
async def sync_export_record(table: str, record_id: int):
    """Return a single row by local id (with sync_id)."""
    db = get_db()
    record = db.export_record(table, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found.")
    return record


@router.post("/sync/merge")
async def sync_merge(body: dict = Body(...)):
    """Merge remote rows into local DB.

    Expects: { "table": str, "rows": list[dict] }
    Settings rows are matched by key, others by sync_id.
    """
    table = body.get("table", "")
    rows = body.get("rows", [])
    if not table or not isinstance(rows, list):
        raise HTTPException(status_code=400, detail="table and rows are required.")

    db = get_db()
    merged = 0
    skipped = 0

    for row in rows:
        try:
            if table == "settings":
                key = row.get("key")
                value = row.get("value")
                updated_at = row.get("updated_at", "")
                if key and value is not None:
                    if db.merge_settings_row(key, str(value), updated_at):
                        merged += 1
                    else:
                        skipped += 1
            else:
                if db.merge_record(table, row):
                    merged += 1
                else:
                    skipped += 1
        except Exception:
            skipped += 1

    return {"merged": merged, "skipped": skipped}
