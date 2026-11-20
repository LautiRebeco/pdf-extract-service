from __future__ import annotations

import io

from app.pdf.errors import OCRError


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
