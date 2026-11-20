from __future__ import annotations

import fitz

from app.pdf.errors import InvalidPDFError, INVALID_PDF_CONTENT_ERROR
from app.pdf.ocr import extract_text_from_image_bytes
from app.pdf.headings import compute_body_font_size, block_to_markdown
from app.schemas.extraction import ExtractionResult

TEXT_BLOCK = 0
IMAGE_BLOCK = 1
TEXT_ONLY_FLAGS = fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES


def _extract_text_from_block(block: dict, ocr_enabled: bool, ocr_languages: str) -> list[str]:
    """Extrae texto de un bloque (texto o imagen con OCR)."""
    block_type = block.get("type")
    if block_type == TEXT_BLOCK:
        lines = [
            "".join(span.get("text", "") for span in line.get("spans", [])).strip()
            for line in block.get("lines", [])
        ]
        valid_lines = [line for line in lines if line]
        return ["\n".join(valid_lines).strip()] if valid_lines else []

    if block_type == IMAGE_BLOCK and ocr_enabled:
        ocr_text = extract_text_from_image_bytes(block.get("image"), ocr_languages)
        return [ocr_text] if ocr_text else []

    return []


def extract_text_from_pdf_bytes(
    file_bytes: bytes, *, ocr_enabled: bool, ocr_languages: str = "eng+spa"
) -> ExtractionResult:
    """Extrae texto plano del PDF."""
    if not file_bytes.startswith(b"%PDF-"):
        raise InvalidPDFError(INVALID_PDF_CONTENT_ERROR)

    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as e:
        raise InvalidPDFError(INVALID_PDF_CONTENT_ERROR) from e

    flags = fitz.TEXTFLAGS_DICT if ocr_enabled else TEXT_ONLY_FLAGS

    texts: list[str] = []
    for page in doc:
        blocks = page.get_text("dict", flags=flags, sort=True).get("blocks", [])
        for block in blocks:
            texts.extend(_extract_text_from_block(block, ocr_enabled, ocr_languages))

    return ExtractionResult(content="\n".join(texts), page_count=doc.page_count)


def extract_markdown_from_pdf_bytes(
    file_bytes: bytes, *, ocr_enabled: bool, ocr_languages: str = "eng+spa"
) -> ExtractionResult:
    """Extrae contenido del PDF convertido a Markdown con detección de headings."""
    if not file_bytes.startswith(b"%PDF-"):
        raise InvalidPDFError(INVALID_PDF_CONTENT_ERROR)

    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as e:
        raise InvalidPDFError(INVALID_PDF_CONTENT_ERROR) from e

    flags = fitz.TEXTFLAGS_DICT if ocr_enabled else TEXT_ONLY_FLAGS

    all_blocks: list[dict] = []
    for page in doc:
        blocks = page.get_text("dict", flags=flags, sort=True).get("blocks", [])
        all_blocks.extend(blocks)

    body_size = compute_body_font_size(all_blocks)

    markdown_parts: list[str] = []
    for block in all_blocks:
        block_texts = _extract_text_from_block(block, ocr_enabled, ocr_languages)
        for text in block_texts:
            markdown_parts.append(block_to_markdown(block, body_size, text))

    return ExtractionResult(content="\n\n".join(markdown_parts), page_count=doc.page_count)