from __future__ import annotations

from functools import partial
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.api.uploads import read_pdf_payload
from app.config.settings import Settings
from app.schemas.extraction import ExtractionResult, ReadinessResponse
from app.services.interfaces import PDFExtractionService

router = APIRouter()


async def get_extraction_service_instance(request: Request) -> PDFExtractionService:
    service: PDFExtractionService = request.app.state.extraction_service
    return service


Service = Annotated[PDFExtractionService, Depends(get_extraction_service_instance)]


@router.get("/health")
@router.get("/health/live")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready", responses={503: {"description": "Extraction unavailable"}})
async def readiness(service: Service, response: Response) -> ReadinessResponse:
    stats = service.get_stats()
    status = "ready"
    if not stats.available:
        response.status_code = 503
        status = (
            "closing"
            if stats.closing
            else "busy" if stats.pending >= stats.max_pending else "unavailable"
        )

    return ReadinessResponse(
        status=status,
        pending_extractions=stats.pending,
        max_pending_extractions=stats.max_pending,
        extraction_workers=stats.workers,
        queue_utilization_percent=round(stats.queue_utilization, 2),
        closing=stats.closing,
    )


async def _run_extraction(
    request: Request, service: PDFExtractionService, *, markdown: bool
) -> ExtractionResult:
    settings: Settings = request.app.state.settings
    read_payload = partial(read_pdf_payload, request, settings.max_pdf_size_bytes)
    extract = service.extract_markdown if markdown else service.extract_text
    return await extract(read_payload, ocr_enabled=settings.ocr_enabled)


@router.post("/extract")
async def extract(request: Request, service: Service) -> ExtractionResult:
    return await _run_extraction(request, service, markdown=True)


@router.post("/extract/text")
async def extract_text(request: Request, service: Service) -> ExtractionResult:
    return await _run_extraction(request, service, markdown=False)
