"""Image-level PHI redaction for scanned medical documents.

Blacks out header and footer regions before images are sent to third-party
LLMs for vision OCR. Medical reports consistently place PHI (patient name,
DOB, MRN, account number) in the top ~12% and bottom ~5% of the page.
"""

from __future__ import annotations

import logging

from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)


def redact_image_phi(image: Image.Image) -> Image.Image:
    """Black out header and footer regions of a scanned medical document.

    Medical reports place PHI (name, DOB, MRN) in the top ~12% and bottom ~5%
    of the page. This function draws black rectangles over those regions before
    the image is sent to a third-party LLM for vision OCR.

    Returns a copy of the image with the regions blacked out.
    """
    img = image.copy()
    draw = ImageDraw.Draw(img)
    w, h = img.size
    # Black out top 12% (patient demographics header)
    draw.rectangle([0, 0, w, int(h * 0.12)], fill="black")
    # Black out bottom 5% (footer with MRN/account repeats)
    draw.rectangle([0, int(h * 0.95), w, h], fill="black")
    return img
