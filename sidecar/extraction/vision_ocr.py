"""LLM vision OCR fallback for scanned pages with low Tesseract confidence."""

from __future__ import annotations

import io
import logging
from typing import TYPE_CHECKING

from PIL import Image

if TYPE_CHECKING:
    from llm.client import LLMClient

logger = logging.getLogger(__name__)

_VISION_SYSTEM_PROMPT = (
    "You are an expert medical document OCR system. "
    "You can read both printed text AND handwritten annotations, "
    "including notes written in margins, circled values, and annotations on diagrams."
)

_VISION_USER_PROMPT = """\
Transcribe ALL text visible on this scanned medical document page.
Include BOTH printed text AND handwritten annotations.

For tabular lab results, output each row on its own line:
  TEST_NAME    VALUE    UNITS    REFERENCE_RANGE    FLAG

Rules:
- Preserve exact numeric values, units, and reference ranges
- Include ALL text: headers, patient info, lab info, notes
- Include handwritten annotations: circled values, underlined text, margin notes
- Recognize common medical annotation patterns:
  - Percentage values written near anatomical structures (e.g. "50%", "70-80%")
  - Plus signs (+, ++, +++) indicating severity or calcification
  - Arrows or lines pointing to specific areas
  - Circled or boxed values indicating emphasis
  - Handwritten pressure values in tables (e.g. systolic/diastolic like "120/80")
- Mark handwritten text with [HW] prefix so downstream processing can distinguish it
- Do NOT interpret, summarize, or omit anything
- If a value is unclear, give your best reading and note uncertainty with [?]"""

# Haiku model IDs for cheap vision OCR
_HAIKU_MODELS = {
    "claude": "claude-haiku-4-20250514",
    "bedrock": None,  # use the user's configured model (Haiku doesn't support images via Bedrock inference profiles)
    "openai": "gpt-4.1-mini",
}


async def vision_ocr_page(
    llm_client: LLMClient,
    page_image: Image.Image,
    additional_hints: str | None = None,
) -> tuple[str, float]:
    """OCR a page image using LLM vision.

    Args:
        llm_client: The LLM client to use for vision OCR.
        page_image: The page image to OCR.
        additional_hints: Optional handler-specific hints to append to the
            vision prompt (e.g. coronary diagram annotation guidance).

    Returns (transcribed_text, confidence).
    Confidence is fixed at 0.95 on success, 0.0 on failure.
    """
    try:
        # Redact PHI from header/footer regions before sending to LLM
        from phi.image_redactor import redact_image_phi
        page_image = redact_image_phi(page_image)
        logger.info("Applied image PHI redaction (header/footer blackout)")

        # Convert PIL Image to PNG bytes in-memory
        buf = io.BytesIO()
        page_image.save(buf, format="PNG")
        image_bytes = buf.getvalue()

        # Build user prompt, optionally with handler-specific hints
        user_prompt = _VISION_USER_PROMPT
        if additional_hints:
            user_prompt += (
                "\n\nADDITIONAL CONTEXT FOR THIS DOCUMENT TYPE:\n"
                + additional_hints
            )

        # Use a cheap vision-capable model for OCR
        original_model = llm_client.model
        haiku = _HAIKU_MODELS.get(llm_client.provider.value)
        if haiku:
            llm_client.model = haiku

        try:
            response = await llm_client.call_with_vision(
                system_prompt=_VISION_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                image_bytes=image_bytes,
                media_type="image/png",
                max_tokens=4096,
                temperature=0.0,
            )
        finally:
            llm_client.model = original_model

        text = response.text_content.strip()
        if text:
            logger.info(
                "Vision OCR produced %d chars (in=%d, out=%d tokens)",
                len(text),
                response.input_tokens,
                response.output_tokens,
            )
            return text, 0.95

        logger.warning("Vision OCR returned empty text")
        return "", 0.0

    except Exception:
        logger.exception("Vision OCR failed")
        return "", 0.0
