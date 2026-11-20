from __future__ import annotations

from typing import Protocol
from app.schemas.extraction import ExtractionResult


class PDFExtractionService(Protocol):
    """Interfaz para extracción de PDF — permite tests con mocks y futuras estrategias."""

    async def extract_text(self, file_bytes: bytes, *, ocr_enabled: bool) -> ExtractionResult:
        """Extrae texto plano del PDF."""
        ...

    async def extract_markdown(self, file_bytes: bytes, *, ocr_enabled: bool) -> ExtractionResult:
        """Extrae contenido convertido a Markdown."""
        ...

    def get_stats(self) -> ServiceStats:
        """Retorna estadísticas del servicio (cola, workers, utilización)."""
        ...

    def shutdown(self) -> None:
        """Cierra el pool de workers de forma ordenada."""
        ...


from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceStats:
    """Estadísticas del servicio de extracción."""
    pending: int
    max_pending: int
    workers: int
    queue_utilization: float