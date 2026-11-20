from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from concurrent.futures import BrokenExecutor, ProcessPoolExecutor, ThreadPoolExecutor
from functools import partial
from multiprocessing import get_context

from app.config.settings import Settings
from app.logging_config import configure_logging
from app.pdf.extractor import extract_markdown_from_pdf_bytes as _extract_markdown
from app.pdf.extractor import extract_text_from_pdf_bytes as _extract_text
from app.schemas.extraction import ExtractionResult
from app.services.errors import ExtractionTimeoutError, ServiceOverloadedError
from app.services.interfaces import PDFPayload, ServiceStats

logger = logging.getLogger(__name__)


class PDFExtractionServiceImpl:
    """Admits a bounded number of jobs on the application event loop."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._workers = min(settings.extract_workers, settings.max_pending_extractions)
        # PyMuPDF supports parallel extraction across processes. Keep the
        # single-worker case in a dedicated thread to avoid IPC overhead.
        self._pool = (
            ThreadPoolExecutor(max_workers=1)
            if self._workers == 1
            else ProcessPoolExecutor(
                max_workers=self._workers,
                mp_context=get_context("spawn"),
                initializer=configure_logging,
                initargs=(settings.log_level, settings.log_format),
            )
        )
        self._worker_available = asyncio.Event()
        self._worker_available.set()
        self._active: set[asyncio.Future[ExtractionResult]] = set()
        self._pending = 0
        self._closing = False
        self._failed = False

    async def extract_text(self, payload: PDFPayload, *, ocr_enabled: bool) -> ExtractionResult:
        return await self._run(_extract_text, payload, ocr_enabled)

    async def extract_markdown(self, payload: PDFPayload, *, ocr_enabled: bool) -> ExtractionResult:
        return await self._run(_extract_markdown, payload, ocr_enabled)

    def _check_available(self) -> None:
        if self._closing or self._failed:
            raise ServiceOverloadedError("Servicio de extracción no disponible.")

    async def _run(
        self, extract: Callable[..., ExtractionResult], payload: PDFPayload, ocr_enabled: bool
    ) -> ExtractionResult:
        self._check_available()
        if self._pending >= self._settings.max_pending_extractions:
            raise ServiceOverloadedError("Servicio saturado, reintentá en unos segundos.")

        self._pending += 1
        submitted = False
        timeout = asyncio.timeout(self._settings.extraction_timeout_seconds)
        try:
            file_bytes = payload if isinstance(payload, bytes) else await payload()
            self._check_available()
            async with timeout:
                while len(self._active) >= self._workers:
                    await self._worker_available.wait()
                    self._check_available()
                future = asyncio.get_running_loop().run_in_executor(
                    self._pool,
                    partial(
                        extract,
                        file_bytes,
                        ocr_enabled=ocr_enabled,
                        ocr_languages=self._settings.ocr_languages,
                    ),
                )
                self._active.add(future)
                if len(self._active) == self._workers:
                    self._worker_available.clear()
                future.add_done_callback(self._finish)
                submitted = True
                return await asyncio.shield(future)
        except TimeoutError as exc:
            if not timeout.expired():
                raise
            logger.warning(
                "Extraction wait exceeded %s seconds", self._settings.extraction_timeout_seconds
            )
            raise ExtractionTimeoutError(
                f"Tiempo de extracción excedido ({self._settings.extraction_timeout_seconds}s)"
            ) from exc
        except BrokenExecutor as exc:
            self._failed = True
            raise ServiceOverloadedError("Servicio de extracción no disponible.") from exc
        finally:
            if not submitted:
                self._pending -= 1

    def _finish(self, future: asyncio.Future[ExtractionResult]) -> None:
        self._active.discard(future)
        self._pending -= 1
        self._worker_available.set()
        # Retrieve failures even when the HTTP caller has already left.
        if not future.cancelled() and isinstance(future.exception(), BrokenExecutor):
            self._failed = True

    def get_stats(self) -> ServiceStats:
        maximum = self._settings.max_pending_extractions
        return ServiceStats(
            pending=self._pending,
            max_pending=maximum,
            workers=self._workers,
            queue_utilization=100 * self._pending / maximum,
            closing=self._closing,
            available=not self._closing and not self._failed and self._pending < maximum,
        )

    async def shutdown(self) -> None:
        self._closing = True
        self._worker_available.set()
        try:
            if self._active:
                _, remaining = await asyncio.wait(
                    self._active, timeout=self._settings.shutdown_timeout_seconds
                )
                if remaining:
                    logger.warning(
                        "Shutdown wait expired with %d active extractions", len(remaining)
                    )
        finally:
            if self._active and isinstance(self._pool, ProcessPoolExecutor):
                self._pool.terminate_workers()
            else:
                self._pool.shutdown(wait=False, cancel_futures=True)
