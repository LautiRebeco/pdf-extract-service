from __future__ import annotations

import logging
from fastapi import HTTPException, Request
from starlette.datastructures import UploadFile as FormFile

from app.config.settings import Settings

logger = logging.getLogger(__name__)

EMPTY_FILE_ERROR_DETAIL = "El archivo está vacio."
MAX_FILE_SIZE_ERROR_TEMPLATE = "El archivo supera el tamaño máximo permitido de {max_size} bytes."
MISSING_FILE_FIELD_ERROR_DETAIL = "Falta el campo 'file' con el PDF."
SERVICE_BUSY_ERROR_DETAIL = "Servicio saturado, reintentá en unos segundos."


def ensure_valid_size(file_bytes: bytes, filename: str, settings: Settings) -> None:
    """Valida que el archivo no esté vacío y no exceda el tamaño máximo."""
    if not file_bytes:
        logger.warning("Rejected PDF: archivo vacío. filename=%s", filename)
        raise HTTPException(status_code=400, detail=EMPTY_FILE_ERROR_DETAIL)

    if len(file_bytes) > settings.max_pdf_size_bytes:
        logger.warning(
            "Rejected PDF: archivo demasiado grande. filename=%s size_bytes=%d max_size=%d",
            filename,
            len(file_bytes),
            settings.max_pdf_size_bytes,
        )
        raise HTTPException(
            status_code=413,
            detail=MAX_FILE_SIZE_ERROR_TEMPLATE.format(max_size=settings.max_pdf_size_bytes),
        )


async def validate_pdf_payload(request: Request) -> tuple[bytes, str]:
    """Extrae y valida el payload PDF de la request (multipart o raw)."""
    if not request.headers.get("content-type", "").startswith("multipart/form-data"):
        return await request.body(), "raw"

    async with request.form() as form:
        upload = form.get("file")
        if not isinstance(upload, FormFile):
            logger.warning("Rejected extract request: multipart sin campo 'file'")
            raise HTTPException(status_code=400, detail=MISSING_FILE_FIELD_ERROR_DETAIL)
        return await upload.read(), upload.filename or "multipart"