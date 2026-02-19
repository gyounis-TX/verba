import json
import logging
import os
import re
import tempfile

from fastapi import APIRouter, Body, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.analysis_models import DetectTypeRequest, DetectTypeResponse, ParsedReport, ParseRequest
from api.explain_models import (
    AppSettings,
    ExplainRequest,
    ExplainResponse,
    InterpretRequest,
    InterpretResponse,
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
    HistoryRateRequest,
    HistoryRateResponse,
)
from api.letter_models import (
    LetterDeleteResponse,
    LetterGenerateRequest,
    LetterLikeRequest,
    LetterListResponse,
    LetterResponse,
    LetterUpdateRequest,
)
from api.models import DetectionResult, ExtractionResult, PageExtractionResult
from api import settings_store
from storage import get_active_db
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
from api.rate_limit import limiter, ANALYZE_RATE_LIMIT

REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "").lower() == "true"
_USE_PG = bool(os.getenv("DATABASE_URL", ""))

_logger = logging.getLogger(__name__)


def _secure_delete(path: str) -> None:
    """Overwrite file contents before unlinking to prevent forensic recovery of PHI."""
    try:
        size = os.path.getsize(path)
        with open(path, "wb") as f:
            f.write(b"\x00" * size)
            f.flush()
            os.fsync(f.fileno())
    except OSError:
        pass
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass

router = APIRouter()

pipeline = ExtractionPipeline()


async def _build_extract_llm_client(request: Request) -> LLMClient | None:
    """Build an LLM client for vision OCR fallback, or None if unavailable."""
    try:
        user_id = _get_user_id(request)
        settings = await settings_store.get_settings(user_id=user_id)
        provider_str = settings.llm_provider.value
        api_key = settings_store.get_api_key_for_provider(provider_str)
        if api_key:
            return LLMClient(provider=LLMProvider(provider_str), api_key=api_key)
    except Exception:
        _logger.debug("Could not build LLM client for vision OCR", exc_info=True)
    return None


def _get_user_id(request: Request) -> str | None:
    """Extract user_id from request state (set by AuthMiddleware)."""
    return getattr(request.state, "user_id", None)


def _db():
    """Return the active database instance."""
    return get_active_db()


async def _db_call(method_name: str, *args, user_id=None, **kwargs):
    """Call a database method, handling both sync (SQLite) and async (PG) databases.

    For PgDatabase, methods are async coroutines.
    For Database (SQLite), methods are synchronous.
    """
    import logging as _logging
    _db_logger = _logging.getLogger("db_call")
    db = _db()
    method = getattr(db, method_name)

    try:
        if _USE_PG:
            # PgDatabase methods are async and accept user_id
            return await method(*args, user_id=user_id, **kwargs)
        else:
            # SQLite Database methods are sync and ignore user_id
            return method(*args, **kwargs)
    except Exception as exc:
        _db_logger.exception("Database error in %s: %s", method_name, exc)
        raise HTTPException(
            status_code=500,
            detail="A database error occurred. Please try again.",
        )


@router.get("/health")
async def health_check():
    try:
        get_db() if not _USE_PG else get_active_db()
        return {"status": "ok"}
    except Exception:
        return {"status": "starting"}


@router.post("/extract/pdf", response_model=ExtractionResult)
async def extract_pdf(request: Request, file: UploadFile = File(...)):
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

        llm_client = await _build_extract_llm_client(request)
        result = await pipeline.extract_from_pdf(tmp_path, llm_client=llm_client)
        result.filename = file.filename
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("PDF extraction failed: %s", e)
        raise HTTPException(
            status_code=422,
            detail="Failed to extract text from PDF.",
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            _secure_delete(tmp_path)


@router.post("/extract/file", response_model=ExtractionResult)
async def extract_file(request: Request, file: UploadFile = File(...)):
    """Accept PDF, image (jpg/jpeg/png), or text (.txt) files."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    ext = os.path.splitext(file.filename.lower())[1]
    supported = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".txt"}
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

        llm_client = await _build_extract_llm_client(request)

        if ext == ".pdf":
            if not content[:4] == b"%PDF":
                raise HTTPException(
                    status_code=400,
                    detail="File does not appear to be a valid PDF.",
                )
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            result = await pipeline.extract_from_pdf(tmp_path, llm_client=llm_client)
            result.filename = file.filename
            return result

        elif ext in (".jpg", ".jpeg", ".png", ".tif", ".tiff"):
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            result = await pipeline.extract_from_image(tmp_path, llm_client=llm_client)
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
        logger.exception("File extraction failed: %s", e)
        raise HTTPException(
            status_code=422,
            detail="Failed to extract text from file.",
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            _secure_delete(tmp_path)


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
        logger.exception("PDF type detection failed: %s", e)
        raise HTTPException(
            status_code=422,
            detail="Failed to detect PDF type.",
        )
    finally:
        if tmp_path and os.path.exists(tmp_path):
            _secure_delete(tmp_path)


@router.post("/extraction/scrub-preview")
async def scrub_preview(request: Request, body: dict = Body(...)):
    """Return PHI-scrubbed text for preview purposes."""
    full_text = body.get("full_text", "")
    clinical_context = body.get("clinical_context", "")
    if not full_text:
        raise HTTPException(status_code=400, detail="full_text is required.")

    user_id = _get_user_id(request)
    if _USE_PG:
        from api.phi_audit import log_phi_access
        await log_phi_access(request, "preview_scrub", "report")
    settings = await settings_store.get_settings(user_id=user_id)
    providers = list(settings.practice_providers) if settings.practice_providers else None

    scrub_result = scrub_phi(full_text, provider_names=providers)
    scrubbed_clinical = scrub_phi(clinical_context, provider_names=providers).scrubbed_text if clinical_context else ""

    return {
        "scrubbed_text": scrub_result.scrubbed_text,
        "scrubbed_clinical_context": scrubbed_clinical,
        "phi_found": scrub_result.phi_found,
        "redaction_count": scrub_result.redaction_count,
    }


_QUICK_NORMAL_EXCLUDED_TYPES = frozenset({
    "coronary_diagram",  # invasive procedure -- always requires full interpretation
})


_ABNORMAL_TEXT_PATTERNS = re.compile(
    r"(?i)"
    r"(?:dilated\s+(?:ascending\s+aorta|aortic\s+root|aorta|atri|ventricl))"
    r"|(?:compared\s+(?:with|to)\s+(?:the\s+)?(?:prior|previous)\s+(?:study|exam|report|echocardiogram|echo|test))"
    r"|(?:(?:has|have)\s+(?:increased|worsened|deteriorated|decreased|declined|progressed))"
    r"|(?:(?:interval|since\s+prior)\s+(?:increase|decrease|worsening|progression|deterioration|change))"
    r"|(?:since\s+prior\s+(?:study|exam|echo|test|report)\b)"
    r"|(?:(?:worse|worsened|increased|new)\s+(?:compared\s+(?:to|with)|since|from)\s+(?:the\s+)?(?:prior|previous))"
    r"|(?:new\s+(?:finding|abnormality|wall\s+motion\s+abnormality|pericardial\s+effusion|pleural\s+effusion))"
)


def _assess_normalcy(type_id: str | None, extraction_result: "ExtractionResult") -> bool:
    """Check if all parsed measurements are NORMAL or UNDETERMINED and the
    report text contains no abnormal findings or comparison language.

    Returns True only when measurements exist, none are abnormal, and the
    text does not reference prior studies or worsening findings.
    Returns False on any failure, no handler, no measurements, or any abnormal indicator.
    """
    if not type_id:
        return False
    if type_id in _QUICK_NORMAL_EXCLUDED_TYPES:
        return False
    try:
        from api.analysis_models import SeverityStatus

        # Text-based checks: reject if comparison or abnormal language found
        text = extraction_result.full_text or ""
        if _ABNORMAL_TEXT_PATTERNS.search(text):
            return False

        _resolved_id, handler = registry.resolve(type_id)
        if handler is None:
            return False
        parsed = handler.parse(extraction_result)
        if not parsed.measurements:
            return False
        for m in parsed.measurements:
            if m.status not in (SeverityStatus.NORMAL, SeverityStatus.UNDETERMINED):
                return False
        return True
    except Exception:
        return False


async def _try_re_ocr(
    extraction_result: "ExtractionResult",
    handler,
    user_id: str | None,
) -> "ExtractionResult":
    """Re-OCR scanned pages with handler-specific vision hints.

    Returns the original extraction_result unchanged if re-OCR is not
    applicable or fails.
    """
    import logging
    _logger = logging.getLogger(__name__)

    vision_hints = handler.get_vision_hints()
    if vision_hints is None:
        return extraction_result

    # Only re-OCR pages that used OCR/vision_ocr
    has_ocr_pages = any(
        p.extraction_method in ("ocr", "vision_ocr")
        for p in extraction_result.pages
    )
    if not has_ocr_pages:
        return extraction_result

    extraction_id = extraction_result.extraction_id
    if not extraction_id:
        return extraction_result

    from extraction.pipeline import get_cached_images
    cached_images = get_cached_images(extraction_id)
    if not cached_images:
        _logger.debug("No cached images for extraction_id=%s", extraction_id)
        return extraction_result

    # Get LLM client for re-OCR
    try:
        settings = await settings_store.get_settings(user_id=user_id)
        provider_str = settings.llm_provider.value
        api_key = settings_store.get_api_key_for_provider(provider_str)
        if not api_key:
            return extraction_result

        from extraction.vision_ocr import vision_ocr_page
        llm_client = LLMClient(provider=LLMProvider(provider_str), api_key=api_key)

        updated_pages = list(extraction_result.pages)
        re_ocr_count = 0

        for i, page in enumerate(updated_pages):
            if page.extraction_method not in ("ocr", "vision_ocr"):
                continue
            page_img = cached_images.get(page.page_number)
            if not page_img:
                continue

            # Redact PHI from header/footer regions before re-OCR
            from phi.image_redactor import redact_image_phi
            page_img = redact_image_phi(page_img)

            new_text, new_conf = await vision_ocr_page(
                llm_client, page_img, additional_hints=vision_hints,
            )
            # Guard: only accept if re-OCR produced meaningful text
            if new_conf > 0 and len(new_text) >= len(page.text) * 0.5:
                updated_pages[i] = PageExtractionResult(
                    page_number=page.page_number,
                    text=new_text,
                    extraction_method="vision_ocr_enhanced",
                    confidence=new_conf,
                    char_count=len(new_text),
                )
                re_ocr_count += 1

        if re_ocr_count > 0:
            full_text = "\n\n".join(p.text for p in updated_pages if p.text)
            _logger.info(
                "Re-OCR enhanced %d page(s) for extraction_id=%s",
                re_ocr_count, extraction_id,
            )
            return ExtractionResult(
                input_mode=extraction_result.input_mode,
                full_text=full_text,
                pages=updated_pages,
                tables=extraction_result.tables,
                detection=extraction_result.detection,
                total_pages=extraction_result.total_pages,
                total_chars=len(full_text),
                filename=extraction_result.filename,
                warnings=extraction_result.warnings + [
                    f"{re_ocr_count} page(s) re-analyzed with enhanced OCR."
                ],
                extraction_id=extraction_id,
            )
    except Exception:
        _logger.exception("Re-OCR failed, continuing with original text")

    return extraction_result


@router.post("/analyze/detect-type", response_model=DetectTypeResponse)
@limiter.limit(ANALYZE_RATE_LIMIT)
async def detect_test_type(request: Request, body: DetectTypeRequest = Body(...)):
    """Auto-detect the medical test type from extraction results.

    Uses a three-tier strategy:
    1. Keyword detection (fast, free) -- accept if confidence >= 0.4
    2. LLM fallback -- if keywords are low confidence
    3. Return best result with detection_method indicating outcome
    """
    import logging
    _logger = logging.getLogger(__name__)

    if _USE_PG:
        from api.phi_audit import log_phi_access
        await log_phi_access(request, "detect_type", "report")

    try:
        extraction_result = ExtractionResult.model_validate(body.extraction_result)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail="Invalid extraction result.",
        )

    # Extract report date from demographics
    from extraction.demographics import extract_demographics
    _demographics = extract_demographics(extraction_result.full_text)
    _report_date = _demographics.report_date

    available = registry.list_types()

    # Compound report detection
    from extraction.compound_detector import detect_compound_report
    from api.analysis_models import CompoundSegmentInfo
    compound_result = detect_compound_report(extraction_result, registry=registry)
    compound_segments: list[CompoundSegmentInfo] = []
    if compound_result.is_compound:
        compound_segments = [
            CompoundSegmentInfo(
                start_page=seg.start_page,
                end_page=seg.end_page,
                detected_type=seg.detected_type,
                confidence=round(seg.confidence, 3),
                char_count=len(seg.text),
            )
            for seg in compound_result.segments
        ]

    # Tier 1: Keyword detection
    type_id, confidence = registry.detect(extraction_result)

    if confidence >= 0.4 and type_id is not None:
        is_normal = _assess_normalcy(type_id, extraction_result)
        return DetectTypeResponse(
            test_type=type_id,
            confidence=round(confidence, 3),
            available_types=available,
            detection_method="keyword",
            llm_attempted=False,
            is_compound=compound_result.is_compound,
            compound_segments=compound_segments,
            is_likely_normal=is_normal,
            report_date=_report_date,
        )

    # Tier 2: LLM fallback
    llm_attempted = False
    try:
        user_id = _get_user_id(request)
        settings = await settings_store.get_settings(user_id=user_id)
        provider_str = settings.llm_provider.value
        api_key = settings_store.get_api_key_for_provider(provider_str)

        if api_key:
            from test_types.llm_detector import llm_detect_test_type

            llm_attempted = True
            provider_enum = LLMProvider(provider_str)
            client = LLMClient(provider=provider_enum, api_key=api_key)

            # Gather context for structured LLM excerpt
            keyword_candidates = registry.detect_multi(extraction_result, threshold=0.1)
            tables_for_llm = [
                {"headers": t.headers, "page_number": t.page_number}
                for t in (extraction_result.tables or [])
            ]

            # Scrub PHI before sending text to LLM for type detection
            _det_providers = list(settings.practice_providers) if settings.practice_providers else None
            _det_scrubbed = scrub_phi(extraction_result.full_text, provider_names=_det_providers).scrubbed_text

            _det_user_hint = scrub_phi(body.user_hint, provider_names=_det_providers).scrubbed_text if body.user_hint else None
            llm_type_id, llm_confidence, llm_display = await llm_detect_test_type(
                client, _det_scrubbed, _det_user_hint,
                registry_types=available,
                tables=tables_for_llm,
                keyword_candidates=keyword_candidates,
            )

            if llm_type_id is not None and llm_confidence >= 0.5:
                is_normal = _assess_normalcy(llm_type_id, extraction_result)
                return DetectTypeResponse(
                    test_type=llm_type_id,
                    confidence=round(llm_confidence, 3),
                    available_types=available,
                    detection_method="llm",
                    llm_attempted=True,
                    is_compound=compound_result.is_compound,
                    compound_segments=compound_segments,
                    is_likely_normal=is_normal,
                    report_date=_report_date,
                )
    except Exception:
        _logger.exception("LLM fallback failed during detect-type")

    # Tier 3: Return best keyword result with "none" method (frontend shows dropdown)
    is_normal = _assess_normalcy(type_id, extraction_result)
    return DetectTypeResponse(
        test_type=type_id,
        confidence=round(confidence, 3),
        available_types=available,
        detection_method="none",
        llm_attempted=llm_attempted,
        is_compound=compound_result.is_compound,
        compound_segments=compound_segments,
        is_likely_normal=is_normal,
        report_date=_report_date,
    )


@router.post("/analyze/detection-correction")
async def log_detection_correction(request: Request, body: dict = Body(...)):
    """Log when a user corrects the auto-detected test type.

    Used to learn from detection mistakes over time.
    """
    detected = body.get("detected_type", "")
    corrected = body.get("corrected_type", "")
    report_title = scrub_phi(body.get("report_title", "")[:200]).scrubbed_text

    if not detected or not corrected or detected == corrected:
        return {"ok": True}

    user_id = getattr(request.state, "user_id", None)

    try:
        if _USE_PG:
            from storage.pg_database import _get_pool
            pool = await _get_pool()
            await pool.execute(
                """INSERT INTO detection_corrections
                   (user_id, detected_type, corrected_type, report_title)
                   VALUES ($1, $2, $3, $4)""",
                user_id, detected, corrected, report_title,
            )
        else:
            from storage.database import get_db
            db = get_db()
            conn = db._get_conn()
            try:
                conn.execute(
                    """INSERT INTO detection_corrections
                       (detected_type, corrected_type, report_title)
                       VALUES (?, ?, ?)""",
                    (detected, corrected, report_title),
                )
                conn.commit()
            finally:
                conn.close()
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Failed to log detection correction")

    # Refresh correction cache so future detections benefit immediately
    try:
        from test_types.registry import refresh_correction_cache
        await refresh_correction_cache()
    except Exception:
        pass

    return {"ok": True}


@router.post("/analyze/classify-input")
@limiter.limit(ANALYZE_RATE_LIMIT)
async def classify_input(request: Request, body: dict = Body(...)):
    """Classify whether input text is a medical report or a question/request."""
    if _USE_PG:
        from api.phi_audit import log_phi_access
        await log_phi_access(request, "classify_input", "report")

    import re as _re

    text = body.get("text", "").strip()
    if not text:
        return {"classification": "question", "confidence": 0.5}

    # Heuristic tier -- fast, no API call
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

    # Ambiguous -- use LLM for tiebreak (optional, if API key available)
    try:
        user_id = _get_user_id(request)
        settings = await settings_store.get_settings(user_id=user_id)
        api_key = settings_store.get_api_key_for_provider(settings.llm_provider.value)
        if api_key:
            client = LLMClient(
                provider=LLMProvider(settings.llm_provider.value),
                api_key=api_key,
            )
            _classify_scrubbed = scrub_phi(text[:1000]).scrubbed_text
            resp = await with_retry(
                client.call,
                system_prompt="Classify the following text as either 'report' (a medical test report) or 'question' (a question or request for help). Reply with exactly one word: report or question.",
                user_prompt=_classify_scrubbed,
                timeout_seconds=30,
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
async def parse_report(http_request: Request, request: ParseRequest = Body(...)):
    """Parse extraction results into structured medical report."""
    if _USE_PG:
        from api.phi_audit import log_phi_access
        await log_phi_access(http_request, "parse_report", "report")
    try:
        extraction_result = ExtractionResult.model_validate(request.extraction_result)
    except Exception as e:
        logger.exception("parse_report validation failed: %s", e)
        raise HTTPException(
            status_code=400,
            detail="Invalid extraction result.",
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
        logger.exception("parse_report parsing failed: %s", e)
        raise HTTPException(
            status_code=422,
            detail="Failed to parse report.",
        )


class PatientFingerprintRequest(BaseModel):
    texts: list[str]


@router.post("/analyze/patient-fingerprints")
async def compute_patient_fingerprints(http_request: Request, request: PatientFingerprintRequest = Body(...)):
    """Compute patient identity fingerprints for a list of report texts.

    Used during batch upload to detect when reports may belong to different
    patients.  Returns a list of fingerprint hashes (empty string when no
    patient identity is found).  The frontend compares the hashes — if they
    don't all match, it shows a warning modal.
    """
    if _USE_PG:
        from api.phi_audit import log_phi_access
        await log_phi_access(http_request, "compute_fingerprints", "report")

    from phi.scrubber import compute_patient_fingerprint

    fingerprints = [compute_patient_fingerprint(t) for t in request.texts]
    return {"fingerprints": fingerprints}


@router.post("/analyze/explain", response_model=ExplainResponse)
@limiter.limit(ANALYZE_RATE_LIMIT)
async def explain_report(request: Request, body: ExplainRequest = Body(...)):
    """Full analysis pipeline: detect type -> parse -> PHI scrub -> LLM explain."""
    user_id = _get_user_id(request)

    if _USE_PG:
        from api.phi_audit import log_phi_access
        await log_phi_access(request, "generate_explanation", "report")

    # 1. Parse extraction result
    try:
        extraction_result = ExtractionResult.model_validate(body.extraction_result)
    except Exception as e:
        logger.exception("explain validation failed: %s", e)
        raise HTTPException(
            status_code=400,
            detail="Invalid extraction result.",
        )

    # 2. Detect test type
    test_type = body.test_type
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
    patient_age = body.patient_age if body.patient_age is not None else demographics.age
    patient_gender = body.patient_gender if body.patient_gender is not None else demographics.gender
    report_date = demographics.report_date

    # 3. Parse report (or build a generic one for unknown types)
    if handler is not None:
        try:
            parsed_report = handler.parse(extraction_result, gender=patient_gender, age=patient_age)
        except Exception as e:
            logger.exception("explain parsing failed: %s", e)
            raise HTTPException(
                status_code=422,
                detail="Failed to parse report.",
            )
    else:
        # Unknown / user-specified test type -- build a minimal parsed report
        # and let the LLM interpret the raw text directly.
        from test_types.generic import GenericTestType
        fallback_display = test_type.replace("_", " ").title()
        body_part = GenericTestType._extract_body_part(extraction_result.full_text, test_type)
        if body_part:
            fallback_display = f"{fallback_display} -- {body_part}"
        parsed_report = ParsedReport(
            test_type=test_type,
            test_type_display=fallback_display,
            detection_confidence=detection_confidence,
        )

    # 3b. Multi-type detection: find secondary test types and merge their data
    try:
        multi_results = registry.detect_multi(extraction_result, threshold=0.3)
        secondary_types = [
            tid for tid, _conf in multi_results
            if tid != test_type and _conf >= 0.3
        ]
        if secondary_types:
            parsed_report.secondary_test_types = secondary_types
            # Merge secondary measurements and glossary entries
            for sec_type in secondary_types[:2]:  # Limit to 2 secondary types
                sec_handler = registry.get(sec_type)
                if sec_handler:
                    try:
                        sec_parsed = sec_handler.parse(extraction_result, gender=patient_gender, age=patient_age)
                        for m in sec_parsed.measurements:
                            existing_abbrs = {em.abbreviation for em in parsed_report.measurements}
                            if m.abbreviation not in existing_abbrs:
                                parsed_report.measurements.append(m)
                        for f in sec_parsed.findings:
                            if f not in parsed_report.findings:
                                parsed_report.findings.append(f)
                    except Exception:
                        pass  # Non-critical: secondary parsing failures are OK
    except Exception:
        pass

    # --- Quick Normal fast path ---
    if body.quick_normal:
        settings = await settings_store.get_settings(user_id=user_id)
        provider_str = body.provider.value if body.provider else settings.llm_provider.value
        api_key = body.api_key or settings_store.get_api_key_for_provider(provider_str)
        if not api_key:
            raise HTTPException(
                status_code=400,
                detail=f"No API key configured for provider '{provider_str}'.",
            )

        # Resolve physician name
        extracted_physician = extract_physician_name(extraction_result.full_text)
        source = settings.physician_name_source.value
        if source == "auto_extract":
            active_physician = extracted_physician
        elif source == "custom":
            active_physician = settings.custom_physician_name
        else:
            active_physician = None

        voice = settings.explanation_voice.value
        name_drop = settings.name_drop

        prompt_engine = PromptEngine()
        prompt_context = handler.get_prompt_context(extraction_result) if handler else {}
        prompt_context["test_type_display"] = parsed_report.test_type_display
        if settings.specialty and "specialty" not in prompt_context:
            prompt_context["specialty"] = settings.specialty

        # PHI scrub clinical context only (no raw report text sent)
        providers = list(settings.practice_providers) if settings.practice_providers else None
        scrubbed_clinical = (
            scrub_phi(body.clinical_context, provider_names=providers).scrubbed_text
            if body.clinical_context else None
        )

        system_prompt = prompt_engine.build_quick_normal_system_prompt(
            prompt_context=prompt_context,
            physician_name=active_physician,
            explanation_voice=voice,
            name_drop=name_drop,
            literacy_level=settings.literacy_level,
            tone_preference=settings.tone_preference,
            humanization_level=settings.humanization_level,
            custom_phrases=list(settings.custom_phrases) if settings.custom_phrases else None,
        )
        user_prompt = prompt_engine.build_quick_normal_user_prompt(
            parsed_report=parsed_report,
            clinical_context=scrubbed_clinical,
        )

        llm_provider = LLMProvider(provider_str)
        model_override = (
            settings.claude_model
            if provider_str in ("claude", "bedrock")
            else settings.openai_model
        )
        client = LLMClient(provider=llm_provider, api_key=api_key, model=model_override)

        try:
            llm_response = await with_retry(
                client.call_with_tool,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                tool_name=EXPLANATION_TOOL_NAME,
                tool_schema=EXPLANATION_TOOL_SCHEMA,
                max_tokens=256,
                max_attempts=2,
            )
        except (LLMRetryError, Exception) as e:
            raise HTTPException(status_code=502, detail="Quick normal LLM call failed.")

        try:
            explanation, issues = parse_and_validate_response(
                tool_result=llm_response.tool_call_result,
                parsed_report=parsed_report,
                humanization_level=3,
            )
        except ValueError as e:
            raise HTTPException(status_code=502, detail="Quick normal response validation failed.")

        return ExplainResponse(
            explanation=explanation,
            parsed_report=parsed_report,
            validation_warnings=[issue.message for issue in issues],
            phi_categories_found=[],
            physician_name=extracted_physician,
            model_used=llm_response.model,
            input_tokens=llm_response.input_tokens,
            output_tokens=llm_response.output_tokens,
            severity_score=0.0,
            tone_auto_adjusted=False,
        )

    # 4. Resolve API key
    settings = await settings_store.get_settings(user_id=user_id)
    provider_str = body.provider.value if body.provider else settings.llm_provider.value
    api_key = body.api_key or settings_store.get_api_key_for_provider(
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

    # 5. PHI scrub (before any LLM calls)
    providers = list(settings.practice_providers) if settings.practice_providers else None
    scrub_result = scrub_phi(extraction_result.full_text, provider_names=providers)

    # 5a. LLM measurement extraction for generic types without extractors
    inc_measurements_check = body.include_measurements if body.include_measurements is not None else True
    if (
        not parsed_report.measurements
        and inc_measurements_check
        and handler is not None
    ):
        from test_types.generic import GenericTestType
        if isinstance(handler, GenericTestType) and not handler.has_measurement_extractor:
            from test_types.llm_measurement_extractor import llm_extract_measurements
            sections_text = "\n\n".join(
                f"[{s.name}]\n{s.content}" for s in parsed_report.sections
            )
            provider_enum = LLMProvider(provider_str)
            llm_client = LLMClient(provider=provider_enum, api_key=api_key)
            llm_measurements = await llm_extract_measurements(
                llm_client,
                scrub_result.scrubbed_text,
                sections_text,
                parsed_report.test_type_display,
                handler.get_prompt_context(extraction_result).get("specialty", "general"),
            )
            if llm_measurements:
                parsed_report.measurements = llm_measurements

    # 5b. PHI scrub clinical context if provided
    scrubbed_clinical_context = (
        scrub_phi(body.clinical_context, provider_names=providers).scrubbed_text
        if body.clinical_context
        else None
    )

    # Note: demographics (patient_age, patient_gender) already extracted above in step 2b

    # 5b. Always extract physician name from report text (for the UI)
    extracted_physician = extract_physician_name(extraction_result.full_text)

    # Resolve which physician name to use in the LLM prompt
    if body.physician_name_override is not None:
        active_physician = (
            scrub_phi(body.physician_name_override, provider_names=providers).scrubbed_text
            if body.physician_name_override else None
        )
    else:
        source = settings.physician_name_source.value
        if source == "auto_extract":
            active_physician = extracted_physician
        elif source == "custom":
            active_physician = settings.custom_physician_name
        else:
            active_physician = None

    # 5c. Resolve voice & name_drop -- request override takes priority
    voice = body.explanation_voice.value if body.explanation_voice is not None else settings.explanation_voice.value
    name_drop = body.name_drop if body.name_drop is not None else settings.name_drop

    # 6. Build prompts
    literacy_level = LiteracyLevel(body.literacy_level.value)
    prompt_engine = PromptEngine()
    prompt_context = handler.get_prompt_context(extraction_result) if handler else {}
    if not handler:
        # For unknown test types, tell the LLM what the user thinks it is
        prompt_context["test_type_hint"] = test_type
    if settings.specialty and "specialty" not in prompt_context:
        prompt_context["specialty"] = settings.specialty
    tone_pref = body.tone_preference if body.tone_preference is not None else settings.tone_preference
    detail_pref = body.detail_preference if body.detail_preference is not None else settings.detail_preference

    # Severity-adaptive defaults: adjust tone/detail when findings are severe
    from llm.prompt_engine import compute_severity_score
    severity_score = compute_severity_score(parsed_report)
    tone_auto_adjusted = False
    # Only auto-adjust if physician hasn't explicitly set per-request overrides
    if settings.severity_adaptive_tone and body.tone_preference is None and body.detail_preference is None:
        if severity_score > 0.8:
            tone_pref = min(tone_pref + 2, 5)
            detail_pref = min(detail_pref + 1, 5)
            tone_auto_adjusted = True
        elif severity_score > 0.5:
            tone_pref = min(tone_pref + 1, 5)
            detail_pref = min(detail_pref + 1, 5)
            tone_auto_adjusted = True

    inc_findings = body.include_key_findings if body.include_key_findings is not None else settings.include_key_findings
    inc_measurements = body.include_measurements if body.include_measurements is not None else settings.include_measurements
    is_sms = bool(body.sms_summary)
    use_analogies = body.use_analogies if body.use_analogies is not None else settings.use_analogies
    include_lifestyle = body.include_lifestyle_recommendations if body.include_lifestyle_recommendations is not None else settings.include_lifestyle_recommendations
    humanization_level = settings.humanization_level
    system_prompt = prompt_engine.build_system_prompt(
        literacy_level=literacy_level,
        prompt_context=prompt_context,
        tone_preference=tone_pref,
        detail_preference=detail_pref,
        physician_name=active_physician,
        short_comment=bool(body.short_comment),
        explanation_voice=voice,
        name_drop=name_drop,
        short_comment_char_limit=settings.short_comment_char_limit,
        include_key_findings=inc_findings,
        include_measurements=inc_measurements,
        patient_age=patient_age,
        patient_gender=patient_gender,
        sms_summary=is_sms,
        sms_summary_char_limit=settings.sms_summary_char_limit,
        high_anxiety_mode=bool(body.high_anxiety_mode),
        anxiety_level=body.anxiety_level or 0,
        use_analogies=use_analogies,
        include_lifestyle_recommendations=include_lifestyle,
        humanization_level=humanization_level,
    )
    # 6b. Load template if specified
    template_tone = None
    template_instructions = None
    template_closing = None
    if body.template_id is not None:
        tpl = await _db_call("get_template", body.template_id, user_id=user_id)
        if tpl:
            template_tone = tpl.get("tone")
            template_instructions = tpl.get("structure_instructions")
            template_closing = tpl.get("closing_text")
            if template_tone:
                prompt_context["tone"] = template_tone
    elif body.shared_template_sync_id:
        tpl = await _db_call("get_shared_template_by_sync_id", body.shared_template_sync_id, user_id=user_id)
        if tpl:
            template_tone = tpl.get("tone")
            template_instructions = tpl.get("structure_instructions")
            template_closing = tpl.get("closing_text")
            if template_tone:
                prompt_context["tone"] = template_tone

    # 6c. Derive severity band for personalization filtering
    from storage.database import _severity_band
    current_band = _severity_band(severity_score)

    # 6c2. Fetch liked examples for style guidance (severity-filtered)
    liked_examples = await _db_call(
        "get_liked_examples",
        limit=2, test_type=test_type,
        tone_preference=tone_pref, detail_preference=detail_pref,
        severity_band=current_band,
        user_id=user_id,
    )

    # 6d. Fetch teaching points (global + type-specific, including shared)
    teaching_points = await _db_call("list_all_teaching_points_for_prompt", test_type=test_type, user_id=user_id)

    # 6e. Fetch prior results for longitudinal trend comparison
    prior_results = await _db_call("get_prior_measurements", test_type, limit=3, user_id=user_id)

    # 6f. Fetch recent doctor edits for style learning
    recent_edits = await _db_call("get_recent_edits", test_type, limit=3, user_id=user_id)

    # 6g. Fetch learned phrases from doctor edits
    learned_phrases = await _db_call("get_learned_phrases", test_type=test_type, limit=5, user_id=user_id)

    # 6h. Fetch no-edit ratio for positive signal
    no_edit_ratio = await _db_call("get_no_edit_ratio", test_type, limit=10, user_id=user_id)

    # 6i. Fetch word-level edit corrections
    try:
        from storage.edit_analyzer import get_edit_corrections
        edit_corrections = get_edit_corrections(_db(), test_type, user_id=user_id, is_pg=_USE_PG)
        if _USE_PG:
            edit_corrections = await edit_corrections
    except (ImportError, Exception):
        edit_corrections = None

    # 6j. Fetch quality feedback adjustments
    try:
        from storage.feedback_analyzer import get_feedback_adjustments
        quality_feedback = get_feedback_adjustments(_db(), test_type, user_id=user_id, is_pg=_USE_PG)
        if _USE_PG:
            quality_feedback = await quality_feedback
    except (ImportError, Exception):
        quality_feedback = None

    # 6k. Extract lab-printed reference ranges
    lab_ref_section = ""
    try:
        from extraction.reference_range_extractor import extract_reference_ranges, merge_reference_ranges
        lab_ranges = extract_reference_ranges(scrub_result.scrubbed_text)
        if lab_ranges:
            builtin_ranges = handler.get_reference_ranges() if handler else {}
            lab_ref_section = merge_reference_ranges(lab_ranges, builtin_ranges, parsed_report.measurements or [])
    except (ImportError, Exception):
        lab_ref_section = ""

    # 6l. Fetch vocabulary preferences from edit patterns
    try:
        from storage.edit_analyzer import get_vocabulary_preferences
        vocab_prefs = get_vocabulary_preferences(_db(), test_type, user_id=user_id, is_pg=_USE_PG)
        if _USE_PG:
            vocab_prefs = await vocab_prefs
    except (ImportError, Exception):
        vocab_prefs = None

    # 6m. Fetch persistent style profile (severity-filtered)
    try:
        style_profile = await _db_call("get_style_profile", test_type, severity_band=current_band, user_id=user_id)
    except Exception:
        style_profile = None

    # 6n. Fetch preferred sign-off
    try:
        preferred_signoff = await _db_call("get_preferred_signoff", test_type, user_id=user_id)
    except Exception:
        preferred_signoff = None

    # 6o. Fetch term preferences
    try:
        term_preferences = await _db_call("get_term_preferences", test_type=test_type, user_id=user_id)
    except Exception:
        term_preferences = None

    # 6p. Fetch conditional rules for current severity band
    try:
        conditional_rules = await _db_call("get_conditional_rules", test_type, current_band, user_id=user_id)
    except Exception:
        conditional_rules = None

    # Combine custom phrases (from settings) with learned phrases (from edits)
    all_custom_phrases = list(settings.custom_phrases) if hasattr(settings, 'custom_phrases') else []
    for lp in learned_phrases:
        if lp not in all_custom_phrases:
            all_custom_phrases.append(lp)

    # 5c. PHI scrub free-text fields before LLM
    scrubbed_refinement = (
        scrub_phi(body.refinement_instruction, provider_names=providers).scrubbed_text
        if body.refinement_instruction else None
    )
    scrubbed_quick_reasons = (
        [scrub_phi(qr, provider_names=providers).scrubbed_text for qr in body.quick_reasons]
        if body.quick_reasons else None
    )
    scrubbed_custom_phrases = (
        [scrub_phi(cp, provider_names=providers).scrubbed_text for cp in all_custom_phrases]
        if all_custom_phrases else []
    )
    scrubbed_next_steps = (
        [scrub_phi(ns, provider_names=providers).scrubbed_text for ns in body.next_steps]
        if body.next_steps else None
    )
    scrubbed_batch_summaries = None
    if body.batch_prior_summaries:
        scrubbed_batch_summaries = []
        _text_keys = {'summary', 'notes', 'comment', 'context', 'label', 'text'}
        for item in body.batch_prior_summaries:
            scrubbed_item = {**item}
            for k in _text_keys:
                if k in scrubbed_item and scrubbed_item[k]:
                    scrubbed_item[k] = scrub_phi(str(scrubbed_item[k]), provider_names=providers).scrubbed_text
            scrubbed_batch_summaries.append(scrubbed_item)

    # Merge reference ranges and glossary from secondary types
    merged_ref_ranges = handler.get_reference_ranges() if handler else {}
    merged_glossary = handler.get_glossary() if handler else {}
    if parsed_report.secondary_test_types:
        for sec_type in parsed_report.secondary_test_types[:2]:
            sec_handler = registry.get(sec_type)
            if sec_handler:
                for k, v in sec_handler.get_reference_ranges().items():
                    if k not in merged_ref_ranges:
                        merged_ref_ranges[k] = v
                for k, v in sec_handler.get_glossary().items():
                    if k not in merged_glossary:
                        merged_glossary[k] = v

    user_prompt = prompt_engine.build_user_prompt(
        parsed_report=parsed_report,
        reference_ranges=merged_ref_ranges,
        glossary=merged_glossary,
        scrubbed_text=scrub_result.scrubbed_text,
        clinical_context=scrubbed_clinical_context,
        template_instructions=template_instructions,
        closing_text=template_closing,
        refinement_instruction=scrubbed_refinement,
        liked_examples=liked_examples,
        next_steps=scrubbed_next_steps,
        teaching_points=teaching_points,
        short_comment=bool(body.short_comment) or is_sms,
        prior_results=prior_results,
        recent_edits=recent_edits,
        patient_age=patient_age,
        patient_gender=patient_gender,
        quick_reasons=scrubbed_quick_reasons,
        custom_phrases=scrubbed_custom_phrases,
        report_date=report_date,
        no_edit_ratio=no_edit_ratio,
        edit_corrections=edit_corrections,
        quality_feedback=quality_feedback,
        lab_reference_ranges_section=lab_ref_section or None,
        vocabulary_preferences=vocab_prefs,
        style_profile=style_profile,
        batch_prior_summaries=scrubbed_batch_summaries,
        preferred_signoff=preferred_signoff,
        term_preferences=term_preferences,
        conditional_rules=conditional_rules,
    )

    # Log prompt sizes for debugging token issues
    import logging
    _logger = logging.getLogger(__name__)
    _logger.warning(
        "Prompt sizes -- system: %d chars, user: %d chars, short_comment: %s, sms: %s, test_type: %s",
        len(system_prompt), len(user_prompt), bool(body.short_comment), is_sms,
        parsed_report.test_type,
    )
    _logger.info("User prompt length: %d chars", len(user_prompt))

    # 7. Call LLM with retry
    llm_provider = LLMProvider(provider_str)
    model_override = (
        settings.claude_model
        if provider_str in ("claude", "bedrock")
        else settings.openai_model
    )
    if body.deep_analysis and provider_str in ("claude", "bedrock"):
        from llm.client import CLAUDE_DEEP_MODEL
        model_override = CLAUDE_DEEP_MODEL
    client = LLMClient(
        provider=llm_provider,
        api_key=api_key,
        model=model_override,
    )

    # SMS/short comments need far fewer output tokens
    if body.deep_analysis:
        max_tokens = 8192
    elif is_sms:
        max_tokens = 512
    elif body.short_comment:
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
        logger.exception("explain LLM call failed after retries: %s", e)
        raise HTTPException(
            status_code=502,
            detail="LLM API call failed after retries.",
        )
    except Exception as e:
        logger.exception("explain LLM call failed: %s", e)
        raise HTTPException(
            status_code=502,
            detail="LLM API call failed.",
        )

    # 8. Parse and validate response
    try:
        explanation, issues = parse_and_validate_response(
            tool_result=llm_response.tool_call_result,
            parsed_report=parsed_report,
            humanization_level=humanization_level,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=502,
            detail="LLM response validation failed.",
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
        severity_score=severity_score if severity_score > 0 else None,
        tone_auto_adjusted=tone_auto_adjusted,
    )


async def _update_style_profile_from_history(history_id: str, user_id: str | None) -> None:
    """Extract style data from a history record and update the persistent profile."""
    record = await _db_call("get_history", history_id, user_id=user_id)
    if not record:
        return
    test_type = record.get("test_type", "")
    full_response = record.get("full_response", {})
    if isinstance(full_response, str):
        full_response = json.loads(full_response)

    explanation = full_response.get("explanation", {})
    text = explanation.get("overall_summary", "")
    if not text:
        return

    from storage.database import _extract_stylistic_patterns, _severity_band
    patterns = _extract_stylistic_patterns(text)

    # Derive severity band from stored score
    sev_score = record.get("severity_score")
    if sev_score is None:
        sev_score = full_response.get("severity_score")
    band = _severity_band(sev_score) if sev_score is not None else None
    created_at = record.get("created_at")

    # Build profile data from the patterns
    profile_data: dict = {}
    if "avg_sentence_length" in patterns:
        profile_data["avg_sentence_length"] = patterns["avg_sentence_length"]
    if "paragraph_count" in patterns:
        profile_data["avg_paragraph_count"] = patterns["paragraph_count"]
    if "contraction_rate" in patterns:
        profile_data["contraction_rate"] = patterns["contraction_rate"]
    if patterns.get("openings"):
        profile_data["preferred_openings"] = patterns["openings"]
    if patterns.get("closings"):
        profile_data["preferred_closings"] = patterns["closings"]

    if profile_data:
        # Update base profile
        await _db_call("update_style_profile", test_type, profile_data, 0.3,
                        severity_band=band, created_at=created_at, user_id=user_id)


def _sse_event(data: dict) -> str:
    """Format a dict as an SSE data event."""
    return f"data: {json.dumps(data)}\n\n"


async def _explain_stream_gen(explain_request: ExplainRequest, user_id: str | None = None):
    """Async generator that runs the explain pipeline, yielding SSE progress events."""
    import logging
    _logger = logging.getLogger(__name__)

    try:
        # Stage 1: Detect
        yield _sse_event({"stage": "detecting", "message": "Identifying report type..."})

        try:
            extraction_result = ExtractionResult.model_validate(explain_request.extraction_result)
        except Exception as e:
            yield _sse_event({"stage": "error", "message": "Invalid extraction result."})
            return

        test_type = explain_request.test_type
        detection_confidence = 0.0
        if not test_type:
            type_id, confidence = registry.detect(extraction_result)
            if type_id is None or confidence < 0.2:
                yield _sse_event({"stage": "error", "message": "Could not determine the test type. Please specify test_type."})
                return
            test_type = type_id
            detection_confidence = confidence

        resolved_id, handler = registry.resolve(test_type)
        if handler is not None:
            test_type = resolved_id

        # Look up display name
        available = registry.list_types()
        display_name = next(
            (t["display_name"] for t in available if t["test_type_id"] == test_type),
            test_type.replace("_", " ").title(),
        )

        # Stage 1b: Re-OCR with handler-specific vision hints (if applicable)
        if handler is not None:
            try:
                updated = await _try_re_ocr(extraction_result, handler, user_id)
                if updated is not extraction_result:
                    yield _sse_event({
                        "stage": "detecting",
                        "message": f"Re-analyzing images for {display_name} details...",
                    })
                    extraction_result = updated
            except Exception:
                _logger.exception("Re-OCR stage failed, continuing with original text")

        # Stage 2: Parse
        yield _sse_event({"stage": "parsing", "message": f"Parsing {display_name} report..."})

        demographics = extract_demographics(extraction_result.full_text)
        patient_age = explain_request.patient_age if explain_request.patient_age is not None else demographics.age
        patient_gender = explain_request.patient_gender if explain_request.patient_gender is not None else demographics.gender
        report_date = demographics.report_date

        if handler is not None:
            try:
                parsed_report = handler.parse(extraction_result, gender=patient_gender, age=patient_age)
            except Exception as e:
                yield _sse_event({"stage": "error", "message": "Failed to parse report."})
                return
        else:
            from test_types.generic import GenericTestType
            fallback_display = test_type.replace("_", " ").title()
            body_part = GenericTestType._extract_body_part(extraction_result.full_text, test_type)
            if body_part:
                fallback_display = f"{fallback_display} -- {body_part}"
            parsed_report = ParsedReport(
                test_type=test_type,
                test_type_display=fallback_display,
                detection_confidence=detection_confidence,
            )

        # Multi-type detection: merge secondary type data
        try:
            multi_results = registry.detect_multi(extraction_result, threshold=0.3)
            secondary_types = [
                tid for tid, _conf in multi_results
                if tid != test_type and _conf >= 0.3
            ]
            if secondary_types:
                parsed_report.secondary_test_types = secondary_types
                for sec_type in secondary_types[:2]:
                    sec_handler = registry.get(sec_type)
                    if sec_handler:
                        try:
                            sec_parsed = sec_handler.parse(extraction_result, gender=patient_gender, age=patient_age)
                            existing_abbrs = {em.abbreviation for em in parsed_report.measurements}
                            for m in sec_parsed.measurements:
                                if m.abbreviation not in existing_abbrs:
                                    parsed_report.measurements.append(m)
                                    existing_abbrs.add(m.abbreviation)
                            for f in sec_parsed.findings:
                                if f not in parsed_report.findings:
                                    parsed_report.findings.append(f)
                        except Exception:
                            pass
        except Exception:
            pass

        m_count = len(parsed_report.measurements) if parsed_report.measurements else 0
        f_count = len(parsed_report.findings) if parsed_report.findings else 0
        parse_msg = f"Found {m_count} measurement{'s' if m_count != 1 else ''}"
        if f_count:
            parse_msg += f", {f_count} finding{'s' if f_count != 1 else ''}"
        yield _sse_event({"stage": "parsing", "message": parse_msg})

        # Stage 3: Explain (LLM call)
        yield _sse_event({"stage": "explaining", "message": "Preparing prompt..."})

        settings = await settings_store.get_settings(user_id=user_id)
        provider_str = explain_request.provider.value if explain_request.provider else settings.llm_provider.value
        api_key = explain_request.api_key or settings_store.get_api_key_for_provider(provider_str)
        if not api_key:
            yield _sse_event({"stage": "error", "message": f"No API key configured for provider '{provider_str}'. Set it in Settings."})
            return

        # PHI scrub before any LLM calls
        providers = list(settings.practice_providers) if settings.practice_providers else None
        scrub_result = scrub_phi(extraction_result.full_text, provider_names=providers)

        # LLM measurement extraction for generic types without extractors
        inc_measurements_check = explain_request.include_measurements if explain_request.include_measurements is not None else True
        if (
            not parsed_report.measurements
            and inc_measurements_check
            and handler is not None
        ):
            from test_types.generic import GenericTestType
            if isinstance(handler, GenericTestType) and not handler.has_measurement_extractor:
                from test_types.llm_measurement_extractor import llm_extract_measurements
                sections_text = "\n\n".join(
                    f"[{s.name}]\n{s.content}" for s in parsed_report.sections
                )
                provider_enum = LLMProvider(provider_str)
                llm_client = LLMClient(provider=provider_enum, api_key=api_key)
                llm_measurements = await llm_extract_measurements(
                    llm_client,
                    scrub_result.scrubbed_text,
                    sections_text,
                    parsed_report.test_type_display,
                    handler.get_prompt_context(extraction_result).get("specialty", "general"),
                )
                if llm_measurements:
                    parsed_report.measurements = llm_measurements
                    # Update the parse message
                    m_count = len(parsed_report.measurements)
                    yield _sse_event({"stage": "parsing", "message": f"LLM extracted {m_count} measurement{'s' if m_count != 1 else ''}"})
        scrubbed_clinical_context = (
            scrub_phi(explain_request.clinical_context, provider_names=providers).scrubbed_text
            if explain_request.clinical_context
            else None
        )
        extracted_physician = extract_physician_name(extraction_result.full_text)

        if explain_request.physician_name_override is not None:
            active_physician = (
                scrub_phi(explain_request.physician_name_override, provider_names=providers).scrubbed_text
                if explain_request.physician_name_override else None
            )
        else:
            source = settings.physician_name_source.value
            if source == "auto_extract":
                active_physician = extracted_physician
            elif source == "custom":
                active_physician = settings.custom_physician_name
            else:
                active_physician = None

        voice = explain_request.explanation_voice.value if explain_request.explanation_voice is not None else settings.explanation_voice.value
        name_drop = explain_request.name_drop if explain_request.name_drop is not None else settings.name_drop

        literacy_level = LiteracyLevel(explain_request.literacy_level.value)
        prompt_engine = PromptEngine()
        prompt_context = handler.get_prompt_context(extraction_result) if handler else {}
        if not handler:
            prompt_context["test_type_hint"] = test_type
        if settings.specialty and "specialty" not in prompt_context:
            prompt_context["specialty"] = settings.specialty
        tone_pref = explain_request.tone_preference if explain_request.tone_preference is not None else settings.tone_preference
        detail_pref = explain_request.detail_preference if explain_request.detail_preference is not None else settings.detail_preference

        # Severity-adaptive defaults
        from llm.prompt_engine import compute_severity_score
        severity_score = compute_severity_score(parsed_report)
        tone_auto_adjusted = False
        if settings.severity_adaptive_tone and explain_request.tone_preference is None and explain_request.detail_preference is None:
            if severity_score > 0.8:
                tone_pref = min(tone_pref + 2, 5)
                detail_pref = min(detail_pref + 1, 5)
                tone_auto_adjusted = True
            elif severity_score > 0.5:
                tone_pref = min(tone_pref + 1, 5)
                detail_pref = min(detail_pref + 1, 5)
                tone_auto_adjusted = True

        inc_findings = explain_request.include_key_findings if explain_request.include_key_findings is not None else settings.include_key_findings
        inc_measurements = explain_request.include_measurements if explain_request.include_measurements is not None else settings.include_measurements
        is_sms = bool(explain_request.sms_summary)
        use_analogies = explain_request.use_analogies if explain_request.use_analogies is not None else settings.use_analogies
        include_lifestyle = explain_request.include_lifestyle_recommendations if explain_request.include_lifestyle_recommendations is not None else settings.include_lifestyle_recommendations
        humanization_level = settings.humanization_level
        scrubbed_avoid_openings = (
            [scrub_phi(ao, provider_names=providers).scrubbed_text for ao in explain_request.avoid_openings]
            if explain_request.avoid_openings else None
        )

        system_prompt = prompt_engine.build_system_prompt(
            literacy_level=literacy_level,
            prompt_context=prompt_context,
            tone_preference=tone_pref,
            detail_preference=detail_pref,
            physician_name=active_physician,
            short_comment=bool(explain_request.short_comment),
            explanation_voice=voice,
            name_drop=name_drop,
            short_comment_char_limit=settings.short_comment_char_limit,
            include_key_findings=inc_findings,
            include_measurements=inc_measurements,
            patient_age=patient_age,
            patient_gender=patient_gender,
            sms_summary=is_sms,
            sms_summary_char_limit=settings.sms_summary_char_limit,
            high_anxiety_mode=bool(explain_request.high_anxiety_mode),
            anxiety_level=explain_request.anxiety_level or 0,
            use_analogies=use_analogies,
            include_lifestyle_recommendations=include_lifestyle,
            avoid_openings=scrubbed_avoid_openings,
            humanization_level=humanization_level,
        )

        template_tone = None
        template_instructions = None
        template_closing = None
        if explain_request.template_id is not None:
            tpl = await _db_call("get_template", explain_request.template_id, user_id=user_id)
            if tpl:
                template_tone = tpl.get("tone")
                template_instructions = tpl.get("structure_instructions")
                template_closing = tpl.get("closing_text")
                if template_tone:
                    prompt_context["tone"] = template_tone
        elif explain_request.shared_template_sync_id:
            tpl = await _db_call("get_shared_template_by_sync_id", explain_request.shared_template_sync_id, user_id=user_id)
            if tpl:
                template_tone = tpl.get("tone")
                template_instructions = tpl.get("structure_instructions")
                template_closing = tpl.get("closing_text")
                if template_tone:
                    prompt_context["tone"] = template_tone

        # Derive severity band for personalization filtering
        from storage.database import _severity_band
        current_band = _severity_band(severity_score)

        liked_examples = await _db_call(
            "get_liked_examples",
            limit=2, test_type=test_type,
            tone_preference=tone_pref, detail_preference=detail_pref,
            severity_band=current_band,
            user_id=user_id,
        )
        teaching_points = await _db_call("list_all_teaching_points_for_prompt", test_type=test_type, user_id=user_id)
        prior_results = await _db_call("get_prior_measurements", test_type, limit=3, user_id=user_id)
        recent_edits = await _db_call("get_recent_edits", test_type, limit=3, user_id=user_id)
        learned_phrases = await _db_call("get_learned_phrases", test_type=test_type, limit=5, user_id=user_id)

        # Fetch no-edit ratio for positive signal
        no_edit_ratio = await _db_call("get_no_edit_ratio", test_type, limit=10, user_id=user_id)

        # Fetch word-level edit corrections
        try:
            from storage.edit_analyzer import get_edit_corrections
            edit_corrections = get_edit_corrections(_db(), test_type, user_id=user_id, is_pg=_USE_PG)
            if _USE_PG:
                edit_corrections = await edit_corrections
        except (ImportError, Exception):
            edit_corrections = None

        # Fetch quality feedback adjustments
        try:
            from storage.feedback_analyzer import get_feedback_adjustments
            quality_feedback = get_feedback_adjustments(_db(), test_type, user_id=user_id, is_pg=_USE_PG)
            if _USE_PG:
                quality_feedback = await quality_feedback
        except (ImportError, Exception):
            quality_feedback = None

        # Extract lab-printed reference ranges
        lab_ref_section = ""
        try:
            from extraction.reference_range_extractor import extract_reference_ranges, merge_reference_ranges
            lab_ranges = extract_reference_ranges(scrub_result.scrubbed_text)
            if lab_ranges:
                builtin_ranges = handler.get_reference_ranges() if handler else {}
                lab_ref_section = merge_reference_ranges(lab_ranges, builtin_ranges, parsed_report.measurements or [])
        except (ImportError, Exception):
            lab_ref_section = ""

        # Fetch vocabulary preferences from edit patterns
        try:
            from storage.edit_analyzer import get_vocabulary_preferences
            vocab_prefs = get_vocabulary_preferences(_db(), test_type, user_id=user_id, is_pg=_USE_PG)
            if _USE_PG:
                vocab_prefs = await vocab_prefs
        except (ImportError, Exception):
            vocab_prefs = None

        # Fetch persistent style profile (severity-filtered)
        try:
            style_profile = await _db_call("get_style_profile", test_type, severity_band=current_band, user_id=user_id)
        except Exception:
            style_profile = None

        # Fetch preferred sign-off
        try:
            preferred_signoff = await _db_call("get_preferred_signoff", test_type, user_id=user_id)
        except Exception:
            preferred_signoff = None

        # Fetch term preferences
        try:
            term_preferences = await _db_call("get_term_preferences", test_type=test_type, user_id=user_id)
        except Exception:
            term_preferences = None

        # Fetch conditional rules for current severity band
        try:
            conditional_rules = await _db_call("get_conditional_rules", test_type, current_band, user_id=user_id)
        except Exception:
            conditional_rules = None

        all_custom_phrases = list(settings.custom_phrases) if hasattr(settings, 'custom_phrases') else []
        for lp in learned_phrases:
            if lp not in all_custom_phrases:
                all_custom_phrases.append(lp)

        # PHI scrub free-text fields before LLM
        scrubbed_refinement = (
            scrub_phi(explain_request.refinement_instruction, provider_names=providers).scrubbed_text
            if explain_request.refinement_instruction else None
        )
        scrubbed_quick_reasons = (
            [scrub_phi(qr, provider_names=providers).scrubbed_text for qr in explain_request.quick_reasons]
            if explain_request.quick_reasons else None
        )
        scrubbed_custom_phrases = (
            [scrub_phi(cp, provider_names=providers).scrubbed_text for cp in all_custom_phrases]
            if all_custom_phrases else []
        )
        scrubbed_next_steps = (
            [scrub_phi(ns, provider_names=providers).scrubbed_text for ns in explain_request.next_steps]
            if explain_request.next_steps else None
        )
        scrubbed_batch_summaries = None
        if explain_request.batch_prior_summaries:
            scrubbed_batch_summaries = []
            _text_keys = {'summary', 'notes', 'comment', 'context', 'label', 'text'}
            for item in explain_request.batch_prior_summaries:
                scrubbed_item = {**item}
                for k in _text_keys:
                    if k in scrubbed_item and scrubbed_item[k]:
                        scrubbed_item[k] = scrub_phi(str(scrubbed_item[k]), provider_names=providers).scrubbed_text
                scrubbed_batch_summaries.append(scrubbed_item)

        # Merge reference ranges and glossary from secondary types
        merged_ref_ranges = handler.get_reference_ranges() if handler else {}
        merged_glossary = handler.get_glossary() if handler else {}
        if parsed_report.secondary_test_types:
            for sec_type in parsed_report.secondary_test_types[:2]:
                sec_handler = registry.get(sec_type)
                if sec_handler:
                    for k, v in sec_handler.get_reference_ranges().items():
                        if k not in merged_ref_ranges:
                            merged_ref_ranges[k] = v
                    for k, v in sec_handler.get_glossary().items():
                        if k not in merged_glossary:
                            merged_glossary[k] = v

        user_prompt = prompt_engine.build_user_prompt(
            parsed_report=parsed_report,
            reference_ranges=merged_ref_ranges,
            glossary=merged_glossary,
            scrubbed_text=scrub_result.scrubbed_text,
            clinical_context=scrubbed_clinical_context,
            template_instructions=template_instructions,
            closing_text=template_closing,
            refinement_instruction=scrubbed_refinement,
            liked_examples=liked_examples,
            next_steps=scrubbed_next_steps,
            teaching_points=teaching_points,
            short_comment=bool(explain_request.short_comment) or is_sms,
            prior_results=prior_results,
            recent_edits=recent_edits,
            patient_age=patient_age,
            patient_gender=patient_gender,
            quick_reasons=scrubbed_quick_reasons,
            custom_phrases=scrubbed_custom_phrases,
            report_date=report_date,
            no_edit_ratio=no_edit_ratio,
            edit_corrections=edit_corrections,
            quality_feedback=quality_feedback,
            lab_reference_ranges_section=lab_ref_section or None,
            vocabulary_preferences=vocab_prefs,
            style_profile=style_profile,
            batch_prior_summaries=scrubbed_batch_summaries,
            preferred_signoff=preferred_signoff,
            term_preferences=term_preferences,
            conditional_rules=conditional_rules,
        )

        llm_provider = LLMProvider(provider_str)
        model_override = (
            settings.claude_model
            if provider_str in ("claude", "bedrock")
            else settings.openai_model
        )
        if explain_request.deep_analysis and provider_str in ("claude", "bedrock"):
            from llm.client import CLAUDE_DEEP_MODEL
            model_override = CLAUDE_DEEP_MODEL

        model_display = model_override or provider_str
        yield _sse_event({"stage": "explaining", "message": f"Generating explanation ({model_display})..."})

        client = LLMClient(
            provider=llm_provider,
            api_key=api_key,
            model=model_override,
        )

        if explain_request.deep_analysis:
            max_tokens = 8192
        elif is_sms:
            max_tokens = 512
        elif explain_request.short_comment:
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
            yield _sse_event({"stage": "error", "message": "LLM API call failed after retries. Please try again."})
            return
        except Exception as e:
            yield _sse_event({"stage": "error", "message": "LLM API call failed. Please try again."})
            return

        # Stage 4: Validate
        yield _sse_event({"stage": "validating", "message": "Checking response quality..."})

        try:
            explanation, issues = parse_and_validate_response(
                tool_result=llm_response.tool_call_result,
                parsed_report=parsed_report,
                humanization_level=humanization_level,
            )
        except ValueError as e:
            yield _sse_event({"stage": "error", "message": "LLM response validation failed. Please try again."})
            return

        # Stage 5: Done
        # Assemble personalization metadata for the frontend
        _p_meta: dict = {}
        if style_profile and style_profile.get("sample_count", 0) >= 3:
            _p_meta["style_sample_count"] = style_profile["sample_count"]
        if edit_corrections:
            _p_meta["edit_corrections_count"] = len(edit_corrections)
        if quality_feedback:
            _p_meta["feedback_adjustments_count"] = len(quality_feedback)
        if vocab_prefs:
            _p_meta["vocab_preferences_count"] = len(vocab_prefs)
        if term_preferences:
            _p_meta["term_preferences_count"] = len(term_preferences)
        if liked_examples:
            _p_meta["liked_examples_count"] = len(liked_examples)

        response = ExplainResponse(
            explanation=explanation,
            parsed_report=parsed_report,
            validation_warnings=[issue.message for issue in issues],
            phi_categories_found=scrub_result.phi_found,
            physician_name=extracted_physician,
            model_used=llm_response.model,
            input_tokens=llm_response.input_tokens,
            output_tokens=llm_response.output_tokens,
            severity_score=severity_score if severity_score > 0 else None,
            tone_auto_adjusted=tone_auto_adjusted,
            personalization_metadata=_p_meta if _p_meta else None,
        )

        yield _sse_event({"stage": "done", "data": response.model_dump(mode="json")})

    except Exception as e:
        _logger.exception("Unexpected error in explain stream")
        yield _sse_event({"stage": "error", "message": "An unexpected error occurred. Please try again."})


@router.post("/analyze/interpret", response_model=InterpretResponse)
@limiter.limit(ANALYZE_RATE_LIMIT)
async def interpret_report(request: Request, body: InterpretRequest = Body(...)):
    """Doctor-to-doctor clinical interpretation of any imported document."""
    import logging
    _logger = logging.getLogger(__name__)
    user_id = _get_user_id(request)

    if _USE_PG:
        from api.phi_audit import log_phi_access
        await log_phi_access(request, "generate_interpretation", "report")

    try:
        extraction_result = ExtractionResult.model_validate(body.extraction_result)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid extraction result.")

    # Detect / resolve test type
    test_type = body.test_type
    if not test_type:
        type_id, confidence = registry.detect(extraction_result)
        if type_id is not None and confidence >= 0.2:
            test_type = type_id
        else:
            test_type = "unknown"

    resolved_id, handler = registry.resolve(test_type)
    if resolved_id:
        test_type = resolved_id

    # Re-OCR with handler-specific vision hints (if applicable)
    if handler:
        try:
            extraction_result = await _try_re_ocr(extraction_result, handler, user_id)
        except Exception:
            _logger.exception("Re-OCR failed in interpret, continuing with original text")

    # Parse report
    if handler:
        parsed_report = handler.parse(extraction_result)
        prompt_context = handler.get_prompt_context(extraction_result)
        reference_ranges = handler.get_reference_ranges()
        glossary = handler.get_glossary()
        display_name = handler.display_name
    else:
        from api.analysis_models import ParsedReport as PR
        parsed_report = PR(
            test_type=test_type, test_type_display=test_type,
            detection_confidence=0.0,
        )
        prompt_context = {}
        reference_ranges = {}
        glossary = {}
        display_name = test_type

    # Get LLM client
    settings = await settings_store.get_settings(user_id=user_id)

    # PHI scrub
    providers = list(settings.practice_providers) if settings.practice_providers else None
    scrub_result = scrub_phi(extraction_result.full_text, provider_names=providers)
    provider_str = settings.llm_provider.value
    api_key = settings_store.get_api_key_for_provider(provider_str)
    if not api_key:
        raise HTTPException(status_code=400, detail=f"No API key configured for provider '{provider_str}'.")

    llm_provider = LLMProvider(provider_str)
    model_override = (
        settings.claude_model
        if provider_str in ("claude", "bedrock")
        else settings.openai_model
    )
    client = LLMClient(provider=llm_provider, api_key=api_key, model=model_override)

    # Build prompts
    prompt_engine = PromptEngine()
    system_prompt = prompt_engine.build_interpret_system_prompt(prompt_context)
    user_prompt = prompt_engine.build_interpret_user_prompt(
        scrubbed_text=scrub_result.scrubbed_text,
        parsed_report=parsed_report,
        reference_ranges=reference_ranges,
        glossary=glossary,
    )

    _logger.info(
        "Interpret prompt sizes -- system: %d chars, user: %d chars, test_type: %s",
        len(system_prompt), len(user_prompt), test_type,
    )

    # Call LLM (plain text, no tool use)
    try:
        llm_response = await with_retry(
            client.call,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=4096,
            max_attempts=2,
        )
    except (LLMRetryError, Exception) as e:
        raise HTTPException(status_code=502, detail="Interpret LLM call failed.")

    return InterpretResponse(
        interpretation=llm_response.text_content.strip(),
        test_type=test_type,
        test_type_display=display_name,
        model_used=llm_response.model,
        input_tokens=llm_response.input_tokens,
        output_tokens=llm_response.output_tokens,
    )


@router.post("/analyze/explain-stream")
@limiter.limit(ANALYZE_RATE_LIMIT)
async def explain_report_stream(request: Request, body: ExplainRequest = Body(...)):
    """Full analysis pipeline with SSE progress events."""
    user_id = _get_user_id(request)

    if _USE_PG:
        from api.phi_audit import log_phi_access
        await log_phi_access(request, "generate_explanation", "report")

    return StreamingResponse(
        _explain_stream_gen(body, user_id=user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/analyze/compare")
@limiter.limit(ANALYZE_RATE_LIMIT)
async def compare_reports(request: Request, body: dict = Body(...)):
    """Generate a trend summary comparing two reports of the same type."""
    if _USE_PG:
        from api.phi_audit import log_phi_access
        await log_phi_access(request, "compare_reports", "report")

    newer_response = body.get("newer_response")
    older_response = body.get("older_response")
    newer_date = body.get("newer_date", "recent")
    older_date = body.get("older_date", "previous")

    if not newer_response or not older_response:
        raise HTTPException(status_code=400, detail="Both newer_response and older_response are required.")

    newer_expl = newer_response.get("explanation", {})
    older_expl = older_response.get("explanation", {})
    newer_parsed = newer_response.get("parsed_report", {})
    test_type_display = newer_parsed.get("test_type_display", "Report")

    # Build measurement summaries
    def format_measurements(expl: dict) -> str:
        measurements = expl.get("measurements", [])
        if not measurements:
            return "No measurements available."
        lines = []
        for m in measurements:
            lines.append(f"- {m.get('abbreviation', '?')}: {m.get('value', '?')} {m.get('unit', '')} ({m.get('status', 'undetermined')})")
        return "\n".join(lines)

    def format_findings(expl: dict) -> str:
        findings = expl.get("key_findings", [])
        if not findings:
            return "No key findings."
        lines = []
        for f in findings:
            lines.append(f"- {f.get('finding', '?')} (severity: {f.get('severity', '?')})")
        return "\n".join(lines)

    system_prompt = (
        "You are a physician reviewing two medical reports of the same type for the same patient, "
        "taken at different times. Generate a brief, patient-friendly trend summary that explains "
        "what has changed between the two reports.\n\n"
        "Rules:\n"
        "- Write in plain language appropriate for patients\n"
        "- Focus on clinically significant changes\n"
        "- Note improvements, worsenings, and stable findings\n"
        "- Be concise (2-5 sentences)\n"
        "- Do NOT suggest treatments, future testing, or hypothetical actions\n"
        "- Do NOT include any patient-identifying information\n"
        "- Return ONLY the trend summary text, no preamble\n"
    )

    user_prompt = (
        f"Compare these two {test_type_display} reports:\n\n"
        f"NEWER REPORT ({newer_date}):\n"
        f"Summary: {newer_expl.get('overall_summary', 'N/A')}\n"
        f"Measurements:\n{format_measurements(newer_expl)}\n"
        f"Key Findings:\n{format_findings(newer_expl)}\n\n"
        f"OLDER REPORT ({older_date}):\n"
        f"Summary: {older_expl.get('overall_summary', 'N/A')}\n"
        f"Measurements:\n{format_measurements(older_expl)}\n"
        f"Key Findings:\n{format_findings(older_expl)}\n\n"
        f"Generate a brief trend summary for the patient."
    )

    user_id = _get_user_id(request)
    settings = await settings_store.get_settings(user_id=user_id)
    provider_str = settings.llm_provider.value
    api_key = settings_store.get_api_key_for_provider(provider_str)
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail=f"No API key configured for provider '{provider_str}'. Set it in Settings.",
        )

    model_override = (
        settings.claude_model if provider_str in ("claude", "bedrock") else settings.openai_model
    )
    client = LLMClient(
        provider=LLMProvider(provider_str),
        api_key=api_key,
        model=model_override,
    )

    try:
        llm_response = await with_retry(
            client.call,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=1024,
            timeout_seconds=90,
        )
    except LLMRetryError as e:
        if isinstance(e.last_error, TimeoutError):
            logger.exception("compare LLM call timed out: %s", e)
            raise HTTPException(status_code=504, detail="LLM request timed out.")
        logger.exception("compare LLM call failed: %s", e)
        raise HTTPException(status_code=502, detail="LLM API call failed.")
    except Exception as e:
        logger.exception("compare LLM call failed: %s", e)
        raise HTTPException(status_code=502, detail="LLM API call failed.")

    return {
        "trend_summary": llm_response.text_content,
        "model_used": getattr(llm_response, "model", ""),
        "input_tokens": getattr(llm_response, "input_tokens", 0),
        "output_tokens": getattr(llm_response, "output_tokens", 0),
    }


@router.post("/analyze/synthesize")
@limiter.limit(ANALYZE_RATE_LIMIT)
async def synthesize_reports(request: Request, body: dict = Body(...)):
    """Generate a unified summary synthesizing multiple reports."""
    if _USE_PG:
        from api.phi_audit import log_phi_access
        await log_phi_access(request, "synthesize_reports", "report")

    responses = body.get("responses", [])
    labels = body.get("labels", [])
    clinical_context = body.get("clinical_context", "")

    if not responses or len(responses) < 2:
        raise HTTPException(status_code=400, detail="At least 2 responses are required.")
    if len(responses) > 5:
        raise HTTPException(status_code=400, detail="Maximum 5 responses allowed.")

    # Build per-report summaries
    report_sections = []
    for i, resp in enumerate(responses):
        label = labels[i] if i < len(labels) else f"Report {i + 1}"
        expl = resp.get("explanation", {})
        parsed = resp.get("parsed_report", {})
        test_type_display = parsed.get("test_type_display", "Report")

        measurements = expl.get("measurements", [])
        m_lines = []
        for m in measurements:
            m_lines.append(
                f"- {m.get('abbreviation', '?')}: {m.get('value', '?')} "
                f"{m.get('unit', '')} ({m.get('status', 'undetermined')}) -- "
                f"{m.get('plain_language', '')}"
            )

        findings = expl.get("key_findings", [])
        f_lines = []
        for f in findings:
            f_lines.append(
                f"- {f.get('finding', '?')} (severity: {f.get('severity', '?')}): "
                f"{f.get('explanation', '')}"
            )

        section = (
            f"### {label} ({test_type_display})\n"
            f"Summary: {expl.get('overall_summary', 'N/A')}\n"
            f"Measurements:\n{chr(10).join(m_lines) if m_lines else 'None'}\n"
            f"Key Findings:\n{chr(10).join(f_lines) if f_lines else 'None'}\n"
        )
        report_sections.append(section)

    # Load settings for tone/anxiety/voice
    user_id = _get_user_id(request)
    settings = await settings_store.get_settings(user_id=user_id)
    provider_str = settings.llm_provider.value
    api_key = settings_store.get_api_key_for_provider(provider_str)
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail=f"No API key configured for provider '{provider_str}'. Set it in Settings.",
        )

    # Resolve physician voice
    voice = settings.explanation_voice.value
    physician_section = ""
    if voice == "first_person":
        physician_section = (
            "Write in first person as the physician. "
            'Use "I" language: "I have reviewed your results".\n'
        )
    else:
        source = settings.physician_name_source.value
        if source == "custom" and settings.custom_physician_name:
            physician_section = (
                f'When referring to the physician, use "{settings.custom_physician_name}".\n'
            )

    from llm.prompt_engine import _TONE_DESCRIPTIONS, _DETAIL_DESCRIPTIONS
    tone_desc = _TONE_DESCRIPTIONS.get(settings.tone_preference, _TONE_DESCRIPTIONS[3])
    detail_desc = _DETAIL_DESCRIPTIONS.get(settings.detail_preference, _DETAIL_DESCRIPTIONS[3])

    system_prompt = (
        "You are a physician writing a unified summary that ties together findings from "
        "multiple medical reports for the same patient. This combined summary should help "
        "the patient understand the overall clinical picture.\n\n"
        "Rules:\n"
        "- Write in plain, compassionate language appropriate for patients\n"
        "- Connect findings across reports (e.g., 'Your echo shows your heart is pumping "
        "well, and your labs confirm your cholesterol is improving')\n"
        "- Lead with the overall picture, then highlight the most important findings from "
        "each report\n"
        "- Note any cross-report patterns (e.g., kidney labs + imaging findings)\n"
        "- Use contractions and natural language\n"
        "- Do NOT suggest treatments, future testing, or hypothetical actions\n"
        "- Do NOT include any patient-identifying information\n"
        "- Return ONLY the combined summary text, no preamble or meta-commentary\n"
        f"{physician_section}"
        f"\nTone: {tone_desc}\n"
        f"Detail level: {detail_desc}\n"
    )

    providers = list(settings.practice_providers) if settings.practice_providers else None
    clinical_context_section = ""
    if clinical_context:
        scrubbed = scrub_phi(clinical_context, provider_names=providers).scrubbed_text
        clinical_context_section = f"\nClinical Context: {scrubbed}\n"

    user_prompt = (
        f"Synthesize these {len(responses)} reports into one unified patient-facing summary:"
        f"{clinical_context_section}\n\n"
        + "\n".join(report_sections)
        + "\nGenerate a combined summary for the patient that ties all these results together."
    )

    model_override = (
        settings.claude_model if provider_str in ("claude", "bedrock") else settings.openai_model
    )
    client = LLMClient(
        provider=LLMProvider(provider_str),
        api_key=api_key,
        model=model_override,
    )

    try:
        llm_response = await with_retry(
            client.call,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=2048,
            timeout_seconds=90,
        )
    except LLMRetryError as e:
        if isinstance(e.last_error, TimeoutError):
            logger.exception("synthesize LLM call timed out: %s", e)
            raise HTTPException(status_code=504, detail="LLM request timed out.")
        logger.exception("synthesize LLM call failed: %s", e)
        raise HTTPException(status_code=502, detail="LLM API call failed.")
    except Exception as e:
        logger.exception("synthesize LLM call failed: %s", e)
        raise HTTPException(status_code=502, detail="LLM API call failed.")

    return {
        "combined_summary": llm_response.text_content,
        "model_used": getattr(llm_response, "model", ""),
        "input_tokens": getattr(llm_response, "input_tokens", 0),
        "output_tokens": getattr(llm_response, "output_tokens", 0),
    }


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
    if _USE_PG:
        from api.phi_audit import log_phi_access
        await log_phi_access(request, "export_pdf", "report")

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
            detail="PDF generation failed.",
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
async def get_settings(request: Request):
    """Return current application settings with masked API keys."""
    user_id = _get_user_id(request)
    settings = await settings_store.get_settings(user_id=user_id)
    settings.claude_api_key = _mask_api_key(settings.claude_api_key)
    settings.openai_api_key = _mask_api_key(settings.openai_api_key)
    settings.aws_access_key_id = _mask_api_key(settings.aws_access_key_id)
    settings.aws_secret_access_key = _mask_api_key(settings.aws_secret_access_key)
    return settings


@router.patch("/settings", response_model=AppSettings)
async def update_settings(request: Request, update: SettingsUpdate = Body(...)):
    """Update application settings (partial update)."""
    user_id = _get_user_id(request)
    updated = await settings_store.update_settings(update, user_id=user_id)
    updated.claude_api_key = _mask_api_key(updated.claude_api_key)
    updated.openai_api_key = _mask_api_key(updated.openai_api_key)
    updated.aws_access_key_id = _mask_api_key(updated.aws_access_key_id)
    updated.aws_secret_access_key = _mask_api_key(updated.aws_secret_access_key)
    return updated


# --- Template Endpoints ---


@router.get("/templates", response_model=TemplateListResponse)
async def list_templates(request: Request):
    """Return all templates."""
    user_id = _get_user_id(request)
    items, total = await _db_call("list_templates", user_id=user_id)
    return TemplateListResponse(
        items=[TemplateResponse(**item) for item in items],
        total=total,
    )


@router.post("/templates", response_model=TemplateResponse, status_code=201)
async def create_template(request: Request, body: TemplateCreateRequest = Body(...)):
    """Create a new template."""
    user_id = _get_user_id(request)
    # If setting as default, clear other defaults for overlapping test types
    if body.is_default and body.test_types:
        if not _USE_PG:
            from storage.database import get_db as _get_db
            conn = _get_db()._get_conn()
            try:
                for t in body.test_types:
                    conn.execute(
                        """UPDATE templates SET is_default = 0
                           WHERE is_default = 1 AND EXISTS (
                             SELECT 1 FROM json_each(
                               CASE WHEN test_type LIKE '[%' THEN test_type ELSE json_array(test_type) END
                             ) WHERE value = ?
                           )""",
                        (t,),
                    )
                conn.commit()
            finally:
                conn.close()
    record = await _db_call(
        "create_template",
        name=body.name,
        test_type=body.test_type,
        test_types=body.test_types,
        tone=body.tone,
        structure_instructions=body.structure_instructions,
        closing_text=body.closing_text,
        user_id=user_id,
    )
    # Set is_default after creation if requested
    if body.is_default and body.test_types:
        record = await _db_call("update_template", record["id"], is_default=1, user_id=user_id)
    return TemplateResponse(**record)


@router.post("/templates/shared/sync")
async def sync_shared_templates(request: Request, body: dict = Body(...)):
    """Full-replace local shared templates cache."""
    user_id = _get_user_id(request)
    rows = body.get("rows", [])
    if not isinstance(rows, list):
        raise HTTPException(status_code=400, detail="rows must be a list.")
    count = await _db_call("replace_shared_templates", rows, user_id=user_id)
    return {"replaced": count}


@router.get("/templates/shared")
async def list_shared_templates(request: Request):
    """Return cached shared templates."""
    user_id = _get_user_id(request)
    return await _db_call("list_shared_templates", user_id=user_id)


@router.get("/templates/default/{test_type}")
async def get_default_template(request: Request, test_type: str):
    """Return the default template for a given test type, or null."""
    user_id = _get_user_id(request)
    record = await _db_call("get_default_template_for_type", test_type, user_id=user_id)
    if not record:
        return {"template": None}
    return {"template": TemplateResponse(**record)}


@router.patch("/templates/{template_id}", response_model=TemplateResponse)
async def update_template(request: Request, template_id: str, body: TemplateUpdateRequest = Body(...)):
    """Update an existing template."""
    user_id = _get_user_id(request)
    update_data = body.model_dump(exclude_unset=True)
    record = await _db_call("update_template", template_id, user_id=user_id, **update_data)
    if not record:
        raise HTTPException(status_code=404, detail="Template not found.")
    return TemplateResponse(**record)


@router.delete("/templates/{template_id}")
async def delete_template(request: Request, template_id: str):
    """Delete a template."""
    user_id = _get_user_id(request)
    deleted = await _db_call("delete_template", template_id, user_id=user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Template not found.")
    return {"deleted": True, "id": template_id}


# --- History Endpoints ---


# Deprecated type IDs that have been replaced by specific subtypes
_DEPRECATED_TYPE_MAP: dict[str, tuple[str, str]] = {
    "cardiac_pet": ("pharma_pet_stress", "Pharmacologic PET/PET-CT Stress"),
    "nuclear_stress": ("pharma_spect_stress", "Pharmacologic SPECT Nuclear Stress"),
    "stress_test": ("exercise_treadmill_test", "Exercise Treadmill Test"),
    "pharmacological_stress_test": ("pharma_spect_stress", "Pharmacologic SPECT Nuclear Stress"),
}


@router.get("/history/test-types")
async def list_history_test_types(request: Request):
    """Return distinct test types from user's history.

    Normalises deprecated type IDs to their modern replacements so the
    dropdown never shows stale entries like 'Cardiac PET / PET-CT'.
    """
    user_id = _get_user_id(request)
    if _USE_PG:
        from api.phi_audit import log_phi_access
        await log_phi_access(request, "list_test_types", "history")
    raw: list[dict] = await _db_call("list_history_test_types", user_id=user_id)
    seen: set[str] = set()
    out: list[dict] = []
    for row in raw:
        tid = row.get("test_type", "")
        if tid in _DEPRECATED_TYPE_MAP:
            new_id, new_display = _DEPRECATED_TYPE_MAP[tid]
            tid = new_id
            row = {"test_type": new_id, "test_type_display": new_display}
        if tid not in seen:
            seen.add(tid)
            out.append(row)
    out.sort(key=lambda r: r.get("test_type_display", ""))
    return out


@router.get("/history", response_model=HistoryListResponse)
async def list_history(
    request: Request,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    liked_only: bool = Query(False),
):
    """Return paginated history list, newest first."""
    user_id = _get_user_id(request)
    if _USE_PG:
        from api.phi_audit import log_phi_access
        await log_phi_access(request, "list_reports", "history")

    items, total = await _db_call(
        "list_history",
        offset=offset, limit=limit, search=search, liked_only=liked_only,
        user_id=user_id,
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
async def get_history_detail(request: Request, history_id: str):
    """Return single history record with full_response."""
    user_id = _get_user_id(request)
    record = await _db_call("get_history", history_id, user_id=user_id)
    if not record:
        raise HTTPException(status_code=404, detail="History record not found.")
    record["liked"] = bool(record.get("liked", 0))
    if _USE_PG:
        from api.phi_audit import log_phi_access
        await log_phi_access(request, "view_report", "history", history_id)
    return HistoryDetailResponse(**record)


@router.post("/history", response_model=HistoryDetailResponse, status_code=201)
async def create_history(request: Request, body: HistoryCreateRequest = Body(...)):
    """Save a new analysis history record."""
    user_id = _get_user_id(request)
    if _USE_PG:
        from api.phi_audit import log_phi_access
        await log_phi_access(request, "save_report", "history")

    # Extract severity_score from full_response if available
    _sev_score = None
    if isinstance(body.full_response, dict):
        _sev_score = body.full_response.get("severity_score")
        if _sev_score is not None:
            try:
                _sev_score = float(_sev_score)
            except (TypeError, ValueError):
                _sev_score = None

    # Scrub PHI from filename before persisting (e.g. "Smith_John_Echo.pdf")
    _scrubbed_filename = body.filename
    if _scrubbed_filename:
        from phi.scrubber import scrub_phi
        _scrubbed_filename = scrub_phi(_scrubbed_filename).scrubbed_text

    record = await _db_call(
        "save_history",
        test_type=body.test_type,
        test_type_display=body.test_type_display,
        summary=body.summary,
        full_response=body.full_response,
        filename=_scrubbed_filename,
        tone_preference=body.tone_preference,
        detail_preference=body.detail_preference,
        severity_score=_sev_score,
        user_id=user_id,
    )
    # Record which settings were used for edit-parameter correlation
    if body.tone_preference is not None or body.detail_preference is not None:
        try:
            await _db_call(
                "save_history_settings_used",
                record["id"],
                tone=body.tone_preference,
                detail=body.detail_preference,
                literacy=body.literacy_level,
                was_edited=False,
                user_id=user_id,
            )
        except Exception:
            pass  # Non-critical
    record["liked"] = bool(record.get("liked", 0))
    return HistoryDetailResponse(**record)


@router.delete("/history/{history_id}", response_model=HistoryDeleteResponse)
async def delete_history(request: Request, history_id: str):
    """Hard-delete a history record."""
    user_id = _get_user_id(request)
    deleted = await _db_call("delete_history", history_id, user_id=user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="History record not found.")
    if _USE_PG:
        from api.phi_audit import log_phi_access
        await log_phi_access(request, "delete_report", "history", history_id)
    return HistoryDeleteResponse(deleted=True, id=history_id)


@router.patch("/history/{history_id}/like", response_model=HistoryLikeResponse)
async def toggle_history_liked(
    request: Request,
    history_id: str,
    body: HistoryLikeRequest = Body(...),
):
    """Toggle the liked status of a history record."""
    user_id = _get_user_id(request)
    if _USE_PG:
        from api.phi_audit import log_phi_access
        await log_phi_access(request, "like_report", "history", history_id)

    updated = await _db_call("update_history_liked", history_id, body.liked, user_id=user_id)
    if not updated:
        raise HTTPException(status_code=404, detail="History record not found.")
    # Update style profile when liked
    if body.liked:
        try:
            await _update_style_profile_from_history(history_id, user_id)
        except Exception:
            pass
        # Trigger conditional pattern analysis (non-blocking)
        try:
            record = await _db_call("get_history", history_id, user_id=user_id)
            if record:
                from storage.conditional_pattern_analyzer import analyze_and_store_patterns
                await analyze_and_store_patterns(_db(), record.get("test_type", ""), user_id=user_id, is_pg=_USE_PG)
        except Exception:
            pass
    return HistoryLikeResponse(id=history_id, liked=body.liked)


@router.put("/history/{history_id}/copied")
async def mark_history_copied(request: Request, history_id: str):
    """Mark a history record as copied (lightweight positive signal)."""
    user_id = _get_user_id(request)
    updated = await _db_call("mark_copied", history_id, user_id=user_id)
    if not updated:
        raise HTTPException(status_code=404, detail="History record not found.")
    if _USE_PG:
        from api.phi_audit import log_phi_access
        await log_phi_access(request, "copy_report", "history", history_id)
    # Trigger conditional pattern analysis (non-blocking)
    try:
        record = await _db_call("get_history", history_id, user_id=user_id)
        if record:
            from storage.conditional_pattern_analyzer import analyze_and_store_patterns
            await analyze_and_store_patterns(_db(), record.get("test_type", ""), user_id=user_id, is_pg=_USE_PG)
    except Exception:
        pass
    return {"id": history_id, "copied": True}


class EditedTextRequest(BaseModel):
    edited_text: str


@router.patch("/history/{history_id}/edited_text")
async def save_edited_text(request: Request, history_id: str, body: EditedTextRequest = Body(...)):
    """Save the doctor's edited version of the explanation text."""
    user_id = _get_user_id(request)
    updated = await _db_call("save_edited_text", history_id, body.edited_text, user_id=user_id)
    if not updated:
        raise HTTPException(status_code=404, detail="History record not found.")
    if _USE_PG:
        from api.phi_audit import log_phi_access
        await log_phi_access(request, "edit_report", "history", history_id)
    # Mark this report as edited for edit-parameter correlation
    try:
        await _db_call("save_history_settings_used", history_id, tone=None, detail=None, literacy=None, was_edited=True, user_id=user_id)
    except Exception:
        pass  # Non-critical

    # Extract term preferences from the edit (non-blocking)
    try:
        record = await _db_call("get_history", history_id, user_id=user_id)
        if record:
            fr = record.get("full_response", {})
            if isinstance(fr, str):
                fr = json.loads(fr)
            original = fr.get("explanation", {}).get("overall_summary", "")
            measurements = fr.get("parsed_report", {}).get("measurements")
            if original and body.edited_text:
                from storage.term_extractor import extract_term_preferences
                prefs = extract_term_preferences(original, body.edited_text, measurements)
                test_type = record.get("test_type")
                for pref in prefs:
                    await _db_call(
                        "upsert_term_preference",
                        pref["medical_term"], test_type,
                        pref["preferred_phrasing"],
                        pref.get("keep_technical", False),
                        user_id=user_id,
                    )
    except Exception:
        pass  # Non-critical

    return {"id": history_id, "edited_text_saved": True}


@router.post("/history/{history_id}/rate", response_model=HistoryRateResponse)
async def rate_history(request: Request, history_id: str, body: HistoryRateRequest = Body(...)):
    """Rate the quality of a history record (1-5 stars) with optional note."""
    user_id = _get_user_id(request)
    updated = await _db_call("rate_history", history_id, body.rating, body.note, user_id=user_id)
    if not updated:
        raise HTTPException(status_code=404, detail="History record not found.")
    if _USE_PG:
        from api.phi_audit import log_phi_access
        await log_phi_access(request, "rate_report", "history", history_id)
    # Update style profile for highly-rated reports (4+)
    if body.rating >= 4:
        try:
            await _update_style_profile_from_history(history_id, user_id)
        except Exception:
            pass
    return HistoryRateResponse(id=history_id, quality_rating=body.rating, quality_note=body.note)


@router.get("/history/{history_id}/optimal-settings")
async def get_optimal_settings(request: Request, history_id: str):
    """Return optimal tone/detail settings based on edit patterns for a test type."""
    user_id = _get_user_id(request)
    record = await _db_call("get_history", history_id, user_id=user_id)
    if not record:
        raise HTTPException(status_code=404, detail="History record not found.")
    test_type = record.get("test_type", "")
    optimal = await _db_call("get_optimal_settings", test_type, min_samples=5, user_id=user_id)
    return {"test_type": test_type, "optimal_settings": optimal}


@router.get("/settings/optimal-for/{test_type}")
async def get_optimal_settings_by_type(request: Request, test_type: str):
    """Get optimal tone/detail settings for a given test type based on edit history."""
    user_id = _get_user_id(request)
    optimal = await _db_call("get_optimal_settings", test_type, min_samples=5, user_id=user_id)
    return {"test_type": test_type, "optimal_settings": optimal}


# --- Consent Endpoints ---


@router.get("/settings/raw-key/{provider}")
async def get_raw_key(provider: str):
    """Return the unmasked API key for a provider. Safe because sidecar is local-only.

    Disabled in web mode (REQUIRE_AUTH) for security.
    """
    if REQUIRE_AUTH:
        raise HTTPException(
            status_code=403,
            detail="Raw API key access is not available in web mode.",
        )
    key = settings_store.get_api_key_for_provider(provider)
    if not key:
        raise HTTPException(status_code=404, detail=f"No key configured for {provider}")
    # Bedrock returns a dict; other providers return a string
    if isinstance(key, dict):
        return {"provider": provider, "credentials": key}
    return {"provider": provider, "key": key}


@router.get("/consent", response_model=ConsentStatusResponse)
async def get_consent(request: Request):
    """Check whether the user has given privacy consent."""
    user_id = _get_user_id(request)
    value = await _db_call("get_setting", "privacy_consent_given", user_id=user_id)
    return ConsentStatusResponse(consent_given=value == "true")


@router.post("/consent", response_model=ConsentStatusResponse)
async def grant_consent(request: Request):
    """Record that the user has given privacy consent."""
    user_id = _get_user_id(request)
    await _db_call("set_setting", "privacy_consent_given", "true", user_id=user_id)
    return ConsentStatusResponse(consent_given=True)


# --- Onboarding Endpoints ---


@router.get("/onboarding")
async def get_onboarding(request: Request):
    """Check whether the user has completed onboarding."""
    user_id = _get_user_id(request)
    value = await _db_call("get_setting", "onboarding_completed", user_id=user_id)
    return {"onboarding_completed": value == "true"}


@router.post("/onboarding")
async def complete_onboarding(request: Request):
    """Record that the user has completed onboarding."""
    user_id = _get_user_id(request)
    await _db_call("set_setting", "onboarding_completed", "true", user_id=user_id)
    return {"onboarding_completed": True}


# --- Letter Endpoints ---


# --- Test Types Endpoint ---


@router.get("/test-types")
async def list_test_types():
    """Return all registered test type IDs and display names."""
    from test_types import registry
    types = registry.list_types()
    return [{"id": t["test_type_id"], "name": t["display_name"], "category": t.get("category", "other")} for t in types]


# --- Teaching Points Endpoints ---


@router.get("/teaching-points")
async def list_teaching_points(request: Request, test_type: str | None = Query(None)):
    """Return teaching points (global + test-type-specific)."""
    user_id = _get_user_id(request)
    points = await _db_call("list_teaching_points", test_type=test_type, user_id=user_id)
    return points


@router.post("/teaching-points", status_code=201)
async def create_teaching_point(request: Request, body: dict = Body(...)):
    """Create a new teaching point."""
    user_id = _get_user_id(request)
    text = body.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Teaching point text is required.")
    test_type = body.get("test_type")
    return await _db_call("create_teaching_point", text=text, test_type=test_type, user_id=user_id)


@router.post("/teaching-points/shared/sync")
async def sync_shared_teaching_points(request: Request, body: dict = Body(...)):
    """Full-replace local shared teaching points cache."""
    user_id = _get_user_id(request)
    rows = body.get("rows", [])
    if not isinstance(rows, list):
        raise HTTPException(status_code=400, detail="rows must be a list.")
    count = await _db_call("replace_shared_teaching_points", rows, user_id=user_id)
    # Remove any shared content that was incorrectly merged into the user's
    # own teaching_points table during earlier syncs.
    purged = await _db_call("purge_shared_duplicates_from_own", user_id=user_id)
    return {"replaced": count, "purged_duplicates": purged}


@router.get("/teaching-points/shared")
async def list_shared_teaching_points(request: Request, test_type: str | None = Query(None)):
    """Return cached shared teaching points."""
    user_id = _get_user_id(request)
    return await _db_call("list_shared_teaching_points", test_type=test_type, user_id=user_id)


@router.get("/teaching-points/practice-library")
async def browse_practice_library(request: Request, test_type: str | None = Query(None)):
    """Browse all practice members' teaching points with contributor flag."""
    user_id = _get_user_id(request)
    return await _db_call("browse_practice_teaching_points", test_type=test_type, user_id=user_id)


@router.delete("/teaching-points/{point_id}")
async def delete_teaching_point(request: Request, point_id: str):
    """Delete a teaching point."""
    user_id = _get_user_id(request)
    deleted = await _db_call("delete_teaching_point", point_id, user_id=user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Teaching point not found.")
    return {"deleted": True, "id": point_id}


@router.put("/teaching-points/{point_id}")
async def update_teaching_point(request: Request, point_id: str, body: dict = Body(...)):
    """Update a teaching point's text and/or test_type."""
    user_id = _get_user_id(request)
    updated = await _db_call(
        "update_teaching_point",
        point_id,
        text=body.get("text"),
        test_type=body.get("test_type", "UNSET"),
        user_id=user_id,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Teaching point not found.")
    return updated


# ---------------------------------------------------------------------------
# Sharing — user-to-user sharing of teaching points & templates
# ---------------------------------------------------------------------------

@router.get("/shares/recipients")
async def get_share_recipients(request: Request):
    """Return users I am sharing my content with."""
    user_id = _get_user_id(request)
    return await _db_call("get_share_recipients", user_id=user_id)


@router.get("/shares/sources")
async def get_share_sources(request: Request):
    """Return users who are sharing their content with me."""
    user_id = _get_user_id(request)
    return await _db_call("get_share_sources", user_id=user_id)


@router.post("/shares/recipients")
async def add_share_recipient(request: Request, body: dict = Body(...)):
    """Add a share relationship by recipient email."""
    user_id = _get_user_id(request)
    email = body.get("email", "").strip()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required.")
    try:
        share_id = await _db_call("add_share_recipient", email, user_id=user_id)
        return {"share_id": share_id, "recipient_email": email}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/shares/recipients/{share_id}")
async def remove_share_recipient(request: Request, share_id: int):
    """Remove a share relationship."""
    user_id = _get_user_id(request)
    deleted = await _db_call("remove_share_recipient", share_id, user_id=user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Share not found.")
    return {"deleted": True, "share_id": share_id}


@router.post("/letters/generate", response_model=LetterResponse, status_code=201)
@limiter.limit(ANALYZE_RATE_LIMIT)
async def generate_letter(request: Request, body: LetterGenerateRequest = Body(...)):
    """Generate a patient-facing letter/explanation from free-text input."""
    user_id = _get_user_id(request)
    if _USE_PG:
        from api.phi_audit import log_phi_access
        await log_phi_access(request, "generate_letter", "letter")

    settings = await settings_store.get_settings(user_id=user_id)
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
            "\n## Physician Voice -- First Person\n"
            "You ARE the physician. Write in first person. "
            'Use first-person language: "I wanted to explain", '
            '"In my assessment". '
            "Do NOT open with \"I have reviewed your results\" or similar "
            "result-review phrasing — the patient may be asking a general "
            "question, not receiving a test interpretation. "
            'NEVER use third-person references like "your doctor" or '
            '"your physician".\n'
        )
    elif physician_name:
        attribution = ""
        if name_drop:
            attribution = (
                f" Include at least one explicit attribution such as "
                f'"{physician_name} wanted to share this explanation".'
            )
        physician_section = (
            f"\n## Physician Voice -- Third Person (Care Team)\n"
            f"You are writing on behalf of the physician. "
            f'When referring to the physician, use "{physician_name}" '
            f'instead of generic phrases like "your doctor" or "your physician".{attribution}\n'
        )

    # Fetch teaching points (including shared) and liked examples for style guidance
    teaching_points = await _db_call("list_all_teaching_points_for_prompt", test_type=None, user_id=user_id)
    liked_examples = await _db_call(
        "get_liked_examples",
        limit=2, test_type=None,
        tone_preference=settings.tone_preference,
        detail_preference=settings.detail_preference,
        user_id=user_id,
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
            tp_source = tp.get("source", "own")
            if tp_source == "own":
                teaching_section += f"- {tp['text']}\n"
            else:
                teaching_section += f"- [From {tp_source}] {tp['text']}\n"

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
        f"The patient's request may be about a specific test result, OR it may "
        f"be a general question about a medical condition, diagnosis, or "
        f"situation. Tailor your response accordingly:\n"
        f"- If the request references specific test results or values, explain "
        f"what those results mean.\n"
        f"- If the request is a general question or asks you to explain a "
        f"condition/diagnosis, provide a clear, patient-friendly explanation "
        f"without assuming any specific test was performed.\n\n"
        f"## Rules\n"
        f"1. Write in plain, compassionate language appropriate for patients.\n"
        f"2. Do NOT include any patient-identifying information.\n"
        f"3. Focus on explaining and educating. If test results are provided, "
        f"synthesize findings into meaningful clinical statements — do NOT "
        f"simply recite values. If no results are provided, explain the "
        f"condition or topic in layman's terms.\n"
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
        settings.claude_model if provider_str in ("claude", "bedrock") else settings.openai_model
    )
    client = LLMClient(
        provider=llm_provider,
        api_key=api_key,
        model=model_override,
    )

    # PHI scrub the prompt before sending to LLM
    providers = list(settings.practice_providers) if settings.practice_providers else None
    scrubbed_prompt = scrub_phi(body.prompt, provider_names=providers).scrubbed_text

    try:
        llm_response = await with_retry(
            client.call,
            system_prompt=system_prompt,
            user_prompt=scrubbed_prompt,
            timeout_seconds=90,
        )
    except LLMRetryError as e:
        if isinstance(e.last_error, TimeoutError):
            logger.exception("generate_letter LLM call timed out: %s", e)
            raise HTTPException(status_code=504, detail="LLM request timed out.")
        logger.exception("generate_letter LLM call failed: %s", e)
        raise HTTPException(status_code=502, detail="LLM API call failed.")
    except Exception as e:
        logger.exception("generate_letter LLM call failed: %s", e)
        raise HTTPException(
            status_code=502,
            detail="LLM API call failed.",
        )

    content = llm_response.text_content

    letter_id = await _db_call(
        "save_letter",
        prompt=scrubbed_prompt,
        content=content,
        letter_type=body.letter_type,
        model_used=getattr(llm_response, "model", None),
        input_tokens=getattr(llm_response, "input_tokens", None),
        output_tokens=getattr(llm_response, "output_tokens", None),
        user_id=user_id,
    )
    record = await _db_call("get_letter", letter_id, user_id=user_id)
    return LetterResponse(**record)  # type: ignore[arg-type]


@router.get("/letters", response_model=LetterListResponse)
async def list_letters(
    request: Request,
    offset: int = 0,
    limit: int = 50,
    search: str | None = None,
    liked_only: bool = False,
):
    """Return generated letters with pagination, newest first."""
    user_id = _get_user_id(request)
    if _USE_PG:
        from api.phi_audit import log_phi_access
        await log_phi_access(request, "list_letters", "letter")

    items, total = await _db_call(
        "list_letters",
        offset=offset,
        limit=limit,
        search=search,
        liked_only=liked_only,
        user_id=user_id,
    )
    return LetterListResponse(
        items=[LetterResponse(**item) for item in items],
        total=total,
    )


@router.get("/letters/{letter_id}", response_model=LetterResponse)
async def get_letter(request: Request, letter_id: str):
    """Return a single letter."""
    user_id = _get_user_id(request)
    record = await _db_call("get_letter", letter_id, user_id=user_id)
    if not record:
        raise HTTPException(status_code=404, detail="Letter not found.")
    if _USE_PG:
        from api.phi_audit import log_phi_access
        await log_phi_access(request, "view_letter", "letter", letter_id)
    return LetterResponse(**record)


@router.delete("/letters/{letter_id}", response_model=LetterDeleteResponse)
async def delete_letter(request: Request, letter_id: str):
    """Delete a letter."""
    user_id = _get_user_id(request)
    deleted = await _db_call("delete_letter", letter_id, user_id=user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Letter not found.")
    if _USE_PG:
        from api.phi_audit import log_phi_access
        await log_phi_access(request, "delete_letter", "letter", letter_id)
    return LetterDeleteResponse(deleted=True, id=letter_id)


@router.put("/letters/{letter_id}", response_model=LetterResponse)
async def update_letter(request: Request, letter_id: str, body: LetterUpdateRequest = Body(...)):
    """Update a letter's content."""
    user_id = _get_user_id(request)
    record = await _db_call("update_letter", letter_id, body.content, user_id=user_id)
    if not record:
        raise HTTPException(status_code=404, detail="Letter not found.")
    if _USE_PG:
        from api.phi_audit import log_phi_access
        await log_phi_access(request, "edit_letter", "letter", letter_id)
    return LetterResponse(**record)


@router.put("/letters/{letter_id}/like")
async def toggle_letter_liked(request: Request, letter_id: str, body: LetterLikeRequest = Body(...)):
    """Toggle the liked status of a letter."""
    user_id = _get_user_id(request)
    updated = await _db_call("toggle_letter_liked", letter_id, body.liked, user_id=user_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Letter not found.")
    if _USE_PG:
        from api.phi_audit import log_phi_access
        await log_phi_access(request, "like_letter", "letter", letter_id)
    return {"id": letter_id, "liked": body.liked}


# --- Sync Endpoints ---


@router.get("/sync/export/{table}")
async def sync_export_all(request: Request, table: str):
    """Return all local rows for a table (for sync push)."""
    user_id = _get_user_id(request)
    if _USE_PG:
        from api.phi_audit import log_phi_access
        await log_phi_access(request, "export_table", table)

    rows = await _db_call("export_table", table, user_id=user_id)
    return rows


@router.get("/sync/export/{table}/{record_id}")
async def sync_export_record(request: Request, table: str, record_id: str):
    """Return a single row by local id (with sync_id)."""
    user_id = _get_user_id(request)
    if _USE_PG:
        from api.phi_audit import log_phi_access
        await log_phi_access(request, "export_record", table, record_id)

    record = await _db_call("export_record", table, record_id, user_id=user_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Record not found.")
    return record


@router.post("/sync/merge")
async def sync_merge(request: Request, body: dict = Body(...)):
    """Merge remote rows into local DB.

    Expects: { "table": str, "rows": list[dict] }
    Settings rows are matched by key, others by sync_id.
    """
    user_id = _get_user_id(request)
    table = body.get("table", "")
    rows = body.get("rows", [])
    if not table or not isinstance(rows, list):
        raise HTTPException(status_code=400, detail="table and rows are required.")

    merged = 0
    skipped = 0

    for row in rows:
        try:
            if table == "settings":
                key = row.get("key")
                value = row.get("value")
                updated_at = row.get("updated_at", "")
                if key and value is not None:
                    if await _db_call("merge_settings_row", key, str(value), updated_at, user_id=user_id):
                        merged += 1
                    else:
                        skipped += 1
            else:
                if await _db_call("merge_record", table, row, user_id=user_id):
                    merged += 1
                else:
                    skipped += 1
        except Exception:
            skipped += 1

    return {"merged": merged, "skipped": skipped}
