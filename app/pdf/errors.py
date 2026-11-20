from __future__ import annotations


class InvalidPDFError(ValueError):
    """Excepción lanzada cuando el contenido no es un PDF válido."""

    pass


INVALID_PDF_CONTENT_ERROR = "El contenido no corresponde a un PDF valido."


class OCRError(Exception):
    """OCR was requested but recognition failed."""
