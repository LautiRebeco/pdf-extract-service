from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

import fitz

from app.pdf.errors import INVALID_PDF_CONTENT_ERROR, InvalidPDFError, OCRError
from app.pdf.headings import block_to_markdown, compute_body_font_size
from app.pdf.ocr import extract_text_from_image_bytes
from app.schemas.extraction import ExtractionResult

logger = logging.getLogger(__name__)

TEXT_BLOCK = 0
IMAGE_BLOCK = 1
TEXT_ONLY_FLAGS = fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES


@contextmanager
def _open_pdf(file_bytes: bytes) -> Iterator[fitz.Document]:
    if not file_bytes.startswith(b"%PDF-"):
        raise InvalidPDFError(INVALID_PDF_CONTENT_ERROR)

    try:
        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
            if not doc.is_pdf or doc.needs_pass or doc.page_count < 1:
                raise InvalidPDFError(INVALID_PDF_CONTENT_ERROR)
            yield doc
    except InvalidPDFError:
        raise
    except (RuntimeError, ValueError) as exc:
        raise InvalidPDFError(INVALID_PDF_CONTENT_ERROR) from exc


def _blocks(doc: fitz.Document, ocr_enabled: bool) -> Iterator[dict]:
    flags = fitz.TEXTFLAGS_DICT if ocr_enabled else TEXT_ONLY_FLAGS
    for page in doc:
        yield from page.get_text("dict", flags=flags, sort=True).get("blocks", [])


def _block_text(block: dict, ocr_enabled: bool, languages: str) -> str:
    block_type = block.get("type")
    if block_type == TEXT_BLOCK:
        lines = (
            "".join(span.get("text", "") for span in line.get("spans", [])).strip()
            for line in block.get("lines", [])
        )
        return "\n".join(line for line in lines if line)
    if block_type == IMAGE_BLOCK and ocr_enabled:
        return extract_text_from_image_bytes(block.get("image"), languages)
    return ""


def _extract(
    file_bytes: bytes, *, ocr_enabled: bool, ocr_languages: str, markdown: bool
) -> ExtractionResult:
    parts: list[str] = []
    ocr_error = None
    with _open_pdf(file_bytes) as doc:
        blocks = _blocks(doc, ocr_enabled)
        body_size = 0.0
        if markdown:
            all_blocks = list(blocks)
            body_size = compute_body_font_size(all_blocks)
            blocks = iter(all_blocks)

        for block in blocks:
            try:
                text = _block_text(block, ocr_enabled, ocr_languages)
            except OCRError as exc:
                logger.warning("%s %s", exc, exc.__cause__)
                ocr_error = exc
                continue
            if text:
                parts.append(block_to_markdown(block, body_size, text) if markdown else text)

        if not parts and ocr_error is not None:
            raise ocr_error
        separator = "\n\n" if markdown else "\n"
        return ExtractionResult(content=separator.join(parts), page_count=doc.page_count)


def extract_text_from_pdf_bytes(
    file_bytes: bytes, *, ocr_enabled: bool, ocr_languages: str = "eng+spa"
) -> ExtractionResult:
    return _extract(
        file_bytes, ocr_enabled=ocr_enabled, ocr_languages=ocr_languages, markdown=False
    )


def extract_markdown_from_pdf_bytes(
    file_bytes: bytes, *, ocr_enabled: bool, ocr_languages: str = "eng+spa"
) -> ExtractionResult:
    return _extract(file_bytes, ocr_enabled=ocr_enabled, ocr_languages=ocr_languages, markdown=True)
