from __future__ import annotations

import asyncio
import functools
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from app.config.settings import Settings
from app.services.interfaces import PDFExtractionService, ServiceStats
from app.pdf.extractor import (
    extract_text_from_pdf_bytes as _extract_text,
    extract_markdown_from_pdf_bytes as _extract_markdown,
)
from app.pdf.errors import InvalidPDFError

logger = logging.getLogger(__name__)


class PDFExtractionServiceImpl(PDFExtractionService):
    """Implementación concreta con bulkhead (ThreadPoolExecutor + cola acotada) y timeout."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._pool = ThreadPoolExecutor(max_workers=settings.extract_workers)
        self._pending = 0
        self._max_pending = settings.max_pending_extractions
        self._timeout = settings.extraction_timeout_seconds
        self._ocr_languages = settings.ocr_languages
        logger.info(
            "PDFExtractionService initialized: workers=%d, max_pending=%d, timeout=%ds, ocr_languages=%s",
            settings.extract_workers,
            settings.max_pending_extractions,
            settings.extraction_timeout_seconds,
            settings.ocr_languages,
        )

    async def extract_text(self, file_bytes: bytes, *, ocr_enabled: bool) -> ExtractionResult:
        return await self._run_in_pool(_extract_text, file_bytes, ocr_enabled=ocr_enabled)

    async def extract_markdown(self, file_bytes: bytes, *, ocr_enabled: bool) -> ExtractionResult:
        return await self._run_in_pool(_extract_markdown, file_bytes, ocr_enabled=ocr_enabled)

    async def _run_in_pool(self, func, *args, **kwargs) -> ExtractionResult:
        if self._pending >= self._max_pending:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=503,
                detail="Servicio saturado, reintentá en unos segundos.",
                headers={"Retry-After": "1"},
            )

        self._pending += 1
        try:
            loop = asyncio.get_event_loop()
            # Pasar ocr_languages si la función lo acepta
            if "ocr_languages" not in kwargs:
                kwargs["ocr_languages"] = self._ocr_languages
            # run_in_executor solo acepta args posicionales, usar partial para kwargs
            wrapped = functools.partial(func, *args, **kwargs)
            future = loop.run_in_executor(self._pool, wrapped)
            return await asyncio.wait_for(future, timeout=self._timeout)
        except asyncio.TimeoutError:
            logger.error("Extraction timeout after %ds", self._timeout)
            raise InvalidPDFError(f"Tiempo de extracción excedido ({self._timeout}s)")
        except Exception as e:
            logger.exception("Extraction failed: %s", e)
            raise
        finally:
            self._pending -= 1

    def get_stats(self) -> ServiceStats:
        return ServiceStats(
            pending=self._pending,
            max_pending=self._max_pending,
            workers=self._settings.extract_workers,
            queue_utilization=(self._pending / self._max_pending) * 100 if self._max_pending > 0 else 0,
        )

    def shutdown(self) -> None:
        logger.info("Shutting down extraction pool...")
        self._pool.shutdown(wait=True)
        logger.info("Extraction pool stopped")