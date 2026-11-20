from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)


def extract_text_from_image_bytes(image_bytes: bytes | None, languages: str = "eng+spa") -> str:
    """Extrae texto de una imagen usando OCR (Tesseract).
    
    Args:
        image_bytes: Bytes de la imagen (PNG, JPEG, etc.)
        languages: Idiomas para Tesseract (ej: "eng+spa")
    
    Returns:
        Texto extraído o string vacío si falla.
    """
    if not image_bytes:
        return ""

    try:
        import pytesseract
        from PIL import Image
    except Exception as exc:
        logger.warning("OCR dependencies not available: %s", exc)
        return ""

    try:
        image = Image.open(io.BytesIO(image_bytes))
        text: str = pytesseract.image_to_string(image, lang=languages)
        return text.strip()
    except Exception as exc:
        logger.warning("OCR failed for image block: %s", exc, exc_info=True)
        return ""