from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol, TypeAlias

from app.schemas.extraction import ExtractionResult

PDFPayload: TypeAlias = bytes | Callable[[], Awaitable[bytes]]


@dataclass(frozen=True)
class ServiceStats:
    pending: int
    max_pending: int
    workers: int
    queue_utilization: float
    closing: bool
    available: bool


class PDFExtractionService(Protocol):
    async def extract_text(self, payload: PDFPayload, *, ocr_enabled: bool) -> ExtractionResult: ...

    async def extract_markdown(
        self, payload: PDFPayload, *, ocr_enabled: bool
    ) -> ExtractionResult: ...

    def get_stats(self) -> ServiceStats: ...
