"""LLM vision OCR fallback for scanned pages with low Tesseract confidence."""

from __future__ import annotations

import io
import logging
from typing import TYPE_CHECKING

from PIL import Image

if TYPE_CHECKING:
    from llm.client import LLMClient

logger = logging.getLogger(__name__)

_VISION_SYSTEM_PROMPT = "You are an expert medical document OCR system."

_VISION_USER_PROMPT = """\
Transcribe ALL text visible on this scanned medical document page exactly as printed.

For tabular lab results, output each row on its own line:
  TEST_NAME    VALUE    UNITS    REFERENCE_RANGE    FLAG

Rules:
- Preserve exact numeric values, units, and reference ranges
- Include ALL text: headers, patient info, lab info, notes
- Do NOT interpret, summarize, or omit anything
- If a value is unclear, give your best reading"""

# Haiku model IDs for cheap vision OCR
_HAIKU_MODELS = {
    "claude": "claude-haiku-4-20250514",
    "bedrock": "claude-haiku-4-20250514",
    "openai": "gpt-4.1-mini",
}


async def vision_ocr_page(
    llm_client: LLMClient,
    page_image: Image.Image,
) -> tuple[str, float]:
    """OCR a page image using LLM vision.

    Returns (transcribed_text, confidence).
    Confidence is fixed at 0.95 on success, 0.0 on failure.
    """
    try:
        # Convert PIL Image to PNG bytes in-memory
        buf = io.BytesIO()
        page_image.save(buf, format="PNG")
        image_bytes = buf.getvalue()

        # Use a cheap vision-capable model for OCR
        original_model = llm_client.model
        haiku = _HAIKU_MODELS.get(llm_client.provider.value)
        if haiku:
            llm_client.model = haiku

        try:
            response = await llm_client.call_with_vision(
                system_prompt=_VISION_SYSTEM_PROMPT,
                user_prompt=_VISION_USER_PROMPT,
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
