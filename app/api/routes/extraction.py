from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.config.settings import Settings, get_settings
from app.services.interfaces import PDFExtractionService
from app.services.pdf_extraction_service import PDFExtractionServiceImpl
from app.utils.validators import ensure_valid_size, validate_pdf_payload

router = APIRouter()


def get_extraction_service_instance() -> PDFExtractionService:
    """Factory para el servicio de extracción (para Depends)."""
    settings = get_settings()
    return PDFExtractionServiceImpl(settings)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/live")
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
def readiness(
    service: PDFExtractionService = Depends(get_extraction_service_instance),
) -> dict[str, str | int | float]:
    stats = service.get_stats()
    return {
        "status": "ready" if stats.queue_utilization < 100 else "busy",
        "pending_extractions": stats.pending,
        "max_pending_extractions": stats.max_pending,
        "extraction_workers": stats.workers,
        "queue_utilization_percent": round(stats.queue_utilization, 2),
    }


async def _run_extraction(
    request: Request,
    extractor_method: str,
    service: PDFExtractionService,
    settings: Settings,
) -> dict[str, str | int]:
    file_bytes, filename = await validate_pdf_payload(request)
    ensure_valid_size(file_bytes, filename, settings)

    method = getattr(service, extractor_method)
    result = await method(file_bytes, ocr_enabled=settings.ocr_enabled)
    return {"content": result.content, "page_count": result.page_count}


@router.post("/extract")
async def extract(
    request: Request,
    service: PDFExtractionService = Depends(get_extraction_service_instance),
    settings: Settings = Depends(get_settings),
) -> dict[str, str | int]:
    return await _run_extraction(request, "extract_markdown", service, settings)


@router.post("/extract/text")
async def extract_text(
    request: Request,
    service: PDFExtractionService = Depends(get_extraction_service_instance),
    settings: Settings = Depends(get_settings),
) -> dict[str, str | int]:
    return await _run_extraction(request, "extract_text", service, settings)