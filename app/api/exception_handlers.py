from __future__ import annotations

import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

from app.pdf.errors import InvalidPDFError
from app.services.errors import ExtractionTimeoutError, ServiceOverloadedError

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Registra todos los manejadores de excepciones de la aplicación."""

    @app.exception_handler(ServiceOverloadedError)
    async def overloaded_handler(request: Request, exc: ServiceOverloadedError):
        return JSONResponse(status_code=503, content={"detail": str(exc)}, headers={"Retry-After": "1"})

    @app.exception_handler(ExtractionTimeoutError)
    async def timeout_handler(request: Request, exc: ExtractionTimeoutError):
        return JSONResponse(status_code=504, content={"detail": str(exc)})

    @app.exception_handler(InvalidPDFError)
    async def invalid_pdf_handler(request: Request, exc: InvalidPDFError):
        logger.warning("Invalid PDF: %s", exc)
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        # Preserva headers (Retry-After en 503)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Error interno del servidor"},
        )