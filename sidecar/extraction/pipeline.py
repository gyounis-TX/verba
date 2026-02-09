import os

from PIL import Image

from api.models import (
    ExtractionResult,
    InputMode,
    PageExtractionResult,
    PageType,
)
from .detector import PDFDetector
from .emr_fingerprint import detect_emr_source
from .ocr_extractor import OCRExtractor
from .preprocessor import ImagePreprocessor
from .table_extractor import TableExtractor
from .text_extractor import TextExtractor


class ExtractionPipeline:
    @staticmethod
    def _extract_pdf_metadata(file_path: str) -> dict | None:
        """Extract PDF metadata using PyMuPDF if available."""
        try:
            import fitz
            doc = fitz.open(file_path)
            metadata = doc.metadata
            doc.close()
            return metadata
        except Exception:
            return None

    def extract_from_pdf(self, file_path: str) -> ExtractionResult:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        warnings: list[str] = []

        # Step 1: Detect page types
        detector = PDFDetector(file_path)
        detection = detector.detect()

        # Step 2: Route pages to appropriate extractor
        text_pages = [
            p.page_number for p in detection.pages
            if p.page_type == PageType.TEXT
        ]
        scanned_pages = [
            p.page_number for p in detection.pages
            if p.page_type == PageType.SCANNED
        ]

        page_results: list[PageExtractionResult] = []

        if text_pages:
            text_extractor = TextExtractor(file_path)
            page_results.extend(text_extractor.extract_pages(text_pages))

        if scanned_pages:
            try:
                ocr_extractor = OCRExtractor(file_path)
                ocr_results = ocr_extractor.extract_pages(scanned_pages)
                page_results.extend(ocr_results)

                for r in ocr_results:
                    if r.confidence < 0.3:
                        warnings.append(
                            f"Page {r.page_number}: very low OCR confidence "
                            f"({r.confidence:.0%}). Text is likely unreliable — "
                            "consider re-scanning at higher resolution."
                        )
                    elif r.confidence < 0.5:
                        warnings.append(
                            f"Page {r.page_number}: low OCR confidence "
                            f"({r.confidence:.0%}). Some text may be inaccurate."
                        )
            except Exception as e:
                warnings.append(
                    f"OCR failed for scanned pages: {str(e)}. "
                    "Only text-based pages were extracted."
                )

        page_results.sort(key=lambda r: r.page_number)

        # Step 3: Extract tables from text pages
        tables = []
        if text_pages:
            table_extractor = TableExtractor(file_path)
            tables = table_extractor.extract_tables(text_pages)

        # Step 4: Combine into full text
        full_text = "\n\n".join(r.text for r in page_results if r.text)

        if not full_text.strip():
            warnings.append("No text could be extracted from this PDF.")

        # Step 5: EMR/PACS source fingerprinting
        pdf_metadata = self._extract_pdf_metadata(file_path)
        emr_fp = detect_emr_source(full_text, pdf_metadata=pdf_metadata, input_mode="pdf")

        return ExtractionResult(
            input_mode=InputMode.PDF,
            full_text=full_text,
            pages=page_results,
            tables=tables,
            detection=detection,
            total_pages=detection.total_pages,
            total_chars=len(full_text),
            filename=os.path.basename(file_path),
            warnings=warnings,
            emr_source=emr_fp.source.value if emr_fp.source.value != "unknown" else None,
            emr_source_confidence=emr_fp.confidence,
        )

    def extract_from_image(self, file_path: str) -> ExtractionResult:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        warnings: list[str] = []

        image = Image.open(file_path)
        preprocessor = ImagePreprocessor()
        processed = preprocessor.preprocess(image, source_dpi=72)

        ocr = OCRExtractor.__new__(OCRExtractor)
        ocr.preprocessor = preprocessor
        text, avg_confidence = ocr._ocr_with_best_psm(processed)

        if avg_confidence < 0.3:
            warnings.append(
                f"Very low OCR confidence ({avg_confidence:.0%}). "
                "Text is likely unreliable — consider re-scanning at "
                "higher resolution."
            )
        elif avg_confidence < 0.5:
            warnings.append(
                f"Low OCR confidence ({avg_confidence:.0%}). "
                "Some text may be inaccurate."
            )

        if not text:
            warnings.append("No text could be extracted from this image.")

        page_result = PageExtractionResult(
            page_number=1,
            text=text,
            extraction_method="ocr",
            confidence=round(avg_confidence, 3),
            char_count=len(text),
        )

        return ExtractionResult(
            input_mode=InputMode.IMAGE,
            full_text=text,
            pages=[page_result],
            tables=[],
            detection=None,
            total_pages=1,
            total_chars=len(text),
            filename=os.path.basename(file_path),
            warnings=warnings,
        )

    def extract_from_text(self, text: str) -> ExtractionResult:
        text = text.strip()
        page_result = PageExtractionResult(
            page_number=1,
            text=text,
            extraction_method="direct_input",
            confidence=1.0,
            char_count=len(text),
        )

        # EMR/PACS source fingerprinting
        emr_fp = detect_emr_source(text, input_mode="text")

        return ExtractionResult(
            input_mode=InputMode.TEXT,
            full_text=text,
            pages=[page_result],
            tables=[],
            detection=None,
            total_pages=1,
            total_chars=len(text),
            filename=None,
            warnings=[],
            emr_source=emr_fp.source.value if emr_fp.source.value != "unknown" else None,
            emr_source_confidence=emr_fp.confidence,
        )
