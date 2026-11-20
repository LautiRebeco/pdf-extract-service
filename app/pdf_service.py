from __future__ import annotations

import io
import logging
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager

import fitz
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class InvalidPDFError(ValueError):
    """Excepción lanzada cuando el contenido no es un PDF válido."""

    pass


INVALID_PDF_CONTENT_ERROR = "El contenido no corresponde a un PDF valido."


class OCRError(Exception):
    """OCR was requested but recognition failed."""


class ExtractionResult(BaseModel):
    """Respuesta estándar de extracción — compatible con contrato original."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(description="Texto extraído (plano o Markdown)")
    page_count: int = Field(ge=0, description="Número de páginas del PDF")


H1_SIZE_RATIO = 1.5
H2_SIZE_RATIO = 1.2


def compute_body_font_size(blocks: list[dict]) -> float:
    """Calcula el tamaño de fuente más común (body text) ponderado por caracteres."""
    chars_by_size: Counter[float] = Counter()
    for block in blocks:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "").strip()
                if text:
                    chars_by_size[round(span["size"], 1)] += len(text)
    return chars_by_size.most_common(1)[0][0] if chars_by_size else 0.0


def block_to_markdown(block: dict, body_size: float, text: str = "") -> str:
    """Convierte un bloque a Markdown detectando headings por tamaño de fuente.

    Args:
        block: Bloque del PDF
        body_size: Tamaño de fuente base
        text: Texto ya extraído (usado para OCR). Si está vacío, se extrae del bloque.
    """
    # Usar el texto proporcionado o extraer del bloque
    if text:
        block_text = text
    else:
        block_text = "".join(
            span.get("text", "")
            for line in block.get("lines", [])
            for span in line.get("spans", [])
        )

    sizes = [
        round(span["size"], 1)
        for line in block.get("lines", [])
        for span in line.get("spans", [])
        if span.get("text", "").strip()
    ]
    ratio = max(sizes) / body_size if sizes and body_size > 0 else 0

    clean_text = block_text.replace("\n", " ")
    if ratio >= H1_SIZE_RATIO:
        return f"# {clean_text}"
    if ratio >= H2_SIZE_RATIO:
        return f"## {clean_text}"
    return block_text


def extract_text_from_image_bytes(image_bytes: bytes | None, languages: str = "eng+spa") -> str:
    """Return recognized text, or raise OCRError if recognition could not run."""
    if not image_bytes:
        return ""

    try:
        import pytesseract
        from PIL import Image

        with Image.open(io.BytesIO(image_bytes)) as image:
            text: str = pytesseract.image_to_string(image, lang=languages, timeout=10)
        return text.strip()
    except Exception as exc:
        raise OCRError("Falló el OCR de un bloque de imagen.") from exc


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
