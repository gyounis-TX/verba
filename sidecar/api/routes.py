import os
import tempfile

from fastapi import APIRouter, Body, File, HTTPException, Query, Request, Response, UploadFile

from api.analysis_models import DetectTypeResponse, ParsedReport, ParseRequest
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
    LetterListResponse,
    LetterResponse,
)
from api.models import DetectionResult, ExtractionResult
from api import settings_store
from storage.database import get_db
from extraction import ExtractionPipeline, extract_physician_name
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


@router.post("/analyze/detect-type", response_model=DetectTypeResponse)
async def detect_test_type(body: dict = Body(...)):
    """Auto-detect the medical test type from extraction results."""
    try:
        extraction_result = ExtractionResult(**body)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid extraction result: {str(e)}",
        )

    type_id, confidence = registry.detect(extraction_result)
    return DetectTypeResponse(
        test_type=type_id,
        confidence=round(confidence, 3),
        available_types=registry.list_types(),
    )


@router.post("/analyze/parse", response_model=ParsedReport)
async def parse_report(request: ParseRequest = Body(...)):
    """Parse extraction results into structured medical report."""
    try:
        extraction_result = ExtractionResult(**request.extraction_result)
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
        extraction_result = ExtractionResult(**request.extraction_result)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid extraction result: {str(e)}",
        )

    # 2. Detect test type
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
            detail=f"Unknown test type: {test_type}",
        )

    # 3. Parse report
    try:
        parsed_report = handler.parse(extraction_result)
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Failed to parse report: {str(e)}",
        )

    # 4. Resolve API key
    settings = settings_store.get_settings()
    provider_str = request.provider.value
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

    # 5b. Resolve physician name — request override takes priority
    if request.physician_name_override is not None:
        physician_name = request.physician_name_override or None
    else:
        source = settings.physician_name_source.value
        if source == "auto_extract":
            physician_name = extract_physician_name(extraction_result.full_text)
        elif source == "custom":
            physician_name = settings.custom_physician_name
        else:
            physician_name = None

    # 5c. Resolve voice & name_drop — request override takes priority
    voice = request.explanation_voice.value if request.explanation_voice is not None else settings.explanation_voice.value
    name_drop = request.name_drop if request.name_drop is not None else settings.name_drop

    # 6. Build prompts
    literacy_level = LiteracyLevel(request.literacy_level.value)
    prompt_engine = PromptEngine()
    prompt_context = handler.get_prompt_context()
    if settings.specialty and "specialty" not in prompt_context:
        prompt_context["specialty"] = settings.specialty
    tone_pref = request.tone_preference if request.tone_preference is not None else settings.tone_preference
    detail_pref = request.detail_preference if request.detail_preference is not None else settings.detail_preference
    system_prompt = prompt_engine.build_system_prompt(
        literacy_level=literacy_level,
        prompt_context=prompt_context,
        tone_preference=tone_pref,
        detail_preference=detail_pref,
        physician_name=physician_name,
        short_comment=bool(request.short_comment),
        explanation_voice=voice,
        name_drop=name_drop,
        short_comment_char_limit=settings.short_comment_char_limit,
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

    # 6c. Fetch liked examples for style guidance
    liked_examples = get_db().get_liked_examples(
        limit=2, test_type=test_type,
        tone_preference=tone_pref, detail_preference=detail_pref,
    )

    user_prompt = prompt_engine.build_user_prompt(
        parsed_report=parsed_report,
        reference_ranges=handler.get_reference_ranges(),
        glossary=handler.get_glossary(),
        scrubbed_text=scrub_result.scrubbed_text,
        clinical_context=request.clinical_context,
        template_instructions=template_instructions,
        closing_text=template_closing,
        refinement_instruction=request.refinement_instruction,
        liked_examples=liked_examples,
        next_steps=request.next_steps,
    )

    # 7. Call LLM with retry
    llm_provider = LLMProvider(provider_str)
    model_override = (
        settings.claude_model
        if provider_str == "claude"
        else settings.openai_model
    )
    client = LLMClient(
        provider=llm_provider,
        api_key=api_key,
        model=model_override,
    )

    try:
        llm_response = await with_retry(
            client.call_with_tool,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            tool_name=EXPLANATION_TOOL_NAME,
            tool_schema=EXPLANATION_TOOL_SCHEMA,
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
        physician_name=physician_name,
        model_used=llm_response.model,
        input_tokens=llm_response.input_tokens,
        output_tokens=llm_response.output_tokens,
    )


@router.get("/glossary/{test_type}")
async def get_glossary(test_type: str):
    """Return glossary of medical terms for a given test type."""
    handler = registry.get(test_type)
    if handler is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown test type: {test_type}. "
            f"Available: {[t['test_type_id'] for t in registry.list_types()]}",
        )
    return {"test_type": test_type, "glossary": handler.get_glossary()}


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
    new_id = db.save_history(
        test_type=request.test_type,
        test_type_display=request.test_type_display,
        summary=request.summary,
        full_response=request.full_response,
        filename=request.filename,
        tone_preference=request.tone_preference,
        detail_preference=request.detail_preference,
    )
    record = db.get_history(new_id)
    return HistoryDetailResponse(**record)  # type: ignore[arg-type]


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


# --- Consent Endpoints ---


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


# --- Letter Endpoints ---


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

    system_prompt = (
        "You are a medical communication assistant. Your job is to help physicians "
        "create clear, empathetic, patient-facing content.\n\n"
        "## Rules\n"
        "1. Write in plain, compassionate language appropriate for patients.\n"
        "2. Do NOT include any patient-identifying information.\n"
        "3. Use hedging language (may, appears to, could suggest) to reflect medical uncertainty.\n"
        "4. Be thorough but concise.\n"
        "5. Structure the response clearly with paragraphs or sections as appropriate.\n"
        "6. Return ONLY the letter/explanation text. No preamble or meta-commentary."
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
    )
    record = db.get_letter(letter_id)
    return LetterResponse(**record)  # type: ignore[arg-type]


@router.get("/letters", response_model=LetterListResponse)
async def list_letters():
    """Return all generated letters, newest first."""
    db = get_db()
    items, total = db.list_letters()
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
