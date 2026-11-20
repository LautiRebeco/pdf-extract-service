
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.schemas.extraction import ExtractionResult


@dataclass(frozen=True)
class ServiceStats:
    pending: int
    max_pending: int
    workers: int
    queue_utilization: float
    closing: bool
    available: bool


class PDFExtractionService(Protocol):
    async def extract_text(self, file_bytes: bytes, *, ocr_enabled: bool) -> ExtractionResult: ...

    async def extract_markdown(self, file_bytes: bytes, *, ocr_enabled: bool) -> ExtractionResult: ...

    def get_stats(self) -> ServiceStats: ...
